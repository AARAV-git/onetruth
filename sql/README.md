# ONETRUTH Supply Chain — SQL Run Order

Reproduces the entire `ONETRUTH` database from scratch.
Run each file in order against a Snowflake account with `ACCOUNTADMIN` (or a role with `CREATE DATABASE`).

| # | File | What it does |
|---|------|-------------|
| 01 | `01_setup.sql` | Create database `ONETRUTH`, schemas `RAW` / `SEMANTIC` / `APP`, and warehouse `ONETRUTH_WH` |
| 02 | `02_dim_plants.sql` | 3 manufacturing plants |
| 03 | `03_dim_parts.sql` | 40 parts across 8 categories, each linked to a primary supplier |
| 04 | `04_dim_customers.sql` | 25 customers across 6 geographic regions |
| 05 | `05_dim_suppliers_erp.sql` | 15 suppliers with ERP IDs (`SUP-nnn`) |
| 06 | `06_dim_suppliers_logistics.sql` | Same 15 suppliers with logistics IDs (`LS-nnnn`) and different name formats |
| 07 | `07_dim_supplier_xref.sql` | Cross-reference mapping ERP ↔ logistics supplier IDs |
| 08 | `08_gen_staging.sql` | Deterministic staging table (HASH-based seed) — 4 500 order lines with controlled on-time and partial-shipment rates |
| 09 | `09_gen_orders_erp.sql` | `ORDERS_ERP` from staging (drops internal columns) |
| 10 | `10_gen_shipments.sql` | `SHIPMENTS_LOGISTICS` from staging with transit-time logic |
| 11 | `11_gen_inventory.sql` | `INVENTORY_SNAPSHOT` — daily snapshots for 3 plants × 40 parts × 183 days |
| 12 | `12_cleanup_staging.sql` | Drop the `_STG` staging table |
| 13 | `13_shift_dates.sql` | Shift all dates forward 823 days (2024 → 2026-04 to 2026-09) and trim inventory to ≤ 2026-09-30 |
| 14 | `14_view_order_lines.sql` | `ORDER_LINES_V` — pre-joined orders + shipments |
| 15 | `15_view_suppliers.sql` | `SUPPLIERS_V` — unified supplier dimension via `SUPPLIER_XREF` |
| 16 | `16_view_persona.sql` | `PERSONA_BEFORE_ONETRUTH` — four OTD perspectives for Q3 2026 |
| 17 | `17_semantic_view.sql` | `SUPPLY_CHAIN_SV` — governed semantic view with 4 metrics, 6 relationships, full comments and synonyms |

## Key data properties (invariant across date shifts)

| Metric | Value |
|--------|-------|
| On-time by ERP delivered date | 91.8% |
| On-time by customer receipt | 79.4% |
| Partial shipments | 9.3% |
| Order lines | 4 500 |
| Distinct orders | 1 431 |

## Files 02–07 can be run in any order (no dependencies between dimension tables).
## Files 08–12 must be run sequentially (staging → facts → cleanup).
## Files 14–17 require the tables from 02–13 to exist.
