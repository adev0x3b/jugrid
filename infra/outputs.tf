output "url" {
  description = "Where the app answers."
  value       = "https://${aws_cloudfront_distribution.main.domain_name}"
}

output "deploy_role_arn" {
  description = "Set as the AWS_DEPLOY_ROLE_ARN variable of the GitHub repository."
  value       = aws_iam_role.deploy.arn
}

output "deploy_settings" {
  description = "The other repository variables the deploy workflow reads."
  value = {
    AWS_REGION                 = var.region
    ECR_REPOSITORY             = aws_ecr_repository.api.name
    ECS_CLUSTER                = aws_ecs_cluster.main.name
    ECS_SERVICE                = aws_ecs_service.api.name
    API_TASK_FAMILY            = aws_ecs_task_definition.api.family
    INGEST_TASK_FAMILY         = aws_ecs_task_definition.ingest.family
    WEB_BUCKET                 = aws_s3_bucket.web.id
    CLOUDFRONT_DISTRIBUTION_ID = aws_cloudfront_distribution.main.id
  }
}

output "run_ingest" {
  description = "Run the ingest now instead of waiting for the schedule."
  value = join(" ", [
    "aws ecs run-task --cluster ${aws_ecs_cluster.main.name}",
    "--task-definition ${aws_ecs_task_definition.ingest.family} --launch-type FARGATE",
    "--network-configuration 'awsvpcConfiguration={subnets=[${join(",", aws_subnet.private[*].id)}],securityGroups=[${aws_security_group.ingest.id}]}'",
  ])
}

output "alerts_topic_arn" {
  description = "SNS topic the alarms and failed ingests publish to; subscribe chat or on-call here."
  value       = aws_sns_topic.alerts.arn
}
