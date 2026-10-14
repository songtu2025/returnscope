from typing import Annotated, Any, Callable

from fastapi import APIRouter, Depends, Query

from web_backend.routers.task_route_support import task_request_errors
from web_backend.task_service import TaskService


def register_task_recycle_routes(
    router: APIRouter, service: TaskService, current_user: Callable[..., dict[str, Any]]
) -> None:
    User = Annotated[dict[str, Any], Depends(current_user)]

    @router.get("/api/tasks/recycle")
    def recycled_listings(
        _user: User,
        q: str = "",
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, ge=1, le=100),
    ) -> dict[str, Any]:
        with task_request_errors():
            return service.recycle.listings(q=q, page=page, page_size=page_size)
