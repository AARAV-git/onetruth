-- 15_view_suppliers.sql  Unified supplier dimension via XREF
CREATE OR REPLACE VIEW ONETRUTH.RAW.SUPPLIERS_V AS
SELECT
    e.erp_supplier_id, x.logistics_supplier_id,
    e.supplier_name, e.country, e.payment_terms, e.quality_rating,
    l.contact_email, x.verified_date, x.match_confidence
FROM ONETRUTH.RAW.SUPPLIERS_ERP e
JOIN ONETRUTH.RAW.SUPPLIER_XREF x ON e.erp_supplier_id = x.erp_supplier_id
JOIN ONETRUTH.RAW.SUPPLIERS_LOGISTICS l ON x.logistics_supplier_id = l.logistics_supplier_id;
