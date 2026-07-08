# Todo platform on AWS EKS

A production-style todo application: one `terraform apply` provisions the entire AWS stack, ArgoCD deploys the app from git, secrets are synced from AWS Secrets Manager, and Gateway API routes public traffic.

## Architecture

Terraform provisions a VPC and an EKS 1.31 cluster (2× t3.medium), then installs three platform components via Helm: ArgoCD, External Secrets Operator (ESO), and NGINX Gateway Fabric (plus the Gateway API CRDs). From there everything is GitOps:

- **ArgoCD** watches `helm/todo-app` on the `main` branch of this repo and syncs it into the `todo-app` namespace with automated prune and self-heal. Manual `kubectl` edits get reverted.
- **ESO** reads the `todo/app` secret from AWS Secrets Manager (authenticated via EKS Pod Identity, no static credentials) and materializes it as the `todo-secret` Kubernetes Secret that the API and postgres consume. No credentials live in git.
- **NGINX Gateway Fabric** implements the Gateway API. A `Gateway` (class `nginx`) exposes an AWS load balancer; an `HTTPRoute` sends `/api` to the api service on port 8000 (with a `URLRewrite` filter stripping the `/api` prefix) and everything else (`/`) to the frontend on port 3000.

```mermaid
flowchart TB
    subgraph AWS
        SM[Secrets Manager<br/>todo/app]
        subgraph EKS["EKS cluster (todo-eks)"]
            NGF[NGINX Gateway Fabric<br/>Gateway + HTTPRoute]
            ARGO[ArgoCD]
            ESO[External Secrets Operator]
            subgraph app["namespace: todo-app"]
                FE[Frontend<br/>Next.js :3000]
                API[API<br/>FastAPI :8000]
                PG[(PostgreSQL)]
                RD[(Redis)]
                MQ[RabbitMQ]
                WK[Worker]
                SEC[Secret: todo-secret]
            end
        end
    end
    TF[terraform apply] --> EKS
    TF --> ARGO
    TF --> ESO
    TF --> NGF
    GIT[git push to main<br/>helm/todo-app] --> ARGO
    ARGO --> app
    ESO -->|sync| SM
    ESO --> SEC
    SEC --> API
    SEC --> PG
    USER[Browser] --> NGF
    NGF -->|"/api (prefix stripped)"| API
    NGF -->|"/"| FE
    API --> PG
    API --> RD
    API -->|todo.* events| MQ
    MQ --> WK
```

The app itself: the FastAPI backend stores todos in PostgreSQL, caches reads in Redis, and publishes `todo.created` / `todo.updated` / `todo.deleted` events to a RabbitMQ topic exchange, which a separate worker consumes and logs. Redis and RabbitMQ are optional at runtime — if either is down the API logs a warning and keeps working.

## CI/CD

Every push and pull request runs pytest and ruff. Pull requests that touch a service (`api/`, `worker/`, `frontend/`, or a Dockerfile) also get a Docker build check per service: three path-filtered jobs call a single reusable `workflow_call` workflow (`docker-build.yaml`) with `push: false`, so PR checks receive no registry credentials. Branch protection requires all five checks (pytest, ruff, and the three build checks) before merge. On merge to main, per-service path-filtered workflows call the same reusable workflow with `secrets: inherit`, build and push the changed service's image tagged with the commit SHA, and commit the new tag into `helm/todo-app/values.yaml` — ArgoCD detects the change and deploys it.

```mermaid
flowchart LR
    PR[Pull request] --> CHECKS[pytest + ruff + build checks]
    CHECKS --> MERGE[Merge to main]
    MERGE --> BUILD[Build + push :sha image]
    BUILD --> BUMP[Commit tag to values.yaml]
    BUMP --> ARGO[ArgoCD sync]
```

## Tech stack

| Layer | Technology |
|-------|-----------|
| API | Python, FastAPI, SQLModel (async) |
| Frontend | Next.js 15, React 19, TypeScript, Tailwind CSS, shadcn/ui |
| Database | PostgreSQL 16 |
| Cache | Redis 7 |
| Messaging | RabbitMQ 3 + aio-pika worker |
| Containers | Docker, Docker Compose |
| Orchestration | Kubernetes (AWS EKS 1.31) |
| Packaging | Helm 3 |
| GitOps | ArgoCD |
| Infrastructure | Terraform (VPC, EKS, platform Helm releases) |
| Ingress | Gateway API via NGINX Gateway Fabric |
| Secrets | External Secrets Operator + AWS Secrets Manager |
| CI/CD | GitHub Actions — PRs run pytest, ruff, and credential-free Docker build checks; merges to main build and push the changed service's image tagged with the commit SHA, then CI commits the new tag into `helm/todo-app/values.yaml`, which ArgoCD detects and deploys. Branch protection requires all five checks before merge |

## Features

- Cookie-based JWT auth: httpOnly `access_token` cookie (SameSite=lax, 24h expiry), bcrypt password hashing. Register, login, logout, and session restore in the frontend.
- Per-user todo isolation: every todo query is scoped to the authenticated owner (`owner_id`), so requesting another user's todo ID returns 404 — no IDOR.
- Per-user Redis caching: list and detail reads are cached per user with a 5-minute TTL; any write invalidates that user's keys.
- Event-driven worker: the API publishes `todo.*` events to a topic exchange; the worker consumes them from a durable queue and reconnects with exponential backoff.
- Same-origin API routing: the browser only ever calls `/api/*` on its own origin (via the Gateway in production, via a Next.js rewrite proxy locally), so cookies stay first-party and no CORS config is needed.

## Local development

Copy `.env.example` to `.env` (it includes a placeholder `JWT_SECRET` — fine for local use), then:

```bash
docker compose up --build
```

