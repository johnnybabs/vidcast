# Cosign image signing key for VidCast (S2.5).
# Asymmetric KMS key (ECC P-256) used by cosign to sign container images in CI.
# Sprint S3 wires this key ARN into the GitHub Actions workflow so every built
# image is signed before it can be admitted by the Kyverno verify-images policy.
#
# Key usage: SIGN_VERIFY with ECC_NIST_P256 — the algorithm cosign's KMS path
# expects. Key rotation is disabled on asymmetric keys (AWS does not support it
# for SIGN_VERIFY keys; rotation for asymmetric keys requires creating a new key).

data "aws_caller_identity" "current" {}

resource "aws_kms_key" "cosign" {
  description              = "Cosign image signing key for VidCast CI"
  deletion_window_in_days  = 7
  enable_key_rotation      = false  # not supported for asymmetric SIGN_VERIFY keys
  key_usage                = "SIGN_VERIFY"
  customer_master_key_spec = "ECC_NIST_P256"

  tags = merge(
    var.tags,
    { Name = "${var.cluster_name}-cosign-key" }
  )
}

# Alias gives the key a stable human-readable name used in the cosign --key flag:
# awskms:///alias/vidcast-cosign
resource "aws_kms_alias" "cosign" {
  name          = "alias/${var.cluster_name}-cosign"
  target_key_id = aws_kms_key.cosign.key_id
}

resource "aws_kms_key_policy" "cosign" {
  key_id = aws_kms_key.cosign.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "EnableRootAccountPermissions"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
        }
        Action   = "kms:*"
        Resource = "*"
      },
      {
        # Allow the GitHub Actions OIDC deploy role to sign images (Sign) and
        # let Kyverno/cosign verify signatures (GetPublicKey). The deploy role
        # ARN follows the naming convention set in modules/github-oidc/main.tf:
        # "${cluster_name}-github-deploy".
        Sid    = "AllowGitHubActionsOIDCToSign"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/${var.cluster_name}-github-deploy"
        }
        Action = [
          "kms:Sign",
          "kms:GetPublicKey",
          "kms:DescribeKey",
        ]
        Resource = "*"
      },
    ]
  })
}

output "cosign_key_arn" {
  value       = aws_kms_key.cosign.arn
  description = "ARN of the Cosign signing key — used as the --key value in Sprint S3 CI signing step"
}

output "cosign_key_id" {
  value       = aws_kms_key.cosign.key_id
  description = "Key ID of the Cosign signing key — add as COSIGN_KMS_KEY_ID GitHub Actions secret"
}

output "cosign_key_alias" {
  value       = aws_kms_alias.cosign.name
  description = "Alias of the Cosign signing key"
}
