# CLAUDE.md

Guide for AI assistants working on this repo.

## What this is

A containerized todo app demonstrating microservice architecture, deployed to AWS EKS via Helm + ArgoCD (GitOps).

## Architecture

```
Browser ──► Frontend (Next.js 15 :3000, same-origin /api/* rewrite proxy)
              └─► API (FastAPI :8000, JWT cookie auth)
                    ├─► PostgreSQL 16   (persistent storage, SQLModel async)
                    ├─► Redis 7         (response cache, 5-min TTL, graceful no-op if down)
                    └─► RabbitMQ 3      (topic exchange "todos", graceful skip if down)
                              └─► Worker (aio-pika consumer, binds todo.*, logs events)
```

- **API** (`api/`): FastAPI + SQLModel (async). JWT auth via httponly `access_token` cookie (24h expiry, HS256, bcrypt password hashing). All `/todos` routes require auth and are owner-scoped (`Todo.owner_id`). Publishes `todo.created` / `todo.updated` / `todo.deleted` / `user.created` events. Redis and RabbitMQ are optional at runtime — failures log a warning and the API keeps working (cache no-ops, publishes skipped).
- **Worker** (`worker/main.py`): consumes from durable queue `todo_worker` bound to `todo.*` on the `todos` topic exchange and logs events. Note: `user.created` has no consumer (worker binds only `todo.*`). Reconnects with exponential backoff (1s → 60s cap).
- **Frontend** (`frontend/`): Next.js 15 App Router, React 19, Tailwind, shadcn/ui. The browser calls same-origin `/api/*`; `next.config.mjs` rewrites proxy that server-side to `process.env.API_URL` (default `http://api:8000`). Built with `output: "standalone"`.
- **Schema management**: `create_tables()` runs `SQLModel.metadata.create_all` on API startup. There are **no migrations** (no Alembic) — schema changes require dropping/recreating or manual ALTERs.

## Repo layout

| Path | Contents |
|------|----------|
| `api/` | FastAPI app: `main.py` (routes, cache, auth deps), `models.py` (SQLModel models), `database.py` (async engine/session), `security.py` (bcrypt + PyJWT), `rabbitmq.py` (publisher) |
| `worker/` | RabbitMQ consumer (`main.py`) |
| `frontend/` | Next.js app: `src/app/` (pages), `src/components/` (todo-form, todo-item, shadcn ui/), `src/lib/api.ts` (API client) |
| `tests/` | pytest suite: `conftest.py` (async client fixture), `test_todos.py` |
| `helm/todo-app/` | Helm chart — **the source of truth for k8s deployment** (ArgoCD syncs this path) |
| `k8s/` | Legacy raw manifests; superseded by the Helm chart, kept for reference |
| `terraform/` | EKS cluster provisioning (VPC, EKS, ArgoCD helm_release) |
| `argocd/` | ArgoCD `Application` definition |
| Root | `Dockerfile.api` / `Dockerfile.worker` / `Dockerfile.frontend`, `docker-compose.yml`, `ruff.toml`, `pytest.ini`, `.pre-commit-config.yaml` |

## API endpoints

| Method | Path | Auth | Success |
|--------|------|------|---------|
| GET | `/health` | no | 200 |
| POST | `/auth/register` | no | 201 (sets cookie, publishes `user.created`) |
| POST | `/auth/login` | no | 200 (sets cookie) |
| POST | `/auth/logout` | no | 200 (clears cookie) |
| GET | `/auth/me` | yes | 200 |
| POST | `/todos` | yes | 201 |
| GET | `/todos` | yes | 200 (newest first, Redis-cached per user) |
| GET | `/todos/{id}` | yes | 200 (Redis-cached) |
| PUT | `/todos/{id}` | yes | 200 |
| DELETE | `/todos/{id}` | yes | 204 |

Models: `Todo` (UUID pk, `title` ≤200, `description` ≤500, `priority` enum low/medium/high, `completed`, `owner_id` FK→user), `User` (UUID pk, unique `email`, `password_hash`). Cache keys: `todos:{user_id}:list` and `todos:{user_id}:{todo_id}`; writes invalidate `todos:{user_id}:*`.

## How config flows

- **Local (docker-compose)**: `.env` at repo root is loaded via `env_file` for api and worker. Compose also injects `API_URL=http://api:8000` into the frontend for the rewrite proxy.
- **Kubernetes (Helm)**: `helm/todo-app/values.yaml` drives everything. ConfigMap `todo-config` holds URLs (`REDIS_URL`, `RABBITMQ_URL`); Secret `todo-secret` holds credentials (`DATABASE_URL`, `POSTGRES_USER`, `POSTGRES_PASSWORD`). API and worker deployments mount both via `envFrom`.
- The **API hard-fails at import** on missing env vars — `os.environ[KEY]` with no default for `DATABASE_URL`, `REDIS_URL`, `RABBITMQ_URL` (per-module) and `JWT_SECRET` (`api/security.py`). The worker is the exception: it uses `os.getenv("RABBITMQ_URL", ...)` with a default.
- Required API env vars: `DATABASE_URL`, `REDIS_URL`, `RABBITMQ_URL`, `JWT_SECRET`.

