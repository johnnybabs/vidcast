1# VidCast Infrastructure Audit
**Initial audit:** 2026-06-19 (cluster age 4d19h) — read-only snapshot  
**Updated:** 2026-06-19 — ArgoCD OOMKill fixed, dev sync restored

---

## Summary Table

| Component | Expected (per diagram) | Actual (live) | Match? | Notes |
|-----------|----------------------|---------------|--------|-------|
| **CLUSTER** |||||
| EKS cluster | vidcast-cluster, eu-west-2 | vidcast-cluster, eu-west-2, v1.31.13 | ✅ | 2 nodes, Amazon Linux 2, containerd 1.7.29 |
| Node count | Not specified | 2 nodes (10.0.1.116, 10.0.2.121) | ✅ | Both Ready |
| Namespace | `vidcast` (plan docs) | `default` (live) | ⚠️ | All app workloads in `default`. No `vidcast` namespace exists |
| **TRAFFIC PATH** |||||
| Route 53 | User → Route 53 → ALB | ALB exists; Route 53 not audited | ⚠️ | ALB: `k8s-vidcast-ca0864c28b-1555970207.eu-west-2.elb.amazonaws.com` |
| ALB / Ingress | ALB → nginx Ingress | ALB via AWS LBC, 3 Ingress resources | ✅ | `vidcast.online`, `grafana.vidcast.online`, `kubecost.vidcast.online` all behind same ALB |
| ACM TLS | HTTPS via ACM | Ingresses show ports 80/443 | ✅ | `aws-load-balancer-tls` secret confirms cert on ALB |
| **APP SERVICES** |||||
| Frontend (React/nginx) | Running | Running — `vidcast-frontend:47c1265` | ✅ | ClusterIP :8080; ECR image |
| Gateway (Flask) | Running | Running — `gateway-service:44329bf` | ⚠️ | At `44329bf`, not `327530e` — cd.yml overwrote it (see Divergences §2) |
| Auth | Diagram labels "Node.js" | Running Flask — `auth-service:44329bf`, 2 replicas | ❌ | **Diagram wrong**: Auth is Python/Flask, not Node.js |
| Converter | Running, KEDA-scaled | 0 replicas (queue empty) | ✅ | Expected — KEDA scales to 0 when RabbitMQ video queue is empty |
| Notification | Running | Running — `notification-service:44329bf`, 2 replicas | ✅ | |
| Outbox Relay | Running | Running — `outbox-relay:65f2f57` | ⚠️ | On older SHA; not in CI build matrix |
| **DATASTORES** |||||
| PostgreSQL | Diagram shows AWS RDS | In-cluster `postgres:16.4-alpine` Deployment | ❌ | **Diagram wrong**: not RDS. In-cluster single pod |
| MongoDB | Diagram shows AWS DocumentDB | In-cluster `mongo:4.2` StatefulSet | ❌ | **Diagram wrong**: not DocumentDB. StatefulSet with EBS PVC |
| Redis | Diagram shows AWS ElastiCache | In-cluster `redis:7.4-alpine` Deployment | ❌ | **Diagram wrong**: not ElastiCache. Plain Deployment, no persistence |
| RabbitMQ | "RabbitMQ Cluster" | `rabbitmq:3-management` StatefulSet, 1 pod | ⚠️ | Single instance, not a cluster |
| **PLATFORM TOOLS** |||||
| Argo CD | Managing GitOps | Running — controller healthy, `vidcast-dev` Synced + Healthy | ✅ | Fixed: was OOMKilling at 512Mi; limit raised to 1Gi. `vidcast-prod` OutOfSync by design (single-cluster conflict — see Divergences §1) |
| Prometheus | Running | Running `prometheus:v3.12.0-distroless` in `monitoring` | ✅ | |
| Grafana | Running | Running `grafana:13.0.2` in `monitoring`, NodePort 30007 + ALB Ingress | ✅ | |
| Kyverno | Running | Running v1.18.1 in `kyverno`, 4 controllers | ✅ | All 7 policies in **Audit** mode — not Enforce |
| KEDA | Running | Running v2.20.1 in `keda` | ✅ | ScaledObject on converter: min 0, max 2, RabbitMQ trigger |
| ESO | Running, syncing from Parameter Store | Running v0.18.2, all 4 ExternalSecrets `SecretSynced` | ✅ | ClusterSecretStore `vidcast-parameter-store` Valid |
| Kubecost | Running | Running v2.8.6 in `kubecost`, ALB Ingress at `kubecost.vidcast.online` | ✅ | |
| Alertmanager | Running | Running `alertmanager:v0.33.0` in `monitoring`, NodePort 30008 | ✅ | |
| Falco | Running | Running v0.44.1, DaemonSet 2/2, Falcosidekick 2/2 | ✅ | Installed 2026-06-18, Helm revision 5 |
| **SECURITY** |||||
| NetworkPolicy | Shown as a component | 20 policies in `default` + 1 in `kyverno` | ✅ | `default-deny-all` present; all expected service policies confirmed |
| Cosign / KMS | Shown in diagram | KMS key `alias/vidcast-cluster-cosign` **Enabled**, ECC_NIST_P256 | ✅ | Key exists and `COSIGN_KMS_KEY_ID` set in GitHub. Signing step not yet in CI |
| Kyverno verify-images | Enforce (planned) | Audit mode | ⚠️ | Intentionally deferred until Cosign signing wired into CI |
| **AWS SERVICES** |||||
| Parameter Store | Syncing secrets | ✅ via ESO | ✅ | 4 secrets syncing |
| ECR | `vidcast-frontend` repo | ✅ `501562869470.dkr.ecr.eu-west-2.amazonaws.com/vidcast-frontend` | ✅ | |
| S3 (backups) | Not in diagram | `vidcast-backups-501562869470` bucket, Terraform-managed | — | Backup CronJobs completing nightly |
| EBS CSI | Not in diagram | Running; manages MongoDB PVC (gp3/Retain) | — | |
| IAM / OIDC | GitHub Actions OIDC | `vidcast-cluster-github-deploy` role, OIDC provider in Terraform state | ✅ | |
| DynamoDB (TF lock) | Not applicable | **Not in Terraform state** — deprecation warning in `terraform output` | ⚠️ | `dynamodb_table` param is deprecated; migrate to `use_lockfile` |
| **CI/CD PIPELINE** |||||
| Gitleaks | CI gate | In ci.yml (Sprint S1.2 live) | ✅ | |
| Checkov | CI gate | In ci.yml, `.checkov.yaml` exists | ✅ | |
| Bandit (SAST) | CI gate | In ci.yml | ✅ | |
| pip-audit (OSV) | CI gate | In ci.yml | ✅ | |
| Grype (SCA) | CI gate | In ci.yml | ✅ | Replaced OWASP DC. `NVD_API_KEY` secret is now stale |
| Trivy (image scan) | CI gate, SHA-pinned | In ci.yml — `aquasecurity/trivy-action@master` | ❌ | **Not SHA-pinned** — only action that missed S1.1 pinning |
| Docker build + push | CI | Pushing to Docker Hub on main | ⚠️ | Matrix: auth, gateway, converter, notification only — `outbox-relay` missing |
| Cosign signing | CI gate (planned) | **Not in CI** | ❌ | Intentionally deferred (S3). KMS key ready, wiring pending |
| Argo CD sync | GitOps pull delivery | cd.yml uses `kubectl set image` directly | ❌ | Old push model still active. Pull model described in GITOPS.md not yet implemented in cd.yml |

