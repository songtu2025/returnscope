from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import call

import pytest
from fastapi import HTTPException, UploadFile
from test_dataset_router_contract import harness as harness
from test_dataset_router_contract import synthetic_user

from web_backend.routers.datasets import XLSX_CONTENT_TYPE

UPLOAD_CASES = (
    ("inspect_return_import", "/api/return-imports/inspect", {}, 200),
    ("create", "/api/datasets", {"name": "合成数据", "kind": "products"}, 201),
    (
        "add_version",
        "/api/datasets/dataset-1/versions",
        {"change_note": "验证追加"},
        201,
    ),
)
CONTENT = b"column\nsynthetic-value\n"


@pytest.mark.parametrize(("service_method", "path", "form", "status"), UPLOAD_CASES)
def test_upload_routes_preserve_file_metadata_and_cleanup(
    harness: SimpleNamespace,
    service_method: str,
    path: str,
    form: dict[str, str],
    status: int,
) -> None:
    harness.service.get.return_value = {"kind": "products"}
    captured: dict[str, Any] = {}

    def capture(*args: Any, **kwargs: Any) -> dict[str, str]:
        source = args[0] if args else kwargs["source_path"]
        assert source.read_bytes() == CONTENT
        captured.update(source=source, args=args, kwargs=kwargs)
        return {"id": "synthetic-dataset"}

    getattr(harness.service, service_method).side_effect = capture
    response = harness.client.post(
        path, data=form, files={"file": ("synthetic.CSV", CONTENT, "text/csv")}
    )
    assert response.status_code == status
    assert response.json() == {"id": "synthetic-dataset"}
    source = captured["source"]
    assert source.suffix == ".csv"
    if service_method == "inspect_return_import":
        expected_args = (source, "synthetic.CSV")
        expected_kwargs = {"actor_id": "42", "content_type": "text/csv"}
        assert source.parent == harness.settings.data_dir / "tmp" / "dataset-imports"
        assert source.exists()
    else:
        expected_args = ()
        expected_kwargs = {
            "source_path": source,
            "original_name": "synthetic.CSV",
            "content_type": "text/csv",
            "actor_id": "42",
            "change_note": form.get("change_note", ""),
        }
        if service_method == "create":
            expected_kwargs.update(name="合成数据", kind="products", description="")
        else:
            expected_kwargs["dataset_id"] = "dataset-1"
        assert source.parent == harness.settings.data_dir / "tmp"
        assert not source.exists()
    assert captured["args"] == expected_args
    assert captured["kwargs"] == expected_kwargs
    assert harness.service.mock_calls == (
        [call.get("dataset-1")] if service_method == "add_version" else []
    ) + [getattr(call, service_method)(*expected_args, **expected_kwargs)]
    assert harness.mysql.mock_calls == []


@pytest.mark.parametrize(
    ("service_method", "path", "form"), [case[:3] for case in UPLOAD_CASES]
)
@pytest.mark.parametrize("error_type", (ValueError, RuntimeError))
def test_upload_errors_preserve_mapping_and_remove_temporary_files(
    harness: SimpleNamespace,
    service_method: str,
    path: str,
    form: dict[str, str],
    error_type: type[Exception],
) -> None:
    harness.service.get.return_value = {"kind": "products"}
    captured = []
    error = error_type("合成上传异常")

    def fail(*args: Any, **kwargs: Any) -> None:
        source = args[0] if args else kwargs["source_path"]
        assert source.read_bytes() == CONTENT
        captured.append(source)
        raise error

    getattr(harness.service, service_method).side_effect = fail
    options = {"data": form, "files": {"file": ("synthetic.csv", CONTENT, "text/csv")}}
    if error_type is ValueError:
        response = harness.client.post(path, **options)
        assert response.status_code == 400
        assert response.json() == {"detail": "合成上传异常"}
    else:
        with pytest.raises(RuntimeError) as raised:
            harness.client.post(path, **options)
        assert raised.value is error
    assert len(captured) == 1
    assert not captured[0].exists()


@pytest.mark.parametrize(
    ("path", "form"), [(case[1], case[2]) for case in UPLOAD_CASES]
)
def test_upload_size_limit_is_enforced_before_service_call(
    harness: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    form: dict[str, str],
) -> None:
    harness.service.get.return_value = {"kind": "products"}
    monkeypatch.setattr(
        "web_backend.routers.datasets.MAX_UPLOAD_BYTES", len(CONTENT) - 1
    )
    response = harness.client.post(
        path, data=form, files={"file": ("synthetic.csv", CONTENT, "text/csv")}
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "单个文件不能超过 200 MB"}
    assert harness.service.mock_calls == (
        [call.get("dataset-1")] if "/versions" in path else []
    )
    assert harness.mysql.mock_calls == []
    assert list(harness.settings.data_dir.rglob("*.csv")) == []


@pytest.mark.parametrize(
    ("path", "form"), [(case[1], case[2]) for case in UPLOAD_CASES]
)
def test_upload_routes_require_login_without_saving_files(
    harness: SimpleNamespace, path: str, form: dict[str, str]
) -> None:
    def reject_user() -> dict[str, Any]:
        raise HTTPException(status_code=401, detail="请先登录")

    harness.client.app.dependency_overrides[synthetic_user] = reject_user
    response = harness.client.post(
        path, data=form, files={"file": ("synthetic.csv", CONTENT, "text/csv")}
    )
    assert response.status_code == 401
    assert harness.service.mock_calls == harness.mysql.mock_calls == []
    assert not (harness.settings.data_dir / "tmp").exists()


