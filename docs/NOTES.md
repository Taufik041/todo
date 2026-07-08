# Deployment Notes — solved gotchas

Hard-won fixes that must not be reintroduced. Each one cost real debugging time on EKS.
Read this before changing anything in `helm/`, `terraform/`, or the frontend's API wiring.

## 1. EKS has no default StorageClass (1.30+)

Clusters created on EKS 1.30+ ship **no default StorageClass** (the old `gp2` default is gone), so a bare PVC sits in `Pending` forever and postgres never schedules.

**Fix (in the chart):**
- `helm/todo-app/templates/storageclass.yaml` explicitly creates a `gp3` StorageClass (`provisioner: ebs.csi.aws.com`, `volumeBindingMode: WaitForFirstConsumer`, `allowVolumeExpansion: true`), gated by `.Values.storageClass.create`.
- `templates/postgres.yaml` pins the PVC with `storageClassName: {{ .Values.postgres.storageClassName }}` (default `gp3`) — **in `spec`**, not as an annotation.

Prerequisite: the EBS CSI driver must exist — `terraform/eks.tf` installs the `aws-ebs-csi-driver` cluster addon and attaches `AmazonEBSCSIDriverPolicy` to the node group role. Without either half, PVCs stay `Pending` with no obvious error.

## 2. t3.medium pod limit is ~17 pods per node

Pod density on EKS is capped by ENI/IP limits, not CPU/memory. A t3.medium supports 3 ENIs × 6 IPs = **17 pods max** (incl. system pods: coredns, kube-proxy, aws-node, csi…). One node fills up fast once ArgoCD (+7 pods) and the app (+6 pods) are on it, and pods stick in `Pending` with misleading "Insufficient pods" events.

**Fix:** node group runs `min_size = max_size = desired_size = 2` in `terraform/eks.tf`. Don't drop to 1 node without cutting workloads.

## 3. EKS module ignores `desired_size` on updates

`terraform-aws-modules/eks` deliberately sets `ignore_changes` on `desired_size` (so it doesn't fight cluster-autoscaler). Editing `desired_size` in `eks.tf` and running `terraform apply` **does nothing** to an existing node group.

**Fix:** to actually resize, change `min_size`/`max_size` (which are applied) or scale the node group out-of-band (console / `aws eks update-nodegroup-config`). `desired_size` only matters at creation time.

## 4. Postgres on EBS needs a PGDATA subdirectory

Fresh ext4 EBS volumes contain a `lost+found` directory at the mount root. Postgres `initdb` refuses to initialize a non-empty directory, so the pod crash-loops with "directory exists but is not empty".

**Fix:** `templates/postgres.yaml` sets `PGDATA=/var/lib/postgresql/data/pgdata` while the volume mounts at `/var/lib/postgresql/data` — initdb gets an empty subdirectory. Keep the env var if you touch the postgres template.

## 5. `nodePort` is forbidden on ClusterIP services

Rendering `nodePort:` in a Service spec when `type: ClusterIP` makes the API server reject the manifest — which under ArgoCD shows up as a sync error, not a local helm error.

**Fix:** api and frontend service templates render it conditionally:

```yaml
{{- if eq .Values.api.serviceType "NodePort" }}
nodePort: {{ .Values.api.nodePort }}
{{- end }}
```

Both `serviceType` and `nodePort` stay in `values.yaml` (defaults: ClusterIP; 30001 api / 30000 frontend) so NodePort can be flipped on for clusters without a load balancer.

## 6. Browser-side API URL: in-cluster hostnames don't work

Anything baked into the browser bundle (`NEXT_PUBLIC_*`) executes on the user's machine, where cluster DNS names like `http://api:8000` are meaningless. Pointing the frontend at the API this way works in-cluster and silently breaks for every real user.

**Fix (what the code actually does):** same-origin routing via **Next.js rewrites**, not a browser-visible URL:
- `frontend/src/lib/api.ts` calls relative `/api/*` — same origin, so it works from any browser and cookies stay first-party.
- `frontend/next.config.mjs` rewrites `/api/:path*` → `${API_URL}/:path*`; the proxying happens **server-side** in the Next.js pod, where `http://api:8000` resolves fine. `API_URL` defaults to `http://api:8000` and is set explicitly in `docker-compose.yml`.

The same-origin approach also means no CORS configuration is needed on the API.

⚠️ Leftover wart: `templates/frontend.yaml` still sets `NEXT_PUBLIC_API_URL` from `values.frontend.apiUrl` — the code never reads it (and rewrites read `API_URL` at runtime on the server). It only works today because the rewrite's fallback default happens to match. If the API service name or port ever changes, set `API_URL` in the frontend deployment instead of relying on the fallback. (There is no nginx ingress in this repo; if one is added later for TLS/domains, the rewrite proxy still works behind it.)

## Not yet solved (don't cargo-cult the above as "all green")

- `JWT_SECRET` is required by the API at import time but is **absent from `templates/secret.yaml`** — the api pod will `CrashLoopBackOff` on a fresh deploy until it's added to the `todo-secret` Secret (and to `.env.example` for compose users). See "Known issues" in `CLAUDE.md`.
- ArgoCD `selfHeal: true` reverts manual `kubectl` edits, and `:latest` image pushes don't trigger a rollout by themselves — restart the deployment (`kubectl rollout restart`) after pushing new images.
