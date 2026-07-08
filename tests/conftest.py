import os
from unittest.mock import AsyncMock, patch

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
os.environ.setdefault("JWT_SECRET", "test-secret-0123456789abcdef0123456789abcdef")

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel

from api.database import get_session
from api.main import app

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def anon_client():
    test_engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    test_session_factory = sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )

    # ASGITransport does not trigger the ASGI lifespan, so create tables manually.
    # StaticPool ensures every session checkout reuses this same connection.
    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async def override_get_session():
        async with test_session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session

    with (
        patch("api.main.create_tables", new_callable=AsyncMock),
        patch("api.rabbitmq.publish_event", new_callable=AsyncMock),
        patch("api.rabbitmq.close", new_callable=AsyncMock),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac

    app.dependency_overrides.clear()

    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
    await test_engine.dispose()


@pytest_asyncio.fixture
async def client(anon_client):
    """An AsyncClient already authenticated as test@example.com.

    Registering sets the access_token cookie on the client's cookie jar,
    so subsequent requests hit protected routes as this user.
    """
    resp = await anon_client.post(
        "/auth/register",
        json={
            "email": "test@example.com",
            "password": "password123",
            "confirm_password": "password123",
        },
    )
    assert resp.status_code == 201
    return anon_client
