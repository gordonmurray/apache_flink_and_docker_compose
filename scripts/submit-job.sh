#!/usr/bin/env bash
set -euo pipefail
for value in "$CDC_PASSWORD" "$SINK_PASSWORD"; do
  [[ "$value" =~ ^[a-zA-Z0-9_]+$ ]] || {
    echo 'CDC_PASSWORD and SINK_PASSWORD must contain only letters, digits or underscores.' >&2
    exit 1
  }
done
job_file=$(mktemp /tmp/flink-job.XXXXXX.sql)
trap 'rm -f "$job_file"' EXIT
sed -e "s/__CDC_PASSWORD__/$CDC_PASSWORD/g" \
    -e "s/__SINK_PASSWORD__/$SINK_PASSWORD/g" /opt/flink/job.sql > "$job_file"
# The optional argument is a checkpoint/savepoint URI from this same job version.
if [[ $# -gt 0 ]]; then
  [[ "$1" =~ ^file:///opt/flink/(checkpoints|savepoints)/[a-zA-Z0-9/_-]+$ ]] || {
    echo 'Expected a checkpoint or savepoint URI under /opt/flink.' >&2
    exit 1
  }
  sed -i "1i SET 'execution.savepoint.path' = '$1';" "$job_file"
fi
/opt/flink/bin/sql-client.sh -f "$job_file"
