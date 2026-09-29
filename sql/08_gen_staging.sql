-- 08_gen_staging.sql  Deterministic staging table with HASH-based random seed
-- Generates ~4500 order lines with controlled on-time and partial-shipment rates:
--   ~80% on-time by customer receipt, ~92% on-time by ERP delivered date, ~10% partial
-- Dates start at 2024-01-01; shifted to final range by 13_shift_dates.sql

CREATE OR REPLACE TABLE ONETRUTH.RAW._STG AS
WITH
raw_seq AS (
    SELECT ROW_NUMBER() OVER (ORDER BY SEQ4()) AS rn
    FROM TABLE(GENERATOR(ROWCOUNT => 4500))
),
boundaries AS (
    SELECT rn,
           CASE WHEN rn = 1 THEN 1
                WHEN MOD(ABS(HASH(rn, 19)), 100) < 33 THEN 1
                ELSE 0 END AS new_order
    FROM raw_seq
),
ord_assign AS (
    SELECT rn, SUM(new_order) OVER (ORDER BY rn) AS order_num
    FROM boundaries
),
with_line AS (
    SELECT rn, order_num,
           ROW_NUMBER() OVER (PARTITION BY order_num ORDER BY rn) AS line_id
    FROM ord_assign
),
with_attrs AS (
    SELECT rn, order_num, line_id,
           'ORD-' || LPAD(order_num::STRING, 6, '0') AS order_id,
           'C-' || LPAD((MOD(ABS(HASH(order_num, 100)), 25) + 1)::STRING, 3, '0') AS customer_id,
           'PT-' || LPAD((MOD(ABS(HASH(rn, 200)), 40) + 1)::STRING, 3, '0') AS part_id,
           'P00' || (MOD(ABS(HASH(order_num, 150)), 3) + 1)::STRING AS plant_id,
           DATEADD('day', MOD(ABS(HASH(order_num, 250)), 181), '2024-01-01'::DATE) AS order_date,
           ABS(MOD(HASH(rn, 300), 1000000)) / 1000000.0 AS fate,
           MOD(ABS(HASH(rn, 350)), 491) + 10 AS ordered_qty,
           ROUND(5.0 + 495.0 * ABS(MOD(HASH(rn, 450), 1000000)) / 1000000.0, 2) AS unit_price
    FROM with_line
),
with_promised AS (
    SELECT *,
           DATEADD('day', MOD(ABS(HASH(rn, 400)), 16) + 10, order_date) AS promised_date,
           CASE WHEN ABS(MOD(HASH(rn, 600), 1000)) < 100
                THEN GREATEST(ROUND(ordered_qty * (0.3 + 0.6 * ABS(MOD(HASH(rn, 700), 1000)) / 1000.0))::INT, 1)
                ELSE ordered_qty END AS shipped_qty
    FROM with_attrs
),
with_erp AS (
    SELECT *,
           CASE
               WHEN fate < 0.80
                   THEN DATEADD('day', -(MOD(ABS(HASH(rn, 500)), 6) + 2), promised_date)
               WHEN fate < 0.92
                   THEN DATEADD('day', -(MOD(ABS(HASH(rn, 500)), 3) + 1), promised_date)
               ELSE DATEADD('day', MOD(ABS(HASH(rn, 500)), 8) + 1, promised_date)
           END AS erp_delivered_date
    FROM with_promised
)
SELECT * FROM with_erp;
