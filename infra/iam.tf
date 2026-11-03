locals {
  ecs_trust = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
      Condition = { StringEquals = { "aws:SourceAccount" = local.account_id } }
    }]
  })
}

# Pulls the image, writes logs, reads the database password for the ingest.
resource "aws_iam_role" "execution" {
  name               = "${var.project}-execution"
  assume_role_policy = local.ecs_trust
}

resource "aws_iam_role_policy_attachment" "execution" {
  role       = aws_iam_role.execution.name
  policy_arn = "${local.arn_prefix}:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "execution_secret" {
  name = "database-secret"
  role = aws_iam_role.execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "secretsmanager:GetSecretValue"
        Resource = aws_db_instance.main.master_user_secret[0].secret_arn
      },
      {
        Effect    = "Allow"
        Action    = "kms:Decrypt"
        Resource  = aws_kms_key.main.arn
        Condition = { StringEquals = { "kms:ViaService" = "secretsmanager.${var.region}.amazonaws.com" } }
      },
    ]
  })
}

locals {
  api_db_user = "jugrid_api"
}

resource "aws_iam_role_policy" "api_database" {
  name = "database-sign-in"
  role = aws_iam_role.api.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "rds-db:connect"
      Resource = "${local.arn_prefix}:rds-db:${var.region}:${local.account_id}:dbuser:${aws_db_instance.main.resource_id}/${local.api_db_user}"
    }]
  })
}

# The API only reads the climate store; the ingest writes it.
resource "aws_iam_role" "api" {
  name               = "${var.project}-api"
  assume_role_policy = local.ecs_trust
}

resource "aws_iam_role" "ingest" {
  name               = "${var.project}-ingest"
  assume_role_policy = local.ecs_trust
}

resource "aws_iam_role_policy" "store" {
  for_each = {
    api    = { role = aws_iam_role.api.id, actions = ["s3:GetObject"], kms = ["kms:Decrypt"] }
    ingest = { role = aws_iam_role.ingest.id, actions = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"], kms = ["kms:Decrypt", "kms:GenerateDataKey"] }
  }
  name = "climate-store"
  role = each.value.role

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "s3:ListBucket"
        Resource = aws_s3_bucket.data.arn
      },
      {
        Effect   = "Allow"
        Action   = each.value.actions
        Resource = "${aws_s3_bucket.data.arn}/climate.zarr/*"
      },
      {
        Effect    = "Allow"
        Action    = each.value.kms
        Resource  = aws_kms_key.main.arn
        Condition = { StringEquals = { "kms:ViaService" = "s3.${var.region}.amazonaws.com" } }
      },
    ]
  })
}

resource "aws_iam_role" "flow_logs" {
  name = "${var.project}-flow-logs"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "vpc-flow-logs.amazonaws.com" }
      Action    = "sts:AssumeRole"
      Condition = { StringEquals = { "aws:SourceAccount" = local.account_id } }
    }]
  })
}

resource "aws_iam_role_policy" "flow_logs" {
  name = "write-flow-logs"
  role = aws_iam_role.flow_logs.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["logs:CreateLogStream", "logs:PutLogEvents", "logs:DescribeLogStreams"]
      Resource = "${aws_cloudwatch_log_group.flow.arn}:*"
    }]
  })
}

resource "aws_iam_role" "rds_monitoring" {
  name = "${var.project}-rds-monitoring"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "monitoring.rds.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "rds_monitoring" {
  role       = aws_iam_role.rds_monitoring.name
  policy_arn = "${local.arn_prefix}:iam::aws:policy/service-role/AmazonRDSEnhancedMonitoringRole"
}
