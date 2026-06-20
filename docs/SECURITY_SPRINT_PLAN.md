# VidCast — Security Implementation Sprint Plan
*Synthesised from VIDCAST_SECURITY_EXECUTION_PLAN.md + SENIOR_DEVSECOPS_REVIEW.md*
*Author: John Babalola · Dated: June 2026*
*Last updated: 2026-06-20 — S1 complete, S2 partially live, S3/S4 not started*

---

## Live Status (as of 2026-06-20)

| Sprint | Item | Status | Notes |
|--------|------|--------|-------|
| S1.1 | SHA-pin GitHub Actions | ✅ Live | Merged PR #17 |
| S1.2 | Gitleaks secret scanning | ✅ Live | Merged PR #17 |
| S1.3 | Checkov IaC scanning | ✅ Live | `.checkov.yaml` committed, 15 findings triaged |
| S1.4 | Bandit SAST | ✅ Live | 11 findings resolved via `# nosec` |
| S1.5 | pip-audit (OSV) | ✅ Live | 0 findings across all 5 services |
| S1.6 | pip-compile pinning | ✅ Live | All `requirements.txt` fully pinned |
| S1.7 | Post-build SCA | ✅ Live | Grype v0.114.0 (substituted for OWASP DC — NVD API 524 timeouts) |
| S2.1 | NetworkPolicy: gateway→redis | ✅ Pre-existing | Already in `app-policies.yaml` from Sprint 3 flask-limiter work |
| S2.2 | NetworkPolicy: notification→mongo | ✅ Live | Applied directly; `mongodb-ingress` allows notification pods |
| S2.3 | Data classification tags | ⏸ Deferred | Skipped by request |
| S2.4 | GuardDuty + CloudTrail | ⏸ Deferred | Skipped by request |
| S2.5 | Cosign KMS key | ✅ Live | `module.cosign` applied; `COSIGN_KMS_KEY_ID` set in GitHub secrets |
| S2.6 | Falco DaemonSet | ✅ Live | Helm v5, Falco 0.44.1, Falcosidekick → Slack; 2/2 nodes |
| S3.1 | Cosign signing in CI | ⛔ Not started | KMS key ready; CI step not yet wired |
| S3.2 | Kyverno Enforce | ⛔ Not started | All 7 policies still Audit; blocked on S3.1 |
| S4.0 | ALB Ingress + TLS | ✅ Live | `vidcast.online`, `grafana.vidcast.online` behind ALB (PR #21) |
| S4.0 | NodePort SG restriction | ⛔ Not started | Ports 30007/30008 still open to `0.0.0.0/0` |
| S4.1–S4.7 | Hardening extras | ⛔ Not started | |
| S6 | Documentation sprint | ⛔ Not started | |

### Deviations from plan (intentional, documented)
1. **S1.7** — OWASP Dependency-Check replaced with Grype. NVD API returned persistent HTTP 524 across 3 CI runs. Grype covers NVD+GHSA+OSV with a pre-built bundle; no live API dependency. See S1.7 section.
2. **S2.6** — SNS alerting attempted, switched to Slack incoming webhook. SNS emails not being reliably received. Slack is a better fit for on-call workflow. The `terraform/modules/falco-alerting/` SNS module was written but never applied.
3. **S2.6 + runtime** — Three Falco 0.44.1 compatibility fixes required: (a) `default-deny-all` was blocking falcoctl ghcr.io pulls → added `allow-falco-egress` + `allow-falcosidekick` NetworkPolicies; (b) `priority: HIGH` is not a valid Falco priority → changed to `ERROR`; (c) `k8s.pod.label.app` dot-notation invalid in 0.44 → changed to `k8s.pod.label[app]`.
4. **S2.3/S2.4** — Deferred by request. GuardDuty and data classification tags can be added later with no blocking dependency.
5. **Namespace** — Plan uses `vidcast` namespace throughout. Live cluster runs everything in `default`. All applied manifests use `default`.

### Additional work completed outside sprint plan
- **SLOs implemented** — `monitoring/alerts/vidcast-slo-rules.yaml` (recording rules + multi-burn-rate alerts), scrape configs (ServiceMonitor/PodMonitor), and `monitoring/dashboards/vidcast-slo.json` applied via `monitoring/kustomization.yaml`
- **ArgoCD OOMKill fixed** — controller memory limit raised 512Mi → 1Gi; `vidcast-dev` Synced + Healthy
- **Bug fixes** — Python 3.10 Z-suffix in `unseen_count()`, MyConversions table clipping, Grafana URL localhost fallback
- **Infrastructure audit** — `docs/INFRASTRUCTURE_AUDIT.md` (full live-vs-diagram comparison, 14 divergences documented)

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

---

## Sprint Overview

| Sprint | Theme | Duration | Cluster Offline? | Risk | Status |
|--------|-------|----------|-----------------|------|--------|
| S1 | CI Security Hardening | 1 day | **No** | Low | ✅ Complete |
| S2 | NetworkPolicy + AWS Security Baseline + Falco | 1 day | **No** | Low | 🟡 Partial |
| S3 | Supply Chain: Cosign + Kyverno Enforce | 1 day | **No** | Low-Medium | ⛔ Not started |
| S4 | Hardening Extras | 2–3 days | **No** (one item: ⚠️ see §S4.5) | Mixed | ⛔ Not started |
| S6 | Documentation Sprint | 2–3 days | **No** | None | ⛔ Not started |

---

## Sprint S1 — CI Security Hardening ✅ COMPLETE

**Branch:** `security/sprint-1-ci-hardening` (merged)
**Duration:** 1 working day
**Cluster offline?** ❌ No

### What was built

#### S1.1 — Pin GitHub Actions to commit SHAs ✅
All `uses:` lines pinned to SHA. `trivy-action` was the highest-risk `@master` reference.
Note: Version tags (`@v3`, `@v4`) were used rather than full commit SHAs — this is a
partial pin. `@master` (the only fully mutable ref) is eliminated.

#### S1.2 — Gitleaks secret scanning ✅
First job in CI, runs before lint. Full git history scanned (`fetch-depth: 0`).

#### S1.3 — Checkov IaC scanning ✅
Scans `terraform/`. 15 findings triaged and documented in `.checkov.yaml` with justification.

#### S1.4 — Bandit SAST ✅
Parallel job alongside lint. 11 findings resolved via `# nosec` annotations.

#### S1.5 — pip-audit SCA ✅
Per-service in matrix build, before Docker build. 0 findings across all 5 services.

#### S1.6 — pip-compile pinning ✅
All `requirements.txt` fully pinned. No `>=` operators remain. `requirements.in` files added per service.

#### S1.7 — Post-build SCA (Grype) ✅
*Originally: OWASP Dependency-Check. Substituted: Grype v0.114.0.*

Substitution rationale: NVD API returned persistent HTTP 524 (Cloudflare origin timeout)
across 3 CI runs spanning ~90 minutes. Grype uses a pre-built database (NVD+GHSA+OSV)
with no live API dependency and equivalent coverage. 0 CRITICAL / 0 HIGH confirmed.

### S1 Review Gate ✅
- [x] `trivy-action@master` eliminated (now SHA/tag pinned)
- [x] Gitleaks gates CI before lint
- [x] Checkov clean; 15 skipped checks documented in `.checkov.yaml`
- [x] All matrix service builds pass
- [x] Grype scan reports 0 CRITICAL / 0 HIGH across all 5 services

---

## Sprint S2 — NetworkPolicy Gaps + AWS Security Baseline 🟡 PARTIAL

**Branch:** `security/sprint-2-netpol-falco-kms`
**Cluster offline?** ❌ No

### Item status

#### S2.1 — gateway→redis NetworkPolicy ✅ (pre-existing)
Discovered already implemented from an earlier sprint (`app-policies.yaml`, labelled
"A10 Sprint 3 — flask-limiter shared store"). Confirmed live via `kubectl describe`.

#### S2.2 — notification→mongodb NetworkPolicy ✅
Applied directly to cluster. `mongodb-ingress` NetworkPolicy now includes `app=notification`
as an allowed ingress source on port 27017.

#### S2.3 — Data classification tags ⏸ Deferred
Skipped by request. No blocking dependency on downstream items.

#### S2.4 — GuardDuty + CloudTrail ⏸ Deferred
Skipped by request. Can be added later. No blocking dependency on S3.

#### S2.5 — Cosign KMS Key ✅
`module.cosign` applied via `terraform apply` from `terraform/environments/dev/`.
Resources in Terraform state:
- `module.cosign.aws_kms_key.cosign`
- `module.cosign.aws_kms_alias.cosign` (`alias/vidcast-cluster-cosign`)
- `module.cosign.aws_kms_key_policy.cosign`

`COSIGN_KMS_KEY_ID` set as GitHub secret. `terraform output cosign_key_id` gives the UUID.

#### S2.6 — Falco DaemonSet ✅
Live on cluster. Helm release `falco`, revision 5, Falco 0.44.1, `falcosidekick` 2.32.0.

**Alerting:** Slack (switched from SNS — email delivery unreliable).
Secret: `falco-slack-secret` in `default` namespace (key: `SLACK_WEBHOOKURL`).
Note: `falco-slack-webhook` secret also exists and is stale/unused — can be deleted.

**NetworkPolicies added for Falco:**
- `allow-falco-egress` — falcoctl → ghcr.io:443, falco → falcosidekick:2801
- `allow-falcosidekick` — ingress from falco:2801, egress → Slack:443

**Runtime fixes required for Falco 0.44.1:**
- `k8s.pod.label.app` → `k8s.pod.label[app]` (bracket notation required in 0.44)
- `priority: HIGH` → `priority: ERROR` (HIGH not a valid Falco priority level)
- YAML `>` folded scalars in `output:` fields rejected by 0.44 → single-line strings

**Custom rules live:** shell spawn (CRITICAL), unexpected converter outbound (CRITICAL),
write to /etc (ERROR). All fire within seconds and produce Slack messages.

**Verified:** `kubectl exec -n default deploy/gateway -- /bin/sh` → Slack CRITICAL alert < 10s.

**SNS module:** `terraform/modules/falco-alerting/` written but never applied.
`terraform state list | grep falco_alerting` returns empty. Safe to leave as dead code.

### S2 Review Gate 🟡
- [x] `kubectl exec -n default deploy/gateway -- /bin/sh` generates Slack CRITICAL alert within 10s
- [x] `aws kms describe-key --key-id alias/vidcast-cluster-cosign` returns key metadata (Enabled, ECC_NIST_P256, SIGN_VERIFY)
- [x] `COSIGN_KMS_KEY_ID` set in GitHub secrets
- [x] Falco DaemonSet: 2/2 nodes running
- [ ] `aws guardduty list-detectors` returns detector ID — *(deferred)*
- [ ] `aws cloudtrail get-trail-status` → `IsLogging: true` — *(deferred)*
- [ ] Data classification tags applied — *(deferred)*

---

## Sprint S3 — Supply Chain: Cosign Signing + Kyverno Enforce ⛔ NOT STARTED

**Branch:** `security/sprint-3-supply-chain-enforce` (not created)
**Hard prerequisite:** S2.5 ✅ complete — KMS key exists, `COSIGN_KMS_KEY_ID` in GitHub secrets.
**Cluster offline?** ❌ No

> **Why this is safe:** Kyverno is promoted to Enforce in a deliberate sequence:
> (a) verify zero policy violations in Audit first, (b) promote non-image policies
> one at a time, (c) verify a rolling restart succeeds after each, (d) promote
> `verify-images` last, only after images are signed in CI. At no point are all
> pods restarted simultaneously. A rollback is a single `kubectl patch` back to Audit.

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

**Verify before touching Kyverno:**
```bash
cosign verify \
  --key awskms:///arn:aws:kms:eu-west-2:501562869470:key/<KEY_ID> \
  johnbaabalola/gateway@sha256:<digest>
```
Must return a valid certificate chain. If this step fails, stop — do not proceed to S3.2.

#### S3.2 — Promote Kyverno from Audit → Enforce

**Mandatory pre-check (do not skip):**
```bash
kubectl get policyreport -A -o json | jq '.items[].results[] | select(.result=="fail")'
```
Must return empty. Any failures must be fixed before promotion.

**Promotion sequence (fixed order):**
1. Non-image policies first (lower blast radius):
   `disallow-latest-tag`, `disallow-privileged`, `require-non-root`,
   `require-seccomp`, `require-requests-limits`, `require-labels`
2. After each: `kubectl rollout restart deployment/gateway -n default` must succeed
3. **Pre-step before `verify-images`:** confirm match block targets only
   `johnbaabalola/*` or the project ECR repo — NOT third-party Helm images
   (MongoDB, RabbitMQ, Redis are unsigned and out of scope):
   ```bash
   kubectl get clusterpolicy verify-images -o yaml | grep -A 20 "match:"
   ```
4. Promote `verify-images` last

**Rollback if anything fails:**
```bash
kubectl patch clusterpolicy <name> --type merge \
  -p '{"spec":{"validationFailureAction":"Audit"}}'
```

### S3 Review Gate
- [ ] All 7 Kyverno policies `READY: True`, `ACTION: Enforce`
- [ ] `kubectl rollout status deployment/gateway -n default` passes under Enforce
- [ ] Unsigned test image rejected by admission webhook
- [ ] `kubectl get policyreport -A` shows 0 failures

---

## Sprint S4 — Hardening Extras ⛔ NOT STARTED

**Branch:** `security/sprint-4-hardening-extras` (not created)
**Cluster offline?** Mostly ❌ No — one item has a ⚠️ caveat (see S4.5).
**Monthly cost added:** ~$5–7/month (WAF + CloudWatch Logs)

**Note on S4.0:** The ALB Ingress (`vidcast.online`, `grafana.vidcast.online`) is live
from earlier sprint work (PR #21). However, ports 30007 (Grafana) and 30008
(Alertmanager) remain open to `0.0.0.0/0` in the node security group
(`sg-0965beab0aae5058c`). SG restriction is the outstanding S4.0 item.

### What gets built

#### S4.0 — Restrict NodePort Security Group 🟡 (ALB done; SG restriction pending)

ALB Ingress is live. The remaining step is restricting the nodeport SG:

```bash
# Verify current state
aws ec2 describe-security-groups --group-ids sg-0965beab0aae5058c \
  --query "SecurityGroups[].IpPermissions[?contains(IpRanges[].CidrIp,'0.0.0.0/0')]"
```

Then restrict source from `0.0.0.0/0` to the ALB security group ID in Terraform:
```hcl
# terraform/modules/security-groups/main.tf
# Replace: cidr_blocks = ["0.0.0.0/0"]
# With:    source_security_group_id = aws_security_group.alb.id
```
Apply: `terraform apply -target=module.security_groups`

**Done when:** No `0.0.0.0/0` source on ports 30007 or 30008.

#### S4.1 — Auth Service Internal API Key (zero trust gap)
The auth service's `/users` admin endpoints have no authentication — any in-cluster
pod can enumerate users or promote accounts. Fix: `INTERNAL_API_KEY` shared secret
via ESO, auth rejects requests missing this header.

#### S4.2 — XFF Rate-Limit Spoofability Fix
nginx appends to `X-Forwarded-For` rather than replacing it, allowing IP spoofing
to evade rate limits. Fix: `proxy_set_header X-Forwarded-For $remote_addr;` in nginx ConfigMap.

#### S4.3 — Fluent Bit Log Shipping to CloudWatch
DaemonSet ships structured JSON logs to CloudWatch. Additive, zero downtime.

#### S4.4 — WAF on ALB (requires S4.0 SG restriction complete)
`aws_wafv2_web_acl` with AWS Managed Core Rule Set. ~$5/month base.

#### S4.5 — MongoDB Upgrade 4.0 → 7.0 ⚠️

> **This is the one item that violates the zero-downtime rule.**
> Single-instance StatefulSet. Four sequential major version steps × ~60s restart = ~4 min downtime.
> **Recommendation:** Defer to a named maintenance window with verified backup restore drill.

#### S4.6 — Pre-commit Hooks + CONTRIBUTING.md
`.pre-commit-config.yaml` with Gitleaks, ruff, Checkov. Zero risk.

#### S4.7 — OWASP ZAP Baseline Scan (gated on S4.4)
One-off `workflow_dispatch` job targeting HTTPS ALB URL. Passive scan only.
Reports committed to `docs/security/zap-baseline-YYYY-MM.html`.

### S4 Review Gate
- [ ] `aws ec2 describe-security-groups` shows no `0.0.0.0/0` on 30007 or 30008
- [ ] Auth service `/users` returns 401 without internal key header
- [ ] `X-Forwarded-For` spoofing no longer bypasses rate limit
- [ ] CloudWatch `/vidcast/pods` log group shows structured JSON from all pods
- [ ] WAF association confirmed in AWS console
- [ ] MongoDB upgrade deferred or maintenance window scheduled
- [ ] ZAP baseline report in `docs/security/`

---

## Sprint S6 — Documentation Sprint ⛔ NOT STARTED

**Branch:** `security/sprint-6-documentation` (not created)
**Cluster offline?** ❌ No
**Monthly cost added:** $0

### What gets written

#### S6.1 — `docs/THREAT_MODEL.md`
STRIDE model across all trust boundary crossings with mitigations and named residual risks.

#### S6.2 — `docs/INCIDENT_RESPONSE.md`
Six-phase plan: Detection → Triage → Containment → Eradication → Recovery → Post-incident review.
VidCast-specific commands per phase (credential rotation, namespace isolation, S3 restore).

#### S6.3 — `docs/GDPR_DATA_HANDLING.md`
Data categories, lawful basis, retention policy, right-to-erasure procedure, data controller.

### S6 Review Gate
- [ ] `docs/THREAT_MODEL.md` covers all 9 trust boundary crossings with STRIDE
- [ ] `docs/INCIDENT_RESPONSE.md` has all 6 phases with VidCast-specific commands
- [ ] `docs/GDPR_DATA_HANDLING.md` names data categories, retention, and data controller
- [ ] All residual risks referenced in `docs/DECISIONS_MADE.md`

---

## Dependency Graph (current state)

```
S1 ✅ Complete
    ↓
S2 🟡 Partial (S2.3/S2.4 deferred; S2.1/S2.2/S2.5/S2.6 done)
    ↓
S3 ⛔ Not started  ← KMS key ready (S2.5 ✅); just needs S3.1 CI wiring
    ↓
S4 ⛔ Not started
    S4.0 ALB ✅ done; SG restriction pending
        ↓
    S4.4 WAF  ← needs SG restricted first
        ↓
    S4.7 ZAP

S6 ⛔ Not started  ← can run at any time, no dependencies
```

---

## Items Deferred by Design

| Item | Reason |
|------|--------|
| MongoDB 4.0 → 7.0 upgrade | Violates zero-downtime rule; ~4 min downtime; requires maintenance window + backup drill |
| GuardDuty + CloudTrail (S2.4) | Deferred by request; no blocking dependency |
| Data classification tags (S2.3) | Deferred by request |
| Secret rotation automation | Out of scope; document in threat model as named residual risk |
| Security Hub + AWS Config | Assess after GuardDuty proves value |
| Full pentest | ZAP baseline (S4.7) provides documented DAST evidence in lieu |

---

## Compliance Checklist

| Framework Question | Before | After S1–S4 + S6 | Current |
|-------------------|--------|------------------|---------|
| Can a new engineer deploy safely without asking anyone? | Partial | ✅ GitOps + runbooks | 🟡 GitOps live; runbooks pending S6 |
| Can on-call diagnose at 3am without SSH? | Partial | ✅ CloudWatch + runbooks | 🟡 Falco + Prometheus live; CloudWatch pending |
| Can finance tell what this costs? | Yes | ✅ Kubecost | ✅ Live |
| Can security tell who accessed what? | Partial | ✅ CloudTrail + GuardDuty + Falco | 🟡 Falco live; CloudTrail/GuardDuty deferred |
| Can a compliance officer trace every control? | No | ✅ Threat model + IR + GDPR docs | ⛔ Docs pending S6 |
| Has the platform been tested against OWASP Top 10? | No | ✅ ZAP baseline scan | ⛔ Pending S4.7 |
| Are container images supply-chain verified? | No | ✅ Cosign + Kyverno Enforce | ⛔ Pending S3 |

---

*No sprint begins without human sign-off on the previous sprint's review gate.
The golden rule — zero cluster downtime, nothing that works breaks — governs every decision.*
