FROM flink:2.2.1-java17

USER root

# Pin connector bytes as well as versions; fail on HTTP errors or checksum mismatch.
COPY connectors.lock /tmp/connectors.lock
RUN set -eu; \
    while read -r checksum artifact; do \
      case "$checksum" in \#*|'') continue ;; esac; \
      jar="/opt/flink/lib/${artifact##*/}"; \
      curl --fail --show-error --silent --location --retry 3 \
        "https://repo.maven.apache.org/maven2/$artifact" --output "$jar"; \
      echo "$checksum  $jar" | sha256sum --check --strict -; \
    done < /tmp/connectors.lock; \
    rm /tmp/connectors.lock; \
    mkdir -p /opt/flink/checkpoints /opt/flink/savepoints; \
    chown -R flink:flink /opt/flink/lib /opt/flink/checkpoints /opt/flink/savepoints

COPY --chown=flink:flink jobs/job.sql /opt/flink/job.sql
COPY --chmod=755 scripts/submit-job.sh /opt/flink/submit-job.sh

USER flink
