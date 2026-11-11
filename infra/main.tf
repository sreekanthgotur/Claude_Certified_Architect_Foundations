terraform {
  backend "s3" {
    bucket         = "ccar-f-mvp-terraform-state"
    key            = "state/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "ccar-f-mvp-terraform-locks"
    encrypt        = true
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Environment = var.environment
      Project     = var.project_name
      ManagedBy   = "terraform"
    }
  }
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  name_prefix = "${var.project_name}-${var.environment}"
}

module "dynamodb" {
  source = "./modules/dynamodb"

  table_name  = "${local.name_prefix}-sessions"
  environment = var.environment
  enable_pitr = var.enable_pitr
}

module "secrets" {
  source = "./modules/secrets"

  environment     = var.environment
  lambda_role_arn = module.lambda.role_arn
  name_prefix     = local.name_prefix
}

module "lambda" {
  source = "./modules/lambda"

  function_name   = "${local.name_prefix}-api"
  runtime         = "python3.12"
  memory_size     = var.lambda_memory_size
  timeout         = var.lambda_timeout
  s3_bucket       = var.lambda_s3_bucket
  s3_key          = var.lambda_s3_key
  dynamodb_table_arn = module.dynamodb.table_arn
  secrets_arn        = module.secrets.api_key_secret_arn
  name_prefix        = local.name_prefix

  environment_variables = {
    ENVIRONMENT          = var.environment
    DYNAMODB_TABLE       = module.dynamodb.table_name
    ANTHROPIC_API_KEY_ARN = module.secrets.api_key_secret_arn
    LOG_LEVEL            = var.environment == "prod" ? "WARNING" : "DEBUG"
  }
}

module "api_gateway" {
  source = "./modules/api-gateway"

  lambda_invoke_arn    = module.lambda.invoke_arn
  lambda_function_name = module.lambda.function_name
  environment          = var.environment
  name_prefix          = local.name_prefix
  domain_name          = var.domain_name
  certificate_arn      = var.certificate_arn
}

module "s3_cloudfront" {
  source = "./modules/s3-cloudfront"

  bucket_name     = "${local.name_prefix}-frontend"
  environment     = var.environment
  domain_name     = var.domain_name
  certificate_arn = var.certificate_arn
  api_gateway_url = module.api_gateway.http_api_url
  name_prefix     = local.name_prefix
}

module "waf" {
  source = "./modules/waf"

  name        = "${local.name_prefix}-waf"
  environment = var.environment
  rate_limit  = var.waf_rate_limit

  api_gateway_stage_arn = module.api_gateway.http_api_stage_arn
}

module "monitoring" {
  source = "./modules/monitoring"

  environment          = var.environment
  lambda_function_name = module.lambda.function_name
  api_gateway_name     = "${local.name_prefix}-http-api"
  alert_email          = var.alert_email
  log_retention_days   = var.log_retention_days
  name_prefix          = local.name_prefix
}
