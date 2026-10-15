"""持久保存可恢复的导出任务；文件与业务数据库分离。"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import re
import threading
import time
from pathlib import Path
from typing import Any

from web_backend.classification_result_service import ClassificationResultService

EXPORT_FORMAT = "readable-feedback-v2"
EXPORT_TTL_SECONDS = 24 * 60 * 60
_LOGGER = logging.getLogger(__name__)


class ResultExportService:
    def __init__(self, results: ClassificationResultService, directory: Path) -> None:
        self.results = results
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

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
        # 快照包含全部导出字段，人工修正或产品信息变化都会形成不同缓存键。
        with self._lock:
            snapshot = self.results.capture_export(list(dict.fromkeys(version_ids)))
            content = json.dumps(snapshot, ensure_ascii=False, sort_keys=True).encode(
                "utf-8"
            )
            job_id = hashlib.sha256(EXPORT_FORMAT.encode() + content).hexdigest()
            try:
                existing = self._load(job_id)
            except FileNotFoundError:
                existing = None
            if existing and existing["status"] != "failed":
                if (
                    existing["status"] != "ready"
                    or self._path(job_id, ".xlsx").is_file()
                ):
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
            with gzip.open(temporary, "wb") as stream:
                stream.write(content)
            temporary.replace(path)
            self._save(job)
            return self._public(job)

    def get(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._load(job_id)
            # 与原下载入口一样要求结果仍然存在，永久删除后不能从缓存取回。
            for version_id in job["version_ids"]:
                self.results.get(version_id)
            return self._public(job)

    def file(self, job_id: str) -> tuple[Path, str]:
        job = self.get(job_id)
        if job["status"] != "ready":
            raise ValueError("文件尚未生成，请稍后重试")
        path = self._path(job_id, ".xlsx")
        if not path.is_file():
            raise FileNotFoundError("导出文件已过期，请重新下载")
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
