from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    due: Optional[date] = None


class Task(TaskCreate):
    id: int
    owner: str
    done: bool = False


class TaskList(BaseModel):
    items: list[Task]
