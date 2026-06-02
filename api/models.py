from datetime import datetime, timezone
from enum import Enum
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Priority(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class TodoBase(SQLModel):
    title: str = Field(max_length=200)
    description: str | None = Field(default=None, max_length=500)
    priority: Priority = Field(default=Priority.medium)


class Todo(TodoBase, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    completed: bool = Field(default=False)
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)


class TodoCreate(TodoBase):
    pass


class TodoUpdate(SQLModel):
    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=500)
    priority: Priority | None = None
    completed: bool | None = None


class TodoResponse(TodoBase):
    id: UUID
    completed: bool
    created_at: datetime
    updated_at: datetime
