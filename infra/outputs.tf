output "api_gateway_url" {
  description = "HTTP API Gateway invoke URL"
  value       = module.api_gateway.http_api_url
}

output "api_gateway_websocket_url" {
  description = "WebSocket API Gateway URL"
  value       = module.api_gateway.websocket_api_url
}

output "cloudfront_distribution_url" {
  description = "CloudFront distribution domain for the frontend"
  value       = module.s3_cloudfront.cloudfront_domain_name
}

output "lambda_function_arn" {
  description = "Lambda function ARN"
  value       = module.lambda.function_arn
}

output "dynamodb_table_name" {
  description = "DynamoDB session table name"
  value       = module.dynamodb.table_name
}

output "s3_bucket_name" {
  description = "S3 bucket for frontend assets"
  value       = module.s3_cloudfront.bucket_name
}

output "waf_web_acl_arn" {
  description = "WAF web ACL ARN"
  value       = module.waf.web_acl_arn
}

output "sns_topic_arn" {
  description = "SNS topic ARN for monitoring alerts"
  value       = module.monitoring.sns_topic_arn
}
