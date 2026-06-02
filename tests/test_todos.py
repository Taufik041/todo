from httpx import AsyncClient


async def test_health(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_create_todo(client: AsyncClient):
    resp = await client.post("/todos", json={"title": "Buy milk", "priority": "high"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "Buy milk"
    assert data["priority"] == "high"
    assert data["completed"] is False
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data


async def test_create_todo_missing_title(client: AsyncClient):
    resp = await client.post("/todos", json={"priority": "low"})
    assert resp.status_code == 422


async def test_list_todos(client: AsyncClient):
    await client.post("/todos", json={"title": "First"})
    await client.post("/todos", json={"title": "Second"})
    resp = await client.get("/todos")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


async def test_get_todo(client: AsyncClient):
    created = await client.post("/todos", json={"title": "Read book"})
    todo_id = created.json()["id"]
    resp = await client.get(f"/todos/{todo_id}")
    assert resp.status_code == 200
    assert resp.json()["title"] == "Read book"


async def test_get_todo_not_found(client: AsyncClient):
    resp = await client.get("/todos/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


async def test_update_todo(client: AsyncClient):
    created = await client.post("/todos", json={"title": "Exercise"})
    todo_id = created.json()["id"]
    resp = await client.put(f"/todos/{todo_id}", json={"completed": True})
    assert resp.status_code == 200
    assert resp.json()["completed"] is True


async def test_update_todo_not_found(client: AsyncClient):
    resp = await client.put(
        "/todos/00000000-0000-0000-0000-000000000000", json={"completed": True}
    )
    assert resp.status_code == 404


async def test_delete_todo(client: AsyncClient):
    created = await client.post("/todos", json={"title": "Clean desk"})
    todo_id = created.json()["id"]
    resp = await client.delete(f"/todos/{todo_id}")
    assert resp.status_code == 204
    assert (await client.get(f"/todos/{todo_id}")).status_code == 404


async def test_delete_todo_not_found(client: AsyncClient):
    resp = await client.delete("/todos/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


async def test_priority_values(client: AsyncClient):
    for priority in ("low", "medium", "high"):
        resp = await client.post(
            "/todos", json={"title": f"Todo {priority}", "priority": priority}
        )
        assert resp.status_code == 201
        assert resp.json()["priority"] == priority


async def test_list_todos_order(client: AsyncClient):
    await client.post("/todos", json={"title": "Older"})
    await client.post("/todos", json={"title": "Newer"})
    resp = await client.get("/todos")
    assert resp.status_code == 200
    items = resp.json()
    titles = [item["title"] for item in items]
    assert titles.index("Newer") < titles.index("Older")
