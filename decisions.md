# Design Decisions
 
Wikimedia recent-changes pipeline on AWS, built to run on the free tier. This file records what I chose, why, what it costs me, and what I would revisit. Each entry is short on purpose.
 
## Platform and access
 
### D1. IAM user for local CLI, not IAM Identity Center
- **Why:** Joining AWS Organizations (which Identity Center normally needs) upgrades a free-plan account to a paid plan and ends free-tier credits.
- **Tradeoff:** The IAM user has a long-lived access key on my machine. Mitigations: MFA on the user, key never committed, and CI uses OIDC (D4) so no keys live in GitHub.
- **Revisit if:** the account moves to a paid plan; then use Identity Center with short-lived credentials.
### D2. Terraform instead of CloudFormation, CDK or SAM
- **Why:** Terraform appears in far more data engineering job postings, is cloud-agnostic, and the same skill carries over to Databricks provisioning.
- **Tradeoff:** SAM would be faster for a Lambda-only project. I accepted slower setup for the transferable skill.
### D3. Remote state in S3 with native locking; bootstrap stack uses local state
- **Why:** `use_lockfile` (S3-native locking) removes the need for a DynamoDB lock table. The bootstrap stack creates the state bucket itself, so it cannot use that bucket as its own backend.
- **Tradeoff:** The bootstrap state lives only on my machine. It changes rarely and is easy to re-import.
### D4. GitHub Actions authenticates to AWS with OIDC, one broad role
- **Why:** No AWS keys stored in GitHub. The trust policy only accepts tokens from this repo's `main` branch and its pull requests.
- **Tradeoff:** The CI role has AdministratorAccess, which is not least privilege. This is a single-owner sandbox account.
- **Revisit:** Split into a read-only plan role and a narrowly scoped apply role.
## Ingestion
 
### D5. Scheduled micro-batch instead of continuous streaming
- **Why:** Always-on streaming infrastructure (Kinesis bills per stream-hour; MSK is costlier) is not free. A Lambda on a 5-minute schedule consumes the live Wikimedia stream from a checkpoint, which keeps the cost near zero.
- **Honest limit:** This is near-real-time micro-batch, not continuous streaming. It does not demonstrate Kafka, Flink or exactly-once semantics at volume.
- **At scale I would use:** Kinesis or MSK as the buffer, with a managed stream processor, and keep S3 as the landing zone.
### D6. Write data first, then advance the checkpoint; S3 keys derived from the starting checkpoint
- **Why:** If a run dies between the two steps, the next run re-reads the same events (at-least-once). Because the object key is a hash of the starting checkpoint, a retry overwrites the same file instead of creating a duplicate.
- **Tradeoff:** The event at a batch boundary can be delivered twice. It is deduplicated downstream on `meta.id`.
### D7. Stop when caught up instead of fixed-length windows
- **Why:** Each run drains the backlog since the last checkpoint and exits once events are under 10 seconds old. Runs are short and cheap, and no events are skipped as long as the gap between runs stays inside the stream's retention window (about a week).
### D8. Standard-library-only ingest Lambda, no VPC
- **Why:** No packaging or layers to maintain. A VPC would need a NAT gateway to reach the public stream, which costs money.
### D9. Schedule deployed disabled, enabled after a manual test
- **Why:** Lets me test and inspect a single run before anything runs unattended. The enabled flag is a Terraform variable, so the change is reviewed in a PR.
### D10. DynamoDB checkpoint table uses provisioned 1 RCU / 1 WCU
- **Why:** Stays inside DynamoDB's always-free capacity. The table has one item and a few writes per hour.
## Processing
 
### D11. Raw layer is complete and verbatim; the English filter lives in silver
- **Why:** Keeping every event means I can change the filter (another language, another wiki) and reprocess without losing history. The filter is the `TARGET_WIKI` setting, default `enwiki` (English Wikipedia only; English Wiktionary and others are separate wikis).
- **Tradeoff:** Raw storage is several times larger than the filtered data. It expires after 30 days, so the cost is small. Filtering at ingest would save storage but make raw lossy.
### D12. Filtered-out events and quarantined events are different things
- **Why:** An event from another wiki is valid but out of scope; it is counted and dropped. A malformed or unexpected event is a data problem; it goes to quarantine with an error code and the original line, so it can be inspected and replayed.
### D13. Per-record validation and an explicit Parquet schema
- **Why:** One bad record must never fail a whole batch. Every record is validated and type-coerced; only records that fit the schema reach silver. An unknown event `type` lands in quarantine, which doubles as schema-drift detection. Timestamps are written at millisecond precision for broad Athena compatibility.
### D14. AWS-managed SDK for pandas layer for pyarrow
- **Why:** Avoids building and size-tuning a custom pyarrow package.
- **Tradeoff:** Depends on an AWS-managed layer version that I pin in Terraform.
### D15. Retries, a dead-letter queue, and a guard against trigger loops
- **Why:** Failed invocations retry twice, then land in an SQS queue instead of disappearing. The S3 trigger is limited to `raw/` and `.jsonl.gz`; without that prefix filter the Lambda's own outputs would re-trigger it in a loop. The handler also ignores any key outside `raw/` as a second safeguard.
### D16. Deduplicate within a batch only
- **Why:** The processor sees one batch at a time. Cross-batch duplicates (the boundary event from D6) are removed in the dbt layer, where the full history is available.
## Catalog and querying
 
