# IAM: Identity and Access Management

**Session 18, Task 2.1** | Author: Lavya ([@LAVYA255](https://github.com/LAVYA255))

## What IAM is

IAM is the service that decides **who can do what** in an AWS account. Every single API call to AWS, whether from the console, the CLI, an SDK or another AWS service, is authenticated and then authorised by IAM before it runs. There is no way around it, which is why getting IAM right matters more than almost anything else in an AWS account.

Two separate questions, and it helps to keep them apart:

- **Authentication**: who are you? (a user with a password or access key, a role assumed via a token)
- **Authorisation**: are you allowed to do this? (evaluated from the policies attached to that identity and to the resource)

IAM is global, not regional. A user you create exists across every region.

## Users

An IAM user is a long-lived identity for a person or a legacy application. It can have:

- a **password** for console sign-in
- **access keys** (an ID and a secret) for the CLI and SDKs
- **MFA**, which should be mandatory on anything with real permissions

The thing to understand is that access keys are long-lived credentials sitting on someone's laptop or in a CI config. They do not expire on their own. Most leaked-AWS-credential incidents are an access key committed to a repository. Modern practice is to avoid IAM users almost entirely for humans (use IAM Identity Center / SSO) and entirely for workloads (use roles).

## Groups

A group is a container for users, and policies attach to the group. Users in it inherit those permissions.

Groups exist purely to stop you attaching the same policy to thirty users one at a time. A user can belong to several groups and gets the union of their permissions. Groups cannot be nested, and a group is not an identity, so nothing can "act as" a group.

Typical shape: `Developers`, `ReadOnly`, `Billing`, `Admins`.

## Roles

A role is a set of permissions that an identity **assumes temporarily**. It has no password and no access keys. When something assumes a role, STS issues short-lived credentials that expire, usually in an hour.

This is the single most important IAM concept in practice, because it is how you avoid long-lived secrets:

| Situation | What the role does |
| --- | --- |
| EC2 instance needs to read S3 | Attach an instance profile. The SDK fetches temporary credentials from the instance metadata service. No key is ever stored on disk. |
| Lambda function needs DynamoDB | Execution role, same idea. |
| EKS pod needs AWS access | IRSA, so the pod's service account maps to a role. |
| GitHub Actions needs to deploy | OIDC federation, so the workflow assumes a role with no stored secret at all. |
| Cross-account access | Role in account B trusts account A; users in A assume it. |

A role has two policies: a **trust policy** (who may assume it) and **permission policies** (what it can do once assumed). Forgetting the trust policy is the usual reason an assume-role call fails.

## Policies

A policy is a JSON document listing permissions. The core elements:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadAppBucket",
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:ListBucket"],
      "Resource": [
        "arn:aws:s3:::my-app-bucket",
        "arn:aws:s3:::my-app-bucket/*"
      ],
      "Condition": {
        "IpAddress": { "aws:SourceIp": "203.0.113.0/24" }
      }
    }
  ]
}
```

- **Effect**: `Allow` or `Deny`
- **Action**: the API calls, e.g. `s3:GetObject`, `ec2:RunInstances`. Wildcards allowed (`s3:Get*`)
- **Resource**: which ARNs this applies to. `"*"` means everything, and is where most over-permissive policies come from
- **Condition**: optional extra constraints (source IP, MFA present, tag matching, time of day)

Note the two ARNs in the example. `s3:ListBucket` acts on the *bucket*, `s3:GetObject` acts on *objects inside it*. Getting this wrong is a classic source of "access denied" on a policy that looks correct.

Policy types:

- **AWS managed**: maintained by AWS (`AmazonS3ReadOnlyAccess`). Convenient, usually broader than you need.
- **Customer managed**: yours, reusable, versioned. The right default.
- **Inline**: embedded in one identity, deleted with it. Fine for genuinely one-off permissions, awkward to audit.

## How permissions are actually evaluated

This order decides every request, and it is worth memorising:

1. **Explicit Deny** anywhere wins. Always. Nothing overrides it.
2. Otherwise, an **explicit Allow** permits the action.
3. Otherwise, **implicit deny**. Everything is denied by default.

So permissions are additive across groups and attached policies, except that a single `Deny` anywhere beats every `Allow`. Service Control Policies at the Organization level and permission boundaries act as further ceilings: they can only restrict, never grant.

## Least privilege

Grant the minimum permissions needed, and no more. In practice:

- Start from nothing and add permissions as things fail, rather than starting from `*` and trimming later. Nobody ever trims later.
- Scope `Resource` to specific ARNs instead of `"*"`.
- Use conditions to narrow further (require MFA, restrict source IP or VPC endpoint).
- Prefer roles with temporary credentials over users with access keys.
- Use IAM Access Analyzer, which reads CloudTrail and generates a policy based on what was genuinely used.

The policy that causes real damage is almost always `{"Effect":"Allow","Action":"*","Resource":"*"}` attached to something that got compromised.

## Best practices

1. **Lock away the root user.** Use it only for the handful of tasks that require it (closing the account, changing support plan). MFA on it, no access keys, strong unique password.
2. **MFA on every human identity**, without exception for admins.
3. **Roles, not users, for anything that is not a person.** No access keys on EC2, in Lambda, or in CI.
4. **Rotate what you cannot eliminate.** If an access key must exist, rotate it on a schedule and alert on old ones.
5. **Groups for humans, policies on groups.** Never attach policies to individual users at scale.
6. **Least privilege, scoped resources**, reviewed periodically.
7. **CloudTrail on and retained**, so every API call is logged and attributable.
8. **Use IAM Identity Center (SSO)** rather than per-account IAM users once there is more than one account.
9. **Permission boundaries and SCPs** so that even a mistaken grant cannot exceed a ceiling.

## Common use cases

- **An EC2 web server reading from S3.** Instance profile with a role scoped to one bucket prefix. No credentials on the instance.
- **A CI pipeline deploying to AWS.** GitHub Actions assumes a role via OIDC. Nothing long-lived is stored in the repository, which is exactly the problem the secret-scanning stage in Session 17 exists to catch.
- **A contractor needing read-only access.** A group with `ReadOnlyAccess`, MFA required by condition, time-limited.
- **Separate dev and prod accounts.** Cross-account roles, so a developer in the dev account assumes a limited role in prod rather than holding prod credentials.
- **An application needing a database password.** Not IAM directly: the credential lives in Secrets Manager and IAM controls who may read it. This is the pattern Session 12 covered.

## How it connects to the rest of the course

Kubernetes RBAC (Sessions 10 to 14) is the same idea applied inside a cluster: subjects, verbs, resources, deny by default, additive allows. IAM is that model for the cloud account. And the Session 17 lesson, that credentials in source control are the problem, is precisely what roles with temporary credentials are designed to eliminate.

## References

- https://docs.aws.amazon.com/IAM/latest/UserGuide/introduction.html
- https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html
- https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic.html