---

## Cluster State Detail

### Nodes
```
NAME                                       STATUS  VERSION              INTERNAL-IP   EXTERNAL-IP
ip-10-0-1-116.eu-west-2.compute.internal  Ready   v1.31.13-eks-ecaa3a6  10.0.1.116  13.135.252.35
ip-10-0-2-121.eu-west-2.compute.internal  Ready   v1.31.13-eks-ecaa3a6  10.0.2.121  13.42.32.135
```

### Pods with issues at time of audit
| Pod | Namespace | Status | Restarts | Notes |
|-----|-----------|--------|----------|-------|
| `argocd-application-controller-0` | argocd | ~~CrashLoopBackOff~~ → **Running** | 0 | **Fixed 2026-06-19**: OOMKilled at 512Mi limit. Raised to 1Gi via `helm upgrade argocd --set controller.resources.limits.memory=1Gi` |
| `nettest` | default | Error | 0 | Stale test pod from Falco NetworkPolicy debugging — orphaned |

### All running pods (default namespace)
| Pod | Image | Status |
|-----|-------|--------|
| auth (×2) | `auth-service:44329bf` | Running |
| falco-falcosidekick (×2) | `falcosidekick:2.32.0` | Running |
| falco (×2) | `falco:0.44.1` + `falcoctl:0.13.0` | Running 2/2 |
| frontend | `vidcast-frontend:47c1265` (ECR) | Running |
| gateway | `gateway-service:44329bf` | Running |
| mongodb-0 | `mongo:4.2` | Running |
| notification (×2) | `notification-service:44329bf` | Running |
| outbox-relay | `outbox-relay:65f2f57` | Running |
| postgres-deploy | `postgres:16.4-alpine` | Running |
| rabbitmq-0 | `rabbitmq:3-management` | Running |
| redis | `redis:7.4-alpine` | Running |
| mongo-backup (×3 completed) | — | Completed (CronJob) |
| postgres-backup (×3 completed) | — | Completed (CronJob) |