### D17. Glue tables defined in Terraform, no crawlers
- **Why:** The schema is versioned, reviewed in PRs, and exactly what I wrote. Crawlers cost DPU-hours and can infer the wrong types.
- **Tradeoff:** The table definition and the writer's Parquet schema can drift apart. A unit test compares them in CI (D20).
### D18. Partition projection instead of stored partitions
- **Why:** Athena computes `dt=.../hr=...` locations from a pattern, so there are no crawlers and no `MSCK REPAIR` or partition-add jobs. New hourly folders are queryable immediately.
- **Tradeoff:** The date range has a fixed lower bound that I set in config. Queries without a `dt` filter scan every projected partition, so I always filter on `dt`.
### D19. Athena workgroup with a scan cap and short result retention
- **Why:** A per-query data-scanned cap (1 GB) turns a runaway query into an error instead of a bill. Query results expire after 7 days.
### D20. Contract test between the writer's schema and the catalog
- **Why:** The one real drift risk in this design is the Parquet schema in code and the table definition in Terraform disagreeing. CI fails if their column names or types differ.
## Cost
 
Everything is chosen to sit inside always-free or free-plan limits: Lambda, DynamoDB (provisioned 1/1), S3 with lifecycle expiry, Glue Data Catalog, EventBridge, SQS, CloudWatch with short log retention, and Athena with a scan cap. A budget alarm is defined in Terraform.
 
| Item | Measured monthly cost |
|---|---|
| Total AWS bill | _fill in from Billing after a full month_ |
| S3 storage (raw, silver) | _fill in_ |
| Athena data scanned | _fill in_ |
 
The free plan ends after six months or when credits run out unless upgraded to a paid plan. The stack is fully reproducible from Terraform, and the README captures sample outputs so the project does not depend on the live account staying up.
 
## Known limitations
 
- Micro-batch, not continuous streaming (D5).
- CI role is broader than least privilege (D4).
- Cross-batch deduplication happens downstream, not at ingest (D16).
- Single environment, single region, no multi-account setup.
## Code map
 
| File | What it does |
|---|---|
| `infra/bootstrap/main.tf` | One-time stack with local state. Creates the Terraform state bucket and the GitHub Actions OIDC provider and role. |
| `infra/envs/dev/main.tf` | Core stack. Remote-state backend, the data lake bucket (encryption, public access block, lifecycle expiry) and the monthly budget alarm. |
| `infra/envs/dev/ingest.tf` | Ingest path. Checkpoint table, ingest Lambda with a least-privilege role, log group, and the 5-minute EventBridge schedule. |
| `infra/envs/dev/process.tf` | Processing path. S3-triggered processing Lambda, the managed pyarrow layer, retry config and the dead-letter queue. |
| `infra/envs/dev/catalog.tf` | Glue database plus the silver and quarantine tables, using partition projection. |
| `infra/envs/dev/athena.tf` | Athena workgroup with a per-query scan cap and an enforced results location. |
| `src/ingest/sse.py` | Pure helpers. Parses server-sent events, reads event timestamps, builds the deterministic S3 key. |
| `src/ingest/handler.py` | Ingest Lambda. Resumes the Wikimedia stream from the checkpoint until caught up, writes one raw batch, then advances the checkpoint. |
| `src/process/transform.py` | Pure logic. Parses, filters by wiki, validates, flattens and deduplicates raw events into silver rows and quarantine records. |
| `src/process/writer.py` | Defines the silver Parquet schema and serializes rows to Parquet bytes. |
| `src/process/handler.py` | Processing Lambda. For each new raw batch, writes silver Parquet and quarantine files and logs counts. |
| `tests/` | Unit tests for the helpers, the transform and the writer, plus the catalog-to-schema contract test. |
| `scripts/make_test_batch.py` | Builds a synthetic raw batch (good, filtered, invalid, duplicate) to test the processor end to end. |
| `.github/workflows/terraform.yml` | fmt, validate and plan on pull requests; apply on merge to `main`, authenticated through OIDC. |
| `.github/workflows/python.yml` | Runs ruff and pytest on changes to code, tests or the catalog definition. |
| `pytest.ini` | Puts both Lambda source folders on the test import path. |
 