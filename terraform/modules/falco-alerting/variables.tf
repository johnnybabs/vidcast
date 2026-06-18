variable "cluster_name" {
  description = "EKS cluster name — used to prefix the IRSA role name"
  type        = string
}

variable "aws_region" {
  description = "AWS region (e.g. eu-west-2)"
  type        = string
}

variable "oidc_provider_arn" {
  description = "ARN of the EKS cluster's OIDC provider (from module.eks.oidc_provider_arn)"
  type        = string
}

variable "oidc_provider_url" {
  description = "URL of the EKS cluster's OIDC provider, with or without https:// prefix"
  type        = string
}

variable "alert_email" {
  description = "Email address to subscribe to the Falco SNS alert topic. AWS sends a confirmation email on apply — alerts are not delivered until the recipient confirms."
  type        = string
}

variable "falcosidekick_namespace" {
  description = "Kubernetes namespace where Falco/Falcosidekick is installed"
  type        = string
  default     = "default"
}

variable "falcosidekick_service_account" {
  description = "ServiceAccount name created by the Falco Helm chart for Falcosidekick. With release name 'falco' this is 'falco-falcosidekick'."
  type        = string
  default     = "falco-falcosidekick"
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}