---

## NetworkPolicy State

**Total:** 21 (20 in `default`, 1 in `kyverno`)

| Policy | Namespace | Selector | What it allows |
|--------|-----------|----------|----------------|
| `default-deny-all` | default | all pods | Blocks all ingress + egress (baseline) |
| `allow-dns-egress` | default | all pods | UDP/TCP :53 to kube-dns |
| `allow-falco-egress` | default | `app.k8s.io/name=falco` | DNS + TCP 443 to 0.0.0.0/0 + TCP 2801 to falcosidekick |
| `allow-falcosidekick` | default | `app.k8s.io/name=falcosidekick` | Ingress :2801 from falco; egress DNS + TCP 443 to 0.0.0.0/0 |
| `allow-monitoring-scrape` | default | `app in (auth,gateway)` | Ingress :8080, :5000 from monitoring ns |
| `allow-monitoring-scrape-consumers` | default | `app in (converter,notification)` | Ingress :9000 from monitoring ns |
| `auth` | default | `app=auth` | Ingress :5000 from gateway; egress :5432 to postgres |
| `backup-egress` | default | `component=backup` | Egress to datastores + AWS |
| `converter` | default | `app=converter` | Egress :5672 rabbitmq, :27017 mongodb, :6379 redis |
| `frontend` | default | `app=frontend` | Ingress :8080 from any; egress :8080 to gateway |
| `gateway` | default | `app=gateway` | Ingress :8080 from any; egress :5000 auth, :27017 mongo, :5672 rabbit, :6379 redis |
| `mongodb-ingress` | default | `app=database` | Ingress :27017 from gateway, converter, outbox-relay, notification |
| `mongodb-ingress-backup` | default | `app=database` | Ingress :27017 from backup pods |
| `notification` | default | `app=notification` | Egress :5672 rabbit, :6379 redis, :27017 mongo, :587 SMTP to 0.0.0.0/0 |
| `outbox-relay` | default | `app=outbox-relay` | Egress :27017 mongo, :5672 rabbit |
| `postgres-ingress` | default | `app=auth-app` | Ingress :5432 from auth |
| `postgres-ingress-backup` | default | `app=auth-app` | Ingress :5432 from backup pods |
| `rabbitmq-ingress` | default | `app=rabbitmq` | Ingress :5672 from gateway/outbox-relay/converter/notification + keda ns; :15692 from monitoring |
| `redis-ingress` | default | `app=redis` | Ingress :6379 from converter, notification, gateway |
| `allow-kyverno-sigstore-egress` | kyverno | all kyverno pods | DNS + TCP 443 to 0.0.0.0/0 + TCP 80 to 169.254.169.254/32 (IMDS) |

---

## Helm Releases

