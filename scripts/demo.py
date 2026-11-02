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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["start", "check"])
    args = parser.parse_args()
    if args.command == "start":
        start()
    else:
        check()


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, subprocess.TimeoutExpired) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
