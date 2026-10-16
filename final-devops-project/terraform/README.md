# Terraform: AWS VPC + EKS

Infrastructure for running Kharcha on AWS: a two-AZ VPC and an EKS cluster with a managed node group.

**Honest scope.** Every command below really ran, against **LocalStack 3.8.1** (an AWS emulator in Docker), not a real AWS account. No AWS credentials were used anywhere in this project. The `.tf` files are ordinary AWS Terraform and are written for a real account. LocalStack's free edition emulates EC2, IAM, KMS, CloudWatch Logs and STS, so the whole network applies for real. It does **not** emulate EKS at all, and I show that failure instead of hiding it. The section at the end has the commands for a real account.

| File | What |
| --- | --- |
| [`versions.tf`](./versions.tf) | Terraform >= 1.6, AWS provider `~> 5.0`, default tags on everything |
| [`variables.tf`](./variables.tf) | Inputs with validation |
| [`network.tf`](./network.tf) | VPC, subnets, IGW, NAT, routes, flow logs, locked default SG |
| [`eks.tf`](./eks.tf) | IAM roles, KMS key, EKS cluster, node group, EBS CSI driver via Pod Identity |
| [`outputs.tf`](./outputs.tf) | IDs, endpoint, the `aws eks update-kubeconfig` command |
| [`terraform.tfvars.example`](./terraform.tfvars.example) | Copy to `terraform.tfvars` (git-ignored) |
| [`backend.tf.example`](./backend.tf.example) | S3 + DynamoDB remote state for a real account |

## What it builds

```text
                         VPC 10.20.0.0/16  (ap-south-1)
   ┌──────────────── ap-south-1a ─────────────┬──────────────── ap-south-1b ─────────────┐
   │ public  10.20.0.0/24    NAT gw, ELBs     │ public  10.20.1.0/24    ELBs             │──► Internet Gateway
   │ private 10.20.10.0/24   EKS nodes        │ private 10.20.11.0/24   EKS nodes        │──► NAT (outbound only)
   └──────────────────────────────────────────┴──────────────────────────────────────────┘
          EKS control plane (AWS-managed), API endpoint private by default
```

- **Nodes never get a public IP.** They sit in private subnets and reach the internet (image pulls, AWS APIs) through the NAT gateway. The only way in from outside is a load balancer in a public subnet, created by the ingress controller.
- **Subnets are tagged for EKS** (`kubernetes.io/role/elb`, `kubernetes.io/role/internal-elb`, `kubernetes.io/cluster/<name>`), so load balancers land in the right tier automatically.
- **One NAT gateway** by default (`single_nat_gateway = true`), with the trade-off written next to the variable: one AZ outage cuts every node off from the internet, but one per AZ triples the NAT bill. Each private subnet has its own route table, so switching later only changes route targets.
- **VPC flow logs** to CloudWatch for 14 days, and the VPC's default security group locked to no rules at all.

EKS, with security defaults rather than the console's:

