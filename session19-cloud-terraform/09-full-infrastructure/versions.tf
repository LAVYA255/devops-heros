terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source = "hashicorp/aws"
      # Pinned to 5.x because this is applied against LocalStack. From 6.0 the
      # provider reads S3 bucket tags via the s3control API, which LocalStack
      # community does not implement, and every apply fails with a 501.
      # Against real AWS, "~> 6.0" works fine.
      version = "~> 5.0"
    }
  }
}
