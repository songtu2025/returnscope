from web_backend.insight_reports.v8_text_signals import EARLY_FAILURE


def keep_examples(examples, theme, members, row, text, early, pairs) -> None:
    groups = [theme]
    if early:
        groups.append(EARLY_FAILURE)
    codes = {code for code, _ in members}
    for left, right in pairs:
        small, large = bool(codes.intersection(left)), bool(codes.intersection(right))
        if small or large:
            groups.append(
                "双向" if small and large else "仅偏小" if small else "仅偏大"
            )
    source = dict(row)
    for group in groups:
        if len(examples[group]) >= 2:
            continue
        examples[group].append(
            {
                "record_id": source["id"],
                "source_record_id": source.get("source_record_id"),
                "result_version_id": source["result_version_id"],
                "source_row": source.get("source_row"),
                "excerpt": text[:200],
                "date": source["return_date"],
                "product": source["product_name"]
                if source["product_match_status"] == "matched"
                else None,
                "mapping_status": source["product_match_status"],
                "review_status": source.get("quality_status"),
                "reason": f"命中「{group}」口径",
            }
        )
