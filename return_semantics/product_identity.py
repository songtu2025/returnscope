"""产品资料内的店铺与 MSKU 共同标识唯一商品。"""

import pandas as pd


def validate_product_identities(frame: pd.DataFrame) -> None:
    keys = frame[["店铺/站点", "MSKU"]].fillna("").astype(str)
    keys = keys.apply(lambda column: column.str.strip())
    duplicate = keys.duplicated(keep=False)
    if duplicate.any():
        rows = ", ".join(
            str(index + 2) for index in range(len(keys)) if duplicate.iloc[index]
        )
        raise ValueError(
            f"同一店铺/站点内 MSKU 必须唯一，重复数据位于 Excel 行：{rows}"
        )
