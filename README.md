# Todo App

A containerized todo application demonstrating microservice architecture with a FastAPI backend, Next.js frontend, and async event-driven worker.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **API** | Python, FastAPI, SQLModel |
| **Database** | PostgreSQL 16 |
| **Cache** | Redis 7 |
| **Message Queue** | RabbitMQ 3 |
| **Worker** | Python, aio-pika |
| **Frontend** | Next.js 15, TypeScript, Tailwind CSS, shadcn/ui |
| **Containers** | Docker, Docker Compose, Docker Hub |
| **Orchestration** | Kubernetes (Kind for local dev) |
| **Packaging** | Helm 3 |

## Architecture

```
Browser → Frontend (Next.js :3000)
            └─► API (FastAPI :8000)
                  ├─► PostgreSQL  (persistent storage)
                  ├─► Redis       (response cache, 5-min TTL)
                  └─► RabbitMQ   (publishes todo.created / updated / deleted)
                            └─► Worker (consumes events, logs them)
```

## Running Locally

### Docker Compose

```bash
docker compose up --build
```

- API: http://localhost:8000
- Frontend: http://localhost:3000
- RabbitMQ management: http://localhost:15672 (guest / guest)

### Kubernetes (Kind)

```bash
# Create cluster
kind create cluster --name todo

# Build and load images
docker build -f Dockerfile.api -t todo-api:latest .
docker build -f Dockerfile.worker -t todo-worker:latest .
docker build -f Dockerfile.frontend -t todo-frontend:latest .

kind load docker-image todo-api:latest --name todo
kind load docker-image todo-worker:latest --name todo
kind load docker-image todo-frontend:latest --name todo

# Deploy
helm install todo helm/todo-app/

# Access services
kubectl port-forward -n todo-app svc/api 8000:8000
kubectl port-forward -n todo-app svc/frontend 3000:3000
kubectl port-forward -n todo-app svc/rabbitmq 15672:15672
```

### Production Deployment

Images are published to Docker Hub. Any server with Kubernetes can deploy the app:

```bash
git clone https://github.com/Taufik041/todo.git
cd todo
helm install todo helm/todo-app/
```

- Frontend: http://\<server-ip\>:30000
- API: http://\<server-ip\>:30001

Docker Hub images:
- taufik041/todo-api
- taufik041/todo-worker
- taufik041/todo-frontend

## API Endpoints

| Method | Path | Description | Success |
|--------|------|-------------|---------|
| `POST` | `/todos` | Create a todo | `201` |
| `GET` | `/todos` | List all todos (newest first) | `200` |
| `GET` | `/todos/{id}` | Get a single todo | `200` |
| `PUT` | `/todos/{id}` | Update a todo | `200` |
| `DELETE` | `/todos/{id}` | Delete a todo | `204` |
| `GET` | `/health` | Health check | `200` |

**Create / Update payload fields:** `title` (string, required), `description` (string, optional), `priority` (`low` / `medium` / `high`), `completed` (bool, update only).

## Running Tests

```bash
pip install -r api/requirements.txt
pytest tests/ -v
```

Tests use an in-memory SQLite database and mock RabbitMQ and Redis — no infrastructure required.

## Linting

```bash
ruff check .
```

Config in `ruff.toml`. Rules: E, F, W, I, N, UP, B, A, COM, C4, T20, RET, SIM.

## Project Structure

```
todo/
├── api/
│   ├── main.py         routes, middleware, cache logic
│   ├── models.py       SQLModel data models
│   ├── database.py     async engine and session factory
│   └── rabbitmq.py     event publishing via aio-pika
├── worker/
│   └── main.py         RabbitMQ consumer, logs events
├── frontend/
│   └── src/
│       ├── app/        Next.js app router pages
│       ├── components/ todo-form, todo-item, shadcn/ui
│       └── lib/        API client, utilities
├── tests/
│   ├── conftest.py     async client fixture, DB/mq overrides
│   └── test_todos.py   endpoint tests
├── helm/todo-app/      Helm chart (values, templates)
├── k8s/                raw Kubernetes manifests
├── docker-compose.yml
├── Dockerfile.api
├── Dockerfile.worker
└── Dockerfile.frontend
```
