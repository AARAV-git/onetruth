-- 11_gen_inventory.sql  Daily inventory snapshots (3 plants x 40 parts x 183 days)
CREATE OR REPLACE TABLE ONETRUTH.RAW.INVENTORY_SNAPSHOT AS
WITH dates AS (
    SELECT DATEADD('day', ROW_NUMBER() OVER (ORDER BY SEQ4()) - 1, '2024-01-01'::DATE) AS snapshot_date
    FROM TABLE(GENERATOR(ROWCOUNT => 183))
),
combos AS (
    SELECT p.plant_id, pt.part_id
    FROM ONETRUTH.RAW.PLANTS p
    CROSS JOIN ONETRUTH.RAW.PARTS pt
)
SELECT
    c.plant_id,
    c.part_id,
    d.snapshot_date,
    GREATEST(
        ROUND(
            (MOD(ABS(HASH(c.plant_id, c.part_id, 1)), 451) + 50)
            * (0.3 + 1.2 * ABS(MOD(HASH(c.plant_id, c.part_id, d.snapshot_date, 2), 1000)) / 1000.0)
        )::INT,
        0
    ) AS on_hand_qty,
    ROUND(
        (MOD(ABS(HASH(c.plant_id, c.part_id, 3)), 76) + 5)
        * (0.85 + 0.30 * ABS(MOD(HASH(c.plant_id, c.part_id, d.snapshot_date, 4), 1000)) / 1000.0),
        1
    ) AS avg_daily_usage
FROM combos c
CROSS JOIN dates d;