| Release | Namespace | Chart | App Version | Revision | Status |
|---------|-----------|-------|-------------|----------|--------|
| argocd | argocd | argo-cd-9.5.21 | v3.4.3 | 2 | deployed |
| aws-load-balancer-controller | kube-system | aws-load-balancer-controller-3.4.0 | v3.4.0 | 1 | deployed |
| external-secrets | external-secrets | external-secrets-0.18.2 | v0.18.2 | 2 | deployed |
| **falco** | default | **falco-9.1.0** | **0.44.1** | **5** | deployed |
| keda | keda | keda-2.20.1 | 2.20.1 | 1 | deployed |
| kubecost | kubecost | cost-analyzer-2.8.6 | 2.8.6 | 2 | deployed |
| kyverno | kyverno | kyverno-3.8.1 | v1.18.1 | 1 | deployed |
| mongodb | default | mongodb-0.1.0 | 1.0.0 | 2 | deployed |
| monitoring | monitoring | kube-prometheus-stack-86.2.3 | v0.91.0 | 2 | deployed |
| postgres | default | postgres-0.1.0 | 1.0.0 | 2 | deployed |
| rabbitmq | default | rabbitmq-0.1.0 | 1.0.1 | 2 | deployed |

---

## Falco Detail

- **DaemonSet:** 2 desired, 2 ready, 2 available
- **Falcosidekick:** 2 replicas, both Running
- **Alerting target:** Slack via `falco-slack-secret` (key: `SLACK_WEBHOOKURL`)
- **Active secret:** `falco-slack-secret` — referenced in `falco-values.yaml` via `existingSecret`
- **Stale secret:** `falco-slack-webhook` — exists in cluster, not referenced by Falco

---

## Kyverno Detail

**7 ClusterPolicies, all Audit:**

| Policy | Mode | Background | Ready |
|--------|------|------------|-------|
| disallow-latest-tag | Audit | true | True |
| disallow-privileged | Audit | true | True |
| require-labels | Audit | true | True |
| require-non-root | Audit | true | True |
| require-requests-limits | Audit | true | True |
| require-seccomp-runtime-default | Audit | true | True |
| verify-images | Audit | **false** | True |

**Policy reports:** 24 (violations being tracked in audit mode)

---

## KEDA Detail

**ScaledObject: `converter-scaler`**
- Target: `Deployment/converter`
- Min replicas: 0 — Max replicas: 2
- Trigger: RabbitMQ queue `video`, protocol amqp, queue-length threshold 5
- Auth: `keda-rabbitmq-auth`
- Poll interval: 15s — Cooldown: 60s
- Current replicas: 0 (queue empty)

**HPA: `gateway-hpa`** (separate from KEDA)
- Target: `Deployment/gateway`
- CPU trigger: 70% threshold
- Min: 1 — Max: 3
- Current: 1 replica, 3% CPU

---

## Argo CD Detail

| App | Sync Status | Health | Auto-sync | Revision |
|-----|-------------|--------|-----------|----------|
| vidcast-dev | **Synced** | **Healthy** | enabled (prune+selfHeal) | 44329bf |
| vidcast-prod | OutOfSync | Healthy | disabled (manual) | 44329bf |

**Controller:** Running, 0 restarts. Memory limit raised from 512Mi → 1Gi (was OOMKilling under load of reconciling two apps simultaneously).

**vidcast-dev Synced:** Auto-sync fired immediately once the controller recovered.

**vidcast-prod OutOfSync:** Expected on this single-cluster setup. `vidcast-dev` auto-sync applies dev overlay values (1 replica, `environment: dev` labels) which diverge from prod overlay values (2 replicas, `environment: prod` labels) on the same Deployments. Syncing prod pushes prod values back; dev auto-sync will overwrite them again within ~3 minutes. This is the documented single-cluster caveat in `docs/GITOPS.md` §5. Sync prod manually with:
```bash
kubectl patch application vidcast-prod -n argocd \
  --type merge \
  -p '{"operation": {"initiatedBy": {"username": "admin"}, "sync": {"revision": "HEAD", "syncStrategy": {"hook": {}}}}}'
```

---

## External Secrets Detail

