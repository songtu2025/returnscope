from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from test_manual_correction import _items, _record
from test_result_version_reviews import _publish_review_required

from web_backend.classification_result_publication import ResultPublicationConflict
from web_backend.classification_result_service import ClassificationResultService
from web_backend.classification_results.manual_correction import correct_group


def test_concurrent_manual_corrections_keep_one_result_and_allow_fresh_retry(tmp_path):
    context, version = _publish_review_required(tmp_path)
    service = ClassificationResultService(context.database)
    record_id = _record(context, version)
    barrier = Barrier(2)

    def correct():
        barrier.wait(timeout=5)
        try:
            return correct_group(
                service, version["version_id"], record_id, _items(), "user-2"
            )["version_id"]
        except ResultPublicationConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: correct(), range(2)))
    assert results.count("conflict") == 1
    current_id = next(value for value in results if value != "conflict")
    current = service.get(current_id)
    repeated = correct_group(
        service, current_id, _record(context, current), _items(), "user-2"
    )
    assert repeated["version_id"] == current_id
    with context.database.connect() as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM classification_result_versions"
            ).fetchone()[0]
            == 2
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM audit_logs WHERE action='manual_correction'"
            ).fetchone()[0]
            == 1
        )
        assert (
            connection.execute(
                "SELECT result_version_id FROM task_segments WHERE id=?",
                (context.segment_id,),
            ).fetchone()[0]
            == current_id
        )
