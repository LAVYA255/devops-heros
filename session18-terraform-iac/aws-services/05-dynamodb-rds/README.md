# DynamoDB and RDS: Database Services

**Session 18, Task 2.5** | Author: Lavya ([@LAVYA255](https://github.com/LAVYA255))

Two managed database services that solve different problems. The short version: **RDS** when you need relational data, joins and transactions; **DynamoDB** when you need predictable single-digit millisecond lookups at any scale and you know your access patterns up front.

---

# DynamoDB

## NoSQL

DynamoDB is a managed key-value and document store. "NoSQL" here means:

- **No fixed schema.** Beyond the primary key, every item can have different attributes.
- **No joins.** You cannot combine two tables in a query. Related data is either duplicated or stored in the same item.
- **No SQL.** You query by key through an API (PartiQL exists but is a thin layer over the same operations).
- **Horizontal scaling.** It partitions data across servers automatically. There is no instance to size, and performance does not degrade as the table grows.

The trade-off: you give up query flexibility and get guaranteed low latency. A relational database answers questions you had not thought of when you designed it; DynamoDB does not, and that is the main thing to understand before choosing it.

**You design the table around the queries**, which is the opposite of relational modelling where you normalise first and query later. If you do not know your access patterns, DynamoDB is the wrong choice.

## Tables, items, attributes

| Concept | Relational equivalent | Notes |
| --- | --- | --- |
| **Table** | Table | Lives in one region, replicated across 3 AZs automatically |
| **Item** | Row | Max 400 KB. Large blobs go in S3 with the key stored here |
| **Attribute** | Column | Only the key attributes are required |

Attributes can be scalars (string, number, binary, boolean, null), sets, lists or maps, so an item can hold nested JSON-like structure.

## Partition key and sort key

The primary key uniquely identifies an item and comes in two forms.

**Partition key only** (simple key). The key is hashed to decide which physical partition stores the item.

```
Table: Users
  PK: user_id = "u-1042"
  { user_id: "u-1042", email: "lavya@...", plan: "pro" }
```

Lookups by `user_id` are O(1). There is no way to ask "all users on the pro plan" without scanning the whole table.

**Partition key + sort key** (composite key). Items sharing a partition key are stored together, sorted by the sort key.

```
Table: Orders
  PK: customer_id    SK: order_date#order_id

  customer_id  order_date#order_id
  c-77         2026-01-14#o-001
  c-77         2026-03-02#o-019
  c-77         2026-10-07#o-204
```

Now you can do range queries efficiently: all orders for `c-77`, orders after a date, the most recent order, all without a scan. The sort key is what makes DynamoDB useful for more than plain key-value lookups.

**Partition key choice is the main design decision.** It must spread traffic evenly. A key like `status = "ACTIVE"` puts nearly everything in one partition and creates a hot partition that throttles no matter how much capacity you provision. High cardinality and even access distribution are what you want.

**Secondary indexes** give you additional access patterns:

- **LSI** (Local Secondary Index): same partition key, different sort key. Must be created with the table.
- **GSI** (Global Secondary Index): entirely different partition and sort key, effectively a second view of the table. Can be added later, has its own capacity, and is eventually consistent.

## Capacity and cost

- **On-demand**: pay per request, scales instantly, no planning. Right for spiky or unknown traffic.
- **Provisioned**: you set read and write capacity units, optionally with auto-scaling. Cheaper for steady predictable load.

Other features worth knowing: **TTL** auto-deletes expired items at no cost (ideal for sessions), **DynamoDB Streams** emit a change log that can trigger Lambda, **Global Tables** give multi-region active-active replication, and **DAX** is an in-memory cache for microsecond reads.

## DynamoDB use cases

- Session stores and user profiles, keyed by ID.
- Shopping carts and order history, the composite-key pattern above.
- IoT and telemetry ingestion, where write volume is enormous and queries are by device and time.
- Leaderboards and counters.
- Serverless application state, since it pairs naturally with Lambda and has no connection pool to exhaust.
- Anything needing single-digit millisecond latency at unpredictable scale.

**Not** for: ad-hoc reporting, analytics, anything needing joins, or a domain where the query patterns will keep changing.

---

# RDS

## Relational database

RDS is managed relational database hosting. You still get a normal SQL database with tables, joins, transactions and constraints; AWS handles the operational work: provisioning, patching, backups, failover, replication and monitoring.

What you give up is OS-level access. No SSH to the host, no custom extensions beyond the supported list, and some configuration is fixed. If you need that control you run the database on EC2 yourself and own all the operations.

## Supported engines

| Engine | Notes |
| --- | --- |
| **PostgreSQL** | Strong default. Rich features, good JSON support, PostGIS |
| **MySQL** | Very widely used |
| **MariaDB** | MySQL fork |
| **Oracle** | Bring your own licence or licence-included |
| **SQL Server** | Several editions |
| **Aurora** (PostgreSQL and MySQL compatible) | AWS's own engine. Separates compute from a distributed storage layer, giving faster failover, up to 15 read replicas and storage that grows automatically. Costs more; usually worth it at scale |

The Session 21 TaskBoard app uses PostgreSQL, which in a real deployment would be exactly this rather than a container.

## DB instances

An instance is the compute running the engine, sized like EC2 (`db.t3.micro`, `db.m6g.large`, `db.r6g.xlarge`). Memory-optimised `db.r*` classes are common because databases cache aggressively.

Storage is EBS underneath: `gp3` for general use, `io1`/`io2` for provisioned IOPS. Storage autoscaling can grow the volume automatically, and **storage can be increased but never decreased**, which is worth knowing before you over-provision.

Changing instance class requires a restart, so it is done in the maintenance window or with a failover.

## Security

Layered, and all of it matters:

- **Network**: put the instance in **private subnets** with no public accessibility. A DB subnet group spans at least two AZs.
- **Security groups**: allow the database port only from the application's security group, not from a CIDR range. This is the security-group-as-source pattern from the EC2 writeup.
- **Encryption at rest** with KMS. Must be enabled **at creation**; converting an unencrypted instance later means snapshot, copy with encryption, restore.
- **Encryption in transit** with TLS, enforced by a parameter group setting.
- **Authentication**: a master password, or **IAM database authentication** which issues short-lived tokens so no static password exists. Better still, store the credential in **Secrets Manager** with automatic rotation.
- **Audit logging** to CloudWatch Logs.

The anti-pattern is a publicly accessible RDS instance with a security group open to `0.0.0.0/0`. It happens surprisingly often and is immediately scanned.

## Backups

Two mechanisms, and they are not the same:

| | Automated backups | Manual snapshots |
| --- | --- | --- |
| Schedule | Daily, in a backup window | When you take one |
| Retention | 0 to 35 days | Until you delete them |
| Point-in-time restore | Yes, to any second in the window | No, restores to that moment |
| Deleted with the instance | Yes | **No** |

**Point-in-time recovery** is the valuable part: RDS continuously ships transaction logs, so you can restore to any second within the retention period, which is what you want after a bad migration or a mistaken `DELETE`.

Restores always create a **new instance**. You cannot restore in place, so recovery means restore, verify, then repoint the application.

## Multi-AZ

A **synchronous standby replica in a different availability zone**. Not a read replica: you cannot read from it. It exists purely for availability.

- Writes commit on both before acknowledging, so there is a small latency cost.
- Automatic failover on instance failure, AZ failure, or during patching, typically in 60 to 120 seconds.
- The **endpoint DNS name stays the same** and is repointed at the promoted standby, so the application reconnects rather than being reconfigured.
- Roughly doubles the cost.

Multi-AZ is for availability. It does not improve read performance at all, which is the most common misunderstanding.

## Read replicas

**Asynchronous** copies you *can* read from.

- Up to 5 per instance (15 for Aurora), in the same region or cross-region.
- Reads are **eventually consistent**: replication lag means a read immediately after a write may return stale data. The application has to tolerate that.
- Each has its own endpoint, so the application explicitly routes reads to it.
- Can be promoted to a standalone instance, which is a disaster-recovery and migration path.

| | Multi-AZ | Read replica |
| --- | --- | --- |
| Replication | Synchronous | Asynchronous |
| Purpose | Availability | Read scaling |
| Readable | No | Yes |
| Failover | Automatic | Manual promotion |
| Cross-region | No | Yes |

They are complementary: a production setup commonly has Multi-AZ for failover plus read replicas for reporting queries.

## RDS use cases

- Transactional application backends, anything with orders, payments or inventory where ACID guarantees matter.
- Existing applications migrating to the cloud that already speak SQL.
- Reporting and analytics against a read replica, so heavy queries do not affect production.
- Anything where the query patterns will evolve, because SQL lets you ask new questions without redesigning storage.

---

# Choosing between them

| | DynamoDB | RDS |
| --- | --- | --- |
| Model | Key-value / document | Relational |
| Query flexibility | Only designed access patterns | Any SQL query |
| Joins, transactions | No joins; limited transactions | Full |
| Scaling | Automatic, horizontal, effectively unlimited | Vertical, plus read replicas |
| Latency | Single-digit ms, consistent at any scale | Good, degrades as data grows without tuning |
| Schema | Flexible | Fixed, migrations needed |
| Ops burden | Lowest, nothing to size | Low, but you choose instance class and storage |
| Cost shape | Per request, scales to near zero | Per hour, you pay for an idle instance |
| Best when | Known access patterns, huge or spiky scale | Relational data, evolving queries, reporting |

A practical way to decide: write down your queries first. If you can list them all and they are all "fetch by this key" or "fetch a range under this key", DynamoDB will be cheaper, faster and simpler to operate. If you find yourself wanting `JOIN`, `GROUP BY` or "I'm not sure what we'll need to query yet", use RDS.

Using both is normal and often correct: RDS for the core transactional data, DynamoDB for sessions, caching and high-volume event data.

## References

- https://docs.aws.amazon.com/dynamodb/
- https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/best-practices.html
- https://docs.aws.amazon.com/rds/
- https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Concepts.MultiAZ.html
- https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_ReadRepl.html