| ExternalSecret | Store | Refresh | Status |
|----------------|-------|---------|--------|
| auth-secret | vidcast-parameter-store | 1h | SecretSynced ✅ |
| converter-secret | vidcast-parameter-store | 1h | SecretSynced ✅ |
| gateway-secret | vidcast-parameter-store | 1h | SecretSynced ✅ |
| notification-secret | vidcast-parameter-store | 1h | SecretSynced ✅ |

**ClusterSecretStore:** `vidcast-parameter-store` — Valid, ReadWrite, backend: AWS Systems Manager Parameter Store

---

## Ingress and Public Exposure

### Ingress resources
| Namespace | Name | Class | Host | Ports |
|-----------|------|-------|------|-------|
| default | vidcast | alb | vidcast.online | 80, 443 |
| kubecost | kubecost | alb | kubecost.vidcast.online | 80, 443 |
| monitoring | grafana | alb | grafana.vidcast.online | 80, 443 |

### NodePort services (reachable directly on node public IPs)
| Service | Namespace | NodePort | Exposed to |
|---------|-----------|----------|------------|
| monitoring-grafana | monitoring | **30007** | 0.0.0.0/0 |
| monitoring-kube-prometheus-alertmanager | monitoring | **30008**, 31758 | 0.0.0.0/0 |

### AWS Security Group: `vidcast-cluster-nodeport-sg` (sg-0965beab0aae5058c)
All rules below allow **0.0.0.0/0**:

| Port | Service |
|------|---------|
| TCP 30002 | (legacy NodePort — no active service on this port) |
| TCP 30003 | (legacy NodePort) |
| TCP 30004 | (legacy NodePort) |
| TCP 30005 | (legacy NodePort) |
| TCP 30006 | (legacy NodePort) |
| TCP 30007 | Grafana |
| TCP 30008 | Alertmanager |

**Note:** Ports 30002–30006 are open in the SG but no NodePort services exist on those ports. All app services are ClusterIP. The SG rules are stale from an earlier phase; only 30007/30008 map to live services.

---

## AWS Infrastructure Detail

### KMS Key (Cosign)
```
KeyId:    9a3707b0-c04c-40e1-983b-89c6e288abc0
Alias:    alias/vidcast-cluster-cosign
State:    Enabled
Usage:    SIGN_VERIFY
Spec:     ECC_NIST_P256
```

### Terraform State (59 resources)
**Modules present in state:**
- `module.cosign` (3 resources — KMS key, alias, key policy) ✅
- `module.ecr` (2 resources — ECR repo + lifecycle policy) ✅
- `module.eks` (7 resources) ✅
- `module.external_secrets` (3 resources) ✅
- `module.github_oidc` (5 resources) ✅
- `module.iam` (7 resources) ✅
- `module.lbc` (4 resources) ✅
- `module.security_groups` (1 resource — nodeport SG) ✅
- `module.storage` (6 resources — S3 + IRSA) ✅
- `module.vpc` (7 resources) ✅

**Not in Terraform state:**
- `module.falco_alerting` — SNS topic + IRSA role code exists in `terraform/modules/falco-alerting/` but was never applied

### Terraform Outputs
```
backup_bucket_name           = vidcast-backups-501562869470
backup_irsa_role_arn         = arn:aws:iam::501562869470:role/vidcast-cluster-backup-irsa
cluster_endpoint             = https://1D5923877E39131D6A80C0F3D01AFC7C.yl4.eu-west-2.eks.amazonaws.com
cluster_name                 = vidcast-cluster
cosign_key_alias             = alias/vidcast-cluster-cosign
cosign_key_arn               = arn:aws:kms:eu-west-2:501562869470:key/9a3707b0-c04c-40e1-983b-89c6e288abc0
cosign_key_id                = 9a3707b0-c04c-40e1-983b-89c6e288abc0
ecr_repository_urls          = { "vidcast-frontend" = "501562869470.dkr.ecr.eu-west-2.amazonaws.com/vidcast-frontend" }
external_secrets_irsa_role   = arn:aws:iam::501562869470:role/vidcast-cluster-external-secrets-irsa
github_actions_role_arn      = arn:aws:iam::501562869470:role/vidcast-cluster-github-deploy
lbc_irsa_role_arn            = arn:aws:iam::501562869470:role/vidcast-cluster-lbc-irsa
node_security_group_id       = sg-0965beab0aae5058c
oidc_provider_arn            = arn:aws:iam::501562869470:oidc-provider/oidc.eks.eu-west-2.amazonaws.com/id/...
vpc_id                       = vpc-01876334e9073551d
public_subnet_ids            = [subnet-042bdbe4eda31a934, subnet-05d8bcb61f572ac9e]
```

