from datetime import datetime, timezone
from enum import Enum
from uuid import UUID, uuid4

from pydantic import EmailStr
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

    owner_id: UUID | None = Field(default=None, foreign_key="user.id", index=True)


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


class User(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    email: EmailStr = Field(unique=True, index=True)
    password_hash: str
    created_at: datetime = Field(default_factory=_utc_now)


class LoginRequest(SQLModel):
    email: EmailStr
    password: str


class RegisterRequest(SQLModel):
    email: EmailStr
    password: str
    confirm_password: str


class UserCreatedEvent(SQLModel):
    id: UUID
    email: EmailStr
