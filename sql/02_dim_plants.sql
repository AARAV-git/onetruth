-- 02_dim_plants.sql  3 manufacturing plants
CREATE OR REPLACE TABLE ONETRUTH.RAW.PLANTS AS
SELECT column1 AS plant_id, column2 AS plant_name, column3 AS city, column4 AS country
FROM VALUES
('P001','Detroit Assembly','Detroit','USA'),
('P002','Monterrey Works','Monterrey','Mexico'),
('P003','Stuttgart Plant','Stuttgart','Germany');
