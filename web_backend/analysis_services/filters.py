from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class AnalysisFilters:
    start_date: date | None = None
    end_date: date | None = None
    category_a: str | None = None
    category_b: str | None = None
    listing: str | None = None
    sku: str | None = None
    asin: str | None = None
    reason: str | None = None
    status: str | None = None
    problem_code: str | None = None
    claim_relation: str | None = None
    dimension: str = "listing"
    focus_problem: str | None = None
    page: int = 1
    page_size: int = 50
    view: str = "all"
