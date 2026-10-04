from return_semantics.data import RETURN_STORE_COLUMN

FIELD_LABELS = {
    "return-date": "退货日期",
    "order-id": "订单号",
    "sku": "SKU / MSKU",
    "asin": "ASIN",
    "fnsku": "FNSKU",
    "product-name": "产品名称",
    "quantity": "退货数量",
    "reason": "退货原因",
    "customer-comments": "客户评论",
    RETURN_STORE_COLUMN: "店铺/站点",
}
OPTIONAL_FIELDS = {"asin", "fnsku", "product-name", RETURN_STORE_COLUMN}
RAW_COMMENT_COLUMN = "raw_customer_comments"
MARKET_STORE_COLUMN = "market_store"


class MySQLSourceError(ValueError):
    pass


def _quote_identifier(value: str) -> str:
    return "`" + value.replace("`", "``") + "`"
