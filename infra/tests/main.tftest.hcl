# Offline tests: the AWS provider is mocked, so these need no account and create nothing.

mock_provider "aws" {
  mock_data "aws_availability_zones" {
    defaults = { names = ["eu-south-1a", "eu-south-1b", "eu-south-1c"] }
  }
  mock_data "aws_caller_identity" {
    defaults = { account_id = "123456789012" }
  }
  mock_data "aws_partition" {
    defaults = { partition = "aws" }
  }
  mock_resource "aws_iam_openid_connect_provider" {
    defaults = { arn = "arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com" }
  }
  mock_resource "aws_kms_key" {
    defaults = { arn = "arn:aws:kms:eu-south-1:123456789012:key/test" }
  }
  mock_resource "aws_s3_bucket" {
    defaults = { arn = "arn:aws:s3:::jugrid-test" }
  }
  mock_resource "aws_iam_role" {
    defaults = { arn = "arn:aws:iam::123456789012:role/test" }
  }
  mock_resource "aws_cloudwatch_log_group" {
    defaults = { arn = "arn:aws:logs:eu-south-1:123456789012:log-group:test" }
  }
  mock_resource "aws_ecs_cluster" {
    defaults = { arn = "arn:aws:ecs:eu-south-1:123456789012:cluster/jugrid" }
  }
  mock_resource "aws_ecs_task_definition" {
    defaults = {
      arn                  = "arn:aws:ecs:eu-south-1:123456789012:task-definition/jugrid-ingest:1"
      arn_without_revision = "arn:aws:ecs:eu-south-1:123456789012:task-definition/jugrid-ingest"
    }
  }
  mock_resource "aws_cloudfront_distribution" {
    defaults = { arn = "arn:aws:cloudfront::123456789012:distribution/TEST" }
  }
  mock_resource "aws_db_instance" {
    defaults = {
      address = "jugrid.test.eu-south-1.rds.amazonaws.com"
      master_user_secret = [{
        secret_arn    = "arn:aws:secretsmanager:eu-south-1:123456789012:secret:rds-test"
        kms_key_id    = "test"
        secret_status = "active"
      }]
    }
  }
  mock_resource "aws_lb_target_group" {
    defaults = { arn = "arn:aws:elasticloadbalancing:eu-south-1:123456789012:targetgroup/jugrid-api/test" }
  }
  mock_resource "aws_lb" {
    defaults = { arn = "arn:aws:elasticloadbalancing:eu-south-1:123456789012:loadbalancer/app/jugrid/test" }
  }
  mock_resource "aws_lb_listener" {
    defaults = { arn = "arn:aws:elasticloadbalancing:eu-south-1:123456789012:listener/app/jugrid/test/test" }
  }
}

mock_provider "random" {}

run "buckets_are_private_encrypted_and_tls_only" {
  command = apply

  assert {
    condition = alltrue([
      for b in aws_s3_bucket_public_access_block.all :
      b.block_public_acls && b.block_public_policy && b.ignore_public_acls && b.restrict_public_buckets
    ])
    error_message = "Every bucket must block public access."
  }

  assert {
    condition     = length(aws_s3_bucket_public_access_block.all) == 3
    error_message = "The data, web and log buckets all need a public access block."
  }

  assert {
    condition = one([
      for r in aws_s3_bucket_server_side_encryption_configuration.data.rule :
      one(r.apply_server_side_encryption_by_default).sse_algorithm
    ]) == "aws:kms"
    error_message = "The climate store is encrypted with the project's KMS key."
  }

  assert {
    condition = alltrue([
      for policy in [aws_s3_bucket_policy.data.policy, aws_s3_bucket_policy.web.policy, aws_s3_bucket_policy.alb_logs.policy] :
      contains([for s in jsondecode(policy).Statement : s.Sid], "TlsOnly")
    ])
    error_message = "Every bucket refuses plain HTTP."
  }
}

