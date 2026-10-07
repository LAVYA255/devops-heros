provider "aws" {
  region = var.aws_region
}

# Tags applied to everything. One merge() per resource keeps them consistent and
# makes the whole stack findable and billable by tag.
locals {
  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
    Session     = "19"
  }
  name_prefix = "${var.project_name}-${var.environment}"
}

# Data sources read things that already exist rather than creating them.
data "aws_availability_zones" "available" {
  state = "available"
}

# ---------------------------------------------------------------- networking
resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = merge(local.common_tags, { Name = "${local.name_prefix}-vpc" })
}

# Public subnet: has a route to the internet gateway, so instances here are
# reachable from outside and get a public IP on launch.
resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = var.public_subnet_cidr
  availability_zone       = data.aws_availability_zones.available.names[0]
  map_public_ip_on_launch = true

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-public-subnet"
    Tier = "public"
  })
}

# Private subnet: no route to the IGW. Databases and internal services live here.
resource "aws_subnet" "private" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = var.private_subnet_cidr
  availability_zone = data.aws_availability_zones.available.names[0]

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-private-subnet"
    Tier = "private"
  })
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = merge(local.common_tags, { Name = "${local.name_prefix}-igw" })
}

# A subnet is only "public" because its route table sends 0.0.0.0/0 to an IGW.
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = merge(local.common_tags, { Name = "${local.name_prefix}-public-rt" })
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

# The private route table has only the implicit local route, so there is no
# path to the internet at all. Adding a NAT gateway here would give outbound
# only access, which is the usual production shape.
resource "aws_route_table" "private" {
  vpc_id = aws_vpc.main.id

  tags = merge(local.common_tags, { Name = "${local.name_prefix}-private-rt" })
}

resource "aws_route_table_association" "private" {
  subnet_id      = aws_subnet.private.id
  route_table_id = aws_route_table.private.id
}

# ---------------------------------------------------------------- security
resource "aws_security_group" "web" {
  name        = "${local.name_prefix}-web-sg"
  description = "HTTP/HTTPS from anywhere, SSH only from inside the VPC"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "HTTP from the internet"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS from the internet"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # Deliberately not 0.0.0.0/0. An SSH port open to the world is the single most
  # common finding in a cloud security review.
  ingress {
    description = "SSH from inside the VPC only"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.allowed_ssh_cidr]
  }

  egress {
    description = "All outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, { Name = "${local.name_prefix}-web-sg" })
}

# ---------------------------------------------------------------- compute
data "aws_ami" "amazon_linux" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["amzn2-ami-hvm-*-x86_64-gp2"]
  }
}

resource "aws_instance" "web" {
  # Implicit dependencies: Terraform reads these references and works out that
  # the subnet and security group must exist first. No depends_on needed.
  ami                    = data.aws_ami.amazon_linux.id
  instance_type          = var.instance_type
  subnet_id              = aws_subnet.public.id
  vpc_security_group_ids = [aws_security_group.web.id]

  user_data = <<-EOF
    #!/bin/bash
    yum install -y httpd
    systemctl enable --now httpd
    echo "<h1>${local.name_prefix} web server</h1>" > /var/www/html/index.html
  EOF

  tags = merge(local.common_tags, { Name = "${local.name_prefix}-web" })
}

# ---------------------------------------------------------------- storage
resource "aws_s3_bucket" "assets" {
  bucket        = "${local.name_prefix}-assets-${random_id.suffix.hex}"
  force_destroy = true

  tags = merge(local.common_tags, { Name = "${local.name_prefix}-assets" })
}

# Bucket names are globally unique across all of AWS, so a random suffix keeps
# repeated applies from colliding.
resource "random_id" "suffix" {
  byte_length = 4
}

resource "aws_s3_bucket_versioning" "assets" {
  bucket = aws_s3_bucket.assets.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "assets" {
  bucket = aws_s3_bucket.assets.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
