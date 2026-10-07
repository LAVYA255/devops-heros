terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source = "hashicorp/aws"
      # Pinned to 5.x because this project is applied against LocalStack.
      # From 6.0 the AWS provider reads bucket tags through the s3control API
      # (ListTagsForResource), and LocalStack community does not implement that
      # route, so every plan/apply/destroy fails with a 501 even though the
      # bucket itself is created correctly. Against real AWS, "~> 6.0" is fine.
      version = "~> 5.0"
    }
  }
}
