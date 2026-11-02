#!/usr/bin/env python3
"""Start and exercise the local CDC demo using Docker Compose and Python 3."""
import argparse
from decimal import Decimal
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
JOB_NAME = "sales-total"
TERMINAL = {"FINISHED", "FAILED", "CANCELED", "SUSPENDED"}
PROBE_ID = 2147483600


def compose(*args):
    result = subprocess.run(
        ["docker", "compose", *args], cwd=ROOT, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=600,
    )
    if result.returncode:
        raise RuntimeError(result.stdout.strip())
    return result.stdout.strip()


def db(sql):
    return compose("exec", "-T", "mariadb", "sh", "-c",
                   'MYSQL_PWD="$MARIADB_ROOT_PASSWORD" exec mariadb '
                   '--user=root --batch --skip-column-names sales_database --execute "$1"',
                   "--", sql)


def api(path, *curl_args):
    return json.loads(compose("exec", "-T", "jobmanager", "curl", "--fail",
                              "--silent", "--show-error", "--max-time", "10",
                              *curl_args, f"http://localhost:8081/{path}"))


def wait_for(description, predicate, timeout=180):
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        try:
            value = predicate()
            if value:
                print(f"OK: {description}", flush=True)
                return value
        except (RuntimeError, ValueError, KeyError) as exc:
            last_error = exc
        time.sleep(2)
    raise RuntimeError(f"Timed out waiting for {description}. Last error: {last_error}")


def active_job():
    jobs = [job for job in api("jobs/overview")["jobs"]
            if job["name"] == JOB_NAME and job["state"] not in TERMINAL]
    if len(jobs) > 1:
        raise RuntimeError("Multiple sales-total jobs found; cancel duplicates in the Flink UI.")
    return jobs[0] if jobs else None


def running_job():
    job = active_job()
    return job if job and job["state"] == "RUNNING" else None


def submit(restore=None):
    job = active_job()
    if restore and job:
        raise RuntimeError("Cancel the active job before restoring a checkpoint or savepoint.")
    if not job:
        args = (restore,) if restore else ()
        output = compose("exec", "-T", "jobmanager", "/opt/flink/submit-job.sh", *args)
        if "[ERROR]" in output:
            raise RuntimeError(output)
    return wait_for("one running sales-total job", running_job)["jid"]


def start():
    print("Building and starting the demo...", flush=True)
    compose("build", "jobmanager")
    compose("up", "-d", "--no-build", "--wait", "--wait-timeout", "180")
    wait_for("two TaskManagers", lambda: len(api("taskmanagers")["taskmanagers"]) == 2)
    return submit()


def total():
    return Decimal(db("SELECT COALESCE(SUM(sale_amount), 0) FROM sales_records"))


def expect_total(expected, description):
    def matches():
        value = db("SELECT metric_value FROM sales_analytics WHERE metric_name='total_sales'")
        return value and Decimal(value) == expected and total() == expected
    wait_for(f"{description}: total {expected:.2f}", matches)


def ensure_probe_absent():
    if db(f"SELECT COUNT(*) FROM sales_records WHERE sale_id={PROBE_ID}") != "0":
        raise RuntimeError(f"Reserved demo row {PROBE_ID} already exists; remove it before testing.")


def insert_probe(amount):
    db(f"INSERT INTO sales_records VALUES ({PROBE_ID}, 999, 'CDC test', CURRENT_DATE, {amount})")


def remove_probe():
    db(f"DELETE FROM sales_records WHERE sale_id={PROBE_ID} AND product_name='CDC test'")


def check():
    wait_for("one running sales-total job", running_job)
    ensure_probe_absent()
    baseline = total()
    expect_total(baseline, "initial snapshot")
    try:
        insert_probe("12.34")
        expect_total(baseline + Decimal("12.34"), "insert captured")
        db(f"UPDATE sales_records SET sale_amount=98.76 WHERE sale_id={PROBE_ID}")
        expect_total(baseline + Decimal("98.76"), "update captured")
        remove_probe()
        expect_total(baseline, "delete captured")
    finally:
        remove_probe()


def checkpoint(job_id, after_id=-1):
    def completed():
        latest = api(f"jobs/{job_id}/checkpoints")["latest"].get("completed")
        return latest if latest and latest["id"] > after_id and latest.get("external_path") else None
    return wait_for("a completed persistent checkpoint", completed)


def recovery():
    """Kill one worker, then recreate the cluster and explicitly restore state."""
    job_id = wait_for("one running sales-total job", running_job)["jid"]
    ensure_probe_absent()
    baseline = total()
    expect_total(baseline, "before recovery")
    checkpoint(job_id)
    restores_before = api(f"jobs/{job_id}/checkpoints")["counts"]["restored"]
    workers = compose("ps", "-q", "taskmanager").splitlines()
    if len(workers) != 2:
        raise RuntimeError("Recovery test requires exactly two TaskManagers.")
    worker = workers[0]
    try:
        subprocess.run(["docker", "kill", "--signal", "KILL", worker], check=True, timeout=30)
        insert_probe("12.34")
    finally:
        subprocess.run(["docker", "start", worker], check=True, timeout=30)
    try:
        wait_for("TaskManager checkpoint recovery", lambda:
                 api(f"jobs/{job_id}/checkpoints")["counts"]["restored"] > restores_before)
        wait_for("job running after worker failure", running_job)
        expect_total(baseline + Decimal("12.34"), "change during worker outage")

        # Wait for a new checkpoint after the observed database result.
        last = checkpoint(job_id)
        saved = checkpoint(job_id, after_id=last["id"])
        path = saved["external_path"]
        binlog = db("SHOW MASTER STATUS").split("\t")[0]
        print(f"Recreating containers; restoring {path}", flush=True)
        compose("down")
        compose("up", "-d", "--no-build", "--wait", "--wait-timeout", "180")
        if total() != baseline + Decimal("12.34"):
            raise RuntimeError("MariaDB data did not survive container recreation.")
        retained_logs = {line.split("\t")[0] for line in db("SHOW BINARY LOGS").splitlines()}
        if binlog not in retained_logs:
            raise RuntimeError("The checkpoint's binary log did not survive recreation.")
        if active_job():
            raise RuntimeError("Expected a fresh JobManager without a submitted job.")
        db(f"UPDATE sales_records SET sale_amount=98.76 WHERE sale_id={PROBE_ID}")
        restored_id = submit(path)
        wait_for("explicit checkpoint restoration", lambda:
                 api(f"jobs/{restored_id}/checkpoints")["latest"].get("restored", {}).get("external_path") == path)
        expect_total(baseline + Decimal("98.76"), "change while the job was stopped")
        remove_probe()
        expect_total(baseline, "delete after recovery")
    finally:
        remove_probe()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["start", "check", "recovery", "restore"])
    parser.add_argument("path", nargs="?", help="checkpoint or savepoint URI for restore")
    args = parser.parse_args()
    if (args.command == "restore") != bool(args.path):
        parser.error("restore requires a checkpoint/savepoint URI; other commands take no path")
    if args.command == "start":
        start()
    elif args.command == "check":
        check()
    elif args.command == "recovery":
        recovery()
    else:
        submit(args.path)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, subprocess.SubprocessError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
