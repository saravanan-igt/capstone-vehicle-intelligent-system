output "cluster_name" {
  value = module.eks.cluster_name
}

output "ecr_repositories" {
  value = { for k, r in aws_ecr_repository.app : k => r.repository_url }
}

output "github_deploy_role_arn" {
  value = aws_iam_role.github_deploy.arn
}

output "documents_bucket" {
  value = aws_s3_bucket.documents.bucket
}

output "app_secret_arn" {
  value = aws_secretsmanager_secret.app.arn
}

output "postgres_endpoint" {
  value = try(aws_db_instance.postgres[0].address, null)
}

output "redis_endpoints" {
  value = { for k, g in aws_elasticache_replication_group.redis : k => g.primary_endpoint_address }
}
