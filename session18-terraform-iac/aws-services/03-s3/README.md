# S3: Simple Storage Service

**Session 18, Task 2.3** | Author: Lavya ([@LAVYA255](https://github.com/LAVYA255))

## What S3 is

S3 is object storage. You put whole files in and get them back by key over HTTP. It is not a filesystem: there is no appending to a file, no partial write, no directories, and no POSIX semantics. You replace an object or you do not.

What you get in exchange is effectively unlimited capacity, eleven nines of durability (99.999999999%), and no servers to manage. It is probably the most-used AWS service, and it underpins a lot of the others: EBS snapshots, AMIs, CloudTrail logs, Athena queries and Terraform remote state all live in S3.

This is the service I actually provisioned in Session 18 with Terraform, and again in the Session 19 stack.

## Buckets

A bucket is the top-level container.

- The name is **globally unique across all of AWS**, not just your account. Someone else having `test-bucket` is why yours needs a prefix. In my Session 19 project I appended a random suffix for exactly this reason:
  ```hcl
  bucket = "${local.name_prefix}-assets-${random_id.suffix.hex}"
  ```
- A bucket lives in **one region**. The name is global, the data is not.
- Naming rules: 3 to 63 characters, lowercase, numbers, hyphens, dots. No underscores, no uppercase. Dots break TLS for virtual-hosted-style access, so avoid them.
- Buckets are not nestable, and the per-account limit is 100 by default (raisable). You separate concerns with prefixes, not with hundreds of buckets.

## Objects

An object is the data plus its metadata, addressed by a **key**.

- A key is a flat string. `logs/2026/10/07/app.log` looks like a path, but there are no directories; the slashes are just characters. The console renders them as folders as a convenience, and `aws s3 ls --recursive` shows the truth.
- Max object size is 5 TB. Anything over 100 MB should use multipart upload, which uploads parts in parallel and lets you retry just the failed part.
- Each object has a system metadata (`Content-Type`, `Last-Modified`, ETag) and optional user metadata.
- Objects are immutable. "Editing" means uploading a replacement under the same key.

S3 has been **strongly read-after-write consistent** since 2020, so a `GET` immediately after a `PUT` returns the new object. Older documentation describing eventual consistency is out of date, and a surprising amount of defensive retry code exists because of it.

## Storage classes

The same object, different cost and retrieval trade-offs. Picking the right one is where most S3 savings come from.

| Class | Cost per GB | Retrieval | Use for |
| --- | --- | --- | --- |
| **Standard** | Highest | Instant | Active data, website assets, anything hot |
| **Intelligent-Tiering** | Standard + small monitoring fee | Instant | Unpredictable access. Moves objects between tiers automatically. The safe default when you genuinely do not know. |
| **Standard-IA** | ~45% less | Instant, plus a retrieval fee | Backups, older logs. Accessed monthly, not daily. Minimum 30 days billed. |
| **One Zone-IA** | ~20% less than IA | Instant, plus a fee | Re-creatable data only. Stored in one AZ, so an AZ loss loses the data. |
| **Glacier Instant Retrieval** | Much lower | Instant | Archives you still occasionally need immediately, e.g. medical images. |
| **Glacier Flexible Retrieval** | Lower still | Minutes to hours | Backups you rarely touch. |
| **Glacier Deep Archive** | Lowest | 12 hours | Compliance retention, tape replacement. Minimum 180 days. |

The catch with the IA and Glacier classes is the minimum storage duration and the per-GB retrieval charge. Moving a frequently-read object to Standard-IA to "save money" can easily cost more.

## Versioning

Off by default. Once enabled, every write creates a new version and nothing is ever truly overwritten.

- Deleting an object does not remove it. S3 writes a **delete marker** on top, and the previous versions remain. Deleting the marker restores the object.
- To really delete, you delete a specific version ID.
- Versioning can be suspended but **never switched off** once enabled. Existing versions stay.
- You pay for every version, which is why versioning plus a lifecycle rule to expire old versions is the sensible combination.

Versioning plus **MFA Delete** is the standard defence against both accidental deletion and ransomware: an attacker with your credentials still cannot permanently destroy the data.

In my Session 19 stack:

```hcl
resource "aws_s3_bucket_versioning" "assets" {
  bucket = aws_s3_bucket.assets.id
  versioning_configuration { status = "Enabled" }
}
```

## Lifecycle policies

Rules that move or delete objects automatically based on age, so you do not pay Standard prices for data nobody has read in a year.

A typical log bucket:

| Age | Action |
| --- | --- |
| 0 to 30 days | Standard |
| 30 days | Transition to Standard-IA |
| 90 days | Transition to Glacier Flexible Retrieval |
| 365 days | Transition to Deep Archive |
| 7 years | Expire |

Rules can target a prefix or tag, apply separately to current and noncurrent versions, and clean up incomplete multipart uploads, which is a real and commonly forgotten source of invisible cost: failed uploads leave parts that are billed but do not appear in listings.

## Encryption

**At rest**, every bucket is encrypted by default now (SSE-S3). The options:

| Mode | Key managed by | Notes |
| --- | --- | --- |
| **SSE-S3** | AWS | Default, free, nothing to configure |
| **SSE-KMS** | You, via KMS | Auditable in CloudTrail, per-key access control. Use `bucket_key_enabled` or KMS request costs become significant on high-volume buckets. |
| **SSE-C** | You supply the key per request | AWS never stores it. Rare. |
| **Client-side** | You, before upload | S3 only ever sees ciphertext |

**In transit**, use HTTPS. Enforce it with a bucket policy denying requests where `aws:SecureTransport` is false, because the default allows both.

## Bucket policies and access control

Several mechanisms overlap, which is why S3 permissions confuse people:

1. **Block Public Access.** An account and bucket level switch that overrides everything else. On by default for new buckets. This is the setting whose absence caused most of the famous "exposed S3 bucket" breaches. Leave it on unless you are deliberately hosting a public website.
   ```hcl
   resource "aws_s3_bucket_public_access_block" "assets" {
     bucket                  = aws_s3_bucket.assets.id
     block_public_acls       = true
     block_public_policy     = true
     ignore_public_acls      = true
     restrict_public_buckets = true
   }
   ```
2. **Bucket policy.** A resource-based JSON policy on the bucket. This is how you grant cross-account access or enforce encryption and TLS.
3. **IAM policies.** Identity-based, attached to a user or role.
4. **ACLs.** The legacy mechanism. AWS now recommends disabling them entirely (`Bucket owner enforced`).

Evaluation is the IAM model: explicit deny wins, then explicit allow, then implicit deny. For same-account access, an allow in *either* the IAM policy or the bucket policy is enough.

A bucket policy enforcing TLS:

```json
{
  "Effect": "Deny",
  "Principal": "*",
  "Action": "s3:*",
  "Resource": ["arn:aws:s3:::my-bucket", "arn:aws:s3:::my-bucket/*"],
  "Condition": { "Bool": { "aws:SecureTransport": "false" } }
}
```

**Presigned URLs** are the right answer for "let this one user download this one file for ten minutes" without making anything public.

## Common use cases

- **Static website and asset hosting**, usually S3 behind CloudFront. Cheaper and more reliable than a web server for files that never change.
- **Backups and archives**, with lifecycle rules dropping them into Glacier.
- **Data lake.** Raw data in S3, queried in place by Athena or Redshift Spectrum without loading it anywhere.
- **Log aggregation.** ALB, CloudFront, VPC Flow Logs and CloudTrail all write here natively.
- **Terraform remote state**, with DynamoDB for locking. Directly relevant to Session 18: the local `terraform.tfstate` I used is exactly what you replace with an S3 backend on a team.
- **Application uploads.** The browser uploads straight to S3 via a presigned URL, so the file never passes through your servers.
- **Container image layers.** ECR stores them in S3 underneath.

## Things that catch people out

- Bucket names are **global**. Your first choice is almost certainly taken.
- Keys are flat. There are no folders, and renaming a "folder" means copying every object.
- Deleting with versioning on does not free storage. You need a lifecycle rule for noncurrent versions.
- Incomplete multipart uploads are billed and invisible. Add the cleanup rule.
- Cross-region data transfer costs money; same-region transfer to EC2 does not.
- A `404` on an object you can see in the console usually means your IAM policy grants `s3:ListBucket` on the bucket ARN but not `s3:GetObject` on the `bucket/*` ARN. They are different resources.

## References

- https://docs.aws.amazon.com/s3/
- https://docs.aws.amazon.com/AmazonS3/latest/userguide/storage-class-intro.html
- https://docs.aws.amazon.com/AmazonS3/latest/userguide/security-best-practices.html
- https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lifecycle-mgmt.html
