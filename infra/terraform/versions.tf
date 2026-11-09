terraform {
  # eks module 21.29.0 requires >= 1.5.7; S3 native state locking (use_lockfile) requires >= 1.10.
  required_version = ">= 1.10.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.72" # verified latest 6.72.0 on 2026-11-09; vpc 6.7.3 needs >= 6.28, eks 21.29.0 needs >= 6.59
    }
  }

  # Partial configuration: terraform init -backend-config=backend.hcl (see backend.hcl.example).
  backend "s3" {}
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project     = "vehicle-loan-advisor"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}
