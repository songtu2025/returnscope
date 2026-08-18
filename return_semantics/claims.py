from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from return_semantics.schemas import ListingClaimsConfig
from return_semantics.taxonomy import load_listing_claims

NO_CLAIMS_VERSION = "no-claims-v1"


@dataclass(frozen=True)
class ClaimsEntry:
    store: str
    listing: str
    capability_key: str
    path: Path
    version: str


class ClaimsResolver:
    def __init__(self, registry_path: Path) -> None:
        data = json.loads(registry_path.read_text(encoding="utf-8"))
        self.registry_version = str(data["version"])
        self.entries: tuple[ClaimsEntry, ...] = tuple(
            self._load_entry(registry_path.parent, item)
            for item in data.get("entries", [])
        )

    @staticmethod
    def _load_entry(base_dir: Path, item: dict[str, object]) -> ClaimsEntry:
        path = base_dir / str(item["path"])
        claims = load_listing_claims(path)
        return ClaimsEntry(
            store=str(item["store"]).strip(),
            listing=str(item["listing"]).strip(),
            capability_key=str(item["capability_key"]).strip(),
            path=path,
            version=claims.version,
        )

    def resolve(
        self,
        store: str,
        listing: str | None,
        capability_key: str,
        expected_version: str | None = None,
    ) -> ListingClaimsConfig:
        if expected_version == NO_CLAIMS_VERSION:
            return ListingClaimsConfig(version=NO_CLAIMS_VERSION, claims=[])
        entry = next(
            (
                item
                for item in self.entries
                if item.store == store.strip()
                and item.listing == (listing or "").strip()
                and item.capability_key == capability_key
                and (expected_version is None or item.version == expected_version)
            ),
            None,
        )
        if entry is None:
            if expected_version is not None:
                raise ValueError(f"Listing 承诺版本不可用: {expected_version}")
            return ListingClaimsConfig(version=NO_CLAIMS_VERSION, claims=[])
        return load_listing_claims(entry.path)
