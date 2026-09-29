-- 07_dim_supplier_xref.sql  Maps ERP supplier IDs to logistics IDs
CREATE OR REPLACE TABLE ONETRUTH.RAW.SUPPLIER_XREF AS
SELECT column1 AS erp_supplier_id, column2 AS logistics_supplier_id, column3::DATE AS verified_date, column4::FLOAT AS match_confidence
FROM VALUES
('SUP-001','LS-1001','2023-11-15',0.98),
('SUP-002','LS-1002','2023-11-15',0.95),
('SUP-003','LS-1003','2023-12-01',0.97),
('SUP-004','LS-1004','2023-12-01',0.99),
('SUP-005','LS-1005','2023-11-20',0.92),
('SUP-006','LS-1006','2023-12-10',0.96),
('SUP-007','LS-1007','2023-12-10',0.98),
('SUP-008','LS-1008','2024-01-05',0.94),
('SUP-009','LS-1009','2024-01-05',0.97),
('SUP-010','LS-1010','2023-11-25',0.99),
('SUP-011','LS-1011','2023-12-15',0.93),
('SUP-012','LS-1012','2024-01-10',0.96),
('SUP-013','LS-1013','2024-01-10',0.98),
('SUP-014','LS-1014','2023-12-20',0.97),
('SUP-015','LS-1015','2023-12-20',0.95);
