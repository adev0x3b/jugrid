# Alerts: what pages someone, and what the API does by itself under load. docs/runbook.md says
# what to do for each alarm.

resource "aws_sns_topic" "alerts" {
  name              = "${var.project}-alerts"
  kms_master_key_id = aws_kms_key.main.id
}

# CloudWatch alarms and the EventBridge rule below publish here; nobody else can.
resource "aws_sns_topic_policy" "alerts" {
  arn = aws_sns_topic.alerts.arn
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "AlarmsAndEventsPublish"
      Effect    = "Allow"
      Principal = { Service = ["cloudwatch.amazonaws.com", "events.amazonaws.com"] }
      Action    = "sns:Publish"
      Resource  = aws_sns_topic.alerts.arn
      Condition = { StringEquals = { "aws:SourceAccount" = local.account_id } }
    }]
  })
}

# Confirm the subscription from the mail AWS sends. Without an address, subscribe something
# else (chat, on-call) to the topic in the alerts_topic_arn output.
resource "aws_sns_topic_subscription" "email" {
  count     = var.alert_email == "" ? 0 : 1
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

locals {
  alb_dimensions = {
    LoadBalancer = aws_lb.main.arn_suffix
    TargetGroup  = aws_lb_target_group.api.arn_suffix
  }

  # name => what breaches, read by docs/runbook.md
  alarms = {
    api-errors = {
      description = "The API answered 5 or more 5xx in 5 minutes."
      namespace   = "AWS/ApplicationELB"
      metric      = "HTTPCode_Target_5XX_Count"
      statistic   = "Sum"
      dimensions  = local.alb_dimensions
      period      = 300
      periods     = 1
      comparison  = "GreaterThanOrEqualToThreshold"
      threshold   = 5
      missing     = "notBreaching"
    }
    api-down = {
      description = "No healthy API task behind the load balancer for 2 minutes."
      namespace   = "AWS/ApplicationELB"
      metric      = "HealthyHostCount"
      statistic   = "Minimum"
      dimensions  = local.alb_dimensions
      period      = 60
      periods     = 2
      comparison  = "LessThanThreshold"
      threshold   = 1
      missing     = "breaching"
    }
    api-slow = {
      description = "The API's slowest 5% of answers took over 2 seconds for 15 minutes."
      namespace   = "AWS/ApplicationELB"
      metric      = "TargetResponseTime"
      statistic   = null
      percentile  = "p95"
      dimensions  = local.alb_dimensions
      period      = 300
      periods     = 3
      comparison  = "GreaterThanThreshold"
      threshold   = 2
      missing     = "notBreaching"
    }
    db-cpu = {
      description = "The database averaged over 80% CPU for 15 minutes."
      namespace   = "AWS/RDS"
      metric      = "CPUUtilization"
      statistic   = "Average"
      dimensions  = { DBInstanceIdentifier = aws_db_instance.main.identifier }
      period      = 300
      periods     = 3
      comparison  = "GreaterThanThreshold"
      threshold   = 80
      missing     = "notBreaching"
    }
    db-storage = {
      description = "The database has under 2 GiB of free storage."
      namespace   = "AWS/RDS"
      metric      = "FreeStorageSpace"
      statistic   = "Minimum"
      dimensions  = { DBInstanceIdentifier = aws_db_instance.main.identifier }
      period      = 300
      periods     = 1
      comparison  = "LessThanThreshold"
      threshold   = 2 * 1024 * 1024 * 1024
      missing     = "breaching"
    }
  }
}

resource "aws_cloudwatch_metric_alarm" "this" {
  for_each = local.alarms

  alarm_name          = "${var.project}-${each.key}"
  alarm_description   = "${each.value.description} See docs/runbook.md#${each.key}."
  namespace           = each.value.namespace
  metric_name         = each.value.metric
  statistic           = each.value.statistic
  extended_statistic  = lookup(each.value, "percentile", null)
  dimensions          = each.value.dimensions
  period              = each.value.period
  evaluation_periods  = each.value.periods
  datapoints_to_alarm = each.value.periods
  comparison_operator = each.value.comparison
  threshold           = each.value.threshold
  treat_missing_data  = each.value.missing
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
}

# A scheduled ingest that exits non-zero, or never starts, says so instead of leaving the map
# a month older.
resource "aws_cloudwatch_event_rule" "ingest_failed" {
  name        = "${var.project}-ingest-failed"
  description = "The ingest task stopped with an error or did not start"
  event_pattern = jsonencode({
    source      = ["aws.ecs"]
    detail-type = ["ECS Task State Change"]
    detail = {
      clusterArn = [aws_ecs_cluster.main.arn]
      group      = ["family:${aws_ecs_task_definition.ingest.family}"]
      lastStatus = ["STOPPED"]
      "$or" = [
        { containers = { exitCode = [{ anything-but = 0 }] } },
        { stopCode = ["TaskFailedToStart"] },
      ]
    }
  })
}

resource "aws_cloudwatch_event_target" "ingest_failed" {
  rule = aws_cloudwatch_event_rule.ingest_failed.name
  arn  = aws_sns_topic.alerts.arn

  input_transformer {
    input_paths = {
      reason = "$.detail.stoppedReason"
      task   = "$.detail.taskArn"
    }
    input_template = "\"${var.project} ingest failed: <reason> (task <task>). See docs/runbook.md#ingest-failed.\""
  }
}

# The API scales on CPU between api_desired_count and api_max_count tasks.
resource "aws_appautoscaling_target" "api" {
  service_namespace  = "ecs"
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.api.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  min_capacity       = var.api_desired_count
  max_capacity       = var.api_max_count
}

resource "aws_appautoscaling_policy" "api_cpu" {
  name               = "${var.project}-api-cpu"
  policy_type        = "TargetTrackingScaling"
  service_namespace  = aws_appautoscaling_target.api.service_namespace
  resource_id        = aws_appautoscaling_target.api.resource_id
  scalable_dimension = aws_appautoscaling_target.api.scalable_dimension

  target_tracking_scaling_policy_configuration {
    target_value       = 60
    scale_out_cooldown = 60
    scale_in_cooldown  = 300

    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
  }
}
