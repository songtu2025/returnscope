from __future__ import annotations

from web_backend.classification_unit_semantics import SEMANTIC_SCHEMA
from web_backend.database_schema_config import CONFIG_SCHEMA
from web_backend.database_schema_core import CORE_SCHEMA
from web_backend.database_schema_dashboards import DASHBOARD_SCHEMA
from web_backend.database_schema_operations import OPERATIONS_SCHEMA
from web_backend.database_schema_results import RESULT_SCHEMA
from web_backend.database_schema_tasks import TASK_SCHEMA

SCHEMA = (
    SEMANTIC_SCHEMA
    + CORE_SCHEMA
    + CONFIG_SCHEMA
    + TASK_SCHEMA
    + RESULT_SCHEMA
    + DASHBOARD_SCHEMA
    + OPERATIONS_SCHEMA
)
