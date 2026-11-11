variable "environment" {
  description = "Deployment environment"
  type        = string
}

variable "lambda_role_arn" {
  description = "Lambda execution role ARN for Secrets Manager resource policy"
  type        = string
}

variable "name_prefix" {
  description = "Prefix for resource names"
  type        = string
}
