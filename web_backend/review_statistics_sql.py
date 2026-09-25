REVIEW_CHANGED_UNIT_COUNT_SQL = """
COALESCE((
    SELECT COUNT(DISTINCT revision.review_record_id)
    FROM review_batches batch
    JOIN review_records review ON review.batch_id = batch.id
    JOIN review_revisions revision
      ON revision.review_record_id = review.id
    WHERE batch.published_version_id = v.id
      AND (
          json_extract(revision.before_json, '$.semantic_units')
            IS NOT json_extract(revision.after_json, '$.semantic_units')
          OR json_extract(revision.before_json, '$.unknown_semantics')
            IS NOT json_extract(revision.after_json, '$.unknown_semantics')
          OR json_extract(revision.before_json, '$.problem_label_codes')
            IS NOT json_extract(revision.after_json, '$.problem_label_codes')
          OR json_extract(revision.before_json, '$.positive_label_codes')
            IS NOT json_extract(revision.after_json, '$.positive_label_codes')
          OR json_extract(revision.before_json, '$.primary_label_codes')
            IS NOT json_extract(revision.after_json, '$.primary_label_codes')
      )
), 0)
"""
