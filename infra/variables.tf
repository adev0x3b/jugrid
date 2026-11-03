variable "project" {
  description = "Name prefix for every resource."
  type        = string
  default     = "jugrid"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,20}$", var.project))
    error_message = "Use 2-21 lowercase letters, digits or dashes, starting with a letter."
  }
}

variable "region" {
  description = "AWS region. Milan by default, close to the data's users."
  type        = string
  default     = "eu-south-1"
}

variable "github_repository" {
  description = "owner/name of the repository whose main branch may deploy."
  type        = string
  default     = "adev0x3b/jugrid"

  validation {
    condition     = can(regex("^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", var.github_repository))
    error_message = "Write it as owner/name."
  }
}

variable "image_tag" {
  description = "Tag of the API image the services start with. Deploys move it forward."
  type        = string
  default     = "bootstrap"
}

variable "vpc_cidr" {
  description = "Address range of the VPC."
  type        = string
  default     = "10.40.0.0/16"
}

variable "db_instance_class" {
  description = "RDS instance class."
  type        = string
  default     = "db.t4g.micro"
}

variable "db_allocated_storage_gb" {
  description = "RDS storage in GB."
  type        = number
  default     = 20
}

variable "deletion_protection" {
  description = "Protect the database from terraform destroy. Turn off only to tear down a trial."
  type        = bool
  default     = true
}

variable "api_desired_count" {
  description = "How many API tasks to run."
  type        = number
  default     = 1
}

variable "ingest_schedule" {
  description = "When the ingest runs again (EventBridge Scheduler expression). OpenStreetMap changes daily; the climate data does not."
  type        = string
  default     = "cron(0 3 1 * ? *)"
}

variable "log_retention_days" {
  description = "How long CloudWatch keeps logs."
  type        = number
  default     = 90
}

variable "waf_enabled" {
  description = "Put AWS WAF (managed rule groups and a rate limit) in front of CloudFront. About $9 a month before traffic."
  type        = bool
  default     = false
}

variable "waf_rate_limit" {
  description = "Requests one address may make in five minutes before WAF answers 429."
  type        = number
  default     = 1000

  validation {
    condition     = var.waf_rate_limit >= 10 && var.waf_rate_limit <= 2000000000
    error_message = "WAF accepts 10 to 2,000,000,000 requests per window."
  }
}
