# Phase 4-5 data tier. Off by default: the current application build still uses SQLite and has no queue.
# Two Redis groups on purpose: BullMQ needs maxmemory-policy=noeviction, a cache wants allkeys-lru.

resource "aws_security_group" "data" {
  count       = var.enable_data_tier ? 1 : 0
  name        = "${var.name}-${var.environment}-data"
  description = "PostgreSQL and Redis reachable only from EKS nodes"
  vpc_id      = module.vpc.vpc_id
}

resource "aws_vpc_security_group_ingress_rule" "postgres" {
  count                        = var.enable_data_tier ? 1 : 0
  security_group_id            = aws_security_group.data[0].id
  referenced_security_group_id = module.eks.node_security_group_id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
}

resource "aws_vpc_security_group_ingress_rule" "redis" {
  count                        = var.enable_data_tier ? 1 : 0
  security_group_id            = aws_security_group.data[0].id
  referenced_security_group_id = module.eks.node_security_group_id
  ip_protocol                  = "tcp"
  from_port                    = 6379
  to_port                      = 6379
}

resource "aws_db_instance" "postgres" {
  count                               = var.enable_data_tier ? 1 : 0
  identifier                          = "${var.name}-${var.environment}"
  engine                              = "postgres"
  engine_version                      = var.postgres_engine_version
  instance_class                      = var.db_instance_class
  allocated_storage                   = 50
  max_allocated_storage               = 200
  storage_type                        = "gp3"
  storage_encrypted                   = true
  kms_key_id                          = aws_kms_key.app.arn
  db_name                             = "vla"
  username                            = "vla_admin"
  manage_master_user_password         = true # stored and rotated in Secrets Manager, never in state
  db_subnet_group_name                = module.vpc.database_subnet_group_name
  vpc_security_group_ids              = [aws_security_group.data[0].id]
  multi_az                            = var.db_multi_az
  backup_retention_period             = 7 # point-in-time recovery window (RPO ~5 min)
  copy_tags_to_snapshot               = true
  deletion_protection                 = true
  skip_final_snapshot                 = false
  final_snapshot_identifier           = "${var.name}-${var.environment}-final"
  iam_database_authentication_enabled = true
  auto_minor_version_upgrade          = true
  performance_insights_enabled        = true
  performance_insights_kms_key_id     = aws_kms_key.app.arn
}

resource "aws_elasticache_subnet_group" "redis" {
  count      = var.enable_data_tier ? 1 : 0
  name       = "${var.name}-${var.environment}"
  subnet_ids = module.vpc.private_subnets
}

locals {
  redis_groups = var.enable_data_tier ? {
    queue = "noeviction"
    cache = "allkeys-lru"
  } : {}
}

resource "aws_elasticache_parameter_group" "redis" {
  for_each = local.redis_groups
  name     = "${var.name}-${var.environment}-${each.key}"
  family   = var.redis_parameter_family

  parameter {
    name  = "maxmemory-policy"
    value = each.value
  }
}

resource "aws_elasticache_replication_group" "redis" {
  for_each                   = local.redis_groups
  replication_group_id       = "${var.name}-${var.environment}-${each.key}"
  description                = "${each.key} (${each.value})"
  engine                     = "redis"
  engine_version             = var.redis_engine_version
  node_type                  = var.cache_node_type
  num_cache_clusters         = 2
  automatic_failover_enabled = true
  multi_az_enabled           = true
  parameter_group_name       = aws_elasticache_parameter_group.redis[each.key].name
  subnet_group_name          = aws_elasticache_subnet_group.redis[0].name
  security_group_ids         = [aws_security_group.data[0].id]
  at_rest_encryption_enabled = true
  kms_key_id                 = aws_kms_key.app.arn
  transit_encryption_enabled = true
  snapshot_retention_limit   = each.key == "queue" ? 7 : 0
}
