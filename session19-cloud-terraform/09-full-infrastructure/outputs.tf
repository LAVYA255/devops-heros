output "vpc_id" {
  description = "ID of the VPC."
  value       = aws_vpc.main.id
}

output "vpc_cidr" {
  description = "CIDR block of the VPC."
  value       = aws_vpc.main.cidr_block
}

output "public_subnet_id" {
  description = "ID of the public subnet."
  value       = aws_subnet.public.id
}

output "private_subnet_id" {
  description = "ID of the private subnet."
  value       = aws_subnet.private.id
}

output "internet_gateway_id" {
  description = "ID of the internet gateway."
  value       = aws_internet_gateway.main.id
}

output "security_group_id" {
  description = "ID of the web security group."
  value       = aws_security_group.web.id
}

output "instance_id" {
  description = "ID of the EC2 instance."
  value       = aws_instance.web.id
}

output "instance_private_ip" {
  description = "Private IP of the EC2 instance."
  value       = aws_instance.web.private_ip
}

output "instance_public_ip" {
  description = "Public IP of the EC2 instance."
  value       = aws_instance.web.public_ip
}

output "s3_bucket_name" {
  description = "Name of the assets bucket."
  value       = aws_s3_bucket.assets.bucket
}

output "s3_bucket_arn" {
  description = "ARN of the assets bucket."
  value       = aws_s3_bucket.assets.arn
}

output "infrastructure_summary" {
  description = "Everything that was built, in one map."
  value = {
    region            = var.aws_region
    environment       = var.environment
    vpc               = aws_vpc.main.id
    public_subnet     = aws_subnet.public.id
    private_subnet    = aws_subnet.private.id
    security_group    = aws_security_group.web.id
    instance          = aws_instance.web.id
    bucket            = aws_s3_bucket.assets.bucket
    availability_zone = aws_subnet.public.availability_zone
  }
}
