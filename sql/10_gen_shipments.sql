-- 10_gen_shipments.sql  Create SHIPMENTS_LOGISTICS from staging
-- Transit days are tuned so ~80% of lines arrive on or before promised_date,
-- while ~92% have erp_delivered_date on or before promised_date.
CREATE OR REPLACE TABLE ONETRUTH.RAW.SHIPMENTS_LOGISTICS AS
WITH base AS (
    SELECT
        rn, order_id, line_id, fate, erp_delivered_date, promised_date,
        DATEDIFF('day', erp_delivered_date, promised_date) AS days_to_promised,
        DATEADD('hour', MOD(ABS(HASH(rn, 800)), 13) + 6, erp_delivered_date) AS dispatch_ts,
        CASE
            WHEN fate < 0.80
                THEN MOD(ABS(HASH(rn, 900)), GREATEST(DATEDIFF('day', erp_delivered_date, promised_date), 1)) + 1
            WHEN fate < 0.92
                THEN DATEDIFF('day', erp_delivered_date, promised_date) + MOD(ABS(HASH(rn, 900)), 5) + 1
            ELSE MOD(ABS(HASH(rn, 900)), 6) + 2
        END AS transit_days,
        ARRAY_CONSTRUCT('FedEx','DHL','UPS','Maersk','DB Schenker')[MOD(ABS(HASH(rn, 750)), 5)]::STRING AS carrier
    FROM ONETRUTH.RAW._STG
),
with_receipt AS (
    SELECT *,
        DATEADD('hour', MOD(ABS(HASH(rn, 850)), 10) + 8,
                DATEADD('day', transit_days, erp_delivered_date)) AS customer_receipt_ts
    FROM base
)
SELECT
    'SH-' || LPAD(rn::STRING, 7, '0') AS shipment_id,
    order_id, line_id, carrier, dispatch_ts,
    DATEADD('second',
        ROUND(DATEDIFF('second', dispatch_ts, customer_receipt_ts) *
              (0.4 + 0.4 * ABS(MOD(HASH(rn, 860), 1000)) / 1000.0))::INT,
        dispatch_ts) AS gate_in_ts,
    customer_receipt_ts,
    ROUND(50.0 + 1950.0 * ABS(MOD(HASH(rn, 950), 1000000)) / 1000000.0, 2) AS freight_cost,
    ROUND(10.0 + 490.0 * ABS(MOD(HASH(rn, 960), 1000000)) / 1000000.0, 2) AS duty_cost,
    ROUND(5.0 + 195.0 * ABS(MOD(HASH(rn, 970), 1000000)) / 1000000.0, 2) AS handling_cost
FROM with_receipt;
