terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source = "hashicorp/aws"
      # 5.x on purpose: I apply this against LocalStack, and from 6.0 the
      # provider makes calls LocalStack community answers with a 501 (found in
      # Session 19). Against a real AWS account "~> 6.0" works as well.
      version = "~> 5.0"
    }
  }

  # Local state for the LocalStack runs. For a real account, state belongs in
  # S3 with a DynamoDB lock table; see backend.tf.example.
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.project
      Environment = var.environment
      ManagedBy   = "terraform"
      Repo        = "LAVYA255/devops-heros"
    }
  }
}