@pytest.mark.parametrize(
    ("path", "form"), [(case[1], case[2]) for case in UPLOAD_CASES]
)
def test_missing_upload_file_does_not_call_service(
    harness: SimpleNamespace, path: str, form: dict[str, str]
) -> None:
    response = harness.client.post(path, data=form)
    assert response.status_code == 422
    assert harness.service.mock_calls == harness.mysql.mock_calls == []


@pytest.mark.parametrize(
    ("filename", "content_type", "expected"),
    [
        ("synthetic.csv", None, "text/csv"),
        ("synthetic.xlsx", None, XLSX_CONTENT_TYPE),
        ("synthetic.bin", None, "application/octet-stream"),
        ("synthetic.xlsx", "application/custom", "application/custom"),
    ],
)
def test_upload_content_type_fallback_keeps_current_precedence(
    harness: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    filename: str,
    content_type: str | None,
    expected: str,
) -> None:
    async def save_without_content_type(upload: UploadFile, destination: Path) -> None:
        upload.headers = {"content-type": content_type} if content_type else {}
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(await upload.read())

    monkeypatch.setattr(
        "web_backend.routers.datasets._save_upload", save_without_content_type
    )
    harness.service.inspect_return_import.return_value = {}
    response = harness.client.post(
        "/api/return-imports/inspect", files={"file": (filename, CONTENT)}
    )
    assert response.status_code == 200
    assert (
        harness.service.inspect_return_import.call_args.kwargs["content_type"]
        == expected
    )


@pytest.mark.parametrize("service_method", ("create", "add_version"))
def test_upload_routes_forward_optional_form_values(
    harness: SimpleNamespace, service_method: str
) -> None:
    harness.service.get.return_value = {"kind": "products"}
    case = next(case for case in UPLOAD_CASES if case[0] == service_method)
    form = {**case[2], "default_store": "S1", "change_note": "指定变更原因"}
    if service_method == "create":
        form["description"] = "合成说明"
    getattr(harness.service, service_method).return_value = {}
    response = harness.client.post(
        case[1], data=form, files={"file": ("synthetic.csv", CONTENT, "text/csv")}
    )
    assert response.status_code == 201
    forwarded = getattr(harness.service, service_method).call_args.kwargs
    assert "default_store" not in forwarded
    assert forwarded["change_note"] == "指定变更原因"
    if service_method == "create":
        assert forwarded["description"] == "合成说明"


@pytest.mark.parametrize("version", (None, 2))
def test_dataset_download_preserves_bytes_headers_and_version(
    harness: SimpleNamespace, version: int | None
) -> None:
    source = harness.settings.data_dir / "synthetic.csv"
    source.write_bytes(CONTENT)
    harness.service.version_file.return_value = {
        "file_path": str(source),
        "original_name": "download.csv",
        "content_type": "text/csv",
    }
    response = harness.client.get(
        "/api/datasets/dataset-1/download",
        params={} if version is None else {"version": version},
    )
    assert response.status_code == 200
    assert response.content == CONTENT
    assert response.headers["content-type"].startswith("text/csv")
    assert (
        response.headers["content-disposition"] == 'attachment; filename="download.csv"'
    )
    assert harness.service.mock_calls == [call.version_file("dataset-1", version)]
    assert source.read_bytes() == CONTENT


@pytest.mark.parametrize(
    ("missing_version", "detail"), [(True, "数据版本不存在"), (False, "数据文件不存在")]
)
def test_dataset_download_preserves_missing_version_and_file_errors(
    harness: SimpleNamespace, missing_version: bool, detail: str
) -> None:
    harness.service.version_file.return_value = (
        None
        if missing_version
        else {"file_path": str(harness.settings.data_dir / "missing.csv")}
    )
    response = harness.client.get("/api/datasets/dataset-1/download")
    assert response.status_code == 404
    assert response.json() == {"detail": detail}
    assert harness.service.mock_calls == [call.version_file("dataset-1", None)]


def test_dataset_download_requires_login(harness: SimpleNamespace) -> None:
    def reject_user() -> dict[str, Any]:
        raise HTTPException(status_code=401, detail="请先登录")

    harness.client.app.dependency_overrides[synthetic_user] = reject_user
    assert harness.client.get("/api/datasets/dataset-1/download").status_code == 401
    assert harness.service.mock_calls == harness.mysql.mock_calls == []


def test_dataset_download_rejects_invalid_version(harness: SimpleNamespace) -> None:
    assert (
        harness.client.get(
            "/api/datasets/dataset-1/download", params={"version": 0}
        ).status_code
        == 422
    )
    assert harness.service.mock_calls == []


def test_dataset_download_propagates_unexpected_error(harness: SimpleNamespace) -> None:
    error = RuntimeError("合成下载异常")
    harness.service.version_file.side_effect = error
    with pytest.raises(RuntimeError) as raised:
        harness.client.get("/api/datasets/dataset-1/download")
    assert raised.value is error
