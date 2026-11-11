output "dashboard_url" {
  description = "CloudWatch dashboard URL"
  value       = "https://${data.aws_region.current.name}.console.aws.amazon.com/cloudwatch/home#dashboards:name=${aws_cloudwatch_dashboard.main.dashboard_name}"
}

output "sns_topic_arn" {
  description = "SNS topic ARN for alert notifications"
  value       = aws_sns_topic.alerts.arn
}

output "log_group_names" {
  description = "CloudWatch Log Group names"
  value = {
    lambda      = aws_cloudwatch_log_group.lambda.name
    api_gateway = aws_cloudwatch_log_group.api_gateway.name
  }
}
