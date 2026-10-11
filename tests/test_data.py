from pathlib import Path

import pandas as pd
import pytest

from return_semantics.data import (
    RETURN_COLUMNS,
    RETURN_STORE_COLUMN,
    load_return_dataset,
    normalize_comment,
    read_return_csv,
    read_return_file,
)


def test_normalize_comment_decodes_html_and_whitespace() -> None:
    assert normalize_comment("  It&#39;s\n too\t small  ") == "It's too small"


def test_return_csv_supports_utf8_cp1252_and_gb18030(tmp_path: Path) -> None:
    utf8_path = tmp_path / "utf8.csv"
    utf8_path.write_text("comment\n鞋子太大\n", encoding="utf-8-sig")
    cp1252_path = tmp_path / "cp1252.csv"
    cp1252_path.write_bytes("comment\nDidn’t fit\n".encode("cp1252"))
    gb18030_path = tmp_path / "gb18030.csv"
    gb18030_path.write_bytes("comment\n鞋子太大\n".encode("gb18030"))
    gb18030_header_path = tmp_path / "gb18030-header.csv"
    gb18030_header_path.write_bytes(
        "店铺/站点,customer-comments\nSENWAYZON:US,Too small\n".encode("gb18030")
    )

    assert read_return_csv(utf8_path).iloc[0]["comment"] == "鞋子太大"
    assert read_return_csv(cp1252_path).iloc[0]["comment"] == "Didn’t fit"
    assert read_return_csv(gb18030_path).iloc[0]["comment"] == "鞋子太大"
    assert read_return_csv(gb18030_header_path).columns.tolist() == [
        RETURN_STORE_COLUMN,
        "customer-comments",
    ]


def test_return_file_selects_first_valid_xlsx_sheet(tmp_path: Path) -> None:
    path = tmp_path / "returns.xlsx"
    row = {column: "" for column in RETURN_COLUMNS}
    row.update(
        {
            "order-id": "ORDER-1",
            "sku": "SKU-1",
            "customer-comments": "Too small",
            RETURN_STORE_COLUMN: "SENWAYZON:US",
        }
    )
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame([{"说明": "导入说明"}]).to_excel(
            writer,
            sheet_name="说明",
            index=False,
        )
        pd.DataFrame([row]).to_excel(
            writer,
            sheet_name="退货明细",
            index=False,
        )

    frame = read_return_file(path)

    assert frame.attrs["worksheet_name"] == "退货明细"
    assert frame.iloc[0]["order-id"] == "ORDER-1"
    assert frame.iloc[0][RETURN_STORE_COLUMN] == "SENWAYZON:US"


def test_return_file_rejects_xlsx_without_required_columns(tmp_path: Path) -> None:
    path = tmp_path / "invalid-returns.xlsx"
    pd.DataFrame([{"说明": "缺少退货字段"}]).to_excel(path, index=False)

    with pytest.raises(ValueError, match="未找到包含全部必需字段的工作表"):
        read_return_file(path)


def test_real_sk001_data_matches_business_baseline(
    seekway_business_baseline_files: tuple[Path, Path],
) -> None:
    returns_path, products_path = seekway_business_baseline_files
    dataset = load_return_dataset(
        returns_path,
        products_path,
        store="SEEKWAY:US",
        listing="SK001",
    )

    assert len(dataset.mskus) == 280
    assert len(dataset.records) == 9140
    assert int(dataset.records["has_text_evidence"].sum()) == 5758
    assert len(dataset.unique_comments) == 3347
    assert set(dataset.unique_comments["category_a"]) == {"水鞋"}


def test_classification_key_isolated_by_product_category(tmp_path: Path) -> None:
    returns_path = tmp_path / "returns.csv"
    products_path = tmp_path / "products.xlsx"
    pd.DataFrame(
        [
            {
                "return-date": "2026-01-01",
                "order-id": "1",
                "sku": "SKU-HAT",
                "asin": "",
                "fnsku": "",
                "product-name": "hat",
                "quantity": "1",
                "reason": "NOT_AS_DESCRIBED",
                "customer-comments": "Too small",
            },
            {
                "return-date": "2026-01-01",
                "order-id": "2",
                "sku": "SKU-GLASSES",
                "asin": "",
                "fnsku": "",
                "product-name": "glasses",
                "quantity": "1",
                "reason": "NOT_AS_DESCRIBED",
                "customer-comments": "Too small",
            },
        ]
    ).to_csv(returns_path, index=False, encoding="utf-8-sig")
    products = pd.DataFrame(
        [
            {
                "MSKU": "SKU-HAT",
                "店铺/站点": "STORE",
                "Listing": "HAT",
                "品类A": "遮阳帽",
                "品类B": "儿童渔夫帽",
            },
            {
                "MSKU": "SKU-GLASSES",
                "店铺/站点": "STORE",
                "Listing": "GLASSES",
                "品类A": "眼镜",
                "品类B": "儿童眼镜",
            },
        ]
    )
    with pd.ExcelWriter(products_path, engine="openpyxl") as writer:
        products.to_excel(writer, sheet_name="产品信息汇总表", index=False)

    dataset = load_return_dataset(
        returns_path,
        products_path,
        store="STORE",
    )

    assert len(dataset.unique_comments) == 2
    assert dataset.unique_comments["classification_key"].nunique() == 2


def test_user_feedback_title_does_not_change_semantic_identity(tmp_path: Path) -> None:
    returns_path = tmp_path / "feedback.csv"
    products_path = tmp_path / "products.xlsx"
    rows = []
    for order_id, title in (("1", "Great gloves"), ("2", "Winter favorite")):
        rows.append(
            {
                "return-date": "2026-01-01",
                "order-id": order_id,
                "sku": "SKU-GLOVE",
                "asin": "",
                "fnsku": "",
                "product-name": "gloves",
                "quantity": "1",
                "reason": title,
                "customer-comments": "Warm and comfortable",
            }
        )
    pd.DataFrame(rows).to_csv(returns_path, index=False, encoding="utf-8-sig")
    products = pd.DataFrame(
        [
            {
                "MSKU": "SKU-GLOVE",
                "店铺/站点": "STORE",
                "Listing": "GLOVE",
                "品类A": "手套",
                "品类B": "冬季手套",
            }
        ]
    )
    with pd.ExcelWriter(products_path, engine="openpyxl") as writer:
        products.to_excel(writer, sheet_name="产品信息汇总表", index=False)

    dataset = load_return_dataset(
        returns_path,
        products_path,
        store="STORE",
        analysis_context="user_feedback",
    )

    assert len(dataset.records) == 2
    assert len(dataset.unique_comments) == 1
    assert set(dataset.records["feedback_title"]) == {
        "Great gloves",
        "Winter favorite",
    }
    assert "Great gloves" not in dataset.unique_comments.iloc[0]["classification_key"]
