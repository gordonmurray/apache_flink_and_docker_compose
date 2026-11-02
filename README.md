# Apache Flink CDC with Docker Compose

A local demo that captures changes from MariaDB, calculates total sales with
Flink SQL, and writes the result back to MariaDB through JDBC.

The stack has one MariaDB server, one JobManager and two TaskManagers. It is a
learning environment with local demo credentials, not a production deployment.

## Versions

| Component | Version |
| --- | --- |
| Apache Flink / Java | 2.2.1 / 17 |
| MySQL CDC connector | 3.7.0-2.2 |
| JDBC core and MySQL connector | 4.1.0-2.2 |
| MySQL JDBC driver | 8.4.0 |
| MariaDB | 11.8 |

Flink 2.2 is the shared compatibility target for these CDC and JDBC releases.
Connector versions and SHA-256 hashes are pinned in [connectors.lock](connectors.lock).
MariaDB uses the maintained `11.8` image tag; CI exercises this combination.

## Quick start

Install Docker with the Compose plugin and Python 3. Allow roughly 4 GB of memory
for the containers. No Python packages are required.

```bash
git clone https://github.com/gordonmurray/apache_flink_and_docker_compose.git
cd apache_flink_and_docker_compose
cp .env.example .env
python3 scripts/demo.py start
python3 scripts/demo.py check
```

`start` builds the image, waits for the services and submits the `sales-total`
job. Running it again reuses the active job. Do not run concurrent submissions.

`check` verifies the initial total, inserts a sale, updates its amount, and
deletes it. Each step waits for the matching result in `sales_analytics`. The
temporary row is removed afterwards. Run one check at a time without other writes.

A fresh database contains ten sales totalling **5,500.00**. Open the
[Flink dashboard](http://localhost:8081) to inspect the job and checkpoints.

## Inspect or change the data

Open the database shell with the root password configured in `.env`:

```bash
docker compose exec mariadb mariadb -uroot -p sales_database
```

```sql
SELECT * FROM sales_analytics;
SELECT SUM(sale_amount) FROM sales_records;

-- Repeatable example: run each statement separately and inspect the result.
INSERT INTO sales_records
  (sale_id, product_id, product_name, sale_date, sale_amount)
VALUES (11, 111, 'Example product', CURRENT_DATE, 150.00)
ON DUPLICATE KEY UPDATE sale_amount = VALUES(sale_amount);

UPDATE sales_records SET sale_amount = 175.00 WHERE sale_id = 11;
DELETE FROM sales_records WHERE sale_id = 11;
```

The pipeline uses dedicated `flink_cdc` and `flink_sink` accounts. Root is used
only for local administration and the test helper.

## Configuration and storage

Edit `.env` before the first start to change the demo passwords or host ports.
CDC and sink passwords accept letters, digits and underscores. MariaDB and the
Flink dashboard bind to localhost. The defaults are ports `3306` and `8081`.

Database initialization runs only when the data volume is empty. Changing a
password in `.env` does not update an existing database user; update that user
with SQL too, or reset the demo if its data can be discarded.

| Named volume | Contents |
| --- | --- |
| `mariadb-data` | Database tables and binary logs |
| `flink-checkpoints` | Retained checkpoints |
| `flink-savepoints` | Savepoints created manually |

Binary logs are retained for seven days. A checkpoint cannot resume if its
required logs have expired or if the source database has been replaced.

```bash
# Stop containers and keep data and Flink state.
docker compose down

# Delete all demo data, checkpoints and savepoints, then start fresh.
docker compose down -v
python3 scripts/demo.py start
```

When upgrading an older checkout, back up any data you need first. The named
volume does not automatically adopt the previous anonymous database volume or
container-local binlogs. Existing databases also need the new users from
[sql/users.sh](sql/users.sh). Start a fresh job against a freshly initialized
database. Restoring old checkpoints across this major Flink upgrade is not tested.

## Checkpoint recovery

```bash
python3 scripts/demo.py recovery
```

Run this against the demo only: it deliberately kills one TaskManager and then
recreates the entire Compose stack. It waits for a completed checkpoint first,
verifies automatic worker recovery and the resulting sales total, then checks
that database data and binlogs survive container recreation. Finally, it
explicitly resubmits the job from a retained checkpoint and verifies changes
made while the job was stopped.

A TaskManager failure can recover automatically while the JobManager survives.
This session cluster has no JobManager high availability: keeping checkpoint
files alone does not automatically resubmit a job after the JobManager is lost.
Before stopping, copy a completed checkpoint's external path from the dashboard.
After restarting the containers, restore the same job version explicitly:

```bash
docker compose up -d --wait
python3 scripts/demo.py restore file:///opt/flink/checkpoints/JOB_ID/chk-N
```

Replace the example URI with the real path. The helper refuses to restore while
an active demo job exists. Using `start` after losing the JobManager submits a
fresh job and snapshots the database instead of restoring prior Flink state.

Flink checkpoints provide consistent processing state. The JDBC sink uses
at-least-once writes and a primary-key upsert so replayed totals converge on one
row. This is not an end-to-end exactly-once transaction guarantee, and
`calculated_at` can change during replay. No latency target is promised.

## Troubleshooting and CI

```bash
docker compose ps
docker compose logs --tail=100 mariadb jobmanager taskmanager
```

If a check times out, inspect the job's exceptions and checkpoint status in the
dashboard. Ensure both workers are running. The test reserves sale ID
`2147483600`; after an interrupted test, inspect and remove that row if necessary.

[GitHub Actions](https://github.com/gordonmurray/apache_flink_and_docker_compose/actions/workflows/demo.yml) builds the stack, runs the CDC
checks twice, and verifies worker and full-cluster recovery. CI removes its own
volumes at the end. Prometheus monitoring is not included.

Licensed under the [MIT License](LICENSE).