---

## CI/CD Pipeline Detail

### ci.yml jobs
1. **lint** — `ruff check src/ --exclude src/frontend`
2. **build-and-scan** (needs: lint, matrix: auth-service, gateway-service, converter-service, notification-service)
   - Docker build
   - Trivy scan (`aquasecurity/trivy-action@master` — ⚠️ not SHA-pinned)
   - Docker Hub push (main branch only)
   - Additional gates from Sprint S1: Gitleaks, Checkov, Bandit, pip-audit, Grype (confirmed live; not shown in truncated grep output)

### cd.yml — old push model (still active)
```yaml
trigger: workflow_run on ci.yml completion (main branch)
action:  kubectl set image deployment/<svc> <svc>=johnbaabalola/<svc>:$SHORT_SHA
```
This runs on every successful CI build and sets images directly — bypassing Argo CD and the GitOps overlay model described in GITOPS.md.

### Action SHA pinning status
| Action | Ref | Pinned? |
|--------|-----|---------|
| `actions/checkout` | `@v4` | ⚠️ tag, not SHA |
| `actions/setup-python` | `@v5` | ⚠️ tag, not SHA |
| `docker/login-action` | `@v3` | ⚠️ tag, not SHA |
| `aws-actions/configure-aws-credentials` | `@v4` | ⚠️ tag, not SHA |
| `aquasecurity/trivy-action` | `@master` | ❌ mutable branch ref |

**Note:** Sprint S1.1 targeted SHA pinning. The audit shows version tags (`@v3`, `@v4`) not commit SHAs. `@master` is the only fully mutable ref.

### GitHub Secrets
| Secret | Last Updated | Notes |
|--------|-------------|-------|
| `AWS_DEPLOY_ROLE_ARN` | 2026-06-02 | cd.yml OIDC auth |
| `AWS_REGION` | 2026-06-02 | |
| `COSIGN_KMS_KEY_ID` | 2026-06-18 | Ready for S3 wiring |
| `DOCKERHUB_TOKEN` | 2026-06-01 | |
| `DOCKERHUB_USERNAME` | 2026-06-01 | |
| `EKS_CLUSTER_NAME` | 2026-06-02 | cd.yml |
| `NVD_API_KEY` | 2026-06-18 | **Stale** — was for OWASP DC, replaced by Grype |

---

## Image Inventory

### Deployments
| Deployment | Image | Registry |
|------------|-------|----------|
| auth | `johnbaabalola/auth-service:44329bf` | Docker Hub |
| gateway | `johnbaabalola/gateway-service:44329bf` | Docker Hub |
| converter | `johnbaabalola/converter-service:44329bf` | Docker Hub |
| notification | `johnbaabalola/notification-service:44329bf` | Docker Hub |
| outbox-relay | `johnbaabalola/outbox-relay:65f2f57` | Docker Hub |
| frontend | `501562869470.dkr.ecr.eu-west-2.amazonaws.com/vidcast-frontend:47c1265` | ECR |
| falco-falcosidekick | `docker.io/falcosecurity/falcosidekick:2.32.0` | Docker Hub |
| postgres-deploy | `postgres:16.4-alpine` | Docker Hub (mutable version tag) |
| redis | `redis:7.4-alpine` | Docker Hub (mutable version tag) |

### StatefulSets
| StatefulSet | Image |
|-------------|-------|
| mongodb | `mongo:4.2` (mutable version tag) |
| rabbitmq | `rabbitmq:3-management` (mutable version tag) |
| prometheus | `quay.io/prometheus/prometheus:v3.12.0-distroless` |
| alertmanager | `quay.io/prometheus/alertmanager:v0.33.0` |

