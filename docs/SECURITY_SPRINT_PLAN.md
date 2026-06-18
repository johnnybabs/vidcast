# VidCast — Security Implementation Sprint Plan
*Synthesised from VIDCAST_SECURITY_EXECUTION_PLAN.md + SENIOR_DEVSECOPS_REVIEW.md*
*Author: John Babalola · Dated: June 2026*

---

## Golden Rule

> **Zero cluster downtime. Nothing that works today breaks.** Every sprint is either
> additive CI/Terraform, additive Kubernetes manifests applied live, or a rolling
> restart that EKS handles without traffic loss. Any item that cannot meet this bar
> is explicitly flagged and deferred to a maintenance window or alternative approach.

---

## Cost Summary (Monthly AWS Costs Added)

| Item | Monthly Cost | Sprint |
|------|-------------|--------|
| GuardDuty (EKS audit logs, 2-node cluster) | ~$3–8 | Sprint 2 |
| CloudTrail (first trail, management events) | Free | Sprint 2 |
| KMS key for cosign signing | $1 | Sprint 2 |
| Falco + Falcosidekick (compute only, open-source) | $0 | Sprint 2 |
| AWS WAF Core Rule Set on ALB | ~$5 + $0.60/million req | Sprint 4 |
| OWASP ZAP baseline scan (one-off CI job, open-source) | $0 | Sprint 4 |
| CloudWatch Logs via Fluent Bit | ~$0.50–2 | Sprint 4 |
| **Total new AWS infrastructure cost** | **~$10–16/month** | — |

| Item | Monthly Cost | Sprint |
|------|-------------|--------|
| Anthropic API — CVE triage agent (~10 CVEs/month) | ~$1–3 | Future |
| Anthropic API — PR description (~30 PRs/month) | ~$1–2 | Future |
| Anthropic API — Runbook drafts (~10 alerts/month) | ~$1–3 | Future |
| Anthropic API — Policy drift + cost correlator | ~$1–5 | Future |
| **Total AI agent API cost (if Future Improvements built)** | **~$5–13/month** | — |

**Total new monthly cost after S1–S4 + S6 (core hardening): ~$10–16/month**
**Total if Future Improvements (AI agents) are also built: ~$15–29/month**

> *One-time engineering cost: ~6–8 working days across S1–S4 + S6 (core hardening sprints).
> No paid tooling licenses required — all tools used (Gitleaks, Checkov, Bandit, pip-audit,
> OWASP Dependency-Check, ratchet, Cosign, Fluent Bit, Falco, Falcosidekick, OWASP ZAP)
> are open-source/free tier.*

---

## Sprint Overview

| Sprint | Theme | Duration | Cluster Offline? | Risk |
|--------|-------|----------|-----------------|------|
| S1 | CI Security Hardening (incl. OWASP Dependency-Check) | 1 day | **No** | Low |
| S2 | NetworkPolicy + AWS Security Baseline + Falco | 1 day | **No** | Low |
| S3 | Supply Chain: Cosign + Kyverno Enforce | 1 day | **No** | Low-Medium |
| S4 | Hardening Extras (Auth, Logging, ALB, WAF, ZAP, Fixes) | 2–3 days | **No** (one item: ⚠️ see §S4.5) | Mixed |
| S6 | Documentation Sprint | 2–3 days | **No** | None |
| — | *Future Improvements: AI Agent Integration (documented, not committed)* | *~1 week if built* | *No* | *Low* |

---

## Sprint S1 — CI Security Hardening

**Branch:** `security/sprint-1-ci-hardening`
**Duration:** 1 working day (2–3 hours Claude Code + 30 min review)
**Cluster offline?** ❌ No — all changes are additive CI steps only. Zero infrastructure touched.
**Monthly cost added:** $0

### What gets built

#### S1.1 — Pin GitHub Actions to commit SHAs
All `uses:` lines in `.github/workflows/ci.yml` and `cd.yml` are replaced with
40-character commit SHAs using `ratchet pin`. Current state has `@master` on
`aquasecurity/trivy-action` — the highest-risk unfixed reference.

```
Before: uses: aquasecurity/trivy-action@master
After:  uses: aquasecurity/trivy-action@915b19bbe73b92a6cf82a1bc12b087c9a19a5fe  # 0.28.0
```

**Done when:** `grep -r "@v\|@master" .github/` returns empty.

#### S1.2 — Add Gitleaks secret scanning
Added as the first CI job — runs before lint, before build. Fails immediately on
any committed credential pattern (AWS key format, private key headers, etc.).
Full git history scanned on every push (`fetch-depth: 0`).

**Done when:** A test branch with `AKIAIOSFODNN7EXAMPLE` fails at step 1 of CI.

#### S1.3 — Add Checkov IaC scanning
Scans `terraform/` on every PR. Documented skip entries for two accepted risks
(S3 cross-region replication and access logging) with justification in `.checkov.yaml`.

**Done when:** Pipeline runs Checkov and exits 0 on current Terraform. Skipped
checks are documented with justification.

#### S1.4 — Add Bandit SAST
Parallel job alongside lint. Scans `src/` at medium confidence, medium severity
minimum. Exit 1 on any finding at or above threshold.

**Done when:** Bandit exits 0 on clean code. Any new `eval()`, SQL string
interpolation, or hardcoded credential pattern breaks the build.

#### S1.5 — Add pip-audit SCA
Runs per service in the matrix build, before Docker build. Audits each
`requirements.txt` against the OSV vulnerability database.

**Done when:** Each service's dependencies are checked on every push.

