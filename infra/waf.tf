# AWS WAF in front of CloudFront, off by default: it costs about $9 a month before traffic
# ($5 for the web ACL, $1 for each of its four rules, $0.60 per million requests), more than
# a read-only map of public data needs on a trial. Turn it on with waf_enabled = true.
#
# A web ACL for CloudFront lives in us-east-1, whatever the region of the rest.

resource "aws_wafv2_web_acl" "cdn" {
  count    = var.waf_enabled ? 1 : 0
  provider = aws.us_east_1

  name        = "${var.project}-cdn"
  description = "Managed rule groups and a per-address rate limit in front of CloudFront"
  scope       = "CLOUDFRONT"

  default_action {
    allow {}
  }

  # Addresses AWS has seen in botnets, scanners and attacks.
  rule {
    name     = "ip-reputation"
    priority = 10

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        vendor_name = "AWS"
        name        = "AWSManagedRulesAmazonIpReputationList"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.project}-ip-reputation"
      sampled_requests_enabled   = true
    }
  }

  # One address asking more than waf_rate_limit times in five minutes is answered 429 until
  # it slows down. A map load is a few dozen requests; tiles come from OpenFreeMap.
  rule {
    name     = "rate-limit"
    priority = 20

    action {
      block {
        custom_response {
          response_code = 429
        }
      }
    }

    statement {
      rate_based_statement {
        limit                 = var.waf_rate_limit
        evaluation_window_sec = 300
        aggregate_key_type    = "IP"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.project}-rate-limit"
      sampled_requests_enabled   = true
    }
  }

  # Request shapes known to exploit software (Log4j lookups, Java deserialization, ...).
  rule {
    name     = "known-bad-inputs"
    priority = 30

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        vendor_name = "AWS"
        name        = "AWSManagedRulesKnownBadInputsRuleSet"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.project}-known-bad-inputs"
      sampled_requests_enabled   = true
    }
  }

  # The OWASP-style core set: injection, traversal, oversized requests.
  rule {
    name     = "common"
    priority = 40

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        vendor_name = "AWS"
        name        = "AWSManagedRulesCommonRuleSet"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.project}-common"
      sampled_requests_enabled   = true
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "${var.project}-cdn"
    sampled_requests_enabled   = true
  }
}

# Only blocked requests are logged: they are what someone reads after an incident, and
# allowed ones would cost CloudWatch ingestion for every map load. Sampled requests and
# metrics cover the rest. A CloudFront web ACL logs to us-east-1, where the project key is not.
resource "aws_cloudwatch_log_group" "waf" {
  #checkov:skip=CKV_AWS_158:CloudWatch's own encryption; the project KMS key is in another region
  count    = var.waf_enabled ? 1 : 0
  provider = aws.us_east_1

  name              = "aws-waf-logs-${var.project}"
  retention_in_days = var.log_retention_days
}

resource "aws_wafv2_web_acl_logging_configuration" "cdn" {
  count    = var.waf_enabled ? 1 : 0
  provider = aws.us_east_1

  resource_arn            = aws_wafv2_web_acl.cdn[0].arn
  log_destination_configs = [aws_cloudwatch_log_group.waf[0].arn]

  logging_filter {
    default_behavior = "DROP"

    filter {
      behavior    = "KEEP"
      requirement = "MEETS_ANY"

      condition {
        action_condition {
          action = "BLOCK"
        }
      }
    }
  }
}
