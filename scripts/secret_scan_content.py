from __future__ import annotations

import os
import re
from collections import Counter
from dataclasses import dataclass


@dataclass(frozen=True)
class SecretRule:
    name: str
    pattern: re.Pattern[bytes]


@dataclass(frozen=True, order=True)
class Finding:
    rule: str
    location: str
    count: int


RULES = (
    SecretRule(
        "private-key",
        re.compile(rb"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----"),
    ),
    SecretRule(
        "aws-access-key",
        re.compile(
            rb"(?<![A-Z0-9])(?:AKIA|ASIA|AIDA|AROA|AIPA|ANPA|ANVA|ASCA)"
            rb"[A-Z0-9]{16}(?![A-Z0-9])"
        ),
    ),
    SecretRule(
        "openai-api-key",
        re.compile(
            rb"(?<![A-Za-z0-9_-])(?:sk-(?:proj|svcacct)-[A-Za-z0-9_-]{20,}"
            rb"|sk-[A-Za-z0-9]{32,})(?![A-Za-z0-9_-])"
        ),
    ),
    SecretRule(
        "github-token",
        re.compile(
            rb"(?<![A-Za-z0-9_])(?:gh[pousr]_[A-Za-z0-9]{36,255}"
            rb"|github_pat_[A-Za-z0-9_]{60,255})(?![A-Za-z0-9_])"
        ),
    ),
    SecretRule(
        "gitlab-token",
        re.compile(
            rb"(?<![A-Za-z0-9_-])(?:glpat|glrt)-[A-Za-z0-9_-]{20,}"
            rb"(?![A-Za-z0-9_-])"
        ),
    ),
    SecretRule(
        "slack-token",
        re.compile(
            rb"(?<![A-Za-z0-9-])xox[baprs]-[A-Za-z0-9-]{10,}"
            rb"(?![A-Za-z0-9-])"
        ),
    ),
    SecretRule(
        "google-api-key",
        re.compile(rb"(?<![A-Za-z0-9_-])AIza[A-Za-z0-9_-]{35}(?![A-Za-z0-9_-])"),
    ),
)


PLACEHOLDER_MARKERS = (
    b"placeholder",
    b"example",
    b"sample",
    b"fake",
    b"dummy",
    b"test",
    b"redacted",
    b"changeme",
    b"replace-me",
    b"replace_me",
    b"not-a-real",
    b"not_real",
    b"your-",
)


TOKEN_PREFIXES = (
    b"sk-proj-",
    b"sk-svcacct-",
    b"github_pat_",
    b"glpat-",
    b"glrt-",
    b"xoxb-",
    b"xoxa-",
    b"xoxp-",
    b"xoxr-",
    b"xoxs-",
    b"ghp_",
    b"gho_",
    b"ghu_",
    b"ghs_",
    b"ghr_",
    b"sk-",
    b"AIza",
)


AWS_PREFIXES = (b"AKIA", b"ASIA", b"AIDA", b"AROA", b"AIPA", b"ANPA", b"ANVA", b"ASCA")


def _is_binary(data: bytes) -> bool:
    sample = data[:8192]
    if b"\0" in sample:
        return True
    control_bytes = sum(byte < 32 and byte not in (9, 10, 13) for byte in sample)
    return bool(sample) and control_bytes / len(sample) > 0.3


def _payload(value: bytes) -> bytes:
    lower_value = value.lower()
    for prefix in TOKEN_PREFIXES:
        if lower_value.startswith(prefix.lower()):
            return value[len(prefix) :]
    upper_value = value.upper()
    if upper_value.startswith(AWS_PREFIXES):
        return value[4:]
    return value


def _looks_like_placeholder(data: bytes, start: int, end: int) -> bool:
    value = data[start:end]
    payload = _payload(value).lower().lstrip(b"-_")
    if any(payload.startswith(marker) for marker in PLACEHOLDER_MARKERS):
        return True
    normalized_payload = bytes(byte for byte in payload if chr(byte).isalnum())
    return len(normalized_payload) >= 16 and len(set(normalized_payload)) <= 4


def scan_content(data: bytes, location: str) -> list[Finding]:
    if _is_binary(data):
        return []
    counts: Counter[str] = Counter()
    for rule in RULES:
        for match in rule.pattern.finditer(data):
            if not _looks_like_placeholder(data, match.start(), match.end()):
                counts[rule.name] += 1
    return [Finding(rule, location, count) for rule, count in counts.items()]


def _safe_path(raw_path: bytes) -> str:
    redacted_path = raw_path
    for rule in RULES:
        redacted_path = rule.pattern.sub(b"[secret]", redacted_path)
    path = os.fsdecode(redacted_path).replace("\\", "/")
    return "".join(character if character.isprintable() else "?" for character in path)
