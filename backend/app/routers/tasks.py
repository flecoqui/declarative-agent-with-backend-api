from __future__ import annotations

from itertools import count
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from ..auth import get_current_user
from ..models import Task, TaskCreate, TaskList

router = APIRouter(prefix="/tasks", tags=["tasks"])

# Demo in-memory store keyed by user oid. Replace with a real DB in production.
_store: dict[str, dict[int, Task]] = {}
_ids = count(1)


def _user_key(claims: dict[str, Any]) -> str:
    # `oid` is the stable user object id in the tenant.
    return claims.get("oid") or claims.get("sub") or "anonymous"


@router.get("", response_model=TaskList, summary="List the caller's tasks")
def list_tasks(user: dict[str, Any] = Depends(get_current_user)) -> TaskList:
    items = list(_store.get(_user_key(user), {}).values())
    return TaskList(items=items)


@router.post(
    "",
    response_model=Task,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new task",
)
def create_task(
    body: TaskCreate, user: dict[str, Any] = Depends(get_current_user)
) -> Task:
    key = _user_key(user)
    task = Task(id=next(_ids), owner=key, **body.model_dump())
    _store.setdefault(key, {})[task.id] = task
    return task


@router.post(
    "/{task_id}/complete",
    response_model=Task,
    summary="Mark a task as completed",
)
def complete_task(
    task_id: int, user: dict[str, Any] = Depends(get_current_user)
) -> Task:
    bucket = _store.get(_user_key(user), {})
    task = bucket.get(task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    task.done = True
    return task
