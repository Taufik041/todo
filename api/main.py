import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncGenerator
from uuid import UUID

import redis.asyncio as aioredis
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from api import rabbitmq
from api.database import create_tables, get_session
from api.models import Todo, TodoCreate, TodoResponse, TodoUpdate

logger = logging.getLogger(__name__)

import os

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


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
    try:
        await redis_client.setex(key, CACHE_TTL, value)
    except Exception:
        pass


async def cache_invalidate_todos() -> None:
    if redis_client is None:
        return
    try:
        keys = await redis_client.keys("todo:*")
        if keys:
            await redis_client.delete(*keys)
    except Exception:
        pass


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/todos", response_model=TodoResponse, status_code=201)
async def create_todo(
    payload: TodoCreate,
    session: AsyncSession = Depends(get_session),
) -> Todo:
    todo = Todo(**payload.model_dump())
    session.add(todo)
    await session.commit()
    await session.refresh(todo)
    await cache_invalidate_todos()
    await rabbitmq.publish_event("todo.created", TodoResponse.model_validate(todo).model_dump())
    return todo


@app.get("/todos", response_model=list[TodoResponse])
async def list_todos(session: AsyncSession = Depends(get_session)) -> list[Todo]:
    cache_key = "todo:list"
    cached = await cache_get(cache_key)
    if cached:
        return json.loads(cached)

    result = await session.execute(select(Todo).order_by(Todo.created_at.desc()))
    todos = result.scalars().all()
    serialized = json.dumps(
        [TodoResponse.model_validate(t).model_dump() for t in todos], default=str
    )
    await cache_set(cache_key, serialized)
    return todos


@app.get("/todos/{todo_id}", response_model=TodoResponse)
async def get_todo(todo_id: UUID, session: AsyncSession = Depends(get_session)) -> Todo:
    cache_key = f"todo:{todo_id}"
    cached = await cache_get(cache_key)
    if cached:
        return json.loads(cached)

    todo = await session.get(Todo, todo_id)
    if not todo:
        raise HTTPException(status_code=404, detail="Todo not found")

    await cache_set(cache_key, TodoResponse.model_validate(todo).model_dump_json())
    return todo


@app.put("/todos/{todo_id}", response_model=TodoResponse)
async def update_todo(
    todo_id: UUID,
    payload: TodoUpdate,
    session: AsyncSession = Depends(get_session),
) -> Todo:
    todo = await session.get(Todo, todo_id)
    if not todo:
        raise HTTPException(status_code=404, detail="Todo not found")

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(todo, field, value)
    todo.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

    session.add(todo)
    await session.commit()
    await session.refresh(todo)
    await cache_invalidate_todos()
    await rabbitmq.publish_event("todo.updated", TodoResponse.model_validate(todo).model_dump())
    return todo


@app.delete("/todos/{todo_id}", status_code=204)
async def delete_todo(
    todo_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> None:
    todo = await session.get(Todo, todo_id)
    if not todo:
        raise HTTPException(status_code=404, detail="Todo not found")

    await session.delete(todo)
    await session.commit()
    await cache_invalidate_todos()
    await rabbitmq.publish_event("todo.deleted", {"id": str(todo_id)})