### DaemonSets
| DaemonSet | Images |
|-----------|--------|
| falco | `falcosecurity/falco:0.44.1` + `falcoctl:0.13.0` |
| aws-node | `amazon-k8s-cni:v1.20.5-eksbuild.1` |
| ebs-csi-node | `aws-ebs-csi-driver:v1.61.1` |
| kube-proxy | `602401143452.dkr.ecr.eu-west-2.amazonaws.com/eks/kube-proxy:v1.31.14-eksbuild.9` |

---

## Divergences

### 1. Argo CD application-controller — OOMKill (resolved 2026-06-19)
- **Diagram shows:** Argo CD managing GitOps deployments
- **Was:** `argocd-application-controller-0` OOMKilling repeatedly (exit code 137) at 512Mi memory limit. 23 restarts. Both apps OutOfSync, reconciliation not running
- **Fix applied:** `helm upgrade argocd` raising controller memory limit to 1Gi (request 512Mi). Controller now Running with 0 restarts
- **Current state:** `vidcast-dev` Synced + Healthy. `vidcast-prod` OutOfSync due to single-cluster conflict (see Divergence §2 and §13)
- **Which is correct:** Diagram is now correct — GitOps is operational

### 2. cd.yml uses `kubectl set image`, not overlay bumps
- **Diagram / GITOPS.md shows:** GitOps pull model — Argo CD reconciles from git overlays
- **Live state:** cd.yml triggers on ci.yml completion and runs `kubectl set image` directly
- **Which is correct:** Both are documented — GITOPS.md §6 calls cd.yml the "before" state and names the overlay model the target. cd.yml has not been updated. Both models are simultaneously active, creating conflicts

### 3. Gateway running `44329bf`, not `327530e`
- **Expected (per our last deploy):** `gateway-service:327530e`
- **Live:** `gateway-service:44329bf`
- **Why:** cd.yml ran after the Dashboard.jsx commit (which touched `src/`), rebuilt all services at the new HEAD SHA, and ran `kubectl set image` — overwriting the manually set `327530e`

### 4. Auth service labelled "Node.js" in diagram
- **Diagram:** Auth Service (Node.js)
- **Live:** Python/Flask. `johnbaabalola/auth-service` is a Flask app
- **Which is correct:** Live state. Diagram is wrong

### 5. Datastores are in-cluster, not managed AWS services
- **Diagram:** PostgreSQL → AWS RDS; MongoDB → AWS DocumentDB; Redis → AWS ElastiCache
- **Live:** All three run as in-cluster Kubernetes pods
- **Which is correct:** Live state. The diagram represents the aspirational production architecture; the actual deviation is documented in `MANAGED_SERVICES.md`

### 6. RabbitMQ is a single instance, not a cluster
- **Diagram:** "RabbitMQ Cluster"
- **Live:** Single `rabbitmq-0` StatefulSet pod, no clustering configured
- **Which is correct:** Live state

### 7. Both `falco-slack-secret` and `falco-slack-webhook` exist
- **Active secret:** `falco-slack-secret` — referenced by `falco-values.yaml` via `existingSecret`
- **Stale secret:** `falco-slack-webhook` — exists in cluster, not referenced by anything
- **Which is correct:** `falco-slack-secret` is the live one; `falco-slack-webhook` is orphaned

### 8. Cosign not in CI pipeline despite KMS key existing
- **Diagram:** Cosign shown in Security & Config
- **Live:** KMS key enabled and `COSIGN_KMS_KEY_ID` set in GitHub, but no Cosign step in ci.yml
- **Which is correct:** Both — key is ready, wiring is intentionally deferred (Sprint S3)

### 9. Kyverno in Audit, not Enforce
- **Diagram implies:** Active policy enforcement
- **Live:** All 7 ClusterPolicies are `Audit`. `verify-images` has background scan disabled
- **Which is correct:** Intentional — Audit until Cosign signing is wired (Sprint S3 blocker)

### 10. `outbox-relay` not in CI build matrix
- **Diagram:** Outbox Relay is a first-class service
- **Live:** `outbox-relay:65f2f57` running but NOT in ci.yml's build matrix. New outbox-relay builds do not happen automatically
- **Which is correct:** This is a gap — the service exists but doesn't get rebuilt on code push

