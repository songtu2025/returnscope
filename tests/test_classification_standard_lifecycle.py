from pathlib import Path

import pytest
from test_classification_standards import _service

from web_backend.classification_standard_service import ClassificationStandardConflict


def test_reenable_preserves_published_version_and_allows_new_draft(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    standard = service.list()[0]
    identifier = standard["id"]
    version_id = standard["standard_version_id"]
    before = service.versions(identifier)
    service.delete_standard(identifier, "user-1")
    restored = service.enable_standard(identifier, version_id, "user-1")
    assert restored["status"] == "active"
    assert service.versions(identifier) == before
    assert service.create_draft(identifier, "user-1")["base_version_id"] == version_id
    assert (
        service.enable_standard(identifier, version_id, "user-1")["status"] == "active"
    )


def test_reenable_rejects_stale_version_and_conflicting_category(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    standard = service.list()[0]
    identifier = standard["id"]
    version_id = standard["standard_version_id"]
    service.delete_standard(identifier, "user-1")
    with pytest.raises(ClassificationStandardConflict, match="刷新"):
        service.enable_standard(identifier, "obsolete-version", "user-1")
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            service, "_registry_compatibility_blocking", lambda *args: ["品类冲突"]
        )
        with pytest.raises(ClassificationStandardConflict, match="品类冲突"):
            service.enable_standard(identifier, version_id, "user-1")
    assert service.get(identifier)["status"] == "inactive"
