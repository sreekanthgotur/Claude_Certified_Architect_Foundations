variable "environment" {
  description = "Deployment environment"
  type        = string
}

variable "lambda_function_name" {
  description = "Lambda function name for CloudWatch metrics"
  type        = string
}

variable "api_gateway_name" {
  description = "API Gateway name for CloudWatch metrics"
  type        = string
}

variable "alert_email" {
  description = "Email address for alarm notifications"
  type        = string
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 30
}

variable "name_prefix" {
  description = "Prefix for resource names"
  type        = string
}