### 11. `trivy-action@master` — not SHA-pinned
- **Sprint S1.1 goal:** All GitHub Actions SHA-pinned
- **Live:** `aquasecurity/trivy-action@master` is a mutable branch reference
- **Which is correct:** This is a gap in S1.1 coverage

### 12. `NVD_API_KEY` GitHub secret is stale
- **Was needed for:** OWASP Dependency-Check (replaced by Grype in S1.7)
- **Live:** Present in GitHub secrets but Grype does not use an NVD API key
- **Which is correct:** Secret is harmless dead weight

### 13. vidcast-prod OutOfSync due to single-cluster conflict
- **GITOPS.md:** dev auto-syncs; prod is manual
- **Live:** `vidcast-dev` is Synced + Healthy (auto-sync working after controller OOMKill fix). `vidcast-prod` is OutOfSync because `vidcast-dev` auto-sync continuously applies dev overlay values (1 replica, `environment: dev`) over the same Deployments prod overlay expects (2 replicas, `environment: prod`)
- **Root cause:** Both Argo apps target `default` namespace on the same cluster — documented single-cluster caveat in GITOPS.md §5, not a bug

### 14. NodePort SG rules 30002–30006 are open but no services use them
- **Expected:** NodePorts 30002–30006 are referenced in SG rules
- **Live:** All app services are ClusterIP; the SG rules are leftovers from a prior phase (when services were NodePort). Only 30007 (Grafana) and 30008 (Alertmanager) are active

---

## Stale / Orphaned Resources

| Resource | Type | Namespace | Reason |
|----------|------|-----------|--------|
| `falco-slack-webhook` | Secret | default | Created in a prior session; Falco references `falco-slack-secret` instead |
| `nettest` | Pod (Error) | default | Left over from Falco NetworkPolicy connectivity test (`kubectl run nettest --image=busybox`) |
| `sh.helm.release.v1.falco.v1` through `.v4` | Secrets | default | Superseded Helm release history; v5 is live. Normal Helm behaviour but worth noting (5 revisions) |
| `NVD_API_KEY` | GitHub Secret | — | Was for OWASP DC (S1.7); replaced by Grype; no workflow references it |
| `terraform/modules/falco-alerting/` | Terraform module | — | SNS alerting code; never applied; not in Terraform state; dead code |
| SG rules for TCP 30002–30006 | AWS Security Group (sg-0965beab0aae5058c) | — | No NodePort services on those ports; rules are stale from a prior phase |

---

## Missing from Diagram

| Item | Where | Notes |
|------|-------|-------|
| Backup CronJobs (mongo-backup, postgres-backup) | `default` ns | Running nightly, completing successfully; S3 destination and IRSA role in Terraform state |
| S3 bucket (`vidcast-backups-501562869470`) | AWS | Terraform-managed; backup destination |
| EBS CSI driver | `kube-system` | Manages MongoDB's PVC (gp3/Retain); critical for StatefulSet |
| Metrics Server | `kube-system` | Required for gateway-hpa CPU metrics |
| AWS Load Balancer Controller | `kube-system` | Provisions the ALB from Ingress resources; missing from diagram's traffic path |
| `gateway-hpa` | `default` | CPU-based HPA on gateway (1–3 replicas, 70% threshold); distinct from KEDA |
| GitHub Actions OIDC | AWS IAM | `vidcast-cluster-github-deploy` role used by cd.yml; in Terraform state |
| ECR lifecycle policy | AWS ECR | Terraform-managed on `vidcast-frontend` repo |
| Kubecost Grafana | `kubecost` ns | Separate Grafana instance (`grafana:12.3.1`) inside Kubecost; distinct from monitoring-stack Grafana (`grafana:13.0.2`) |
| `allow-kyverno-sigstore-egress` NetworkPolicy | `kyverno` ns | Allows Kyverno to reach Sigstore/fulcio/rekor for image verification |
| `allow-falco-egress` + `allow-falcosidekick` NetworkPolicies | `default` | Added to allow Falco to pull rules from ghcr.io and post to Slack |
| `argocd-application-controller` crash | `argocd` | Not a component you'd diagram normally, but its crashed state is the most impactful operational fact right now |
