-- 06_dim_suppliers_logistics.sql  15 suppliers with logistics IDs (LS-nnnn)
CREATE OR REPLACE TABLE ONETRUTH.RAW.SUPPLIERS_LOGISTICS AS
SELECT column1 AS logistics_supplier_id, column2 AS supplier_name, column3 AS country, column4 AS contact_email, column5::BOOLEAN AS active
FROM VALUES
('LS-1001','ACME STEEL','USA','shipping@acmesteel.com',TRUE),
('LS-1002','BOSCH COMP','Germany','logistics@bosch-comp.de',TRUE),
('LS-1003','DENSO MFG','Japan','ops@densomfg.jp',TRUE),
('LS-1004','CONTINENTAL','Germany','supply@continental.de',TRUE),
('LS-1005','ZF GROUP','Germany','logistics@zf-group.de',TRUE),
('LS-1006','MAGNA INTL','Canada','shipping@magnaintl.ca',TRUE),
('LS-1007','AISIN','Japan','ops@aisin.jp',TRUE),
('LS-1008','VALEO','France','supply@valeo.fr',TRUE),
('LS-1009','LEAR CORP','USA','logistics@learcorp.com',TRUE),
('LS-1010','BORGWARNER','USA','shipping@borgwarner.com',TRUE),
('LS-1011','SCHAEFFLER','Germany','ops@schaeffler.de',TRUE),
('LS-1012','SKF AB','Sweden','logistics@skf.se',TRUE),
('LS-1013','TIMKEN CO','USA','supply@timken.com',TRUE),
('LS-1014','DANA INC','USA','shipping@dana.com',TRUE),
('LS-1015','MARTINREA','Canada','ops@martinrea.ca',TRUE);
