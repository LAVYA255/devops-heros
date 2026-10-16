variable "aws_region" {
  description = "Region to build in. ap-south-1 (Mumbai) is the closest to me."
  type        = string
  default     = "ap-south-1"
}

variable "project" {
  description = "Name prefix for every resource."
  type        = string
  default     = "kharcha"
}

variable "environment" {
  description = "Environment name, part of every resource name."
  type        = string
  default     = "prod"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be dev, staging or prod."
  }
}

# ------------------------------------------------------------------ network
variable "vpc_cidr" {
  description = "Address space for the VPC. Subnets are carved out of it with cidrsubnet()."
  type        = string
  default     = "10.20.0.0/16"
}

variable "az_count" {
  description = "How many availability zones to spread across. EKS needs at least two."
  type        = number
  default     = 2

  validation {
    condition     = var.az_count >= 2 && var.az_count <= 3
    error_message = "az_count must be 2 or 3 (EKS requires subnets in at least two AZs)."
  }
}

variable "single_nat_gateway" {
  description = <<-EOT
    One NAT gateway shared by all private subnets (cheaper, but one AZ outage
    cuts every node off from the internet) or one per AZ (about 3x the NAT cost).
  EOT
  type        = bool
  default     = true
}

variable "flow_log_retention_days" {
  description = "How long VPC flow logs are kept in CloudWatch."
  type        = number
  default     = 14
}

# ------------------------------------------------------------------ EKS
variable "create_eks" {
  description = <<-EOT
    Create the EKS cluster and node group. Set to false to build only the
    network, which is what I apply on LocalStack: the free community edition
    does not emulate EKS at all.
  EOT
  type        = bool
  default     = true
}

variable "cluster_version" {
  description = "Kubernetes version for the control plane."
  type        = string
  default     = "1.34"
}

variable "endpoint_public_access" {
  description = <<-EOT
    Expose the Kubernetes API endpoint on the internet. Off by default: the API
    is then reachable only from inside the VPC. Turn it on together with
    public_access_cidrs set to your own IP to run kubectl from a laptop.
  EOT
  type        = bool
  default     = false
}

variable "public_access_cidrs" {
  description = "Who may reach a public API endpoint, e.g. [\"203.0.113.7/32\"]. Never the whole internet."
  type        = list(string)
  default     = []

  validation {
    condition     = !contains(var.public_access_cidrs, "0.0.0.0/0")
    error_message = "Refusing to open the Kubernetes API to 0.0.0.0/0. Use your own IP as a /32."
  }
}

variable "node_instance_types" {
  description = "EC2 types for the managed node group. t3.medium is the smallest that fits the app plus system pods comfortably."
  type        = list(string)
  default     = ["t3.medium"]
}

variable "node_desired_size" {
  type    = number
  default = 2
}

variable "node_min_size" {
  type    = number
  default = 2
}

variable "node_max_size" {
  description = "Upper bound for the cluster autoscaler. The app's HPA goes up to 6 backend pods."
  type        = number
  default     = 4
}

variable "node_disk_size" {
  description = "Root volume per node, in GiB."
  type        = number
  default     = 30
}
