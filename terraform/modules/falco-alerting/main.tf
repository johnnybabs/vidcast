# Falco alerting infrastructure (S2.6 completion).
# Two resources:
#   1. SNS topic + email subscription — the on-call alert channel for Falco
#      kernel-level security events (consistent with the alerting path planned
#      for GuardDuty findings, so both appear in one email thread when GuardDuty
#      is enabled in Sprint S2.4).
#   2. IRSA role for Falcosidekick — allows the falco-falcosidekick ServiceAccount
#      (created by the Falco Helm chart in the `default` namespace) to call
#      sns:Publish on *only* this topic. No other SNS topics, no other AWS actions.
#
# After `terraform apply`:
#   - AWS sends a subscription confirmation email to var.alert_email.
#     The recipient MUST click the confirmation link before alerts will be
#     delivered. This is an SNS requirement; Falcosidekick will publish
#     successfully but emails won't arrive until the subscription is confirmed.
#   - Retrieve the two output values and set them in the Helm values file
#     and/or as environment variables before running `helm install falco`.

data "aws_caller_identity" "current" {}

locals {
  # Strip https:// so the string can be used as an IAM condition key prefix.
  # aws_iam_openid_connect_provider.url includes the scheme; the condition key
  # does not. Same pattern as modules/external-secrets/main.tf.
  oidc_host = replace(var.oidc_provider_url, "https://", "")
}

# ─── SNS Topic ────────────────────────────────────────────────────────────────

resource "aws_sns_topic" "falco_alerts" {
  name = "vidcast-falco-alerts"
  tags = merge(var.tags, { Name = "vidcast-falco-alerts" })
}

resource "aws_sns_topic_subscription" "falco_email" {
  topic_arn = aws_sns_topic.falco_alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email

  # NOTE: AWS sends a confirmation email immediately after apply.
  # Alerts will NOT be delivered until the recipient clicks the confirm link.
}

# ─── IRSA role for Falcosidekick ──────────────────────────────────────────────
# The Falco Helm chart (release name: "falco") creates a ServiceAccount named
# "falco-falcosidekick" in the target namespace. This role allows only that
# specific SA to assume it via OIDC — no other principals.

data "aws_iam_policy_document" "falcosidekick_assume" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    effect  = "Allow"

    principals {
      type        = "Federated"
      identifiers = [var.oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.oidc_host}:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.oidc_host}:sub"
      values   = ["system:serviceaccount:${var.falcosidekick_namespace}:${var.falcosidekick_service_account}"]
    }
  }
}

resource "aws_iam_role" "falcosidekick" {
  name               = "${var.cluster_name}-falcosidekick-irsa"
  assume_role_policy = data.aws_iam_policy_document.falcosidekick_assume.json
  tags               = var.tags
}

# Least-privilege: sns:Publish on this topic only, nothing else.
data "aws_iam_policy_document" "falcosidekick_sns_publish" {
  statement {
    sid     = "PublishFalcoAlertsOnly"
    effect  = "Allow"
    actions = ["sns:Publish"]
    resources = [aws_sns_topic.falco_alerts.arn]
  }
}

resource "aws_iam_role_policy" "falcosidekick_sns" {
  name   = "sns-publish-falco-alerts-only"
  role   = aws_iam_role.falcosidekick.id
  policy = data.aws_iam_policy_document.falcosidekick_sns_publish.json
}

# ─── Outputs ──────────────────────────────────────────────────────────────────

output "falco_alerts_topic_arn" {
  value       = aws_sns_topic.falco_alerts.arn
  description = "ARN of the SNS topic — set as falcosidekick.config.sns.topicarn in falco-values.yaml"
}

output "falcosidekick_role_arn" {
  value       = aws_iam_role.falcosidekick.arn
  description = "IRSA role ARN — annotate the falco-falcosidekick ServiceAccount with this value"
}
