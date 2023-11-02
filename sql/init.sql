CREATE DATABASE IF NOT EXISTS sales_database;

USE sales_database;

CREATE TABLE sales_records (
    sale_id INT PRIMARY KEY,
    product_id INT,
    product_name VARCHAR(255),
    sale_date DATE,
    sale_amount DECIMAL(10, 2)
);

-- Insert sample sales records
INSERT INTO sales_records (sale_id, product_id, product_name, sale_date, sale_amount)
VALUES
    (1, 101, 'Product A', '2023-01-01', 100.00),
    (2, 102, 'Product B', '2023-01-02', 200.00),
    (3, 103, 'Product C', '2023-01-03', 300.00),
    (4, 104, 'Product D', '2023-01-04', 400.00),
    (5, 105, 'Product E', '2023-01-05', 500.00),
    (6, 106, 'Product F', '2023-01-06', 600.00),
    (7, 107, 'Product G', '2023-01-07', 700.00),
    (8, 108, 'Product H', '2023-01-08', 800.00),
    (9, 109, 'Product I', '2023-01-09', 900.00),
    (10, 110, 'Product J', '2023-01-10', 1000.00);
