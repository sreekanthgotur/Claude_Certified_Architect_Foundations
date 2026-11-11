variable "name" {
  description = "WAF web ACL name"
  type        = string
}

variable "environment" {
  description = "Deployment environment"
  type        = string
}

variable "rate_limit" {
  description = "Max requests per 5-minute window per IP"
  type        = number
  default     = 1000
}

variable "api_gateway_stage_arn" {
  description = "ARN of the API Gateway stage to associate with WAF"
  type        = string
}
