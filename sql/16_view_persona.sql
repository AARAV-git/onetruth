-- 16_view_persona.sql  Four OTD perspectives for Q3 2026
CREATE OR REPLACE VIEW ONETRUTH.APP.PERSONA_BEFORE_ONETRUTH AS
WITH q3_lines AS (
    SELECT o.order_id, o.line_id, o.promised_date, o.erp_delivered_date,
           o.shipped_qty, o.ordered_qty,
           s.gate_in_ts, s.customer_receipt_ts
    FROM ONETRUTH.RAW.ORDERS_ERP o
    JOIN ONETRUTH.RAW.SHIPMENTS_LOGISTICS s
      ON o.order_id = s.order_id AND o.line_id = s.line_id
    WHERE o.promised_date BETWEEN '2026-07-01' AND '2026-09-30'
),
planning AS (
    SELECT ROUND(100.0 * SUM(CASE WHEN erp_delivered_date <= promised_date THEN 1 ELSE 0 END)
                 / COUNT(*), 1) AS otd
    FROM q3_lines
),
logistics AS (
    SELECT ROUND(100.0 * SUM(CASE WHEN gate_in_ts::DATE <= promised_date THEN 1 ELSE 0 END)
                 / COUNT(*), 1) AS otd
    FROM q3_lines
),
procurement AS (
    SELECT ROUND(100.0 *
        SUM(CASE WHEN lines_in_order = on_time_and_full THEN 1 ELSE 0 END)::FLOAT
        / COUNT(*), 1) AS otd
    FROM (
        SELECT order_id,
               COUNT(*) AS lines_in_order,
               SUM(CASE WHEN erp_delivered_date <= promised_date
                         AND shipped_qty >= ordered_qty THEN 1 ELSE 0 END) AS on_time_and_full
        FROM q3_lines
        GROUP BY order_id
    )
),
governed AS (
    SELECT ROUND(100.0 * SUM(CASE WHEN customer_receipt_ts::DATE <= promised_date THEN 1 ELSE 0 END)
                 / COUNT(*), 1) AS otd
    FROM q3_lines
    WHERE shipped_qty > 0
)
SELECT
    'promised_date BETWEEN 2026-07-01 AND 2026-09-30' AS q3_filter,
    planning.otd    AS planning_otd,
    logistics.otd   AS logistics_otd,
    procurement.otd AS procurement_otd_otif,
    governed.otd    AS governed_otd
FROM planning, logistics, procurement, governed;
