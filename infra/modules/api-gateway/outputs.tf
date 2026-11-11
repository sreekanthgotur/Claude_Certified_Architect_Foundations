output "http_api_url" {
  description = "HTTP API Gateway invoke URL"
  value       = aws_apigatewayv2_stage.http.invoke_url
}

output "websocket_api_url" {
  description = "WebSocket API Gateway URL"
  value       = aws_apigatewayv2_stage.websocket.invoke_url
}

output "http_api_id" {
  description = "HTTP API Gateway ID"
  value       = aws_apigatewayv2_api.http.id
}

output "websocket_api_id" {
  description = "WebSocket API Gateway ID"
  value       = aws_apigatewayv2_api.websocket.id
}

output "http_api_stage_arn" {
  description = "HTTP API stage ARN for WAF association"
  value       = aws_apigatewayv2_stage.http.arn
}
