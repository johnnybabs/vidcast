variable "cluster_name" {
  description = "EKS cluster name — used to name the KMS key and alias"
  type        = string
}

variable "tags" {
  description = "Tags to apply to the KMS key"
  type        = map(string)
  default     = {}
}
