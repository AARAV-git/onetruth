-- 09_gen_orders_erp.sql  Create ORDERS_ERP from staging
CREATE OR REPLACE TABLE ONETRUTH.RAW.ORDERS_ERP AS
SELECT order_id, line_id, customer_id, part_id, plant_id,
       order_date, promised_date, ordered_qty, shipped_qty, unit_price, erp_delivered_date
FROM ONETRUTH.RAW._STG;
