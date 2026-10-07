# VPC: Virtual Private Cloud

**Session 18, Task 2.4** | Author: Lavya ([@LAVYA255](https://github.com/LAVYA255))

## What a VPC is

A VPC is your own isolated network inside AWS. You choose the IP range, carve it into subnets, decide what routes where, and control what can reach in or out. Nothing in a VPC is reachable from the internet unless you explicitly build a path for it.

Almost everything else sits inside one: EC2 instances, RDS databases, EKS nodes, Lambda functions attached to a VPC. If you understand the VPC, most AWS networking problems become obvious rather than mysterious.

A VPC is **regional**, and spans every availability zone in that region. Subnets are the per-AZ subdivision.

I built the whole thing in [Session 19](../../../session19-cloud-terraform/09-full-infrastructure), so the examples below are from that Terraform.

## CIDR

CIDR notation describes a range of IP addresses as `address/prefix-length`. The prefix is how many leading bits are fixed; the rest are available for hosts.

| CIDR | Addresses | Typical use |
| --- | --- | --- |
| `10.0.0.0/16` | 65,536 | A whole VPC |
| `10.0.1.0/24` | 256 | One subnet |
| `10.0.1.0/28` | 16 | A very small subnet |
| `0.0.0.0/0` | everything | "The internet", in a route table or security group |

Smaller prefix means a bigger range. A `/16` contains 256 `/24`s.

Rules worth knowing:

- A VPC CIDR must be between `/16` and `/28`.
- Use private ranges (RFC 1918): `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`.
- **You cannot change a VPC's CIDR after creation.** You can add secondary blocks, but the primary is fixed. Choose with room to grow.
- Plan for non-overlapping ranges across VPCs and your on-premise network, or peering and VPN will be impossible later. Two VPCs both using `10.0.0.0/16` can never be connected.

**AWS reserves 5 addresses in every subnet.** In `10.20.1.0/24` you get 251 usable, not 256:

| Address | Reserved for |
| --- | --- |
| `.0` | Network address |
| `.1` | VPC router |
| `.2` | DNS |
| `.3` | Future use |
| `.255` | Broadcast (not supported, still reserved) |

This matters on EKS, where every pod takes an IP from the subnet. A `/24` per subnet runs out faster than you expect.

My Session 19 layout:

```
VPC              10.20.0.0/16     65,536 addresses
├── public       10.20.1.0/24     251 usable
└── private      10.20.2.0/24     251 usable
```

## Subnets

A subnet is a slice of the VPC CIDR **pinned to one availability zone**. That AZ binding is the important part: it is why high availability means at least one subnet per AZ, and why an EBS-backed volume cannot follow a pod to another AZ.

There is no "public subnet" checkbox. A subnet is public **only** because its route table sends `0.0.0.0/0` to an internet gateway. That is the entire difference.

```hcl
resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.20.1.0/24"
  availability_zone       = data.aws_availability_zones.available.names[0]
  map_public_ip_on_launch = true          # instances here get a public IP
}

resource "aws_subnet" "private" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.20.2.0/24"
  availability_zone = data.aws_availability_zones.available.names[0]
  # no map_public_ip_on_launch, and no IGW route on its route table
}
```

The standard production shape is three tiers across at least two AZs: public subnets for load balancers and NAT gateways, private subnets for application servers, and isolated subnets with no outbound route at all for databases.

## Route tables

A route table is a list of "traffic for this destination goes to this target". Every subnet is associated with exactly one; unassociated subnets use the VPC's main route table.

Every route table has an **implicit local route** for the VPC CIDR that you cannot remove or override. That is why anything in the VPC can always reach anything else in the VPC, subject to security groups.

Routing is **longest prefix match**: the most specific route wins. A route for `10.20.5.0/24` beats one for `0.0.0.0/0`.

My two tables, verified after apply:

```
session19-dev-public-rt
  10.20.0.0/16  -> local
  0.0.0.0/0     -> igw-a6937758      <-- this line makes the subnet public

session19-dev-private-rt
  10.20.0.0/16  -> local             <-- no default route, no internet at all
```

That one-line difference is the whole public/private distinction, and seeing it in `describe-route-tables` output made it click properly.

## Internet Gateway

A horizontally-scaled, redundant component attached to the VPC that allows two-way traffic to the internet. It does not throttle and is not a bottleneck.

It does two jobs:

1. Provides the target for a `0.0.0.0/0` route.
2. Performs 1:1 NAT between an instance's public IP and its private IP. This is why an EC2 instance never sees its own public address in `ip addr`.

For an instance to actually be reachable from the internet, **four** things all have to be true. Missing any one produces the same "it doesn't work" symptom:

1. An IGW is attached to the VPC.
2. The subnet's route table has `0.0.0.0/0 -> igw`.
3. The instance has a public IP or Elastic IP.
4. The security group and NACL allow the traffic.

## NAT Gateway

Lets instances in **private** subnets reach out to the internet (for package updates, API calls, pulling container images) while remaining unreachable **from** the internet. Connections can only be initiated outbound.

Key facts:

- The NAT gateway itself lives in a **public** subnet and needs an Elastic IP.
- The **private** subnet's route table points `0.0.0.0/0` at the NAT gateway.
- It is AZ-specific. For real high availability you need one per AZ, otherwise an AZ failure cuts internet access for the private subnets in the others.
- **It costs money**: an hourly charge plus a per-GB data processing charge. At roughly $32/month per gateway plus data, three of them for HA is a real line item, and NAT data processing charges are a classic surprise on an AWS bill.

| | Internet Gateway | NAT Gateway |
| --- | --- | --- |
| Direction | Inbound and outbound | Outbound only |
| Attached to | The VPC | A specific subnet, in one AZ |
| Needs an EIP | No | Yes |
| Cost | Free | Hourly + per GB |
| Used by | Public subnets | Private subnets |

I did not create one in my Session 19 project, deliberately, so the private subnet is genuinely isolated and the difference between the two route tables is visible.

**VPC endpoints** are the cost optimisation worth knowing: a Gateway Endpoint for S3 or DynamoDB is free and routes that traffic privately without touching the NAT gateway at all. On a workload that reads a lot from S3, adding one can cut the NAT bill dramatically.

## Security Groups

Stateful firewall at the **instance** (network interface) level.

- Allow rules only, no deny.
- Stateful: allow a request in, and the reply is automatically allowed out.
- Can reference other security groups as a source, which is the feature that makes them scale.
- Default: all outbound allowed, all inbound denied.

My Session 19 group, as it ended up in AWS:

```
Cidr            From  Proto  To
0.0.0.0/0       80    tcp    80      HTTP from the internet
0.0.0.0/0       443   tcp    443     HTTPS from the internet
10.20.0.0/16    22    tcp    22      SSH from inside the VPC only
```

## Network ACLs

Stateless firewall at the **subnet** level.

- Supports both allow **and deny** rules.
- Stateless: you must write rules for both directions. Forgetting the outbound rule for ephemeral ports (1024 to 65535) is the classic NACL mistake, and it produces connections that open and then hang.
- Rules are numbered and evaluated in order; the first match wins.
- The default NACL allows everything both ways.

| | Security Group | Network ACL |
| --- | --- | --- |
| Level | Instance / ENI | Subnet |
| State | Stateful | Stateless |
| Rules | Allow only | Allow and Deny |
| Evaluation | All rules, union | In number order, first match wins |
| Default | Deny inbound, allow outbound | Allow everything |

Practical advice: do your access control with security groups, and leave NACLs at the default unless you specifically need a subnet-wide deny, for example blocking a known-bad IP range. Two overlapping firewalls make debugging harder, and most "my traffic is being dropped and I cannot see why" incidents involve a NACL someone edited months ago.

## Public vs private subnet, summarised

| | Public | Private |
| --- | --- | --- |
| Default route | `0.0.0.0/0 -> IGW` | None, or `-> NAT Gateway` |
| `map_public_ip_on_launch` | Usually true | False |
| Reachable from internet | Yes, if SG allows | No |
| Can reach the internet | Yes | Only via a NAT gateway |
| Put here | Load balancers, bastion hosts, NAT gateways | App servers, databases, EKS worker nodes |

The rule of thumb: if something does not need to receive unsolicited inbound traffic from the internet, it belongs in a private subnet. In a well-built VPC the public subnets contain almost nothing except load balancers and NAT gateways.

## How it all fits together

```
                        Internet
                            │
                     [Internet Gateway]
                            │
      ┌─────────────────────┴──────────────────────┐  VPC 10.20.0.0/16
      │                                            │
      │   PUBLIC SUBNET 10.20.1.0/24 (AZ-a)        │
      │   route: 0.0.0.0/0 -> IGW                  │
      │   ┌─────────────┐   ┌──────────────┐       │
      │   │     ALB     │   │ NAT Gateway  │       │
      │   └──────┬──────┘   └──────┬───────┘       │
      │          │                 │               │
      │   PRIVATE SUBNET 10.20.2.0/24 (AZ-a)       │
      │   route: 0.0.0.0/0 -> NAT                  │
      │   ┌──────▼──────┐          │               │
      │   │  App server │──────────┘  outbound only│
      │   └──────┬──────┘                          │
      │   ┌──────▼──────┐                          │
      │   │  RDS (no outbound route at all)        │
      │   └─────────────┘                          │
      └────────────────────────────────────────────┘
```

## Common use cases

- **Standard three-tier web application**: ALB in public subnets, application servers in private, database in isolated subnets, all replicated across two or three AZs.
- **EKS clusters**: worker nodes in private subnets, load balancers in public. Pod IP exhaustion is a VPC CIDR planning problem, not a Kubernetes one.
- **Hybrid connectivity**: Site-to-Site VPN or Direct Connect to an on-premise network, which is where non-overlapping CIDR planning becomes essential.
- **VPC peering or Transit Gateway** to connect environments, again requiring non-overlapping ranges.
- **Compliance isolation**: separate VPCs, or separate accounts, for environments that must not reach each other.

## References

- https://docs.aws.amazon.com/vpc/
- https://docs.aws.amazon.com/vpc/latest/userguide/vpc-security-groups.html
- https://docs.aws.amazon.com/vpc/latest/userguide/vpc-network-acls.html
- https://docs.aws.amazon.com/vpc/latest/userguide/vpc-nat-gateway.html
