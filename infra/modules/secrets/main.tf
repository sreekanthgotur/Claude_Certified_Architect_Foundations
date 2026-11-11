resource "aws_secretsmanager_secret" "anthropic_api_key" {
  name                    = "${var.name_prefix}/anthropic-api-key"
  recovery_window_in_days = var.environment == "prod" ? 30 : 0
}

resource "aws_secretsmanager_secret" "mcp_credentials" {
  name                    = "${var.name_prefix}/mcp-credentials"
  recovery_window_in_days = var.environment == "prod" ? 30 : 0
}

data "aws_iam_policy_document" "secrets_access" {
  statement {
    sid    = "AllowLambdaAccess"
    effect = "Allow"
    actions = [
      "secretsmanager:GetSecretValue",
    ]

    principals {
      type        = "AWS"
      identifiers = [var.lambda_role_arn]
    }

    resources = ["*"]
  }
}

resource "aws_secretsmanager_secret_policy" "anthropic_api_key" {
  secret_arn = aws_secretsmanager_secret.anthropic_api_key.arn
  policy     = data.aws_iam_policy_document.secrets_access.json
}

resource "aws_secretsmanager_secret_policy" "mcp_credentials" {
  secret_arn = aws_secretsmanager_secret.mcp_credentials.arn
  policy     = data.aws_iam_policy_document.secrets_access.json
}
