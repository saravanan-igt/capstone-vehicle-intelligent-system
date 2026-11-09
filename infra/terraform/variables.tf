variable "region" {
  type    = string
  default = "ap-south-1"
}

variable "environment" {
  type    = string
  default = "demo"
}

variable "name" {
  type    = string
  default = "vla"
}

variable "vpc_cidr" {
  type    = string
  default = "10.40.0.0/16"
}

variable "single_nat_gateway" {
  description = "true = cheaper demo (one AZ egress SPOF); false = one NAT per AZ for production."
  type        = bool
  default     = true
}

variable "kubernetes_version" {
  description = "VERIFY against currently supported EKS versions before apply (module examples use 1.33)."
  type        = string
  default     = "1.33"
}

variable "node_instance_types" {
  type    = list(string)
  default = ["t3.large"]
}

variable "github_repository" {
  description = "owner/repo allowed to assume the deploy role via GitHub OIDC (environment 'demo' only)."
  type        = string
}

variable "enable_data_tier" {
  description = "RDS PostgreSQL + ElastiCache. The application does NOT use them until Phases 4-5 are built."
  type        = bool
  default     = false
}

variable "postgres_engine_version" {
  description = "VERIFY with: aws rds describe-db-engine-versions --engine postgres"
  type        = string
  default     = "17"
}

variable "db_instance_class" {
  type    = string
  default = "db.t4g.medium"
}

variable "db_multi_az" {
  type    = bool
  default = false
}

variable "redis_engine_version" {
  description = "VERIFY with: aws elasticache describe-cache-engine-versions --engine redis"
  type        = string
  default     = "7.1"
}

variable "redis_parameter_family" {
  type    = string
  default = "redis7"
}

variable "cache_node_type" {
  type    = string
  default = "cache.t4g.small"
}
