# Runs the ingest task on a schedule; `aws ecs run-task` with the same settings runs it now.
resource "aws_scheduler_schedule" "ingest" {
  name                = "${var.project}-ingest"
  schedule_expression = var.ingest_schedule
  kms_key_arn         = aws_kms_key.main.arn

  flexible_time_window {
    mode                      = "FLEXIBLE"
    maximum_window_in_minutes = 60
  }

  target {
    arn      = aws_ecs_cluster.main.arn
    role_arn = aws_iam_role.scheduler.arn

    ecs_parameters {
      task_definition_arn = aws_ecs_task_definition.ingest.arn_without_revision
      launch_type         = "FARGATE"

      network_configuration {
        subnets          = aws_subnet.private[*].id
        security_groups  = [aws_security_group.ingest.id]
        assign_public_ip = false
      }
    }

    retry_policy {
      maximum_retry_attempts = 0 # a failed ingest leaves the last good data in place
    }
  }
}

resource "aws_iam_role" "scheduler" {
  name = "${var.project}-scheduler"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "scheduler.amazonaws.com" }
      Action    = "sts:AssumeRole"
      Condition = { StringEquals = { "aws:SourceAccount" = local.account_id } }
    }]
  })
}

resource "aws_iam_role_policy" "scheduler" {
  name = "run-ingest"
  role = aws_iam_role.scheduler.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Action    = "ecs:RunTask"
        Resource  = "${aws_ecs_task_definition.ingest.arn_without_revision}:*"
        Condition = { ArnEquals = { "ecs:cluster" = aws_ecs_cluster.main.arn } }
      },
      {
        Effect    = "Allow"
        Action    = "iam:PassRole"
        Resource  = [aws_iam_role.execution.arn, aws_iam_role.ingest.arn]
        Condition = { StringEquals = { "iam:PassedToService" = "ecs-tasks.amazonaws.com" } }
      },
    ]
  })
}