#### S1.6 — Add pip-compile pinning
Generate exact-version `requirements.txt` from current floor-pinned specs using
`pip-compile`. All transitive dependencies locked to a specific version. Developers
update via `pip-compile --upgrade`.

**Done when:** No `>=` operators remain in any `requirements.txt`. A supply chain
compromise on a transitive dependency does not silently update on the next build.

#### S1.7 — Add SCA (Post-Build Dependency Scanning)

*Originally specified: OWASP Dependency-Check against NVD.*
*Implemented as: Grype v0.114.0 (substitution rationale below).*

This is not a duplicate of S1.5 — the distinction matters:

| Tool | Database source | Point in pipeline | What it finds |
|------|----------------|------------------|---------------|
| pip-audit (S1.5) | OSV (Google Open Source Vulnerabilities) | Pre-build, source manifest | CVEs against declared `requirements.txt` dependencies |
| Grype (S1.7) | NVD + GHSA + OSV (Anchore pre-built feed) | Post-build, full manifest | CVEs against all pinned deps (including transitive), covering CVEs that appear in NVD or GHSA before OSV syncs them |

Both tools are warranted: they consult different vulnerability databases and scan at
different stages. A CVE that appears in NVD or GHSA before OSV syncs it is caught by
Grype but not pip-audit. Running both closes the gap between manifest-level and
full-database coverage.

**Substitution rationale:** OWASP Dependency-Check (originally specified) populates
its database via live calls to `services.nvd.nist.gov`. During S1.7 verification,
the NVD API returned persistent HTTP 524 timeouts (Cloudflare origin timeout) across
3 CI runs spanning 90 minutes, exhausting retries and blocking the pipeline. This is
an upstream NIST availability problem, not a configuration error. Grype uses a
pre-built database (NVD + GHSA + OSV, synced by Anchore, downloaded as a single
bundle at scan time) — equivalent coverage with no live API dependency. The
substitution was made on 2026-06-18 after the NVD API failure was confirmed as
non-transient. Local baseline verified: **0 CRITICAL / 0 HIGH** across all 5
services with Grype v0.114.0.

Run as an additional matrix build step after pip-audit. Table-format report uploaded
as a CI artefact (`grype-report-{service}`). Failure threshold: CRITICAL findings
block CI (`--fail-on critical`).

**Done when:** Each service's pinned dependency set is checked against the
NVD+GHSA+OSV database on every push. A CRITICAL CVE in any dependency fails the
build. Grype scan completes in ~2 minutes per service (vs 15–25 for DC NVD sync).

**Cluster offline?** ❌ No — CI-only change.
**Monthly cost added:** $0

### S1 Review Gate (human sign-off required before S2)
- [ ] `grep -r "@v\|@master" .github/` returns empty
- [ ] Fake secret string (`AKIAIOSFODNN7EXAMPLE`) fails CI at step 1
- [ ] Checkov clean (or skip entries documented)
- [ ] All four matrix service builds still pass
- [ ] OWASP Dependency-Check report generated for each service with no CRITICAL findings

---

## Sprint S2 — NetworkPolicy Gaps + AWS Security Baseline

**Branch:** `security/sprint-2-netpol-guardduty`
**Duration:** 1 working day (2–3 hours Claude Code + 30 min review)
**Cluster offline?** ❌ No — NetworkPolicy additions are applied live with zero pod
restarts. Terraform adds new AWS resources; nothing existing is modified.
**Monthly cost added:** ~$4–9/month (GuardDuty + KMS key; Falco is compute-only, $0 AWS cost)

### What gets built

#### S2.1 — `allow-gateway-redis-egress` NetworkPolicy
Fixes the silent failure where gateway pods cannot reach Redis port 6379 under
the default-deny policy. Rate limiting currently falls back to per-process
in-memory mode, effectively doubling the allowed rate. This fix makes rate
limits real.

```yaml
# k8s/network-policies/allow-gateway-redis-egress.yaml
# gateway pods → redis:6379 (TCP)
```

**Applied with:** `kubectl apply -f k8s/network-policies/allow-gateway-redis-egress.yaml`
No pods restart. The NetworkPolicy takes effect for new connections immediately.

#### S2.2 — `allow-notification-mongo-egress` NetworkPolicy
Fixes the silent failure where the notification service cannot query MongoDB for
batch email recipient lists. Required for Sprint 5 batch email features to fire.

```yaml
# k8s/network-policies/allow-notification-mongo-egress.yaml
# notification pods → mongodb:27017 (TCP)
```

#### S2.3 — `data-classification` and `cost-centre` tags
Add two missing tags to `terraform/environments/dev/main.tf` `locals.common_tags`:
- `DataClassification = "confidential"`
- `CostCentre        = "engineering"`

