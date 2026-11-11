variable "bucket_name" {
  description = "S3 bucket name for frontend assets"
  type        = string
}

variable "environment" {
  description = "Deployment environment"
  type        = string
}

variable "domain_name" {
  description = "Custom domain name (empty string to skip)"
  type        = string
  default     = ""
}

variable "certificate_arn" {
  description = "ACM certificate ARN for custom domain"
  type        = string
  default     = ""
}

variable "api_gateway_url" {
  description = "HTTP API Gateway URL for /api origin"
  type        = string
}

variable "name_prefix" {
  description = "Prefix for resource names"
  type        = string
}
