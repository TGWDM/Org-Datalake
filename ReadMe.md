# Org Datalake

A local-first data lake proof of concept, designed around AWS services and prototyped with Docker Compose. It ingests call recordings and call metadata exports, cleans them into typed tables, and exposes purpose-built tables for consumers.

> **Status:** The local stack and the clean-layer schema are in place.<br>
> **Next Steps:** Create pipeline for processing data from the raw layer into the clean layer

## Architecture

The lake follows a medallion layout: **raw → clean → prod** (bronze / silver / gold).

| Layer     | Contents                                                                           | Storage                                                        |
| --------- | ---------------------------------------------------------------------------------- | -------------------------------------------------------------- |
| **Raw**   | Immutable files exactly as received, split by source                               | `org-raw`, `org-recordings` buckets                            |
| **Clean** | Typed, deduplicated, conformed data. Sources merged, with `source_app` as a column | `clean` schema in Postgres, `org-clean` bucket for transcripts |
| **Prod**  | Purpose-built tables trimmed to what consumers need                                | `prod` schema in Postgres                                      |

Design principles:

- Segment by layer first, then domain, then entity.
- Sources (for example a telephony provider) are source systems, not domains. The domain is `calls`.
- One bucket per layer, so access, encryption and lifecycle rules apply at bucket level. The domain is a folder inside the bucket.
- Audio is stored once, in the raw recordings bucket. Tables hold only a `recording_uri` pointer.
- Pipelines are idempotent and read all endpoints and credentials from the environment, so moving to AWS is a configuration change.

### Bucket layout

```
org-raw/{domain}/{source}/{content}/...                 e.g. calls/<source>/metadata/export.csv
org-recordings/{domain}/{source}/year=/month=/day=/     audio files
org-clean/{domain}/transcripts/                         transcript JSON
```

### Local to AWS mapping

| AWS           | Local                                     |
| ------------- | ----------------------------------------- |
| S3            | RustFS (S3-compatible)                    |
| RDS Postgres  | Postgres 17 in Docker                     |
| Glue / Lambda | Python scripts (Dagster or Airflow later) |

## Repository layout

```
.
├── docker-compose.yml # Postgres, RustFS and one-shot init services
├── .env.example # Variable names with placeholder values
├── sql/ # Idempotent SQL, applied in filename order on every `up`
│   ├── 01_schemas.sql
│   └── 02_clean_call_metadata.sql
```

## Getting started

### Prerequisites

- Docker with Compose v2
- A Linux or WSL shell

### Setup

1. Copy the example environment file and fill in real values:

   ```bash
   cp .env.example .env
   ```

   Generate strong passwords with `openssl rand -base64 24`.

2. Start the stack:

   ```bash
   docker compose up -d
   ```

3. Check that everything is healthy:

   ```bash
   docker compose ps
   docker compose logs postgres-init rustfs-init
   ```

### Services

| Service         | Purpose                                    | Address (host)                                 |
| --------------- | ------------------------------------------ | ---------------------------------------------- |
| `postgres`      | Clean and prod tables                      | `localhost:5433`                               |
| `rustfs`        | S3-compatible object storage               | API `localhost:9000`, console `localhost:9001` |
| `postgres-init` | Applies every file in `./sql` on each `up` | n/a                                            |
| `rustfs-init`   | Creates the buckets if they don't exist    | n/a                                            |

Inside the compose network, services reach each other by name (`postgres:5432`, `http://rustfs:9000`). Use path-style S3 addressing and region `us-east-1`.

### Verify

```bash
# Schemas
docker compose exec postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "\dn"'

# Clean-layer table
docker compose exec postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "\d clean.call_metadata"'
```

## Data model (clean layer)

`clean.call_metadata` holds one row per call across all sources and companies:

- `call_id`: generated as `source_app || ':' || source_call_id`, so the same call always gets the same ID
- `source_app`, `source_call_id`, `company_id`
- Timestamps (`start_time`, `end_time`, `answered_time`) stored as `timestamptz` in UTC
- Durations in seconds (`call`, `hold`, `queue`, `wrap`, `total`) as `numeric(10,3)` with non-negative checks
- `recording_uri` and `transcript_uri` pointing into the lake

Rows that fail validation are intended to go to a quarantine table rather than being dropped.

## Security

This repository contains code and configuration only.

- Secrets live in `.env`, which is git-ignored. Only `.env.example` is committed.
- No real recordings, exports or transcripts are committed. Call data contains personal data (phone numbers, voices), so the PoC uses synthetic data only.
- Service ports are bound to `127.0.0.1` so they are not exposed to the local network.
- Image tags should be pinned to specific versions or digests.
- Run `gitleaks detect` before publishing and before large pushes.

For a production deployment on AWS, the intended controls are:

- Least-privilege IAM roles for ingest, clean and read-only access
- S3 Block Public Access, KMS encryption, versioning and TLS-only bucket policies
- Secrets Manager or SSM Parameter Store instead of `.env`
- RDS in private subnets with encryption at rest, and row-level security if companies need isolation
- CloudTrail and access logging, with retention rules for recordings
- A lawful basis for recording calls under UK GDPR, with phone numbers masked where consumers don't need them
