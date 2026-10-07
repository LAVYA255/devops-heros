# EC2: Elastic Compute Cloud

**Session 18, Task 2.2** | Author: Lavya ([@LAVYA255](https://github.com/LAVYA255))

## What EC2 is

EC2 is AWS's virtual machine service. You pick an operating system image, a size, a network to put it in and a firewall, and you get a server you have full root access to. It is the oldest and most general compute service on AWS: anything you could run on a physical server, you can run here.

The trade-off against containers and serverless is that you own more of the stack. You patch the OS, you handle scaling, you decide what runs on boot. In exchange you get complete control, which is why EC2 is still what sits under most EKS node groups.

## AMI, Amazon Machine Image

The template an instance boots from: the root volume contents plus launch metadata. An AMI determines the OS, pre-installed packages and any configuration baked in.

- **AWS-provided**: Amazon Linux 2023, Ubuntu, Windows Server, Red Hat.
- **Marketplace**: vendor images, sometimes with an hourly licence cost on top.
- **Custom**: you configure an instance exactly how you want it, then create an AMI from it. Every instance launched from it starts identical.

AMIs are regional. An AMI built in `ap-south-1` has to be copied before it can be used in `us-east-1`, and the copy gets a new ID. That catches people out when they hardcode an AMI ID into a Terraform file and then deploy to a second region.

The usual pattern is to bake a "golden AMI" with Packer in a pipeline, so instances boot ready rather than spending five minutes installing packages via user data. That is the same immutable-infrastructure idea as a container image.

In my Session 19 Terraform I avoided hardcoding an ID entirely by looking it up:

```hcl
data "aws_ami" "amazon_linux" {
  most_recent = true
  owners      = ["amazon"]
  filter {
    name   = "name"
    values = ["amzn2-ami-hvm-*-x86_64-gp2"]
  }
}
```

## Instance types

The type sets CPU, memory, network and storage performance. Naming is `family + generation + size`, so `t3.micro` is the T family, generation 3, micro size.

| Family | Optimised for | Examples |
| --- | --- | --- |
| **T** | General purpose, burstable | `t3.micro`, `t4g.small`. Cheap, accumulates CPU credits while idle and spends them under load. Good for dev and bursty web apps, bad for sustained CPU. |
| **M** | General purpose, balanced | `m7i.large`. The sensible default for a steady workload. |
| **C** | Compute | `c7i.xlarge`. High CPU-to-memory. Batch processing, encoding, game servers. |
| **R / X** | Memory | `r7i.large`. Databases, caches, in-memory analytics. |
| **I / D** | Storage | `i4i.large`. High local NVMe throughput. |
| **P / G / Inf** | Accelerated | GPUs and inference chips for ML. |

A `g` in the name (`t4g`, `m7g`) means Graviton, AWS's ARM processors, which are usually noticeably cheaper for the same performance if your workload builds for ARM.

Sizing advice that actually holds: start smaller than you think, measure, then resize. Changing instance type is a stop, modify, start, which is minutes of downtime for a single instance and nothing at all behind a load balancer.

## Key pairs

An SSH key pair for logging in. AWS keeps the public key and injects it into the instance's `authorized_keys` at first boot. You keep the private key, and **AWS cannot give you another copy** if you lose it.

Losing the private key to a running instance is recoverable but annoying: detach the root volume, attach it to another instance, edit `authorized_keys`, reattach.

In practice, modern setups often skip SSH entirely and use **Session Manager** instead. No key to lose, no port 22 open, no bastion host, and every session is logged to CloudTrail. If you can use it, it is strictly better.

## Security Groups

A stateful virtual firewall attached to an instance's network interface.

- **Allow rules only.** There is no deny rule. Anything not explicitly allowed is blocked.
- **Stateful.** If you allow an inbound request, the response is automatically allowed back out. You do not write a matching outbound rule.
- Rules reference ports, protocols, and either CIDR blocks or **other security groups**.
- Default outbound is allow-all; default inbound is deny-all.
- Several groups can attach to one instance, and the effect is the union.

Referencing another security group as the source is the feature worth knowing. Instead of "allow 3306 from 10.0.2.0/24", you write "allow 3306 from `sg-app`". The rule then follows the application servers wherever they are and however they scale, and no IP range needs maintaining.

The classic mistake is `0.0.0.0/0` on port 22. In my Session 19 Terraform I deliberately did not do that:

```hcl
ingress {
  description = "SSH from inside the VPC only"
  from_port   = 22
  to_port     = 22
  protocol    = "tcp"
  cidr_blocks = [var.allowed_ssh_cidr]   # the VPC CIDR, not the internet
}
```

Security groups vs Network ACLs: security groups are stateful and attach to instances; NACLs are stateless (you need explicit rules both ways), attach to subnets, and support deny rules. Day to day you use security groups and leave the default NACL alone.

## EBS, Elastic Block Store

Network-attached block storage. An EBS volume behaves like a disk, persists independently of the instance, and can be detached and reattached.

| Type | Use |
| --- | --- |
| `gp3` | General purpose SSD. The sensible default; IOPS and throughput are configurable independently of size. |
| `gp2` | Older general purpose SSD where IOPS scales with size. Prefer gp3. |
| `io2` | Provisioned IOPS, for demanding databases. |
| `st1` / `sc1` | Throughput-optimised and cold HDD, for big sequential workloads and archives. |

Key behaviours:

- An EBS volume lives in **one availability zone** and can only attach to an instance in that AZ.
- **Snapshots** are incremental, stored in S3, and are regional, so they are how you move a volume to another AZ or region.
- Encryption at rest with KMS is a checkbox and has no meaningful performance cost. Turn it on.
- Root volumes default to **delete on termination**; attached data volumes default to keeping. Worth checking, because the default is not always what you want.

**Instance store** is the other option: physical disks on the host. Very fast, and completely lost when the instance stops. Only for caches and scratch.

The relationship to Kubernetes storage from Session 13 is direct: an EBS volume is what a `PersistentVolume` is backed by on EKS, and "a volume lives in one AZ" is exactly why a pod with an EBS-backed PVC cannot be rescheduled to a node in a different AZ.

## Public vs private IP

Every instance gets a **private IP** from its subnet's CIDR range. That is its real address, it does not change for the instance's life, and it is what everything inside the VPC uses.

A **public IP** is optional and is not configured on the instance at all. The instance has no idea it has one. The internet gateway does a 1:1 NAT between the public address and the private address. If you run `ip addr` on an EC2 instance, you only ever see the private IP.

| | Private IP | Public IP (auto-assigned) | Elastic IP |
| --- | --- | --- | --- |
| Changes on stop/start | No | **Yes** | No |
| Reachable from internet | No | Yes | Yes |
| Costs money | No | No, while attached to a running instance | Yes, when **not** attached |
| Good for | Everything internal | Throwaway instances | Something that needs a stable public address |

The "changes on stop/start" row is the one that bites people: you stop an instance overnight to save money, and in the morning its public IP is different and your DNS record is stale. An Elastic IP fixes that, and so does putting the instance behind a load balancer, which is usually better.

An instance only gets a public IP if it is in a subnet with `map_public_ip_on_launch` enabled and that subnet routes `0.0.0.0/0` to an internet gateway. Both conditions. That is exactly the public/private subnet split in my Session 19 project.

## Instance lifecycle

```
pending ──► running ──► stopping ──► stopped ──► (start) ──► running
                │                         │
                │                         └──► terminated
                └──► shutting-down ──► terminated
```

| State | Billed for compute | Notes |
| --- | --- | --- |
| `pending` | No | Booting |
| `running` | Yes | Normal |
| `stopping` / `stopped` | **No** | Still billed for EBS storage. Public IP released, private IP kept. May start on different hardware. |
| `terminated` | No | Gone. Root volume deleted unless configured otherwise. Not recoverable. |

Stop and terminate are very different, and `DisableApiTermination` (termination protection) is worth setting on anything you care about.

**Hibernate** is a third option: RAM is written to the root EBS volume and restored on start, so processes survive. Useful for long-warming applications.

**Pricing models** matter more than most people expect:

- **On-Demand**: pay per second, no commitment. The default.
- **Reserved / Savings Plans**: commit to 1 or 3 years for up to ~70% off. For steady baseline load this is just free money left on the table if unused.
- **Spot**: spare capacity at up to 90% off, but AWS can reclaim it with two minutes' notice. Excellent for batch jobs, CI runners and stateless workers; unusable for a database.

## Common use cases

- **Web and application servers**, usually in an Auto Scaling Group behind an Application Load Balancer across several AZs.
- **Kubernetes nodes.** EKS managed node groups are EC2 instances. Everything above applies to them.
- **Databases you want to manage yourself**, when RDS does not support what you need.
- **Batch and CI**, typically on Spot for the price.
- **Lift-and-shift migrations**, where an existing VM moves to the cloud mostly unchanged.

When *not* to use EC2: if the workload is a short-lived function, Lambda is cheaper and simpler. If it is a container, ECS or EKS handles scheduling for you. EC2 is the right answer when you need the whole machine.

## References

- https://docs.aws.amazon.com/ec2/
- https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/instance-types.html
- https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-security-groups.html
- https://docs.aws.amazon.com/ebs/latest/userguide/ebs-volume-types.html
