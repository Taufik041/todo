from enum import Enum
from uuid import UUID, uuid4
from datetime import datetime, timezone
from typing import Optional
from sqlmodel import SQLModel, Field


class Priority(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class TodoBase(SQLModel):
    title: str = Field(max_length=200)
    description: Optional[str] = Field(default=None, max_length=500)
    priority: Priority = Field(default=Priority.medium)


class Todo(TodoBase, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    completed: bool = Field(default=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))


class TodoCreate(TodoBase):
    pass


class TodoUpdate(SQLModel):
    title: Optional[str] = Field(default=None, max_length=200)
    description: Optional[str] = Field(default=None, max_length=500)
    priority: Optional[Priority] = None
    completed: Optional[bool] = None


class TodoResponse(TodoBase):
    id: UUID
    completed: bool
    created_at: datetime
    updated_at: datetime
