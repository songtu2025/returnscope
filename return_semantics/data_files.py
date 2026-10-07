from __future__ import annotations

import re
from pathlib import Path
from zipfile import BadZipFile

import pandas as pd

RETURN_COLUMNS = [
    "return-date",
    "order-id",
    "sku",
    "asin",
    "fnsku",
    "product-name",
    "quantity",
    "reason",
    "customer-comments",
]

RETURN_STORE_COLUMN = "店铺/站点"

SOURCE_ORIGIN_COLUMN = "source-origin-id"


def _looks_like_gb18030(frame: pd.DataFrame) -> bool:
    sample = "".join(
        frame.head(1000).fillna("").astype(str).to_numpy().ravel().tolist()
    )
    compact = re.sub(r"\s+", "", sample)
    cjk_count = len(re.findall(r"[\u4e00-\u9fff]", compact))
    mixed_count = len(
        re.findall(
            r"(?:[A-Za-z][\u4e00-\u9fff]|[\u4e00-\u9fff][A-Za-z])",
            compact,
        )
    )
    return (
        cjk_count >= 4
        and cjk_count / max(len(compact), 1) >= 0.02
        and mixed_count <= max(1, cjk_count // 4)
    )


def _return_column_score(frame: pd.DataFrame) -> int:
    columns = {str(column) for column in frame.columns}
    return sum(column in columns for column in [*RETURN_COLUMNS, RETURN_STORE_COLUMN])


def _select_columns(
    frame: pd.DataFrame,
    usecols: list[str] | None,
) -> pd.DataFrame:
    if usecols is None:
        return frame
    missing = [column for column in usecols if column not in frame.columns]
    if missing:
        raise ValueError(f"用户反馈数据缺少字段: {', '.join(missing)}")
    selected = set(usecols)
    return frame.loc[:, [column for column in frame.columns if column in selected]]


def read_return_csv(
    path: Path,
    usecols: list[str] | None = None,
    nrows: int | None = None,
) -> pd.DataFrame:
    try:
        frame = pd.read_csv(
            path,
            encoding="utf-8-sig",
            dtype=str,
            nrows=nrows,
        )
        return _select_columns(frame, usecols)
    except UnicodeDecodeError:
        pass

    decoded: dict[str, pd.DataFrame] = {}
    last_error: UnicodeDecodeError | None = None
    for encoding in ("cp1252", "gb18030"):
        try:
            decoded[encoding] = pd.read_csv(
                path,
                encoding=encoding,
                dtype=str,
                nrows=nrows,
            )
        except UnicodeDecodeError as exc:
            last_error = exc
    if "gb18030" in decoded:
        gb18030_frame = decoded["gb18030"]
        cp1252_frame = decoded.get("cp1252")
        gb18030_score = _return_column_score(gb18030_frame)
        cp1252_score = (
            _return_column_score(cp1252_frame) if cp1252_frame is not None else -1
        )
        if (
            cp1252_frame is None
            or gb18030_score > cp1252_score
            or (gb18030_score == cp1252_score and _looks_like_gb18030(gb18030_frame))
        ):
            return _select_columns(gb18030_frame, usecols)
    if "cp1252" in decoded:
        return _select_columns(decoded["cp1252"], usecols)
    assert last_error is not None
    raise last_error


def read_return_xlsx(
    path: Path,
    usecols: list[str] | None = None,
    nrows: int | None = None,
) -> pd.DataFrame:
    try:
        workbook = pd.ExcelFile(path)
    except (BadZipFile, ValueError) as exc:
        raise ValueError("无法读取退货 XLSX 文件，请确认文件未损坏") from exc

    with workbook:
        for sheet_name in workbook.sheet_names:
            header = pd.read_excel(workbook, sheet_name=sheet_name, nrows=0)
            columns = {str(column) for column in header.columns}
            if not set(RETURN_COLUMNS).issubset(columns):
                continue
            frame = pd.read_excel(
                workbook,
                sheet_name=sheet_name,
                dtype=str,
                usecols=usecols,
                nrows=nrows,
            )
            frame.attrs["worksheet_name"] = str(sheet_name)
            return frame

    raise ValueError("退货 XLSX 中未找到包含全部必需字段的工作表")
