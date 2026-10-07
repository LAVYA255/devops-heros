# Session 18: Terraform and Infrastructure as Code

**Author:** Lavya ([@LAVYA255](https://github.com/LAVYA255))
**Course:** SST DevOps & Cloud [SWE]
**Session:** 18 - Terraform and IaC
**Repository:** `devops-heros / session18-terraform-iac`

**Important, please read this first.** Every Terraform command below was really executed, but against **LocalStack**, an AWS emulator running in a container on my machine, not against a real AWS account. The `.tf` files are ordinary AWS Terraform and would apply to real AWS unchanged; only the endpoint differs. I did it this way because provisioning real AWS resources costs money and needs live credentials.

Terraform v1.9.8, AWS provider v5, LocalStack 3.8, in WSL2 Ubuntu.

---

## How LocalStack is wired in

```text
# Everything in this session runs against LocalStack, an AWS emulator in a container,
# rather than a real AWS account. The Terraform workflow is identical; only the endpoint differs.
$ docker ps --filter name=localstack --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
NAMES             IMAGE                       STATUS                   PORTS
localstack-main   localstack/localstack:3.8   Up 4 minutes (healthy)   0.0.0.0:4510-4559->4510-4559/tcp, [::]:4510-4559->4510-4559/tcp, 0.0.0.0:4566->4566/tcp, [::]:4566->4566/tcp, 5678/tcp

$ curl -s http://localhost:4566/_localstack/health | python3 -m json.tool | head -16
{
    "services": {
        "acm": "disabled",
        "apigateway": "disabled",
        "cloudformation": "disabled",
        "cloudwatch": "available",
        "config": "disabled",
        "dynamodb": "available",
        "dynamodbstreams": "available",
        "ec2": "running",
        "es": "disabled",
        "events": "disabled",
        "firehose": "disabled",
        "iam": "running",
        "kinesis": "available",
        "kms": "available",

$ awslocal sts get-caller-identity
{
    "UserId": "AKIAIOSFODNN7EXAMPLE",
    "Account": "000000000000",
    "Arn": "arn:aws:iam::000000000000:root"
}

# tflocal is a thin wrapper that points the AWS provider at http://localhost:4566.
# The .tf files stay exactly as they would be for real AWS.
$ cat $(command -v tflocal) | head -12
#!/home/lavya/.venvs/aws/bin/python3

"""
Thin wrapper around the "terraform" command line interface (CLI) for use
with LocalStack.

The "tflocal" CLI allows you to easily interact with your local services
without having to specify the local endpoints in the "provider" section of
your TF config.
"""

import os
```

**Screenshot**

![localstack](./screenshots/00-localstack.png)

`tflocal` is a thin wrapper around `terraform` that injects `endpoints { ... }` pointing at `http://localhost:4566`. The project files contain no LocalStack-specific anything, so swapping in real credentials and running plain `terraform` would hit real AWS.

---

## Task 1: The S3 demo project

The brief asks for this layout:

```
terraform-s3-demo/
├── main.tf           the bucket resource
├── variables.tf      inputs with types, descriptions and defaults
├── outputs.tf        what the module exposes
├── provider.tf       the AWS provider block
├── terraform.tfvars  values for this environment
└── README.md
```

**Project files**
```text
$ ls -1
README.md
main.tf
outputs.tf
provider.tf
terraform.tf
terraform.tfvars
variables.tf

$ cat terraform.tf
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

$ cat provider.tf
provider "aws" { region = var.aws_region }

$ cat variables.tf
variable "aws_region" {
  type        = string
  description = "AWS region where the S3 bucket will be created."
  default     = "ap-south-1"
}
variable "bucket_name" {
  type        = string
  description = "Name of the S3 bucket."
  default     = "yatri1107"
}

$ cat main.tf
resource "aws_s3_bucket" "devops553" {
  bucket        = var.bucket_name
  force_destroy = true
  tags = {
    Name        = var.bucket_name
    Environment = "dev"
    ManagedBy   = "Terraform"
    Project     = "Session18"
  }
}

$ cat outputs.tf
output "bucket_name" {
  description = "Name of the S3 bucket."
  value       = aws_s3_bucket.devops553.bucket
}
output "bucket_arn" {
  description = "ARN of the S3 bucket."
  value       = aws_s3_bucket.devops553.arn
}
output "bucket_region" {
  description = "AWS region of the S3 bucket."
  value       = aws_s3_bucket.devops553.region
}

$ cat terraform.tfvars
# Values for this environment. Committed here because the bucket name and region
# are not secrets. Anything sensitive belongs in a tfvars file that is gitignored,
# or in environment variables (TF_VAR_*).

aws_region  = "us-east-1"
bucket_name = "lavya-devops-session18-demo"
```

### Two fixes I had to make first

**1. The committed `outputs.tf` was not valid Terraform.** It had `type = string` inside each `output` block. Output blocks accept `value`, `description`, `sensitive`, `depends_on` and `precondition`, but not `type`. `terraform init` refused to run:

```
Error: Unsupported argument
  on outputs.tf line 2, in output "bucket_name":
   2:   type        = string
An argument named "type" is not expected here.
```

`type` belongs on `variable` blocks, where it constrains the input. An output just passes a value through, so its type is whatever the value already is. I removed the three lines.

**2. Provider version.** The project pinned `~> 6.0`. From AWS provider 6.0, reading an S3 bucket's tags goes through the `s3control` API (`ListTagsForResource`), and LocalStack community does not implement that route, so every plan, apply and destroy failed with a 501 even though the bucket itself was created correctly. I pinned `~> 5.0` with a comment explaining why. Against real AWS, `~> 6.0` is fine.

I also renamed `providers.tf` to `provider.tf` to match the layout the brief asks for, and added the `terraform.tfvars` that was missing.

---

## The full workflow

### `terraform init`
```text
# terraform init downloads the provider plugins and sets up the backend.
$ tflocal init -no-color
Initializing the backend...
Initializing provider plugins...
- Finding hashicorp/aws versions matching "~> 5.0"...
- Installing hashicorp/aws v5.100.0...
- Installed hashicorp/aws v5.100.0 (signed by HashiCorp)
Terraform has created a lock file .terraform.lock.hcl to record the provider
selections it made above. Include this file in your version control repository
so that Terraform can guarantee to make the same selections by default when
you run "terraform init" in the future.

Terraform has been successfully initialized!

You may now begin working with Terraform. Try running "terraform plan" to see
any changes that are required for your infrastructure. All Terraform commands
should now work.

If you ever set or change modules or backend configuration for Terraform,
rerun this command to reinitialize your working directory. If you forget, other
commands will detect it and remind you to do so if necessary.

$ ls -la .terraform/providers/registry.terraform.io/hashicorp/aws/*/linux_amd64/ | head -4
total 690400
drwxrwxrwx 1 lavya lavya      4096 Oct  7 15:38 .
drwxrwxrwx 1 lavya lavya      4096 Oct  7 15:38 ..
-rwxrwxrwx 1 lavya lavya     16761 Oct  7 15:38 LICENSE.txt

$ cat .terraform.lock.hcl | head -12
# This file is maintained automatically by "terraform init".
# Manual edits may be lost in future updates.

provider "registry.terraform.io/hashicorp/aws" {
  version     = "5.100.0"
  constraints = "~> 5.0"
  hashes = [
    "h1:edXOJWE4ORX8Fm+dpVpICzMZJat4AX0VRCAy/xkcOc0=",
    "zh:054b8dd49f0549c9a7cc27d159e45327b7b65cf404da5e5a20da154b90b8a644",
    "zh:0b97bf8d5e03d15d83cc40b0530a1f84b459354939ba6f135a0086c20ebbe6b2",
    "zh:1589a2266af699cbd5d80737a0fe02e54ec9cf2ca54e7e00ac51c7359056f274",
    "zh:6330766f1d85f01ae6ea90d1b214b8b74cc8c1badc4696b165b36ddd4cc15f7b",
```

Downloads the provider plugin into `.terraform/` and writes `.terraform.lock.hcl`, which pins the exact provider version and its checksums. That lock file belongs in git: it is what stops a teammate silently getting a different provider.

### `terraform fmt` and `terraform validate`
```text
# terraform fmt rewrites files to the canonical style. -check -diff shows what it would change.
$ tflocal fmt -check -diff -no-color || true

$ tflocal fmt -no-color

# terraform validate checks syntax and internal consistency without contacting AWS.
$ tflocal validate -no-color
Success! The configuration is valid.
```

`fmt` rewrites files to canonical style; `-check -diff` shows what it would change without touching anything, which is what you run in CI. `validate` checks syntax and internal consistency offline, with no AWS call, so it catches a misspelled attribute or a reference to a resource that does not exist.

### `terraform plan`
```text
# terraform plan computes the difference between the config and the recorded state.
$ tflocal plan -no-color -out=tfplan

Terraform used the selected providers to generate the following execution
plan. Resource actions are indicated with the following symbols:
  + create

Terraform will perform the following actions:

  # aws_s3_bucket.devops553 will be created
  + resource "aws_s3_bucket" "devops553" {
      + acceleration_status         = (known after apply)
      + acl                         = (known after apply)
      + arn                         = (known after apply)
      + bucket                      = "lavya-devops-session18-demo"
      + bucket_domain_name          = (known after apply)
      + bucket_prefix               = (known after apply)
      + bucket_regional_domain_name = (known after apply)
      + force_destroy               = true
      + hosted_zone_id              = (known after apply)
      + id                          = (known after apply)
      + object_lock_enabled         = (known after apply)
      + policy                      = (known after apply)
      + region                      = (known after apply)
      + request_payer               = (known after apply)
      + tags                        = {
          + "Environment" = "dev"
          + "ManagedBy"   = "Terraform"
          + "Name"        = "lavya-devops-session18-demo"
          + "Project"     = "Session18"
        }
      + tags_all                    = {
          + "Environment" = "dev"
          + "ManagedBy"   = "Terraform"
          + "Name"        = "lavya-devops-session18-demo"
          + "Project"     = "Session18"
        }
      + website_domain              = (known after apply)
      + website_endpoint            = (known after apply)

      + cors_rule (known after apply)

      + grant (known after apply)

      + lifecycle_rule (known after apply)

      + logging (known after apply)

      + object_lock_configuration (known after apply)

      + replication_configuration (known after apply)

      + server_side_encryption_configuration (known after apply)

      + versioning (known after apply)

      + website (known after apply)
    }

Plan: 1 to add, 0 to change, 0 to destroy.

Changes to Outputs:
  + bucket_arn    = (known after apply)
  + bucket_name   = "lavya-devops-session18-demo"
  + bucket_region = (known after apply)

─────────────────────────────────────────────────────────────────────────────

Saved the plan to: tfplan

To perform exactly these actions, run the following command to apply:
    terraform apply "tfplan"

# the plan is a real file, and can be inspected or stored as a CI artifact:
$ ls -lh tfplan
-rwxrwxrwx 1 lavya lavya 5.0K Oct  7 15:39 tfplan

$ tflocal show -json tfplan | python3 -c "
import json,sys
d=json.load(sys.stdin)
for rc in d.get('resource_changes',[]):
    print(rc['address'], '->', ','.join(rc['change']['actions']))
"
aws_s3_bucket.devops553 -> create
```

**Screenshot**

![terraform plan](./screenshots/01-plan.png)

Plan is the heart of the tool. It reads the current state, compares it to the config, and prints exactly what it would change. `-out=tfplan` writes a real file you can inspect, review, or store as a CI artifact and apply later, which is how you get "the thing that was reviewed is the thing that was applied".

### `terraform apply`
```text
# terraform apply executes the saved plan. No second confirmation is needed when a plan file is given.
$ tflocal apply -no-color tfplan
aws_s3_bucket.devops553: Creating...
aws_s3_bucket.devops553: Creation complete after 1s [id=lavya-devops-session18-demo]

Apply complete! Resources: 1 added, 0 changed, 0 destroyed.

Outputs:

bucket_arn = "arn:aws:s3:::lavya-devops-session18-demo"
bucket_name = "lavya-devops-session18-demo"
bucket_region = "us-east-1"

# proof the bucket really exists, queried with the AWS CLI rather than Terraform:
$ awslocal s3 ls
2026-10-07 15:39:58 lavya-devops-session18-demo

$ awslocal s3api get-bucket-tagging --bucket lavya-devops-session18-demo
{
    "TagSet": [
        {
            "Key": "ManagedBy",
            "Value": "Terraform"
        },
        {
            "Key": "Project",
            "Value": "Session18"
        },
        {
            "Key": "Name",
            "Value": "lavya-devops-session18-demo"
        },
        {
            "Key": "Environment",
            "Value": "dev"
        }
    ]
}

# and it behaves like a bucket:
$ echo 'hello from session 18' > /tmp/s18.txt && awslocal s3 cp /tmp/s18.txt s3://lavya-devops-session18-demo/notes/s18.txt
Completed 22 Bytes/22 Bytes (6.1 KiB/s) with 1 file(s) remaining
upload: ../../../../../../tmp/s18.txt to s3://lavya-devops-session18-demo/notes/s18.txt

$ awslocal s3 ls s3://lavya-devops-session18-demo --recursive
2026-10-07 15:39:59         22 notes/s18.txt

$ awslocal s3 cp s3://lavya-devops-session18-demo/notes/s18.txt -
hello from session 18
```

**Screenshot**

![terraform apply](./screenshots/02-apply.png)

Applying a saved plan file needs no second confirmation, because the decision was made when the plan was produced.

I did not take Terraform's word for it. The bucket is verified with the AWS CLI (`awslocal s3 ls`, `get-bucket-tagging`), then used as a bucket: a file uploaded, listed and read back.

### `terraform show` and `terraform output`
```text
# terraform show prints the current state in human-readable form.
$ tflocal show -no-color
# aws_s3_bucket.devops553:
resource "aws_s3_bucket" "devops553" {
    acceleration_status         = null
    arn                         = "arn:aws:s3:::lavya-devops-session18-demo"
    bucket                      = "lavya-devops-session18-demo"
    bucket_domain_name          = "lavya-devops-session18-demo.s3.amazonaws.com"
    bucket_prefix               = null
    bucket_regional_domain_name = "lavya-devops-session18-demo.s3.us-east-1.amazonaws.com"
    force_destroy               = true
    hosted_zone_id              = "Z3AQBSTGFYJSTF"
    id                          = "lavya-devops-session18-demo"
    object_lock_enabled         = false
    policy                      = null
    region                      = "us-east-1"
    request_payer               = "BucketOwner"
    tags                        = {
        "Environment" = "dev"
        "ManagedBy"   = "Terraform"
        "Name"        = "lavya-devops-session18-demo"
        "Project"     = "Session18"
    }
    tags_all                    = {
        "Environment" = "dev"
        "ManagedBy"   = "Terraform"
        "Name"        = "lavya-devops-session18-demo"
        "Project"     = "Session18"
    }

    grant {
        id          = "75aa57f09aa0c8caeab4f8c24e99d10f8e7faeebf76c078efc7c6caea54ba06a"
        permissions = [
            "FULL_CONTROL",
        ]
        type        = "CanonicalUser"
        uri         = null
    }

    server_side_encryption_configuration {
        rule {
            bucket_key_enabled = false

            apply_server_side_encryption_by_default {
                kms_master_key_id = null
                sse_algorithm     = "AES256"
            }
        }
    }

    versioning {
        enabled    = false
        mfa_delete = false
    }
}

Outputs:

bucket_arn = "arn:aws:s3:::lavya-devops-session18-demo"
bucket_name = "lavya-devops-session18-demo"
bucket_region = "us-east-1"

# terraform output reads the declared outputs. -json makes it machine readable for scripts and CI.
$ tflocal output
bucket_arn = "arn:aws:s3:::lavya-devops-session18-demo"
bucket_name = "lavya-devops-session18-demo"
bucket_region = "us-east-1"

$ tflocal output -json
{
  "bucket_arn": {
    "sensitive": false,
    "type": "string",
    "value": "arn:aws:s3:::lavya-devops-session18-demo"
  },
  "bucket_name": {
    "sensitive": false,
    "type": "string",
    "value": "lavya-devops-session18-demo"
  },
  "bucket_region": {
    "sensitive": false,
    "type": "string",
    "value": "us-east-1"
  }
}

$ tflocal output -raw bucket_arn; echo
arn:aws:s3:::lavya-devops-session18-demo
```

`show` prints the whole state in readable form. `output` reads just the declared outputs, and `-json` or `-raw` makes them consumable by scripts, which is how one Terraform project feeds another or how a pipeline gets a bucket ARN.

### State and idempotence
```text
# the state file is how Terraform remembers what it created.
$ ls -lh terraform.tfstate
-rwxrwxrwx 1 lavya lavya 3.3K Oct  7 15:39 terraform.tfstate

$ tflocal state list
aws_s3_bucket.devops553

$ tflocal state show aws_s3_bucket.devops553 | head -20
# aws_s3_bucket.devops553:
resource "aws_s3_bucket" "devops553" {
    acceleration_status         = null
    arn                         = "arn:aws:s3:::lavya-devops-session18-demo"
    bucket                      = "lavya-devops-session18-demo"
    bucket_domain_name          = "lavya-devops-session18-demo.s3.amazonaws.com"
    bucket_prefix               = null
    bucket_regional_domain_name = "lavya-devops-session18-demo.s3.us-east-1.amazonaws.com"
    force_destroy               = true
    hosted_zone_id              = "Z3AQBSTGFYJSTF"
    id                          = "lavya-devops-session18-demo"
    object_lock_enabled         = false
    policy                      = null
    region                      = "us-east-1"
    request_payer               = "BucketOwner"
    tags                        = {
        "Environment" = "dev"
        "ManagedBy"   = "Terraform"
        "Name"        = "lavya-devops-session18-demo"
        "Project"     = "Session18"

# re-running plan with no config changes shows an empty diff - this is idempotence:
$ tflocal plan -no-color | tail -5

No changes. Your infrastructure matches the configuration.

Terraform has compared your real infrastructure against your configuration
and found no differences, so no changes are needed.
```

State is how Terraform knows what it already owns. Without it, a second apply would try to create the bucket again. Re-running plan with no config change gives an empty diff, which is the whole point of declarative infrastructure: running it twice does nothing the second time.

Worth knowing for real work: this is local state in a file. Teams use remote state (S3 plus DynamoDB locking, or Terraform Cloud) so that two people cannot apply at once, and so the state is not sitting on one laptop. The state file also contains every attribute of every resource in plain text, including anything sensitive, which is a second reason not to commit it.

### `terraform destroy`
```text
# terraform destroy removes everything in the state file.
$ tflocal destroy -auto-approve -no-color
aws_s3_bucket.devops553: Refreshing state... [id=lavya-devops-session18-demo]

Terraform used the selected providers to generate the following execution
plan. Resource actions are indicated with the following symbols:
  - destroy

Terraform will perform the following actions:

  # aws_s3_bucket.devops553 will be destroyed
  - resource "aws_s3_bucket" "devops553" {
      - arn                         = "arn:aws:s3:::lavya-devops-session18-demo" -> null
      - bucket                      = "lavya-devops-session18-demo" -> null
      - bucket_domain_name          = "lavya-devops-session18-demo.s3.amazonaws.com" -> null
      - bucket_regional_domain_name = "lavya-devops-session18-demo.s3.us-east-1.amazonaws.com" -> null
      - force_destroy               = true -> null
      - hosted_zone_id              = "Z3AQBSTGFYJSTF" -> null
      - id                          = "lavya-devops-session18-demo" -> null
      - object_lock_enabled         = false -> null
      - region                      = "us-east-1" -> null
      - request_payer               = "BucketOwner" -> null
      - tags                        = {
          - "Environment" = "dev"
          - "ManagedBy"   = "Terraform"
          - "Name"        = "lavya-devops-session18-demo"
          - "Project"     = "Session18"
        } -> null
      - tags_all                    = {
          - "Environment" = "dev"
          - "ManagedBy"   = "Terraform"
          - "Name"        = "lavya-devops-session18-demo"
          - "Project"     = "Session18"
        } -> null
        # (3 unchanged attributes hidden)

      - grant {
          - id          = "75aa57f09aa0c8caeab4f8c24e99d10f8e7faeebf76c078efc7c6caea54ba06a" -> null
          - permissions = [
              - "FULL_CONTROL",
            ] -> null
          - type        = "CanonicalUser" -> null
            # (1 unchanged attribute hidden)
        }

      - server_side_encryption_configuration {
          - rule {
              - bucket_key_enabled = false -> null

              - apply_server_side_encryption_by_default {
                  - sse_algorithm     = "AES256" -> null
                    # (1 unchanged attribute hidden)
                }
            }
        }

      - versioning {
          - enabled    = false -> null
          - mfa_delete = false -> null
        }
    }

Plan: 0 to add, 0 to change, 1 to destroy.

Changes to Outputs:
  - bucket_arn    = "arn:aws:s3:::lavya-devops-session18-demo" -> null
  - bucket_name   = "lavya-devops-session18-demo" -> null
  - bucket_region = "us-east-1" -> null
aws_s3_bucket.devops553: Destroying... [id=lavya-devops-session18-demo]
aws_s3_bucket.devops553: Destruction complete after 0s

Destroy complete! Resources: 1 destroyed.

$ awslocal s3 ls

$ tflocal state list || echo '(state is now empty)'

$ tflocal show -no-color
The state file is empty. No resources are represented.
```

**Screenshot**

![terraform destroy](./screenshots/03-destroy.png)

Destroy removes everything recorded in state, then the state is empty and `show` prints nothing. Verified independently with `awslocal s3 ls`.

---

## Task 2: AWS services

The brief asks for a separate README per service. They are in [`aws-services/`](./aws-services):

| | Service | README |
| --- | --- | --- |
| 01 | IAM, governance | [aws-services/01-iam](./aws-services/01-iam/README.md) |
| 02 | EC2, compute | [aws-services/02-ec2](./aws-services/02-ec2/README.md) |
| 03 | S3, storage | [aws-services/03-s3](./aws-services/03-s3/README.md) |
| 04 | VPC, networking | [aws-services/04-vpc](./aws-services/04-vpc/README.md) |
| 05 | DynamoDB and RDS, databases | [aws-services/05-dynamodb-rds](./aws-services/05-dynamodb-rds/README.md) |

---

## What I took away

- `terraform validate` catches genuine mistakes. The course's own `outputs.tf` did not parse, and nobody would have noticed until the first `init`.
- Provider version pins are not cosmetic. A major version changed which API is used to read a tag, and that alone broke the entire workflow on an emulator.
- `plan` then `apply <planfile>` is the pattern worth keeping. It separates "decide" from "do", which is exactly what you want in a pipeline.
- Verify with something other than the tool that made the change. `terraform show` reads state; `awslocal s3 ls` reads reality. They can disagree, and when they do, state is the thing that is wrong.

---

## References

- Terraform docs: https://developer.hashicorp.com/terraform/docs
- AWS provider: https://registry.terraform.io/providers/hashicorp/aws/latest/docs
- Terraform state: https://developer.hashicorp.com/terraform/language/state
- LocalStack: https://docs.localstack.cloud/
- Course material in this folder: `01-iac-basics` through `09-state`
