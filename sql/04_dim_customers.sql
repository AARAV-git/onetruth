-- 04_dim_customers.sql  25 customers across 6 regions
CREATE OR REPLACE TABLE ONETRUTH.RAW.CUSTOMERS AS
SELECT column1 AS customer_id, column2 AS customer_name, column3 AS city, column4 AS country, column5 AS region
FROM VALUES
('C-001','Apex Manufacturing','Chicago','USA','North America'),
('C-002','Boreal Industries','Toronto','Canada','North America'),
('C-003','CrestLine Corp','Dallas','USA','North America'),
('C-004','Dynamo GmbH','Munich','Germany','Europe'),
('C-005','EchoTech Ltd','London','UK','Europe'),
('C-006','Falcon Motors','São Paulo','Brazil','South America'),
('C-007','Granite Auto','Detroit','USA','North America'),
('C-008','Harbor Engineering','Shanghai','China','Asia-Pacific'),
('C-009','IronWorks Inc','Pittsburgh','USA','North America'),
('C-010','Jetstream Logistics','Dubai','UAE','Middle East'),
('C-011','Kestrel Systems','Melbourne','Australia','Asia-Pacific'),
('C-012','Lumen Automotive','Seoul','South Korea','Asia-Pacific'),
('C-013','Metro Parts','Paris','France','Europe'),
('C-014','Nordic Assembly','Stockholm','Sweden','Europe'),
('C-015','Onyx Industries','Johannesburg','South Africa','Africa'),
('C-016','Pioneer Corp','Tokyo','Japan','Asia-Pacific'),
('C-017','QuartzTech','San Jose','USA','North America'),
('C-018','Ridge Manufacturing','Atlanta','USA','North America'),
('C-019','Summit Motors','Mexico City','Mexico','North America'),
('C-020','Titan Fabrication','Mumbai','India','Asia-Pacific'),
('C-021','Unity Auto','Warsaw','Poland','Europe'),
('C-022','Vertex Engineering','Milan','Italy','Europe'),
('C-023','Westland Group','Vancouver','Canada','North America'),
('C-024','Xenon Systems','Singapore','Singapore','Asia-Pacific'),
('C-025','Zenith Corp','Phoenix','USA','North America');