run "the_database_is_private_and_terraform_never_holds_its_password" {
  command = apply

  assert {
    condition     = !aws_db_instance.main.publicly_accessible
    error_message = "The database must not be reachable from the internet."
  }

  assert {
    condition     = aws_db_instance.main.storage_encrypted && aws_db_instance.main.manage_master_user_password
    error_message = "Storage is encrypted and RDS manages the password in Secrets Manager."
  }

  assert {
    condition     = toset(aws_db_subnet_group.main.subnet_ids) == toset(aws_subnet.private[*].id)
    error_message = "The database lives in the private subnets."
  }

  assert {
    condition = toset([for r in aws_vpc_security_group_ingress_rule.db_from_tasks : r.referenced_security_group_id]) == toset([
      aws_security_group.api.id, aws_security_group.ingest.id,
    ])
    error_message = "Only the API and the ingest reach the database."
  }

  assert {
    condition     = alltrue([for r in aws_vpc_security_group_ingress_rule.db_from_tasks : r.cidr_ipv4 == null])
    error_message = "The database accepts no address ranges."
  }
}

run "only_cloudfront_reaches_the_load_balancer" {
  command = apply

  assert {
    condition     = aws_vpc_security_group_ingress_rule.alb_from_cloudfront.prefix_list_id == data.aws_ec2_managed_prefix_list.cloudfront.id
    error_message = "The load balancer accepts CloudFront's origin-facing addresses only."
  }

  assert {
    condition     = aws_vpc_security_group_ingress_rule.alb_from_cloudfront.cidr_ipv4 == null
    error_message = "No open address range on the load balancer."
  }

  assert {
    condition     = one(aws_lb_listener.http.default_action).type == "fixed-response"
    error_message = "Requests without the origin header get a 403, not the API."
  }

  assert {
    condition = one([
      for o in aws_cloudfront_distribution.main.origin : one(o.custom_header).value if o.origin_id == "api"
    ]) == random_password.origin_secret.result
    error_message = "CloudFront sends the header the listener rule checks."
  }

  assert {
    condition = one([
      for b in aws_cloudfront_distribution.main.ordered_cache_behavior : b.target_origin_id if b.path_pattern == "/api/*"
    ]) == "api"
    error_message = "/api/* goes to the load balancer."
  }
}

run "github_deploys_only_from_main_of_this_repository" {
  command = apply

  assert {
    condition     = jsondecode(aws_iam_role.deploy.assume_role_policy).Statement[0].Condition.StringEquals["token.actions.githubusercontent.com:sub"] == "repo:adev0x3b/jugrid:ref:refs/heads/main"
    error_message = "Only the main branch of adev0x3b/jugrid may assume the deploy role."
  }

  assert {
    condition     = !contains(flatten([for s in jsondecode(aws_iam_role_policy.deploy.policy).Statement : s.Action]), "*")
    error_message = "The deploy role has no wildcard actions."
  }
}

run "the_api_reads_the_store_and_only_the_ingest_writes_it" {
  command = apply

  assert {
    condition     = !contains(jsondecode(aws_iam_role_policy.store["api"].policy).Statement[1].Action, "s3:PutObject")
    error_message = "The API must not write the climate store."
  }

  assert {
    condition     = contains(jsondecode(aws_iam_role_policy.store["ingest"].policy).Statement[1].Action, "s3:PutObject")
    error_message = "The ingest writes the climate store."
  }

  assert {
    condition     = startswith([for e in jsondecode(aws_ecs_task_definition.api.container_definitions)[0].environment : e.value if e.name == "JUGRID_STORE_URL"][0], "s3://")
    error_message = "The API reads the Zarr store from S3."
  }

  assert {
    condition     = jsondecode(aws_ecs_task_definition.ingest.container_definitions)[0].command == ["jugrid", "ingest", "all"]
    error_message = "The ingest task runs every step."
  }

  assert {
    condition     = alltrue([for t in [aws_ecs_task_definition.api, aws_ecs_task_definition.ingest] : jsondecode(t.container_definitions)[0].readonlyRootFilesystem])
    error_message = "Containers run with a read-only root file system."
  }

  assert {
    condition     = aws_scheduler_schedule.ingest.target[0].ecs_parameters[0].task_definition_arn == aws_ecs_task_definition.ingest.arn_without_revision
    error_message = "The schedule runs the ingest task."
  }
}

run "a_repository_must_be_owner_slash_name" {
  command = plan

  variables {
    github_repository = "jugrid"
  }

  expect_failures = [var.github_repository]
}
