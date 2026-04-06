FROM flink:1.19.3-java17

# Download CDC and connector JARs
ARG MYSQL_CDC_VERSION=3.1.0
ARG JDBC_VERSION=3.2.0-1.19
ARG MYSQL_DRIVER_VERSION=8.4.0

RUN set -eux; \
    # MySQL CDC Connector
    curl -L -o /opt/flink/lib/flink-sql-connector-mysql-cdc-${MYSQL_CDC_VERSION}.jar \
      https://repo1.maven.org/maven2/org/apache/flink/flink-sql-connector-mysql-cdc/${MYSQL_CDC_VERSION}/flink-sql-connector-mysql-cdc-${MYSQL_CDC_VERSION}.jar; \
    # JDBC Connector  
    curl -L -o /opt/flink/lib/flink-connector-jdbc-${JDBC_VERSION}.jar \
      https://repo1.maven.org/maven2/org/apache/flink/flink-connector-jdbc/${JDBC_VERSION}/flink-connector-jdbc-${JDBC_VERSION}.jar; \
    # MySQL JDBC Driver
    curl -L -o /opt/flink/lib/mysql-connector-j-${MYSQL_DRIVER_VERSION}.jar \
      https://repo1.maven.org/maven2/com/mysql/mysql-connector-j/${MYSQL_DRIVER_VERSION}/mysql-connector-j-${MYSQL_DRIVER_VERSION}.jar

# Set proper ownership
RUN chown flink:flink /opt/flink/lib/*.jar

# Create checkpoint and savepoint directories with correct ownership
RUN mkdir -p /opt/flink/checkpoints /opt/flink/savepoints && \
    chown flink:flink /opt/flink/checkpoints /opt/flink/savepoints

# Verify JARs were downloaded
RUN ls -la /opt/flink/lib/flink-*mysql* /opt/flink/lib/flink-*jdbc* /opt/flink/lib/mysql-connector*