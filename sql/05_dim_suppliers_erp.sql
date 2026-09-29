-- 05_dim_suppliers_erp.sql  15 suppliers with ERP IDs (SUP-nnn)
CREATE OR REPLACE TABLE ONETRUTH.RAW.SUPPLIERS_ERP AS
SELECT column1 AS erp_supplier_id, column2 AS supplier_name, column3 AS country, column4 AS payment_terms, column5 AS quality_rating
FROM VALUES
('SUP-001','Acme Steel Co.','USA','Net 30','A'),
('SUP-002','Bosch Components Ltd.','Germany','Net 45','A+'),
('SUP-003','Denso Manufacturing Inc.','Japan','Net 30','A'),
('SUP-004','Continental AG','Germany','Net 60','A'),
('SUP-005','ZF Friedrichshafen','Germany','Net 45','B+'),
('SUP-006','Magna International','Canada','Net 30','A'),
('SUP-007','Aisin Seiki Co.','Japan','Net 30','A+'),
('SUP-008','Valeo SA','France','Net 45','B+'),
('SUP-009','Lear Corporation','USA','Net 30','A'),
('SUP-010','BorgWarner Inc.','USA','Net 45','A'),
('SUP-011','Schaeffler Group','Germany','Net 60','A'),
('SUP-012','SKF Bearings AB','Sweden','Net 30','A+'),
('SUP-013','Timken Company','USA','Net 30','B+'),
('SUP-014','Dana Incorporated','USA','Net 45','A'),
('SUP-015','Martinrea Intl.','Canada','Net 30','B+');
