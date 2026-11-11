output "api_key_secret_arn" {
  description = "ARN of the Anthropic API key secret"
  value       = aws_secretsmanager_secret.anthropic_api_key.arn
}

output "mcp_credentials_secret_arn" {
  description = "ARN of the MCP credentials secret"
  value       = aws_secretsmanager_secret.mcp_credentials.arn
}
