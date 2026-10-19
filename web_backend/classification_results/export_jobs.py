"""持久保存可恢复的导出任务；文件与业务数据库分离。"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import re
import sqlite3
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any

from web_backend.classification_result_service import ClassificationResultService

EXPORT_FORMAT = "readable-feedback-v2"
EXPORT_TTL_SECONDS = 24 * 60 * 60
_LOGGER = logging.getLogger(__name__)


_INDEX_CAPACITY = 64
Generation = tuple[int, int]


class _ExportJobIndex:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        self._connection: sqlite3.Connection | None = None
        self._epoch = 0
        self._generation: Generation | None = None
        self._jobs: OrderedDict[tuple[str, ...], str] = OrderedDict()
        self._lock = threading.RLock()

    def _read_generation(self) -> Generation | None:
        try:
            if self._connection is None:
                self._connection = sqlite3.connect(
                    self._database_path.resolve().as_uri() + "?mode=ro",
                    uri=True,
                    check_same_thread=False,
                    isolation_level=None,
                )
                self._connection.execute("PRAGMA query_only=ON")
                self._epoch += 1
            version = int(self._connection.execute("PRAGMA data_version").fetchone()[0])
        except sqlite3.Error as error:
            self.close()
            _LOGGER.warning(
                "导出变更检测不可用，使用完整快照：%s", type(error).__name__
            )
            return None
        generation = (self._epoch, version)
        if generation != self._generation:
            self._jobs.clear()
            self._generation = generation
        return generation

    def lookup(self, key: tuple[str, ...]) -> tuple[Generation | None, str | None]:
        with self._lock:
            generation = self._read_generation()
            job_id = self._jobs.get(key) if generation is not None else None
            if job_id is not None:
                self._jobs.move_to_end(key)
            return generation, job_id

    def is_current(self, generation: Generation | None) -> bool:
        with self._lock:
            return generation is not None and generation == self._read_generation()

    def remember(
        self, key: tuple[str, ...], generation: Generation | None, job_id: str
    ) -> None:
        with self._lock:
            if not self.is_current(generation):
                return
            self._jobs[key] = job_id
            self._jobs.move_to_end(key)
            while len(self._jobs) > _INDEX_CAPACITY:
                self._jobs.popitem(last=False)

    def close(self) -> None:
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None
            self._generation = None
            self._jobs.clear()


class ResultExportService:
    def __init__(self, results: ClassificationResultService, directory: Path) -> None:
        self.results = results
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._index = _ExportJobIndex(results.database.path)

    def close(self) -> None:
        self._index.close()

    def _path(self, job_id: str, suffix: str = ".json") -> Path:
        if re.fullmatch(r"[a-f0-9]{64}", job_id) is None:
            raise FileNotFoundError("导出任务不存在")
        return self.directory / f"{job_id}{suffix}"

    def _save(self, job: dict[str, Any]) -> None:
        path = self._path(job["id"])
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
        temporary.replace(path)

    def _load(self, job_id: str, *, allow_expired: bool = False) -> dict[str, Any]:
        path = self._path(job_id)
        if not path.is_file():
            raise FileNotFoundError("导出任务不存在或已过期，请重新下载")
        job = json.loads(path.read_text(encoding="utf-8"))
        if not allow_expired and job["expires_at"] <= time.time():
            raise FileNotFoundError("导出文件已过期，请重新下载")
        return job

    @staticmethod
    def _public(job: dict[str, Any]) -> dict[str, Any]:
        return {
            key: job[key] for key in ("id", "status", "filename", "error", "expires_at")
        }

    def create(self, version_ids: list[str]) -> dict[str, Any]:
        versions = list(dict.fromkeys(version_ids))
        key = (EXPORT_FORMAT, *versions)
        generation, indexed_id = self._index.lookup(key)
        if indexed_id is not None:
            with self._lock:
                existing = self._reusable_job(indexed_id)
                if existing and self._index.is_current(generation):
                    return self._public(existing)
        # 完整内容摘要仍是任务身份；索引仅在读取期间无提交时登记。
        snapshot = self.results.capture_export(versions)
        content = json.dumps(snapshot, ensure_ascii=False, sort_keys=True).encode(
            "utf-8"
        )
        job_id = hashlib.sha256(EXPORT_FORMAT.encode() + content).hexdigest()
        with self._lock:
            existing = self._reusable_job(job_id)
            if existing:
                self._index.remember(key, generation, job_id)
                return self._public(existing)
        # 压缩不占状态锁；提交前再次检查，合并并发创建的相同任务。
        compressed = gzip.compress(content)
        with self._lock:
            existing = self._reusable_job(job_id)
            if existing:
                self._index.remember(key, generation, job_id)
                return self._public(existing)
            job = {
                "id": job_id,
                "status": "queued",
                "filename": snapshot[0]["filename"]
                if len(snapshot) == 1
                else "classification-results.xlsx",
                "version_ids": [item["version_id"] for item in snapshot],
                "error": "",
                "expires_at": time.time() + EXPORT_TTL_SECONDS,
            }
            path = self._path(job_id, ".snapshot.gz")
            temporary = path.with_suffix(".gz.tmp")
            temporary.write_bytes(compressed)
            temporary.replace(path)
            self._save(job)
            self._index.remember(key, generation, job_id)
            return self._public(job)

    def _reusable_job(self, job_id: str) -> dict[str, Any] | None:
        try:
            existing = self._load(job_id)
        except FileNotFoundError:
            return None
        if existing["status"] == "failed":
            return None
        if existing["status"] == "ready" and not self._path(job_id, ".xlsx").is_file():
            return None
        return existing

    def get(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._load(job_id)
            # 与原下载入口一样要求结果仍然存在，永久删除后不能从缓存取回。
            for version_id in job["version_ids"]:
                self.results.get(version_id)
            if job["status"] == "ready" and not self._path(job_id, ".xlsx").is_file():
                raise FileNotFoundError("导出文件已清理，请重新下载")
            return self._public(job)

    def file(self, job_id: str) -> tuple[Path, str]:
        job = self.get(job_id)
        if job["status"] != "ready":
            raise ValueError("文件尚未生成，请稍后重试")
        path = self._path(job_id, ".xlsx")
        return path, job["filename"]

    def recover(self) -> None:
        with self._lock:
            self._cleanup()
            for path in self.directory.glob("*.json"):
                job = json.loads(path.read_text(encoding="utf-8"))
                if job["status"] == "running":
                    job["status"] = "queued"
                    self._save(job)

    def _cleanup(self) -> None:
        for path in self.directory.glob("*.json"):
            job = json.loads(path.read_text(encoding="utf-8"))
            if job["expires_at"] > time.time() or job["status"] == "running":
                continue
            for suffix in (".snapshot.gz", ".xlsx", ".xlsx.tmp", ".json"):
                self._path(job["id"], suffix).unlink(missing_ok=True)

    def claim_next(self) -> str | None:
        with self._lock:
            self._cleanup()
            for path in sorted(
                self.directory.glob("*.json"), key=lambda item: item.stat().st_mtime
            ):
                job = json.loads(path.read_text(encoding="utf-8"))
                if job["status"] == "queued":
                    job["status"] = "running"
                    self._save(job)
                    return str(job["id"])
        return None

    def run(self, job_id: str) -> None:
        try:
            self.get(job_id)
            with gzip.open(self._path(job_id, ".snapshot.gz"), "rb") as stream:
                snapshot = json.loads(stream.read())
            content = self.results.snapshot_workbook(snapshot)
            temporary = self._path(job_id, ".xlsx.tmp")
            temporary.write_bytes(content)
            temporary.replace(self._path(job_id, ".xlsx"))
        except Exception as error:
            # 不把原文、SQL 或内部文件路径写入接口错误或日志。
            _LOGGER.error("结果导出失败：%s", type(error).__name__)
            self._finish(job_id, "failed", "文件生成失败，请点击重试")
        else:
            self._finish(job_id, "ready", "")

    def _finish(self, job_id: str, status: str, error: str) -> None:
        with self._lock:
            # 过期只限制下载；正在执行的任务仍须结束，随后清除过期产物。
            job = self._load(job_id, allow_expired=True)
            job.update(status=status, error=error)
            self._save(job)
            self._cleanup()
