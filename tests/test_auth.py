from httpx import AsyncClient

CREDENTIALS = {
    "email": "alice@example.com",
    "password": "s3cretpass",
    "confirm_password": "s3cretpass",
}


async def test_register_sets_cookie(anon_client: AsyncClient):
    resp = await anon_client.post("/auth/register", json=CREDENTIALS)
    assert resp.status_code == 201
    assert "access_token" in resp.cookies


async def test_register_password_mismatch(anon_client: AsyncClient):
    resp = await anon_client.post(
        "/auth/register", json={**CREDENTIALS, "confirm_password": "different"}
    )
    assert resp.status_code == 400


async def test_register_duplicate_email(anon_client: AsyncClient):
    first = await anon_client.post("/auth/register", json=CREDENTIALS)
    assert first.status_code == 201
    resp = await anon_client.post("/auth/register", json=CREDENTIALS)
    assert resp.status_code == 409


async def test_login(anon_client: AsyncClient):
    await anon_client.post("/auth/register", json=CREDENTIALS)
    anon_client.cookies.clear()
    resp = await anon_client.post(
        "/auth/login",
        json={"email": CREDENTIALS["email"], "password": CREDENTIALS["password"]},
    )
    assert resp.status_code == 200
    assert "access_token" in resp.cookies


async def test_login_wrong_password(anon_client: AsyncClient):
    await anon_client.post("/auth/register", json=CREDENTIALS)
    anon_client.cookies.clear()
    resp = await anon_client.post(
        "/auth/login",
        json={"email": CREDENTIALS["email"], "password": "wrongpass"},
    )
    assert resp.status_code == 401


async def test_login_unknown_email(anon_client: AsyncClient):
    resp = await anon_client.post(
        "/auth/login", json={"email": "nobody@example.com", "password": "whatever"}
    )
    assert resp.status_code == 401


async def test_me(client: AsyncClient):
    resp = await client.get("/auth/me")
    assert resp.status_code == 200
    assert resp.json()["email"] == "test@example.com"


async def test_me_unauthenticated(anon_client: AsyncClient):
    resp = await anon_client.get("/auth/me")
    assert resp.status_code == 401


async def test_logout_clears_cookie(client: AsyncClient):
    resp = await client.post("/auth/logout")
    assert resp.status_code == 200
    assert (await client.get("/auth/me")).status_code == 401


async def test_todos_require_auth(anon_client: AsyncClient):
    assert (await anon_client.get("/todos")).status_code == 401
    assert (await anon_client.post("/todos", json={"title": "nope"})).status_code == 401


async def test_todos_are_owner_scoped(anon_client: AsyncClient):
    await anon_client.post("/auth/register", json=CREDENTIALS)
    created = await anon_client.post("/todos", json={"title": "Alice's todo"})
    todo_id = created.json()["id"]

    anon_client.cookies.clear()
    await anon_client.post(
        "/auth/register",
        json={
            "email": "bob@example.com",
            "password": "s3cretpass",
            "confirm_password": "s3cretpass",
        },
    )
    assert (await anon_client.get(f"/todos/{todo_id}")).status_code == 404
    assert (await anon_client.get("/todos")).json() == []
