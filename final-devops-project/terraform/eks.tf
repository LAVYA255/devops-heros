# EKS control plane + one managed node group in the private subnets.
#
# Everything here is behind var.create_eks. On LocalStack I set it to false
# because the community edition has no EKS API; against a real account it is
# on by default.

locals {
  eks_count = var.create_eks ? 1 : 0
}

# ------------------------------------------------------------------ IAM: control plane
data "aws_iam_policy_document" "cluster_assume" {
  statement {
    actions = ["sts:AssumeRole", "sts:TagSession"]
    principals {
      type        = "Service"
      identifiers = ["eks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "cluster" {
  count              = local.eks_count
  name               = "${local.name}-eks-cluster"
  assume_role_policy = data.aws_iam_policy_document.cluster_assume.json
}

resource "aws_iam_role_policy_attachment" "cluster" {
  count      = local.eks_count
  role       = aws_iam_role.cluster[0].name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
}

# ------------------------------------------------------------------ IAM: worker nodes
data "aws_iam_policy_document" "node_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "node" {
  count              = local.eks_count
  name               = "${local.name}-eks-node"
  assume_role_policy = data.aws_iam_policy_document.node_assume.json
}

# The three AWS-managed policies every EKS worker needs: join the cluster,
# run the VPC CNI (pod IPs from the VPC), and pull from ECR (the EKS add-on
# images live there). My own images come from GHCR, which needs no IAM.
resource "aws_iam_role_policy_attachment" "node" {
  for_each = var.create_eks ? toset([
    "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy",
    "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy",
    "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly",
  ]) : toset([])

  role       = aws_iam_role.node[0].name
  policy_arn = each.value
}

# ------------------------------------------------------------------ encryption + logs
# Kubernetes Secrets (the database password) are encrypted in etcd with a key
# I own and that rotates yearly, instead of only AWS's default disk encryption.
resource "aws_kms_key" "eks" {
  count                   = local.eks_count
  description             = "Envelope encryption for ${local.name} Kubernetes secrets"
  enable_key_rotation     = true
  deletion_window_in_days = 7
}

resource "aws_kms_alias" "eks" {
  count         = local.eks_count
  name          = "alias/${local.name}-eks"
  target_key_id = aws_kms_key.eks[0].key_id
}

# Created up front so the retention is mine. If EKS creates this group itself
# it keeps logs forever, which quietly costs money.
resource "aws_cloudwatch_log_group" "eks" {
  count             = local.eks_count
  name              = "/aws/eks/${local.name}/cluster"
  retention_in_days = 14
}

# ------------------------------------------------------------------ the cluster
resource "aws_eks_cluster" "main" {
  count    = local.eks_count
  name     = local.name
  version  = var.cluster_version
  role_arn = aws_iam_role.cluster[0].arn

  enabled_cluster_log_types = ["api", "audit", "authenticator", "controllerManager", "scheduler"]

  vpc_config {
    # Control-plane network interfaces go in the private subnets.
    subnet_ids              = aws_subnet.private[*].id
    endpoint_private_access = true
    endpoint_public_access  = var.endpoint_public_access
    public_access_cidrs     = var.endpoint_public_access ? var.public_access_cidrs : null
  }

  encryption_config {
    provider {
      key_arn = aws_kms_key.eks[0].arn
    }
    resources = ["secrets"]
  }

  # Access entries (IAM -> Kubernetes RBAC) instead of the old aws-auth
  # ConfigMap. Whoever runs terraform apply becomes cluster admin.
  access_config {
    authentication_mode                         = "API"
    bootstrap_cluster_creator_admin_permissions = true
  }

  lifecycle {
    precondition {
      condition     = !var.endpoint_public_access || length(var.public_access_cidrs) > 0
      error_message = "endpoint_public_access = true needs public_access_cidrs, e.g. [\"<your ip>/32\"]."
    }
  }

  depends_on = [
    aws_iam_role_policy_attachment.cluster,
    aws_cloudwatch_log_group.eks,
  ]
}

# ------------------------------------------------------------------ nodes
resource "aws_eks_node_group" "main" {
  count           = local.eks_count
  cluster_name    = aws_eks_cluster.main[0].name
  node_group_name = "${local.name}-general"
  node_role_arn   = aws_iam_role.node[0].arn
  subnet_ids      = aws_subnet.private[*].id

  ami_type       = "AL2023_x86_64_STANDARD"
  capacity_type  = "ON_DEMAND"
  instance_types = var.node_instance_types
  disk_size      = var.node_disk_size

  scaling_config {
    desired_size = var.node_desired_size
    min_size     = var.node_min_size
    max_size     = var.node_max_size
  }

  # Replace nodes one at a time during upgrades. Together with the chart's
  # PodDisruptionBudgets this keeps the app serving through a node rollout.
  update_config {
    max_unavailable = 1
  }

  labels = {
    workload = "general"
  }

  lifecycle {
    # A cluster autoscaler changes desired_size at runtime. Without this,
    # every terraform apply would drag it back to the number in this file.
    ignore_changes = [scaling_config[0].desired_size]
  }

  # Nodes must be able to reach the internet (through NAT) to join the cluster.
  depends_on = [
    aws_iam_role_policy_attachment.node,
    aws_route.private_nat,
  ]
}

# ------------------------------------------------------------------ add-ons
# Postgres runs as a StatefulSet with a PersistentVolumeClaim. On EKS that
# needs the EBS CSI driver, and the driver needs AWS permissions to create
# volumes. EKS Pod Identity gives those permissions to the driver's service
# account only, not to every pod on the node.
resource "aws_eks_addon" "pod_identity" {
  count        = local.eks_count
  cluster_name = aws_eks_cluster.main[0].name
  addon_name   = "eks-pod-identity-agent"
  depends_on   = [aws_eks_node_group.main]
}

data "aws_iam_policy_document" "ebs_csi_assume" {
  statement {
    actions = ["sts:AssumeRole", "sts:TagSession"]
    principals {
      type        = "Service"
      identifiers = ["pods.eks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ebs_csi" {
  count              = local.eks_count
  name               = "${local.name}-ebs-csi"
  assume_role_policy = data.aws_iam_policy_document.ebs_csi_assume.json
}

resource "aws_iam_role_policy_attachment" "ebs_csi" {
  count      = local.eks_count
  role       = aws_iam_role.ebs_csi[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy"
}

resource "aws_eks_pod_identity_association" "ebs_csi" {
  count           = local.eks_count
  cluster_name    = aws_eks_cluster.main[0].name
  namespace       = "kube-system"
  service_account = "ebs-csi-controller-sa"
  role_arn        = aws_iam_role.ebs_csi[0].arn
}

resource "aws_eks_addon" "ebs_csi" {
  count        = local.eks_count
  cluster_name = aws_eks_cluster.main[0].name
  addon_name   = "aws-ebs-csi-driver"
  depends_on = [
    aws_eks_addon.pod_identity,
    aws_eks_pod_identity_association.ebs_csi,
  ]
}
