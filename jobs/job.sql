-- read in the data from the table in mariadb
CREATE TABLE sales_records_table (
    sale_id INT,
    product_id INT,
    sale_date DATE,
    sale_amount DECIMAL(10, 2),
    PRIMARY KEY (sale_id) NOT ENFORCED
) WITH (
    'connector' = 'mysql-cdc',
    'hostname' = 'mariadb',
    'port' = '3306',
    'username' = 'root',
    'password' = 'rootpassword',
    'database-name' = 'sales_database',
    'table-name' = 'sales_records'
);

-- create a view that aggregates the sales records
CREATE TEMPORARY VIEW total_sales AS
SELECT
    SUM(sale_amount) AS total_sales_amount
FROM
    sales_records_table;

-- create a MariaDB sink table for analytics
CREATE TABLE mariadb_analytics_sink (
    metric_name STRING,
    metric_value DECIMAL(15, 2),
    calculated_at TIMESTAMP(3),
    PRIMARY KEY (metric_name) NOT ENFORCED
) WITH (
    'connector' = 'jdbc',
    'url' = 'jdbc:mysql://mariadb:3306/sales_database',
    'username' = 'root',
    'password' = 'rootpassword',
    'table-name' = 'sales_analytics',
    'sink.buffer-flush.max-rows' = '1',
    'sink.buffer-flush.interval' = '1s'
);

-- insert the aggregated sales records into the MariaDB analytics table
INSERT INTO
    mariadb_analytics_sink
SELECT
    'total_sales' AS metric_name,
    total_sales_amount AS metric_value,
    CURRENT_TIMESTAMP AS calculated_at
FROM
    total_sales;