- **API endpoint private-only by default.** To use kubectl from a laptop you set `endpoint_public_access = true` **and** list your own IP. A validation refuses `0.0.0.0/0`, and a precondition refuses public access with an empty list.
- **Secrets encrypted with my own KMS key** (yearly rotation), not just AWS's default disk encryption.
- **All five control-plane log types on**, into a log group Terraform creates first, so the retention is 14 days instead of forever.
- **Access entries** (`authentication_mode = "API"`) instead of the old `aws-auth` ConfigMap.
- **Managed node group:** AL2023, t3.medium, 2 to 4 nodes, `max_unavailable = 1` during upgrades (the chart's PodDisruptionBudgets keep the app serving), and `desired_size` ignored after creation so a cluster autoscaler can own it.
- **EBS CSI driver** with its IAM role attached through **EKS Pod Identity** to the driver's own service account only. The Postgres StatefulSet needs this for its volume; giving the policy to the node role instead would hand it to every pod on the node.

## The runs

### Validate and guard rails

```text
LocalStack 3.8.1
{'ec2': 'available', 'iam': 'available', 'kms': 'available', 'logs': 'available', 'sts': 'available', 'eks': 'NOT PROVIDED'}
- Installed hashicorp/aws v5.100.0 (signed by HashiCorp)
fmt: clean
Success! The configuration is valid.

$ tflocal plan -var 'public_access_cidrs=["0.0.0.0/0"]'
Error: Invalid value for variable   (on variables.tf line 84: variable "public_access_cidrs")
$ tflocal plan -var environment=qa
Error: Invalid value for variable   (on variables.tf line 13: variable "environment")
```

### The full plan: 39 resources

```text
Plan: 39 to add, 0 to change, 0 to destroy.
   2  aws_cloudwatch_log_group        1  aws_internet_gateway
   1  aws_default_security_group      1  aws_kms_alias
   1  aws_eip                         1  aws_kms_key
   2  aws_eks_addon                   1  aws_nat_gateway
   1  aws_eks_cluster                 3  aws_route
   1  aws_eks_node_group              3  aws_route_table
   1  aws_eks_pod_identity_association 4  aws_route_table_association
   1  aws_flow_log                    4  aws_subnet
   4  aws_iam_role                    1  aws_vpc
   1  aws_iam_role_policy
   5  aws_iam_role_policy_attachment

aws_eks_cluster.main[0]:  name "kharcha-prod", version "1.34", authentication_mode "API",
                          endpoint_private_access true, endpoint_public_access false
aws_eks_node_group.main[0]: AL2023_x86_64_STANDARD, ON_DEMAND, 30 GiB, desired 2 / min 2 / max 4
```

### Apply the network (create_eks = false): 23 resources

```text
aws_vpc.main: Creation complete after 10s
...
aws_route.private_nat[1]: Creation complete after 0s
Apply complete! Resources: 23 added, 0 changed, 0 destroyed.

vpc_id             = "vpc-15a997ea"
availability_zones = ["ap-south-1a", "ap-south-1b"]
```

Then asked the (emulated) AWS API directly, independent of Terraform's state:

```text
|  kharcha-prod-public-ap-south-1a  |  10.20.0.0/24  |  ap-south-1a |  False  |
|  kharcha-prod-private-ap-south-1a |  10.20.10.0/24 |  ap-south-1a |  False  |
|  kharcha-prod-private-ap-south-1b |  10.20.11.0/24 |  ap-south-1b |  False  |
|  kharcha-prod-public-ap-south-1b  |  10.20.1.0/24  |  ap-south-1b |  False  |

kharcha-prod-public-rt                igw-88f3c7c2
kharcha-prod-private-rt-ap-south-1a   nat-03525aadf15bb7555
kharcha-prod-private-rt-ap-south-1b   nat-03525aadf15bb7555
```

The last column is `MapPublicIpOnLaunch`: false everywhere. Public routes go to the internet gateway, both private tables to the one NAT gateway. A second plan reports no changes, so the config is idempotent.

### The EKS half on LocalStack

```text
aws_kms_key.eks[0]: Creation complete after 8s
aws_iam_role.cluster[0]: Creation complete after 0s
...
Error: creating EKS Cluster (kharcha-prod): operation error EKS: CreateCluster,
https response error StatusCode: 501, ... api error InternalFailure:
API for service 'eks' not yet implemented or pro feature
```

Everything up to the cluster is created (IAM roles, policy attachments, KMS key, log group). The cluster call gets LocalStack's 501. That is the reason `create_eks` exists. Then `tflocal destroy` removed all 34 resources and the state is empty.

Captures: `screenshots/terminal/17-terraform-validate.png` to `20-terraform-eks-localstack.png`.

## Running it on a real AWS account

This creates billable resources: the EKS control plane (USD 0.10/hour), a NAT gateway (hourly plus per GB) and two t3.medium nodes. That is around USD 6 a day in ap-south-1 before data transfer. Destroy it when done.

```bash
cd final-devops-project/terraform
cp terraform.tfvars.example terraform.tfvars      # set your IP if you want public API access
# optional but recommended: cp backend.tf.example backend.tf and create the bucket/table

aws sts get-caller-identity                        # confirm which account you are in
terraform init
terraform plan -out tfplan
terraform apply tfplan
$(terraform output -raw configure_kubectl)         # aws eks update-kubeconfig ...
kubectl get nodes
```

Then the app, exactly as on Minikube, plus a default StorageClass (EKS 1.30+ ships none marked default) and the ingress controller:

```bash
kubectl apply -f - <<'EOF'
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: gp3
  annotations: {storageclass.kubernetes.io/is-default-class: "true"}
provisioner: ebs.csi.aws.com
parameters: {type: gp3}
volumeBindingMode: WaitForFirstConsumer
EOF
helm upgrade --install ingress-nginx ingress-nginx --repo https://kubernetes.github.io/ingress-nginx \
  -n ingress-nginx --create-namespace --set controller.config.worker-processes=4
kubectl apply -f ../kubernetes/namespace.yaml -f ../kubernetes/resource-guardrails.yaml
bash ../kubernetes/create-db-secret.sh kharcha
helm upgrade --install kharcha ../helm/kharcha -n kharcha -f ../gitops/values-minikube.yaml \
  --set ingress.host=<your host>
```

Tear down: `helm uninstall` the releases first (so the load balancer and EBS volumes they created are deleted), then `terraform destroy`.
