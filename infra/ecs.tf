resource "aws_ecs_cluster" "main" {
  name = var.project

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_cloudwatch_log_group" "tasks" {
  for_each          = toset(["api", "ingest"])
  name              = "/${var.project}/${each.key}"
  retention_in_days = var.log_retention_days
  kms_key_id        = aws_kms_key.main.arn
}

locals {
  image = "${aws_ecr_repository.api.repository_url}:${var.image_tag}"

  environment = [
    { name = "JUGRID_DB_HOST", value = aws_db_instance.main.address },
    { name = "JUGRID_DB_NAME", value = aws_db_instance.main.db_name },
    { name = "JUGRID_STORE_URL", value = "s3://${aws_s3_bucket.data.id}/climate.zarr" },
    { name = "JUGRID_AWS_REGION", value = var.region },
    { name = "JUGRID_CACHE_DIR", value = "/tmp/jugrid" },
  ]

  # The API signs in as a role that can only read (migration 0002), with a 15-minute IAM token
  # made for each new connection: no password to hold, and nothing to break when RDS rotates
  # the owner's password. The short-lived ingest owns the tables and migrates them, so it signs
  # in as the owner with the password RDS keeps in Secrets Manager.
  database = {
    api = {
      environment = [
        { name = "JUGRID_DB_USER", value = local.api_db_user },
        { name = "JUGRID_DB_IAM_AUTH", value = "true" },
      ]
      secrets = []
    }
    ingest = {
      environment = [{ name = "JUGRID_DB_USER", value = aws_db_instance.main.username }]
      secrets = [
        { name = "JUGRID_DB_PASSWORD", valueFrom = "${aws_db_instance.main.master_user_secret[0].secret_arn}:password::" },
      ]
    }
  }

  container = {
    for name, task in {
      api    = { command = null, port = 8000 }
      ingest = { command = ["jugrid", "ingest", "all"], port = null }
      } : name => merge(
      {
        name                   = name
        image                  = local.image
        essential              = true
        readonlyRootFilesystem = true
        user                   = "10001"
        environment            = concat(local.environment, local.database[name].environment)
        secrets                = local.database[name].secrets
        mountPoints            = [{ sourceVolume = "tmp", containerPath = "/tmp" }]
        logConfiguration = {
          logDriver = "awslogs"
          options = {
            awslogs-group         = aws_cloudwatch_log_group.tasks[name].name
            awslogs-region        = var.region
            awslogs-stream-prefix = name
          }
        }
      },
      task.command == null ? {} : { command = task.command },
      task.port == null ? {} : { portMappings = [{ containerPort = task.port, protocol = "tcp" }] },
    )
  }
}

resource "aws_ecs_task_definition" "api" {
  family                   = "${var.project}-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 512
  memory                   = 1024
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.api.arn
  container_definitions    = jsonencode([local.container.api])

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  volume {
    name = "tmp"
  }
}

# The ingest downloads one global NetCDF file per worker at a time, about 250 MB each.
resource "aws_ecs_task_definition" "ingest" {
  family                   = "${var.project}-ingest"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 2048
  memory                   = 8192
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.ingest.arn
  container_definitions    = jsonencode([local.container.ingest])

  ephemeral_storage {
    size_in_gib = 30
  }

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  volume {
    name = "tmp"
  }
}

resource "aws_ecs_service" "api" {
  name            = "api"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.api_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.api.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 8000
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  # Deploys from GitHub register new task definitions; Terraform does not roll them back.
  lifecycle {
    ignore_changes = [task_definition]
  }

  depends_on = [aws_lb_listener.http]
}
