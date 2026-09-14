from __future__ import annotations

from typing import Any, Callable

from web_backend.database import Database
from web_backend.task_contracts import (
    ACTIVE_STATUSES as ACTIVE_STATUSES,
)
from web_backend.task_contracts import (
    FINAL_STATUSES as FINAL_STATUSES,
)
from web_backend.task_contracts import (
    SEGMENT_USER_LIMIT as SEGMENT_USER_LIMIT,
)
from web_backend.task_contracts import (
    WAITING_SEGMENT_STATUSES as WAITING_SEGMENT_STATUSES,
)
from web_backend.task_contracts import (
    TaskPlanConflict as TaskPlanConflict,
)
from web_backend.task_contracts import (
    TaskResultPublishConflict as TaskResultPublishConflict,
)
from web_backend.task_contracts import (
    TaskRevisionConflict as TaskRevisionConflict,
)
from web_backend.task_creation import TaskCreationMixin
from web_backend.task_lifecycle import TaskLifecycleMixin
from web_backend.task_plan_service import TaskPlanService
from web_backend.task_queries import TaskQueriesMixin
from web_backend.task_replan import TaskReplanMixin
from web_backend.task_result_publish import TaskResultPublishMixin
from web_backend.task_segment_operations import TaskSegmentOperationsMixin


class TaskService(
    TaskReplanMixin,
    TaskSegmentOperationsMixin,
    TaskResultPublishMixin,
    TaskCreationMixin,
    TaskLifecycleMixin,
    TaskQueriesMixin,
):
    def __init__(
        self,
        database: Database,
        plan_service: TaskPlanService | None = None,
        result_publisher: Callable[[str, str], dict[str, Any]] | None = None,
    ) -> None:
        self.database = database
        self.plan_service = plan_service or TaskPlanService(database)
        self.result_publisher = result_publisher

    def preflight(
        self,
        dataset_version_id: str,
        product_version_id: str,
        store: str | None,
        listing: str | None,
        config_version_id: str | None = None,
        model_policy: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.plan_service.preflight(
            dataset_version_id=dataset_version_id,
            product_version_id=product_version_id,
            store=store,
            listing=listing,
            config_version_id=config_version_id,
            model_policy=model_policy,
        )
