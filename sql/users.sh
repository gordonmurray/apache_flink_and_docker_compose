#!/usr/bin/env bash
set -euo pipefail
# Restrict demo passwords to avoid SQL and template escaping ambiguities.
for value in "$CDC_PASSWORD" "$SINK_PASSWORD"; do
  [[ "$value" =~ ^[a-zA-Z0-9_]+$ ]] || {
    echo 'CDC_PASSWORD and SINK_PASSWORD must contain only letters, digits or underscores.' >&2
    exit 1
  }
done
MYSQL_PWD="$MARIADB_ROOT_PASSWORD" mariadb --user=root <<SQL
CREATE USER 'flink_cdc'@'%' IDENTIFIED BY '$CDC_PASSWORD';
GRANT SELECT ON sales_database.sales_records TO 'flink_cdc'@'%';
GRANT RELOAD, SHOW DATABASES, REPLICATION SLAVE, REPLICATION CLIENT ON *.* TO 'flink_cdc'@'%';
CREATE USER 'flink_sink'@'%' IDENTIFIED BY '$SINK_PASSWORD';
GRANT SELECT, INSERT, UPDATE, DELETE ON sales_database.sales_analytics TO 'flink_sink'@'%';
SQL
