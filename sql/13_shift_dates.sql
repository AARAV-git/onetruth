-- 13_shift_dates.sql  Shift all dates forward 823 days (731 + 92) and trim inventory
-- This moves data generated with a 2024-01-01 base to 2026-04-03 .. 2026-09-30.

UPDATE ONETRUTH.RAW.ORDERS_ERP
SET order_date        = DATEADD('day', 823, order_date),
    promised_date     = DATEADD('day', 823, promised_date),
    erp_delivered_date = DATEADD('day', 823, erp_delivered_date);

UPDATE ONETRUTH.RAW.SHIPMENTS_LOGISTICS
SET dispatch_ts        = DATEADD('day', 823, dispatch_ts),
    gate_in_ts         = DATEADD('day', 823, gate_in_ts),
    customer_receipt_ts = DATEADD('day', 823, customer_receipt_ts);

UPDATE ONETRUTH.RAW.INVENTORY_SNAPSHOT
SET snapshot_date = DATEADD('day', 823, snapshot_date);

-- Trim inventory to end at 2026-09-30
DELETE FROM ONETRUTH.RAW.INVENTORY_SNAPSHOT
WHERE snapshot_date > '2026-09-30';
