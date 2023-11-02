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

-- create a redis sink table
CREATE TABLE redis_sink (
    key_name STRING,
    total DECIMAL(10, 2),
    PRIMARY KEY (key_name) NOT ENFORCED
) WITH (
    'connector' = 'redis',
    'redis-mode' = 'single',
    'host' = 'redis',
    'port' = '6379',
    'database' = '0',
    'command' = 'SET'
);

-- insert the aggregated sales records into the redis sink table
INSERT INTO
    redis_sink
SELECT
    'total_sales',
    total_sales_amount
FROM
    total_sales;