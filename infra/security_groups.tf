# CloudFront's origin-facing addresses, VPC origins included: the only ones that may reach
# the load balancer.
data "aws_ec2_managed_prefix_list" "cloudfront" {
  name = "com.amazonaws.global.cloudfront.origin-facing"
}

resource "aws_security_group" "alb" {
  name        = "${var.project}-alb"
  description = "Load balancer: HTTP from CloudFront only"
  vpc_id      = aws_vpc.main.id
}

resource "aws_vpc_security_group_ingress_rule" "alb_from_cloudfront" {
  security_group_id = aws_security_group.alb.id
  description       = "CloudFront origin requests"
  prefix_list_id    = data.aws_ec2_managed_prefix_list.cloudfront.id
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
}

resource "aws_vpc_security_group_egress_rule" "alb_to_api" {
  security_group_id            = aws_security_group.alb.id
  description                  = "To the API tasks"
  referenced_security_group_id = aws_security_group.api.id
  ip_protocol                  = "tcp"
  from_port                    = 8000
  to_port                      = 8000
}

resource "aws_security_group" "api" {
  name        = "${var.project}-api"
  description = "API tasks: from the load balancer only"
  vpc_id      = aws_vpc.main.id
}

resource "aws_vpc_security_group_ingress_rule" "api_from_alb" {
  security_group_id            = aws_security_group.api.id
  description                  = "From the load balancer"
  referenced_security_group_id = aws_security_group.alb.id
  ip_protocol                  = "tcp"
  from_port                    = 8000
  to_port                      = 8000
}

resource "aws_security_group" "ingest" {
  name        = "${var.project}-ingest"
  description = "Ingest task: nothing comes in"
  vpc_id      = aws_vpc.main.id
}

# Both tasks reach out over HTTPS (ECR, Secrets Manager, S3, the data sources) and to the database.
resource "aws_vpc_security_group_egress_rule" "https" {
  for_each          = { api = aws_security_group.api.id, ingest = aws_security_group.ingest.id }
  security_group_id = each.value
  description       = "HTTPS out"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
}

resource "aws_vpc_security_group_egress_rule" "to_db" {
  for_each                     = { api = aws_security_group.api.id, ingest = aws_security_group.ingest.id }
  security_group_id            = each.value
  description                  = "PostgreSQL"
  referenced_security_group_id = aws_security_group.db.id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
}

resource "aws_security_group" "db" {
  name        = "${var.project}-db"
  description = "Database: from the API and the ingest only"
  vpc_id      = aws_vpc.main.id
}

resource "aws_vpc_security_group_ingress_rule" "db_from_tasks" {
  for_each                     = { api = aws_security_group.api.id, ingest = aws_security_group.ingest.id }
  security_group_id            = aws_security_group.db.id
  description                  = "From the ${each.key} tasks"
  referenced_security_group_id = each.value
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
}
