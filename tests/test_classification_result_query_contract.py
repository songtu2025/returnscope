from __future__ import annotations

from types import SimpleNamespace

import pytest
from classification_result_router_helpers import BASE_PATH, _path
from classification_result_router_helpers import harness as harness


@pytest.mark.parametrize(
    ("suffix", "method"),
    [
        ("", "list"),
        ("/{version_id}/records", "records"),
        ("/{version_id}/record-groups", "record_groups"),
        ("/{version_id}/drilldown", "drilldown"),
    ],
)
def test_invalid_service_queries_keep_bad_request_response(
    harness: SimpleNamespace,
    suffix: str,
    method: str,
) -> None:
    getattr(harness.result_mock, method).side_effect = ValueError("合成筛选错误")
    response = harness.client.get(
        _path(harness, suffix), params={"group_by": "problem"}
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "合成筛选错误"}


@pytest.mark.parametrize(
    ("suffix", "method"),
    [
        ("/{version_id}/records", "records"),
        ("/{version_id}/record-groups", "record_groups"),
    ],
)
def test_record_filters_are_forwarded_without_loss(
    harness: SimpleNamespace,
    suffix: str,
    method: str,
) -> None:
    filters = {
        "page": 2,
        "page_size": 10,
        "order_id": "ORDER-OTHER",
        "listing": "L1",
        "product_name": "权威",
        "source_sku": "SOURCE-MSKU-1",
        "matched_msku": "SOURCE-MSKU-1",
        "product_sku": "PRODUCT-SKU-1",
        "asin": "ASIN-1",
        "problem": "FIT_TOO_SMALL_U1",
        "quality_status": "ready",
        "comment_status": "NEGATIVE",
        "system_rerun_required": "false",
    }
    response = harness.client.get(_path(harness, suffix), params=filters)
    assert response.status_code == 200, response.text
    getattr(harness.result_mock, method).assert_called_once_with(
        harness.version_id, **filters
    )
    assert response.json() == getattr(harness.service, method)(
        harness.version_id, **filters
    )


def test_result_list_filters_are_forwarded_without_loss(
    harness: SimpleNamespace,
) -> None:
    filters = {
        "page": 2,
        "page_size": 10,
        "q": "权威",
        "store_site": "SEEKWAY:US",
        "listing": "L1",
        "quality_status": "ready",
    }
    response = harness.client.get(BASE_PATH, params=filters)
    assert response.status_code == 200, response.text
    harness.result_mock.list.assert_called_once_with(**filters)
    assert response.json() == harness.service.list(**filters)


def test_drilldown_filters_are_forwarded_without_loss(harness: SimpleNamespace) -> None:
    filters = {
        "page": 2,
        "page_size": 10,
        "problem": "FIT_TOO_SMALL_U1",
        "product_name": "权威",
        "product_sku": "PRODUCT-SKU-1",
        "order_id": "ORDER-OTHER",
    }
    response = harness.client.get(
        _path(harness, "/{version_id}/drilldown"),
        params={"group_by": "category", **filters},
    )
    assert response.status_code == 200, response.text
    harness.result_mock.drilldown.assert_called_once_with(
        harness.version_id, "category", **filters
    )
    assert response.json() == harness.service.drilldown(
        harness.version_id, "category", **filters
    )


@pytest.mark.parametrize(
    "suffix",
    [
        "",
        "/{version_id}/records",
        "/{version_id}/record-groups",
        "/{version_id}/drilldown",
    ],
)
@pytest.mark.parametrize("invalid", [{"page": 0}, {"page_size": 201}])
def test_pagination_bounds_are_validated_before_service_calls(
    harness: SimpleNamespace,
    suffix: str,
    invalid: dict[str, int],
) -> None:
    response = harness.client.get(
        _path(harness, suffix), params={"group_by": "problem", **invalid}
    )
    assert response.status_code == 422
    assert not harness.result_mock.mock_calls


def test_drilldown_still_requires_group_by(harness: SimpleNamespace) -> None:
    response = harness.client.get(_path(harness, "/{version_id}/drilldown"))
    assert response.status_code == 422
    assert not harness.result_mock.mock_calls


@pytest.mark.parametrize(
    "suffix", ["/{version_id}/records", "/{version_id}/record-groups"]
)
@pytest.mark.parametrize("field", ["comment_status", "system_rerun_required"])
def test_semantic_filter_validation_is_enforced_by_api(harness, suffix, field) -> None:
    response = harness.client.get(_path(harness, suffix), params={field: "INVALID"})
    assert response.status_code == 400
    assert response.json() == {"detail": f"{field} 不合法"}
