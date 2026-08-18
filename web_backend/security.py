from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from cryptography.fernet import Fernet, InvalidToken

from web_backend.database import Database

PBKDF2_ITERATIONS = 600_000


class LoginAttemptLimiter:
    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._attempts: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def retry_after(self, key: str) -> int:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            attempts = [
                attempt for attempt in self._attempts.get(key, []) if attempt > cutoff
            ]
            if attempts:
                self._attempts[key] = attempts
            else:
                self._attempts.pop(key, None)
            if len(attempts) < self.limit:
                return 0
            return max(1, int(attempts[0] + self.window_seconds - now))

    def record_failure(self, key: str) -> None:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            attempts = [
                attempt for attempt in self._attempts.get(key, []) if attempt > cutoff
            ]
            attempts.append(now)
            self._attempts[key] = attempts

    def clear(self, key: str) -> None:
        with self._lock:
            self._attempts.pop(key, None)


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def hash_password(password: str) -> str:
    if len(password) < 10:
        raise ValueError("密码至少需要 10 个字符")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )
    return "pbkdf2_sha256${}${}${}".format(
        PBKDF2_ITERATIONS,
        base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, rounds_text, salt_text, digest_text = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_text)
        expected = base64.urlsafe_b64decode(digest_text)
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            int(rounds_text),
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Session:
    token: str
    expires_at: str


class SessionService:
    def __init__(self, database: Database, session_days: int) -> None:
        self.database = database
        self.session_days = session_days

    def create(self, user_id: str) -> Session:
        token = secrets.token_urlsafe(36)
        expires_at = datetime.now(UTC) + timedelta(days=self.session_days)
        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                "DELETE FROM sessions WHERE expires_at <= ?",
                (utc_now(),),
            )
            connection.execute(
                """
                INSERT INTO sessions(id, user_id, token_hash, expires_at, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    secrets.token_hex(16),
                    user_id,
                    token_hash(token),
                    expires_at.isoformat(),
                    utc_now(),
                ),
            )
        return Session(token=token, expires_at=expires_at.isoformat())

    def resolve(self, token: str | None) -> dict[str, object] | None:
        if not token:
            return None
        now = utc_now()
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT u.id, u.email, u.display_name, u.active, u.is_admin
                FROM sessions s
                JOIN users u ON u.id = s.user_id
                WHERE s.token_hash = ? AND s.expires_at > ? AND u.active = 1
                """,
                (token_hash(token), now),
            ).fetchone()
        if row is None:
            return None
        user = dict(row)
        user["active"] = bool(user["active"])
        user["is_admin"] = bool(user["is_admin"])
        return user

    def delete(self, token: str | None) -> None:
        if not token:
            return
        with self.database.transaction() as connection:
            connection.execute(
                "DELETE FROM sessions WHERE token_hash = ?",
                (token_hash(token),),
            )


class SecretBox:
    def __init__(self, key: str) -> None:
        if key:
            raw_key = key.encode("ascii")
        else:
            raw_key = base64.urlsafe_b64encode(
                hashlib.sha256(b"development-only-key").digest()
            )
        try:
            self.fernet = Fernet(raw_key)
        except ValueError as exc:
            raise ValueError("WEBAPP_ENCRYPTION_KEY 必须是 Fernet 密钥") from exc

    def encrypt(self, value: str) -> str:
        return self.fernet.encrypt(value.encode("utf-8")).decode("ascii")

    def decrypt(self, value: str) -> str:
        try:
            return self.fernet.decrypt(value.encode("ascii")).decode("utf-8")
        except InvalidToken as exc:
            raise ValueError("无法解密 API 密钥，请检查加密密钥") from exc