## Known issues (as of the `auth + terraform` commit)

Auth was added to the API but the rest of the stack has not caught up:

1. **`JWT_SECRET` is missing from the Helm Secret** (`helm/todo-app/templates/secret.yaml`) and from `k8s/` manifests — the API pod will crash on startup in-cluster.
2. **`JWT_SECRET` is missing from `.env.example`** (it is present in local `.env`, which is gitignored).
3. **Frontend has no auth UI** — `src/lib/api.ts` only has todo CRUD; every call will 401 in the browser.
4. Helm sets `NEXT_PUBLIC_API_URL` on the frontend deployment, but the code actually reads `API_URL` (in `next.config.mjs`); the in-cluster default `http://api:8000` is what makes it work.

## Conventions

- **Ruff** (`ruff.toml`): line length 88; rules E, F, W, I, N, UP, B, A, COM, C4, T20, RET, SIM; ignores COM812, B008. Rule B904 means `raise HTTPException(...) from None` (or `from exc`) inside `except` blocks — see `api/main.py` `get_current_user`.
- **Pre-commit**: ruff-check `--fix` + ruff-format (`.pre-commit-config.yaml`).
- **CI**: GitHub Actions run pytest and ruff on every push/PR. No image publishing in CI — Docker Hub images are pushed manually.
- **SQLModel async sessions**: use `await session.execute(select(...))` then `.scalars().all()` or `.scalar_one_or_none()` — **not** `.exec()` (that's the sync SQLModel API and doesn't exist on this AsyncSession setup).
- **Tests** (`pytest.ini`: `asyncio_mode = auto`): in-memory SQLite via `aiosqlite` + `StaticPool`; `httpx.AsyncClient` with `ASGITransport`. ASGITransport does not run the lifespan, so tables are created manually in the fixture and `redis_client` stays `None` (cache helpers no-op — that is how Redis is "mocked"). RabbitMQ `publish_event`/`close` are patched with `AsyncMock`. No real infrastructure needed. `conftest.py` sets `JWT_SECRET` and provides two fixtures: `anon_client` (unauthenticated) and `client` (registered as `test@example.com`, auth cookie already on the jar).
- Timestamps are stored as naive UTC (`datetime.now(timezone.utc).replace(tzinfo=None)`).

## Deployment

- **Images**: Docker Hub `taufik041/todo-api`, `taufik041/todo-worker`, `taufik041/todo-frontend` (all `:latest`), built from the root-level Dockerfiles (build context is repo root).
- **Helm**: chart at `helm/todo-app` (namespace `todo-app`). `values.yaml` sections: `api`, `worker`, `frontend` (image/replicas/port/serviceType/nodePort/resources), `storageClass` (create + name, gp3), `postgres` (creds, storage, storageClassName), `redis`, `rabbitmq`. Services default to `ClusterIP`; `nodePort` is only rendered when `serviceType: NodePort`.
- **GitOps**: `argocd/application.yaml` — ArgoCD watches `main` of `https://github.com/Taufik041/todo.git`, path `helm/todo-app`, with automated sync + `prune` + `selfHeal` (manual `kubectl` edits get reverted). Pushing a new `:latest` image alone does NOT redeploy — the manifest is unchanged, so pods must be restarted.
- **Terraform** (`terraform/`, region `ap-south-1`): VPC with public subnets only (no NAT gateway), EKS 1.31 (`todo-eks`) via terraform-aws-modules/eks ~>20, managed node group of t3.medium (min=max=desired=2) with the EBS CSI driver addon + IAM policy, and ArgoCD installed via `helm_release` (chart 7.7.11). State in S3 bucket `taufik-todo-tfstate`.

See `docs/NOTES.md` for deployment gotchas that have already been solved — read it before touching Helm/Terraform.

## Commands

```bash
# Run the full stack locally (needs .env — copy .env.example and add JWT_SECRET)
docker compose up --build
# API http://localhost:8000, frontend http://localhost:3000, RabbitMQ mgmt http://localhost:15672 (guest/guest)

# Tests (venv at .venv; conftest sets JWT_SECRET and mocks all infra)
pip install -r api/requirements.txt
pytest tests/ -v

# Lint / format
ruff check .
ruff format .

# Local k8s via Kind: build images, `kind load docker-image`, then
helm install todo helm/todo-app/
kubectl port-forward -n todo-app svc/frontend 3000:3000

# EKS provisioning
cd terraform && terraform apply
```
