-- 14_view_order_lines.sql  Pre-joined order lines + shipments
CREATE OR REPLACE VIEW ONETRUTH.RAW.ORDER_LINES_V AS
SELECT
    o.order_id, o.line_id, o.customer_id, o.part_id, o.plant_id,
    o.order_date, o.promised_date, o.ordered_qty, o.shipped_qty, o.unit_price, o.erp_delivered_date,
    s.shipment_id, s.carrier, s.dispatch_ts, s.gate_in_ts, s.customer_receipt_ts,
    s.freight_cost, s.duty_cost, s.handling_cost
FROM ONETRUTH.RAW.ORDERS_ERP o
JOIN ONETRUTH.RAW.SHIPMENTS_LOGISTICS s
    ON o.order_id = s.order_id AND o.line_id = s.line_id;
