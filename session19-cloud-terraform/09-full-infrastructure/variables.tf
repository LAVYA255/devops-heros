variable "aws_region" {
  type        = string
  description = "Region to build the infrastructure in."
  default     = "us-east-1"
}

variable "project_name" {
  type        = string
  description = "Prefix applied to every resource name so the stack is easy to find and delete."
  default     = "session19"
}

variable "environment" {
  type        = string
  description = "Environment tag (dev, staging, prod)."
  default     = "dev"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be one of: dev, staging, prod."
  }
}

variable "vpc_cidr" {
  type        = string
  description = "CIDR block for the VPC. /16 gives 65,536 addresses."
  default     = "10.20.0.0/16"
}

variable "public_subnet_cidr" {
  type        = string
  description = "CIDR for the public subnet. Must sit inside vpc_cidr."
  default     = "10.20.1.0/24"
}

variable "private_subnet_cidr" {
  type        = string
  description = "CIDR for the private subnet. Must sit inside vpc_cidr."
  default     = "10.20.2.0/24"
}

variable "instance_type" {
  type        = string
  description = "EC2 instance type for the web server."
  default     = "t3.micro"
}

variable "allowed_ssh_cidr" {
  type        = string
  description = "Who may SSH to the instance. 0.0.0.0/0 is deliberately not the default."
  default     = "10.20.0.0/16"
}
