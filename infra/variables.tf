variable "environment" {
  description = "Deployment environment (dev, staging, prod)"
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be one of: dev, staging, prod."
  }
}

variable "project_name" {
  description = "Project name used in resource naming and tagging"
  type        = string
  default     = "ccar-f-mvp"
}

variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "us-east-1"
}

variable "domain_name" {
  description = "Custom domain name for the application (optional)"
  type        = string
  default     = ""
}

variable "certificate_arn" {
  description = "ACM certificate ARN for the custom domain (required if domain_name is set)"
  type        = string
  default     = ""
}

variable "anthropic_api_key_arn" {
  description = "ARN of the Secrets Manager secret holding the Anthropic API key"
  type        = string
  default     = ""
}

variable "alert_email" {
  description = "Email address for CloudWatch alarm notifications"
  type        = string
}

variable "lambda_memory_size" {
  description = "Lambda function memory in MB"
  type        = number
  default     = 512
}

variable "lambda_timeout" {
  description = "Lambda function timeout in seconds"
  type        = number
  default     = 30
}

variable "lambda_s3_bucket" {
  description = "S3 bucket holding the Lambda deployment package"
  type        = string
  default     = ""
}

variable "lambda_s3_key" {
  description = "S3 key for the Lambda deployment package"
  type        = string
  default     = ""
}

variable "enable_pitr" {
  description = "Enable DynamoDB point-in-time recovery (recommended for prod)"
  type        = bool
  default     = false
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 30
}

variable "waf_rate_limit" {
  description = "WAF rate limit: max requests per 5-minute window per IP"
  type        = number
  default     = 1000
}
