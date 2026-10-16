output "vpc_id" {
  value = aws_vpc.main.id
}

output "availability_zones" {
  value = local.azs
}

output "public_subnet_ids" {
  value = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  value = aws_subnet.private[*].id
}

output "nat_gateway_public_ips" {
  description = "Outbound traffic from the nodes leaves from these addresses (useful for allow-lists)."
  value       = aws_eip.nat[*].public_ip
}

output "cluster_name" {
  value = var.create_eks ? aws_eks_cluster.main[0].name : null
}

output "cluster_endpoint" {
  value = var.create_eks ? aws_eks_cluster.main[0].endpoint : null
}

output "cluster_version" {
  value = var.create_eks ? aws_eks_cluster.main[0].version : null
}

output "configure_kubectl" {
  description = "Run this after apply to point kubectl at the new cluster."
  value       = var.create_eks ? "aws eks update-kubeconfig --region ${var.aws_region} --name ${aws_eks_cluster.main[0].name}" : "EKS not created (create_eks = false)"
}
