# Cloud Deployment Guide

This project is currently a Python Streamlit application with MySQL and optional Redis. The repository has no provider-specific infrastructure-as-code, so this document is a cloud deployment blueprint to adapt to the target provider.

## Recommended production shape

```text
Users -> HTTPS ingress -> Streamlit application service -> Managed MySQL
                                      |
                                      +-> Managed Redis (optional)
                                      +-> Durable object storage for run exports
```

Use managed MySQL rather than running the database in the same container as Streamlit. Use durable object storage for `outputs/` when application disk is ephemeral.

## Resources to provision

- Managed MySQL 8.0 with private network access, backups, and point-in-time recovery.
- A container or Python application service running Streamlit.
- A secret store for database credentials and application settings.
- Durable object storage for exported run artifacts.
- HTTPS ingress and access control for the dashboard.
- Monitoring for application health, database connectivity, failed runs, and export failures.
- Optional managed Redis only when caching or asynchronous work is enabled.

## Build and start

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m src.cli db upgrade
python -m streamlit run app.py --server.address 0.0.0.0 --server.port ${PORT:-8501}
```

For providers that require a fixed port, replace `${PORT:-8501}` with the platform's configured port expression.

## Required environment variables

```text
DB_HOST=<managed-mysql-host>
DB_PORT=3306
DB_NAME=data_quality_db
DB_USER=<application-user>
DB_PASSWORD=<secret>
DB_POOL_SIZE=5
DB_MAX_OVERFLOW=10
PIPELINE_VERSION=1.0.0
LOG_LEVEL=INFO
OUTPUT_DIR=outputs
DATA_DIR=data
REDIS_HOST=<managed-redis-host>
REDIS_PORT=6379
REDIS_ENABLED=false
```

Inject these values through the cloud secret/configuration service. Never place credentials in source control, container images, or browser-visible configuration.

## Release sequence

1. Build and scan the application image or deployment artifact.
2. Provision or verify the managed MySQL database and application user.
3. Apply `python -m src.cli db upgrade` using a controlled release job.
4. Deploy the Streamlit service with the new artifact and environment configuration.
5. Confirm the service responds and verify the database status indicator in Settings.
6. Run a small known input dataset and verify summary/reconciliation artifacts.
7. Promote traffic only after the smoke run succeeds.

## Security checklist

- Restrict the dashboard behind SSO, VPN, private ingress, or equivalent access control.
- Allow database access only from the application network/security group.
- Enable TLS for managed database connections where supported.
- Rotate credentials through the secret manager.
- Use least-privilege database permissions.
- Avoid logging raw sensitive payloads or credentials.
- Apply retention and access controls to rejected records and audit files.
- Test MySQL backup restoration regularly.

## Scaling and operations

The current app and CLI run synchronously. For larger or concurrent workloads, separate the UI from a worker service that invokes the pipeline, then introduce a queue and managed Redis when that worker architecture exists.

Monitor Streamlit restarts and latency, MySQL pool exhaustion and query latency, `pipeline_runs` statuses, reconciliation failures, export failures, and benchmark throughput.

## Current deployment limitations

The repository does not currently include a Dockerfile, provider manifests, CI/CD workflow, object-storage exporter, or dedicated worker/queue process. Those should be added before calling deployment fully production-ready on a specific cloud provider.

See [OPERATIONS.md](OPERATIONS.md) for operational procedures.