`"internal"` was the initial candidate but is not correct for this platform. VidCast
stores end-user PII (email addresses used as login identifiers) and processes third-party
client content (Wavelength Media's law firm and fintech clients upload video files).
`"confidential"` is the tag value that correctly scopes Macie finding sensitivity and
encryption policy enforcement to the data's actual classification. Using `"internal"`
would under-scope controls and produce false negatives in any policy engine that filters
on tag value. This choice is deliberate, not copied from a generic example.

Required for automated policy engines (Macie, encryption enforcement) to scope
controls correctly. 15-minute Terraform change.

#### S2.4 — GuardDuty + CloudTrail (Terraform)
Adds `terraform/environments/dev/guardduty.tf`:
- GuardDuty detector with S3 log analysis, EKS audit log analysis, and EBS
  malware scanning enabled
- CloudTrail trail writing to a dedicated S3 bucket, log file validation on,
  single-region (eu-west-2), management events (free for first trail)
- GuardDuty findings wired to SNS → email alert

This closes the account-level threat detection gap. A compromised OIDC token,
unusual S3 API patterns, or EC2 calling a C2 will now generate an automated alert.

**Terraform plan shows:** Only new resources. No modifications to existing EKS,
VPC, IAM, or security group resources.

#### S2.5 — Cosign KMS Key (prerequisite for S3)
Adds `terraform/modules/cosign/main.tf` — a KMS key used for image signing.
Key ARN output is required input to Sprint S3 CI signing step.

**`terraform apply` must complete before S3 begins — this key is a hard dependency.**

#### S2.6 — Falco Runtime Threat Detection (DaemonSet)

**Why this is not redundant with GuardDuty:** GuardDuty monitors AWS API calls and EKS
audit log events — it sees actions taken against the AWS control plane (credential misuse,
unusual S3 API patterns, EKS API server calls). Falco monitors inside-container kernel
syscalls — it sees what a process does after it is already running inside a pod. These are
complementary observation layers that cover different attack surfaces.

A specific risk that nothing else in this plan covers: FFmpeg, used by the converter
service to process untrusted user-uploaded video files, has a documented history of
exploitable vulnerabilities (CVEs in libavcodec, libavformat, etc.). An exploit that
achieves code execution inside the converter container would not generate a GuardDuty
finding — the pod is already running and no AWS API call is made. Falco detects the
resulting shell spawn and unexpected outbound connection within seconds of syscall
execution. This is the FFmpeg-exploit-to-shell scenario the converter's threat profile
specifically warrants covering, and no other control in this plan closes it.

**Deployed as:** DaemonSet via Helm (`falcosecurity/falco`), eBPF driver
(`driver.kind: modern_ebpf`). No kernel module compilation required — the modern eBPF
driver is fully compatible with EKS managed nodes and requires no node drain or restart.
Additive deployment; zero impact on existing pods.

```yaml
# deploy/helm/falco-values.yaml
driver:
  kind: modern_ebpf

falcosidekick:
  enabled: true
  config:
    slack:
      webhookurl: "${SLACK_WEBHOOK_URL}"   # same webhook as GuardDuty SNS alerts
    sns:
      topicarn: "${GUARDDUTY_SNS_ARN}"     # on-call sees AWS + kernel alerts in one channel
```

**Custom rules scoped to VidCast's threat profile:**

```yaml
# deploy/falco/vidcast-rules.yaml
- rule: Shell spawned in VidCast application pod
  desc: A shell was spawned in a converter, gateway, auth, or notification pod
  condition: spawned_process and proc.name in (shell_binaries) and k8s.ns.name = "vidcast"
    and k8s.pod.label.app in (converter, gateway, auth, notification)
  output: "Shell spawned in %k8s.pod.label.app% pod (user=%user.name cmd=%proc.cmdline)"
  priority: CRITICAL
  tags: [vidcast, shell-spawn]

- rule: Unexpected outbound connection from converter
  desc: Converter pod connected to a destination other than MongoDB or RabbitMQ
  condition: outbound and k8s.pod.label.app = converter
    and not fd.sip in (mongodb_ips, rabbitmq_ips)
  output: "Converter unexpected outbound (dest=%fd.sip:%fd.sport cmd=%proc.cmdline)"
  priority: CRITICAL
  tags: [vidcast, exfiltration, converter]

- rule: Write to /etc in application pod
  desc: A process wrote to /etc inside a VidCast application pod
  condition: open_write and fd.name startswith /etc and k8s.ns.name = "vidcast"
  output: "Write to /etc in %k8s.pod.label.app% pod (file=%fd.name cmd=%proc.cmdline)"
  priority: HIGH
  tags: [vidcast, filesystem-modification]
```

Falcosidekick routes alerts to the same Slack webhook and SNS topic used for GuardDuty
findings, so on-call engineers see both AWS-level and kernel-level security events in a
single channel.

**Done when:** A test `kubectl exec -n vidcast deploy/converter -- /bin/sh` triggers a
Falco `CRITICAL` alert visible in Slack within 10 seconds of the command running.

**Cluster offline?** ❌ No — DaemonSet is additive; existing pods are not restarted.
**Monthly cost added:** $0 (compute only; no AWS managed service)

### S2 Review Gate (human sign-off required before S3)
- [ ] `kubectl exec -n vidcast deploy/gateway -- redis-cli -h redis-service ping` → PONG
- [ ] `X-RateLimit-Remaining` header appears in gateway responses
- [ ] `aws guardduty list-detectors` returns detector ID
- [ ] `aws cloudtrail get-trail-status --name vidcast-trail` → `IsLogging: true`
- [ ] `aws kms describe-key --key-id alias/vidcast-cosign-dev` returns key metadata
- [ ] `terraform plan` on existing state shows zero changes after apply
- [ ] Falco DaemonSet running on all nodes (`kubectl get daemonset -n falco` shows DESIRED=AVAILABLE)
- [ ] Test shell-spawn rule fires: `kubectl exec -n vidcast deploy/converter -- /bin/sh` generates a Slack CRITICAL alert within 10 seconds

---

## Sprint S3 — Supply Chain: Cosign Signing + Kyverno Enforce

**Branch:** `security/sprint-3-supply-chain-enforce`
**Duration:** 1 working day (2 hours Claude Code + 30 min review)
**Hard prerequisite:** S1 and S2 must be merged and `terraform apply` must be complete.
**Cluster offline?** ❌ No — but this sprint requires the most care.

> **Why this is safe:** Kyverno is promoted to Enforce in a deliberate sequence:
> (a) verify zero policy violations in Audit first, (b) promote non-image policies
> one at a time, (c) verify a rolling restart succeeds after each, (d) promote
> `verify-images` last, only after images are signed in CI. At no point are all
> pods restarted simultaneously. A rollback is a single `kubectl patch` back to Audit.

**Monthly cost added:** $0 (KMS key was counted in S2)

### What gets built

#### S3.1 — Wire Cosign signing into CI
Added to `ci.yml` after the Docker push step, using the KMS key ARN from S2:

```yaml
- name: Install Cosign
  uses: sigstore/cosign-installer@<SHA>
- name: Sign image with Cosign (KMS)
  run: |
    cosign sign \
      --key awskms:///arn:aws:kms:eu-west-2:501562869470:key/${{ secrets.COSIGN_KMS_KEY_ID }} \
      ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}@${{ steps.build.outputs.digest }}
```

`COSIGN_KMS_KEY_ID` added as a GitHub Actions secret (value from `terraform output`).

**Verify before touching Kyverno:**
```bash
cosign verify \
  --key awskms:///arn:aws:kms:eu-west-2:501562869470:key/<KEY_ID> \
  johnbaabalola/gateway@sha256:<digest>
```
Must return a valid certificate chain. If this step fails, stop — do not proceed
to S3.2.

#### S3.2 — Promote Kyverno from Audit → Enforce

**Mandatory pre-check (do not skip):**
```bash
kubectl get policyreport -A -o json | jq '.items[].results[] | select(.result=="fail")'
```
Must return empty. Any failures must be fixed before promotion.

**Promotion sequence (fixed order):**
1. Promote non-image policies (lower blast radius):
   `disallow-latest-tag`, `disallow-privileged`, `require-non-root`,
   `require-seccomp`, `require-requests-limits`, `require-labels`
2. After each policy: verify `kubectl rollout restart deployment/gateway -n vidcast`
   completes successfully
3. **Pre-step — scope verification (mandatory before promoting `verify-images`):**
   Confirm the policy's `match` block targets only the project's own image registry
   (`johnbaabalola/*` or the project's ECR repo). It must NOT match third-party Helm
   chart images (MongoDB, RabbitMQ, Redis) — those images are unsigned and out of scope
   for this signing initiative. Promoting an unscoped `verify-images` policy will block
   the next MongoDB or RabbitMQ pod restart, a self-inflicted outage of exactly the kind
   the golden rule exists to prevent.

   ```bash
   kubectl get clusterpolicy verify-images -o yaml | grep -A 20 "match:"
   ```

   If the match block is broader than `vidcast` application images, patch it to scope
   to the project namespace or registry before proceeding. Do not promote `verify-images`
   until this is confirmed.
4. Promote `verify-images` last — only after step S3.1 is confirmed working and the
   scope check above passes

**Rollback if anything fails:**
```bash
kubectl patch clusterpolicy <name> --type merge \
  -p '{"spec":{"validationFailureAction":"Audit"}}'
```
Zero downtime rollback. Takes effect immediately.

### S3 Review Gate
- [ ] `kubectl get clusterpolicy` shows all 7 policies `READY: True`, `ACTION: Enforce`
- [ ] `kubectl rollout status deployment/gateway -n vidcast` passes
- [ ] Attempting to deploy an unsigned test image produces admission webhook rejection
- [ ] `kubectl get policyreport -A` shows 0 failures

---

## Sprint S4 — Hardening Extras

**Branch:** `security/sprint-4-hardening-extras`
**Duration:** 2–3 working days
**Cluster offline?** Mostly ❌ No — one item has a ⚠️ caveat (see S4.5).
**Monthly cost added:** ~$5–7/month (WAF + CloudWatch Logs)

### What gets built

#### S4.0 — Apply ALB Ingress + Restrict NodePort Security Group (prerequisite for S4.4)

This closes SENIOR_DEVSECOPS_REVIEW.md finding 2.5 (NodePorts 30002–30008 open to
`0.0.0.0/0`, including Grafana/30007, Alertmanager/30008, and the gateway API/30002).
The ALB Ingress manifest is already written at `k8s/ingress/vidcast-ingress.yaml`.
**This is the prerequisite that S4.4 (WAF) has been silently assuming.**

**Check live state first before any changes:**
```bash
aws ec2 describe-security-groups \
  --filters "Name=tag:Project,Values=vidcast" \
  --query 'SecurityGroups[].IpPermissions[?IpRanges[?CidrIp==`0.0.0.0/0`]].[GroupId,FromPort,ToPort]'
```
Also inspect `terraform/modules/security-groups/main.tf` for the current `cidr_blocks`
value. If the NodePort SG source is already restricted (ALB SG ID or a known CIDR),
this item is a verification step only — no changes required.

**If source is still `0.0.0.0/0` (apply in this order):**
1. Apply the ALB Ingress: `kubectl apply -f k8s/ingress/vidcast-ingress.yaml`
2. Migrate exposed services to ClusterIP in their Kubernetes Service manifests
3. Wait for ALB health checks to confirm traffic is routing correctly before touching
   the security group
4. Retrieve the ALB's security group ID:
   ```bash
   aws elbv2 describe-load-balancers \
     --query 'LoadBalancers[?contains(LoadBalancerName,`vidcast`)].SecurityGroups'
   ```
5. Restrict the NodePort SG source from `0.0.0.0/0` to the ALB security group ID —
   identity-based, not address-based, per the framework's network access requirement:
   ```hcl
   # terraform/modules/security-groups/main.tf
   # Replace: cidr_blocks = ["0.0.0.0/0"]
   # With:
   source_security_group_id = aws_security_group.alb.id
   ```
   Apply: `terraform apply -target=module.security_groups`

**Done when:** `aws ec2 describe-security-groups` shows no `0.0.0.0/0` source on ports
30002, 30007, or 30008. ALB health checks pass. Application traffic routes through ALB.

**Cluster offline?** ❌ No — ALB is additive. Services continue serving via NodePort
until the SG restriction is applied; apply the SG change only after ALB health checks
confirm traffic is routing correctly through the ALB.
**Monthly cost added:** ALB hourly cost (~$16–20/month) — planned infrastructure cost,
already accounted for in the ALB Ingress work written in earlier sprints.

#### S4.1 — Auth Service Internal API Key (zero trust gap)
The auth service's `/users` and `/users/<email>` admin endpoints have no
authentication check — any in-cluster pod can enumerate users or promote accounts
to admin. Fix: add `INTERNAL_API_KEY` shared secret injected via ESO into gateway
and auth. Auth rejects admin endpoint requests missing this header.

**Applied as:** Rolling restart of gateway + auth deployments. Zero traffic loss
(EKS rolling update, readiness probe gates new pods before old ones are terminated).

#### S4.2 — XFF Rate-Limit Spoofability Fix
nginx currently appends to `X-Forwarded-For` rather than replacing it, allowing
clients to spoof their source IP and cycle fake addresses to evade the 10/min
login rate limit. Fix: add `proxy_set_header X-Forwarded-For $remote_addr;` to
the nginx ConfigMap.

**Applied as:** Rolling restart of the nginx/frontend deployment. Zero downtime.

#### S4.3 — Fluent Bit Log Shipping to CloudWatch
Adds a Fluent Bit DaemonSet to ship all pod stdout (structured JSON) to
CloudWatch Logs. Enables central log querying without `kubectl logs` per pod.
Uses existing node IAM roles with a scoped CloudWatch write policy addition.

**Applied as:** DaemonSet deployment — additive, does not touch existing pods.
Fluent Bit pods start collecting immediately. Zero downtime.

#### S4.4 — WAF on ALB (requires S4.0 complete)
Adds `aws_wafv2_web_acl` with AWS Managed Core Rule Set to the ALB Terraform
module. Association with the ALB is additive — the ALB continues serving traffic
while WAF evaluates requests.

**Hard prerequisite:** S4.0 must be complete and ALB health checks confirmed passing
before this step begins. The ALB ARN is required to create the WAF association, and
the SG must already be restricted (so WAF takes over as the primary traffic filter).

**Cost:** ~$5/month base + $0.60 per million requests.

#### S4.5 — MongoDB Upgrade 4.0.8 → 7.0 ⚠️

> **This is the one item in the security plan that carries downtime risk.**
>
> MongoDB is a single-instance StatefulSet (not a replica set). The current image
> `mongo:4.0.8` is end-of-life (April 2022) and bypasses the Trivy CI gate because
> it is a Helm chart image, not a CI-built image. Upgrading requires sequential
> major version steps: 4.0 → 4.4 → 5.0 → 6.0 → 7.0. Each step involves a pod
> restart.
>
> **Estimated downtime per step:** 30–60 seconds (StatefulSet pod restart).
> **Total estimated downtime:** 4 × 60 seconds = ~4 minutes, spread across 4 steps.
>
> **Golden rule impact:** This item violates the zero-downtime rule.
>
> **Options:**
> 1. **Defer** — accept the EOL risk, document it as a named accepted risk in the
>    threat model. This is the execution plan's recommendation (deferred by design).
> 2. **Maintenance window** — schedule a 10-minute window off-peak, perform all 4
>    version steps with a verified backup restore drill immediately before.
> 3. **Replica set conversion first** — convert to a 3-member replica set, then do
>    a rolling version upgrade with zero downtime. Significant extra work.
>
> **Recommendation:** Defer to a named maintenance window. Do not attempt during
> a no-downtime sprint. Backup drill (mongodump → mongorestore verified) must
> complete first.

#### S4.6 — Pre-commit Hooks + CONTRIBUTING.md
Adds `.pre-commit-config.yaml` with Gitleaks, ruff, and Checkov hooks.
Developers catch secrets and IaC misconfigs before push, not during CI.
No cluster involvement. Zero risk.

#### S4.7 — OWASP ZAP Baseline Scan Against Staging (gated on S4.4)

**Gate condition:** This item does not begin until S4.4 (WAF on ALB) is confirmed
complete and the ALB Ingress is serving live traffic over HTTPS. The staging URL must
be a stable endpoint behind the ALB — not a NodePort.

This converts the open "no pentest, no DAST" gap identified in
SENIOR_DEVSECOPS_REVIEW.md §2.9 into a named, scheduled, low-effort action. A ZAP
baseline scan provides documented evidence of a security test — sufficient to close
the Finding 2.9 gap without requiring a full penetration test engagement.

**Scope:** A ZAP baseline scan (passive analysis — not a full active/attack scan).
Targets:
- `/login` — checks for brute-force protection headers, verifies rate limiting is
  active, confirms no credential disclosure in error responses
- `/upload` — checks for file injection indicators, verifies Content-Type restrictions
- All responses — checks for presence of `Content-Security-Policy`,
  `X-Frame-Options`, and `X-Content-Type-Options` response headers

Missing security headers are a common finding that is low-effort to fix and easy to
evidence in a portfolio review. Addressing them via this scan closes a real gap.

**Run as:** A one-off manually triggered GitHub Actions job targeting the live staging
URL, or a manual `docker run` from a developer machine. Not a recurring scheduled scan.

```yaml
# .github/workflows/zap-baseline.yml (triggered manually via workflow_dispatch)
name: OWASP ZAP Baseline Scan
on:
  workflow_dispatch:
    inputs:
      target_url:
        description: 'Staging HTTPS URL to scan (ALB must be live)'
        required: true

jobs:
  zap-scan:
    runs-on: ubuntu-latest
    steps:
      - name: ZAP Baseline Scan
        uses: zaproxy/action-baseline@<SHA>
        with:
          target: ${{ github.event.inputs.target_url }}
          fail_action: false       # report findings, do not fail CI on first run
          artifact_name: zap-baseline-report
```

**Done when:** ZAP baseline report is generated and committed to
`docs/security/zap-baseline-YYYY-MM.html`. All `X-Frame-Options`,
`X-Content-Type-Options`, and `Content-Security-Policy` findings are either fixed in
the nginx/gateway response headers or documented as accepted risks in
`docs/accepted-risks.yaml`.

**Cluster offline?** ❌ No — scan is external HTTP(S) requests to the live staging
endpoint; it reads responses and does not modify cluster state.
**Monthly cost added:** $0 (ZAP is open-source; CI compute uses existing runners)

### S4 Review Gate
- [ ] S4.0: `aws ec2 describe-security-groups` shows no `0.0.0.0/0` source on ports 30002, 30007, or 30008; ALB health checks passing
- [ ] `kubectl exec -n vidcast deploy/auth -- curl -s -o /dev/null -w "%{http_code}" \
      http://localhost:5000/users` returns 401 without internal key header
- [ ] Sending `X-Forwarded-For: 1.2.3.4` to gateway no longer bypasses rate limit
- [ ] CloudWatch Logs → Log Group `/vidcast/pods` shows structured JSON from all pods
- [ ] WAF association confirmed in AWS console
- [ ] MongoDB upgrade deferred or maintenance window scheduled separately
- [ ] S4.7: ZAP baseline report committed to `docs/security/`; all header findings fixed or documented in `docs/accepted-risks.yaml`

---

## Sprint S5 — AI Agent Integration

> **This sprint has been moved to "Future Improvements — AI-Assisted Operations"**
> (see end of this document). All five component specifications, the Trust Ladder
> table, and the review gate are documented in full there as documented-but-not-committed
> scope.
>
> **Core hardening goal: S1–S4 + S6.** The AI agent layer depends on Prometheus alerts
> and Lambda infrastructure that should be stable and already alerting correctly via
> static runbooks (completed in S6) before an AI-generated layer is added on top.
> Building it before that foundation is solid adds a layer that cannot be properly
> validated. Begin these components only after S1–S4 and S6 are signed off and have
> been running reliably for at least one alert cycle.

---

## Sprint S6 — Documentation Sprint

**Branch:** `security/sprint-6-documentation`
**Duration:** 2–3 working days
**Cluster offline?** ❌ No — documentation only.
**Monthly cost added:** $0

### What gets written

#### S6.1 — `docs/THREAT_MODEL.md`
STRIDE model across all trust boundary crossings:
- browser → nginx
- nginx → gateway
- gateway → auth, gateway → mongodb, gateway → rabbitmq
- converter → mongodb, converter → rabbitmq
- notification → rabbitmq, notification → smtp
- CI → Docker Hub (ECR mirror)
- ESO → AWS SSM

Each crossing maps to: Spoofing / Tampering / Repudiation / Information Disclosure /
Denial of Service / Elevation of Privilege threats, their mitigations, and a named
residual risk entry. Known accepted risks (XFF spoofability, in-cluster trust gap
before S4.1) are named and signed off rather than left implicit.

**This is the most important document missing from the entire security posture.
Without it, controls that exist cannot be verified as complete.**

#### S6.2 — `docs/INCIDENT_RESPONSE.md`
Six-phase plan specific to VidCast's components:
1. **Detection** — GuardDuty + Prometheus alerts, Falco events, CloudTrail anomalies
2. **Triage** — which service, which namespace, blast radius assessment
3. **Containment** — how to revoke the ESO IRSA role; how to isolate a compromised
   namespace with a NetworkPolicy patch (NetworkPolicy is instant, no pod restart)
4. **Eradication** — how to rotate JWT secret with zero downtime; credential rotation
   procedure per secret type
5. **Recovery** — restore from nightly S3 backup; what CloudTrail shows post-incident
6. **Post-incident review** — 5-why template; what gets committed to `docs/runbooks/`

#### S6.3 — `docs/GDPR_DATA_HANDLING.md`
Named compliance document covering:
- Data categories processed (email addresses, video uploads, MP3 conversions)
- Lawful basis (legitimate interest / contract performance)
- Data retention policy (currently: indefinite — document this as accepted risk with
  a 6-month review commitment)
- Right-to-erasure mechanism (manual deletion procedure until automated)
- Named data controller: John Babalola
- EU data residency confirmation: `eu-west-2` (London)

This converts implicit compliance risk into named, accepted, time-bounded risk —
which is professionally stronger than silence.

### S6 Review Gate
- [ ] `docs/THREAT_MODEL.md` covers all 9 trust boundary crossings with STRIDE
- [ ] `docs/INCIDENT_RESPONSE.md` has all 6 phases with VidCast-specific commands
- [ ] `docs/GDPR_DATA_HANDLING.md` names data categories, retention, and the data controller
- [ ] All residual risks in the threat model are referenced in `docs/DECISIONS_MADE.md`

---

## Future Improvements — AI-Assisted Operations

> **Status: Documented but not committed.** These components are specified in enough
> detail to implement, but are held out of the core S1–S4 + S6 hardening sequence
> deliberately. Each agent depends on Prometheus alerts and Lambda infrastructure
> that should be stable and already alerting correctly via static runbooks (S6)
> before an AI-generated layer is added on top. Building the AI layer before that
> foundation is solid adds something that cannot be properly validated.
>
> Begin these only after the core hardening sprints are signed off and have been
> running reliably for at least one full alert cycle.
>
> **If only one component is built before the core sprints are reviewed:** build the
> PR Description Generator (Component 2) first — it has no cluster credentials, no
> infrastructure access, and zero blast radius if a generated description is wrong.
> It is the cleanest demonstration of AI agent value with no risk to the platform.
>
> **The on-call runbook agent (Component 3) should be the first component revisited
> once S1–S4 and S6 are signed off,** given its clear operational payoff and the
> cleanest guardrail story of the five.

**Branch (when built):** `security/future-ai-agents`
**Duration:** ~1 working week (5 components, ~1 day each)
**Cluster offline?** ❌ No — all agents are additive GitHub Actions workflows and
Lambda functions. They read from the cluster but cannot write to it.
**Monthly cost added (if built):** ~$5–13/month (Anthropic API at current PR/alert volume)

> **Design principle:** AI earns trust on low-stakes tasks first. All agents
> are in read/draft mode initially. No agent can merge a PR, modify infrastructure,
> or trigger Argo CD. All AI outputs are labelled `ai-suggested` and require human
> review before action.

### Component 1 — CVE Triage Agent
**Trigger:** Trivy scan fails in CI (CRITICAL or HIGH CVE found)
**What it does:** Researches the CVE via Anthropic API, determines VidCast's
exposure, identifies the minimum patched version, checks for dependency conflicts,
opens a draft PR labelled `ai-suggested/cve-fix` with a structured description.
**File:** `scripts/ai/cve_triage.py` + `.github/workflows/cve-triage.yml`
**Guardrails:** Can only open PRs to `security/` branch prefix. Cannot merge. Cannot
touch `terraform/` or `.github/workflows/`.

**Cost model:** ~$0.01–0.05 per CVE researched. At ~10 CVEs/month: ~$1–3/month.

### Component 2 — PR Description Generator *(lowest risk — build this first)*
**Trigger:** PR opened or updated against `main`
**What it does:** Reads the git diff, identifies affected services and Kyverno
policies, generates a structured PR description (what/why/tests/security relevance/
risk level). Posts as a PR comment from bot account.
**Guardrails:** Reads diff only. No cluster access. No repository write access
beyond the one comment. Posts with `AI-generated — please review` header.

**Cost model:** ~$0.01–0.02 per PR. At ~30 PRs/month: ~$1–2/month.

### Component 3 — On-Call Runbook Generation *(first to build after S1–S4 + S6 signed off)*

This is the component with the clearest immediate operational payoff and the cleanest
guardrail story of the five.

**What it replaces:** The anti-pattern named in SENIOR_DEVSECOPS_REVIEW.md §2.17 —
an on-call engineer reconstructing the relevant runbook from memory during an incident
under pressure. An engineer at 3am reading a raw JSON alert payload and trying to
recall which MongoDB replica or RabbitMQ queue to inspect first is slower and more
error-prone than an engineer reading a structured, alert-specific first-response draft
generated from live pod context. This agent replaces the reconstruction-from-memory
anti-pattern with a starting point that arrives before the engineer opens a terminal.

**What it does NOT replace:** The static runbooks committed in `docs/runbooks/` as
part of S6. Those are the authoritative, pre-validated incident response procedures —
written in advance by the engineer who built the system, not reconstructed under
pressure. The AI-drafted runbook is a first-response aid generated from live alert
context (pod logs, labels, the Prometheus rule definition) — a structured starting
point, not a substitute for the pre-written plan. **The static runbooks in S6 must
exist and be validated before this agent is built.** Adding an AI layer on top of
absent or incorrect runbooks compounds the problem rather than solving it.

**Why held to Future:** This agent requires Prometheus alerts to be configured and
firing correctly, Lambda (or GitHub Actions webhook infrastructure) to be stable, and
the S6 static runbooks to be committed — so the AI-generated draft can be evaluated
against what was pre-agreed. Building it before the foundation is solid produces an
AI assistant with no verified baseline to compare against.

**Trigger:** Prometheus alert fires → Alertmanager webhook → Lambda
**What it does:** Receives alert name and labels, fetches recent pod logs via
read-only `kubectl logs` (scoped IRSA), drafts a runbook with plain-English
explanation, likely causes, diagnostic commands, remediation steps, and escalation
path. Posts to Slack as an on-call notification.
**Guardrails:** Read-only cluster access (`kubectl logs`, `kubectl get` only).
Cannot `kubectl apply`, `kubectl delete`, or `kubectl exec`. Runbook is a Slack
message — never applied automatically.

**Cost model:** ~$0.01–0.05 per alert. At ~10 alerts/month: ~$1–3/month.

### Component 4 — Kyverno Policy Drift Detector
**Trigger:** Scheduled GitHub Actions workflow, daily at 06:00 UTC
**What it does:** Runs `kubectl get policyreport -A` and captures current pod
security contexts, compares against declared policies, classifies discrepancies
as intentional (matches `docs/accepted-risks.yaml`) or misconfiguration drift,
opens corrective PRs for unintentional drift, posts daily GitHub issue summary.
**Guardrails:** Read-only cluster access. Cannot merge PRs. Can only open PRs to
the `security/` branch prefix.

**Cost model:** ~$0.01–0.02 per daily run. At 30 runs/month: ~$0.50–1/month.

### Component 5 — Cost Anomaly Correlator
**Trigger:** Kubecost webhook when namespace cost increases >20% week-over-week
**What it does:** Receives cost spike event, queries deployment history via
GitHub API (what merged in the last 7 days?), correlates with KEDA scale events
and Prometheus CPU/memory metrics, generates a cost anomaly report (responsible
workload, correlating deployment, expected vs suspicious, recommended action).
Posts as Kubecost annotation and GitHub issue.
**Guardrails:** Read-only. Cannot change resource allocations, modify deployments,
or trigger scaling events.

**Cost model:** ~$0.01–0.10 per anomaly event. At ~5 events/month: ~$1–5/month.

### AI Agent Trust Ladder (Expansion Schedule)

| Tier | Agent | Current Authority | Expand When |
|------|-------|------------------|-------------|
| 1 (Week 1) | CVE triage | Opens draft PRs, cannot merge | After 5 accurate CVE assessments |
| 1 (Week 1) | PR description | Posts comments, cannot edit code | After 10 accurate descriptions |
| 2 (Week 2) | Runbook generation | Posts Slack notes, cannot apply anything | After 3 incidents where draft was accurate |
| 2 (Week 2) | Policy drift | Opens corrective PRs, cannot merge | After 5 correct drift classifications |
| 3 (Week 3) | Cost correlator | Posts reports and issues, cannot change resources | After 3 accurate anomaly attributions |
| **Never** | Production sync | — | Compliance control — human only |
| **Never** | IAM policy changes | — | Requires business context |
| **Never** | KMS key operations | — | Irreversible consequences |

### Future AI Review Gate (when built)
- [ ] CVE triage agent opens a labelled draft PR on a test Trivy failure
- [ ] PR description generator posts a structured comment on a test PR
- [ ] Runbook generation posts a Slack message on a test alert firing
- [ ] Policy drift detector runs on schedule and posts a GitHub issue (zero-drift is a valid pass)
- [ ] Cost correlator posts an anomaly report on a test spike event
- [ ] All 5 components' IAM/GitHub App permissions verified as read/draft-only

---

## Full Dependency Graph

```
S1 (CI Hardening: SHA pins, Gitleaks, Checkov, Bandit, pip-audit, OWASP Dependency-Check)
    ↓
S2 (NetworkPolicy + GuardDuty + KMS key + Falco DaemonSet)
    ↓
S3 (Cosign signing + Kyverno Enforce)   ← REQUIRES S1 + S2 complete

S4 (Hardening Extras)                   ← Can run in parallel with S3
    S4.0 (ALB Ingress + NodePort SG)    ← REQUIRED before S4.4
        ↓
    S4.4 (WAF on ALB)                   ← REQUIRED before S4.7
        ↓
    S4.7 (ZAP baseline scan)
    S4.5 (MongoDB upgrade)              = deferred/maintenance window

S6 (Documentation)                      ← Can run in parallel with any sprint

Future Improvements (AI Agents)         ← Documented; begin only after S1–S4 + S6
                                          signed off and running for at least one alert cycle
```

---

## Items Deferred by Design

These items appear in the senior review but are intentionally excluded from this
sprint plan. Each has a documented reason.

| Item | Reason Deferred |
|------|----------------|
| MongoDB 4.0.8 → 7.0 upgrade | Violates zero-downtime rule; single-instance upgrade causes ~4 min downtime; requires maintenance window + backup drill |
| Secret rotation automation | Lambda rotator — out of scope for security sprint; document rotation procedure in threat model as named residual risk |
| GDPR DPIA | DPIA scoped but not completed; named owner is Wavelength Media's data protection lead (fictional client contact); full DPIA review committed within 6 months of go-live |
| Security Hub + AWS Config | Adds ~$2–5/month; assess after GuardDuty proves value for this account size |
| Pentest | Out of scope for portfolio; document as named gap in threat model; ZAP baseline scan (S4.7) provides documented DAST evidence in lieu of full pentest |
| Fluent Bit → Loki integration | CloudWatch path is simpler and uses existing IAM; Loki can replace CloudWatch in a future observability sprint |

---

## The Compliance Checklist — Before + After

| Framework Question | Before | After S1–S4 + S6 |
|-------------------|--------|------------------|
| Can a new engineer deploy safely without asking anyone? | Partial | ✅ Yes — GitOps + runbooks |
| Can on-call diagnose at 3am without SSH? | Partial | ✅ Yes — CloudWatch Logs + static runbooks (S6) |
| Can finance tell what this costs and why? | Yes | ✅ Yes — Kubecost |
| Can security tell who accessed what and when? | Partial | ✅ Yes — CloudTrail + GuardDuty + Falco kernel events |
| Can platform team destroy it cleanly? | Yes | ✅ Yes |
| Can a non-technical stakeholder explain why? | Yes | ✅ Yes |
| Can a compliance officer trace every control to evidence? | No | ✅ Yes — threat model + IR + GDPR docs |
| Can the security engineer show which threats are mitigated? | No | ✅ Yes — THREAT_MODEL.md |
| Can the incident responder contain a breach in 15 minutes? | No | ✅ Yes — INCIDENT_RESPONSE.md + GuardDuty alerts + Falco real-time kernel alerts |
| Has the platform been tested against OWASP Top 10? | No | ✅ Yes — ZAP baseline scan (S4.7) against /login, /upload, and all response headers |

---

*This plan is approved for execution in sprint order. No sprint begins without human
sign-off on the previous sprint's review gate. The golden rule — zero cluster downtime,
nothing that works breaks — governs every implementation decision.*