- Frontend: http://localhost:3000
- API: http://localhost:8000
- RabbitMQ management: http://localhost:15672 (guest / guest)

Tests use in-memory SQLite and mock Redis/RabbitMQ — no infrastructure needed:

```bash
pip install -r api/requirements.txt
pytest tests/ -v
```

Lint and format:

```bash
ruff check .
ruff format .
```

## Deploy to AWS

Run `terraform apply` from a machine with the `aws` CLI and `kubectl` installed — the Gateway API CRD install step shells out to both (`terraform/gateway.tf`).

**One-time per AWS account** — create the S3 bucket for Terraform state (`taufik-todo-tfstate`, referenced in `terraform/providers.tf`):

```bash
aws s3api create-bucket --bucket taufik-todo-tfstate --region ap-south-1 \
  --create-bucket-configuration LocationConstraint=ap-south-1
aws s3api put-bucket-versioning --bucket taufik-todo-tfstate \
  --versioning-configuration Status=Enabled
```

**One-time per AWS account** — create the application secret in Secrets Manager. ESO syncs this into the cluster as `todo-secret`; all four keys are required (replace the placeholder values with real ones, and keep the password inside `DATABASE_URL` in sync with `POSTGRES_PASSWORD`):

```bash
aws secretsmanager create-secret \
  --name todo/app \
  --region ap-south-1 \
  --secret-string '{
    "JWT_SECRET": "REPLACE_WITH_LONG_RANDOM_STRING",
    "POSTGRES_USER": "postgres",
    "POSTGRES_PASSWORD": "REPLACE_WITH_STRONG_PASSWORD",
    "DATABASE_URL": "postgresql+asyncpg://postgres:REPLACE_WITH_STRONG_PASSWORD@postgres:5432/todos"
  }'
```

Then deploy:

```bash
# 1. Provision everything: VPC, EKS, ArgoCD, ESO, NGINX Gateway Fabric (~15 min)
cd terraform && terraform apply

# 2. Point kubectl at the new cluster
aws eks update-kubeconfig --region ap-south-1 --name todo-eks

# 3. Register the app with ArgoCD — it syncs helm/todo-app from main automatically
kubectl apply -f argocd/application.yaml

# 4. Get the public URL (the ADDRESS column, once the load balancer provisions)
kubectl get gateway -n todo-app
```

Open the ADDRESS in a browser — the Gateway routes `/` to the frontend and `/api/*` to the API.

Rollback is a git revert of the CI deploy commit that bumped the image tag in `helm/todo-app/values.yaml`.

## Teardown

```bash
# 1. Delete the app. The resources-finalizer.argocd.argoproj.io finalizer on the
#    Application makes ArgoCD cascade-delete everything it deployed, including
#    the Gateway's load balancer and the postgres PVC/EBS volume.
kubectl delete -f argocd/application.yaml

# 2. Wait until the load balancer is gone before destroying the cluster,
#    otherwise it orphans and blocks VPC deletion:
aws elbv2 describe-load-balancers --region ap-south-1 \
  --query "LoadBalancers[].LoadBalancerName"

# 3. Destroy the infrastructure
cd terraform && terraform destroy
```

After destroy, check for leaked resources:

```bash
# Orphaned EBS volumes — the postgres volume can survive if the CSI controller
# was destroyed mid-delete. Anything "available" in this list costs money:
aws ec2 describe-volumes --region ap-south-1 \
  --filters Name=status,Values=available \
  --query "Volumes[].{ID:VolumeId,Size:Size,Created:CreateTime}"
aws ec2 delete-volume --region ap-south-1 --volume-id vol-xxxxxxxxxxxx

# Leftover load balancers (classic and ALB/NLB):
aws elb describe-load-balancers --region ap-south-1 \
  --query "LoadBalancerDescriptions[].LoadBalancerName"
aws elbv2 describe-load-balancers --region ap-south-1 \
  --query "LoadBalancers[].LoadBalancerName"
```

The `todo/app` secret is intentionally left in place — it costs ~$0.40/month and means the next `terraform apply` needs zero secret setup. If you do want it gone:

```bash
# Schedules deletion with a 30-day recovery window; the name stays locked until then
aws secretsmanager delete-secret --secret-id todo/app --region ap-south-1

# Undo a scheduled deletion
aws secretsmanager restore-secret --secret-id todo/app --region ap-south-1

# Delete immediately, freeing the name (unrecoverable)
aws secretsmanager delete-secret --secret-id todo/app --region ap-south-1 \
  --force-delete-without-recovery
```

## Production notes — real problems solved

Full write-ups in `docs/NOTES.md`; the short version:

- **EKS 1.30+ ships no default StorageClass**, so PVCs pend forever. The chart creates a `gp3` StorageClass explicitly, and Terraform installs the EBS CSI driver addon plus its node IAM policy — both halves are required.
- **t3.medium tops out at ~17 pods per node** (ENI/IP limits, not CPU or memory), and the failure mode is a misleading "Insufficient pods" event. Hence a fixed 2-node group.
- **The EKS Terraform module ignores `desired_size` after creation** (deliberately, to not fight autoscalers). Resize via `min_size`/`max_size` or out-of-band.
- **Postgres crash-loops on a fresh EBS volume** because `lost+found` makes the mount root non-empty and `initdb` refuses it. Fixed by pointing `PGDATA` at a subdirectory of the mount.
- **In-cluster hostnames don't work from the browser**: anything like `http://api:8000` baked into the client bundle breaks for real users. The frontend only calls same-origin `/api/*`, proxied server-side — which also eliminates CORS.
- **Rendering `nodePort` on a ClusterIP service is an API-server error** that surfaces as a confusing ArgoCD sync failure, so the service templates render it conditionally.

## Demo

Video walkthrough: _coming soon_
