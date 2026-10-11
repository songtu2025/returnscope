REVIEW_CHANGED_UNIT_COUNT_SQL = """
CASE WHEN v.version_reason = '反馈组人工修正' THEN (
    SELECT COUNT(*) FROM classification_units current_unit
    LEFT JOIN classification_units parent_unit
      ON parent_unit.result_version_id = v.parent_version_id
     AND parent_unit.classification_key = current_unit.classification_key
    WHERE current_unit.result_version_id = v.id
      AND json_extract(current_unit.classification_json, '$.human_review_assessment.resolved') = 1
      AND (
          parent_unit.id IS NULL
          OR json_extract(current_unit.classification_json, '$.human_review_assessment.assessed_at')
            IS NOT json_extract(parent_unit.classification_json, '$.human_review_assessment.assessed_at')
      )
) ELSE COALESCE((
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
          OR EXISTS (
              SELECT 1 FROM classification_units published_unit
              WHERE published_unit.result_version_id = v.id
                AND published_unit.classification_key = review.classification_key
                AND (
                    json_extract(published_unit.classification_json, '$.semantic_units')
                      IS NOT json_extract(revision.before_json, '$.semantic_units')
                    OR json_extract(published_unit.classification_json, '$.unknown_semantics')
                      IS NOT json_extract(revision.before_json, '$.unknown_semantics')
                )
          )
      )
), 0) END
"""
