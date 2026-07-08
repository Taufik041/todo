import contextlib
import json
import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import UUID

import jwt
import redis.asyncio as aioredis
from fastapi import Cookie, Depends, FastAPI, HTTPException, Response, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from api import rabbitmq
from api.database import create_tables, get_session
from api.models import (
    LoginRequest,
    RegisterRequest,
    Todo,
    TodoCreate,
    TodoResponse,
    TodoUpdate,
    User,
    UserCreatedEvent,
)
from api.security import (
    create_token,
    decode_token,
    hash_password,
    verify_password,
)

logger = logging.getLogger(__name__)

REDIS_URL = os.environ["REDIS_URL"]
CACHE_TTL = 300  # 5 minutes

redis_client: aioredis.Redis | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    global redis_client
    await create_tables()
    try:
        redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)
        await redis_client.ping()
    except Exception as exc:
        logger.warning("Redis unavailable: %s", exc)
        redis_client = None
    yield
    if redis_client:
        await redis_client.aclose()
    await rabbitmq.close()


app = FastAPI(title="Todo API", lifespan=lifespan)


async def cache_get(key: str) -> str | None:
    if redis_client is None:
        return None
    try:
        return await redis_client.get(key)
    except Exception:
        return None


async def cache_set(key: str, value: str) -> None:
    if redis_client is None:
        return
    with contextlib.suppress(Exception):
        await redis_client.setex(key, CACHE_TTL, value)


async def cache_invalidate_todos(user_id: UUID) -> None:
    if redis_client is None:
        return
    try:
        keys = await redis_client.keys(f"todos:{user_id}:*")
        if keys:
            await redis_client.delete(*keys)
    except Exception:
        pass


async def get_current_user(
    access_token: str | None = Cookie(default=None),
    session: AsyncSession = Depends(get_session),
) -> User:
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        )

    try:
        payload = decode_token(access_token)
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Credentials"
        ) from None

    result = await session.execute(select(User).where(User.id == UUID(payload["sub"])))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found"
        )
    return user


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/auth/me")
async def me(user: User = Depends(get_current_user)) -> dict:
    return {"id": user.id, "email": user.email}


@app.post("/auth/login", status_code=status.HTTP_200_OK)
async def login(
    body: LoginRequest, response: Response, session: AsyncSession = Depends(get_session)
) -> dict:
    result = await session.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Credentials"
        )

    token = create_token(user_id=user.id, email=user.email)
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=60 * 60 * 24,
    )
    return {"message": "logged in"}


@app.post("/auth/register", status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> dict:
    if body.password != body.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Passwords don't match"
        )

    user_data = await session.execute(select(User).where(User.email == body.email))
    user = user_data.scalar_one_or_none()

    if user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email is already registered"
        )

    new_user = User(email=body.email, password_hash=hash_password(body.password))
    session.add(new_user)
    await session.commit()
    await session.refresh(new_user)
    event_data = UserCreatedEvent.model_validate(new_user).model_dump(mode="json")
    await rabbitmq.publish_event("user.created", event_data)

    token = create_token(user_id=new_user.id, email=new_user.email)
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=60 * 60 * 24,
    )
    return {"message": "Registered successfully!!"}


@app.post("/auth/logout", status_code=status.HTTP_200_OK)
async def logout(response: Response) -> dict:
    response.delete_cookie(key="access_token")
    return {"message": "Logged out successfully."}


@app.post("/todos", response_model=TodoResponse, status_code=status.HTTP_201_CREATED)
async def create_todo(
    payload: TodoCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Todo:
    todo = Todo(**payload.model_dump(), owner_id=user.id)
    session.add(todo)
    await session.commit()
    await session.refresh(todo)
    await cache_invalidate_todos(user_id=user.id)
    event_data = TodoResponse.model_validate(todo).model_dump(mode="json")
    await rabbitmq.publish_event("todo.created", event_data)
    return todo


@app.get("/todos", response_model=list[TodoResponse])
async def list_todos(
    session: AsyncSession = Depends(get_session), user: User = Depends(get_current_user)
) -> list[Todo]:
    cache_key = f"todos:{user.id}:list"
    cached = await cache_get(cache_key)
    if cached:
        return json.loads(cached)

    result = await session.execute(
        select(Todo).where(Todo.owner_id == user.id).order_by(Todo.created_at.desc())
    )
    todos = result.scalars().all()
    serialized = json.dumps(
        [TodoResponse.model_validate(t).model_dump(mode="json") for t in todos],
        default=str,
    )
    await cache_set(cache_key, serialized)
    return todos


@app.get("/todos/{todo_id}", response_model=TodoResponse)
async def get_todo(
    todo_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Todo:
    cache_key = f"todos:{user.id}:{todo_id}"
    cached = await cache_get(cache_key)
    if cached:
        return json.loads(cached)

    todo = await session.execute(
        select(Todo).where(Todo.id == todo_id, Todo.owner_id == user.id)
    )
    todo = todo.scalar_one_or_none()
    if not todo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Todo not found"
        )

    await cache_set(cache_key, TodoResponse.model_validate(todo).model_dump_json())
    return todo


@app.put("/todos/{todo_id}", response_model=TodoResponse)
async def update_todo(
    todo_id: UUID,
    payload: TodoUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Todo:
    todo = await session.execute(
        select(Todo).where(Todo.id == todo_id, Todo.owner_id == user.id)
    )
    todo = todo.scalar_one_or_none()
    if not todo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Todo not found"
        )

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(todo, field, value)
    todo.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

    session.add(todo)
    await session.commit()
    await session.refresh(todo)
    await cache_invalidate_todos(user_id=user.id)
    event_data = TodoResponse.model_validate(todo).model_dump(mode="json")
    await rabbitmq.publish_event("todo.updated", event_data)
    return todo


@app.delete("/todos/{todo_id}", status_code=204)
async def delete_todo(
    todo_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> None:
    todo = await session.execute(
        select(Todo).where(Todo.id == todo_id, Todo.owner_id == user.id)
    )
    todo = todo.scalar_one_or_none()
    if not todo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Todo not found"
        )

    await session.delete(todo)
    await session.commit()
    await cache_invalidate_todos(user_id=user.id)
    await rabbitmq.publish_event("todo.deleted", {"id": str(todo_id)})
