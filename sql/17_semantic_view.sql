-- 17_semantic_view.sql  Governed semantic view over the supply chain
CREATE OR REPLACE SEMANTIC VIEW ONETRUTH.SEMANTIC.SUPPLY_CHAIN_SV

  TABLES (
    order_lines AS ONETRUTH.RAW.ORDER_LINES_V
      PRIMARY KEY (order_id, line_id)
      COMMENT = 'Order lines joined with shipment logistics data from ERP and logistics systems',
    parts AS ONETRUTH.RAW.PARTS
      PRIMARY KEY (part_id)
      COMMENT = 'Part master data with categories, weights, lead times, and primary supplier',
    plants AS ONETRUTH.RAW.PLANTS
      PRIMARY KEY (plant_id)
      COMMENT = 'Manufacturing plant locations',
    customers AS ONETRUTH.RAW.CUSTOMERS
      PRIMARY KEY (customer_id)
      COMMENT = 'Customer master data with geographic regions',
    suppliers AS ONETRUTH.RAW.SUPPLIERS_V
      PRIMARY KEY (erp_supplier_id)
      COMMENT = 'Unified supplier dimension bridging ERP (SUP-nnn) and logistics (LS-nnnn) ID schemes via SUPPLIER_XREF',
    inventory AS ONETRUTH.RAW.INVENTORY_SNAPSHOT
      PRIMARY KEY (plant_id, part_id, snapshot_date)
      COMMENT = 'Daily inventory snapshots recording on-hand quantity and average daily usage per plant and part'
  )

  RELATIONSHIPS (
    order_to_customer AS
      order_lines (customer_id) REFERENCES customers,
    order_to_part AS
      order_lines (part_id) REFERENCES parts,
    order_to_plant AS
      order_lines (plant_id) REFERENCES plants,
    part_to_supplier AS
      parts (primary_supplier_id) REFERENCES suppliers (erp_supplier_id),
    inventory_to_plant AS
      inventory (plant_id) REFERENCES plants,
    inventory_to_part AS
      inventory (part_id) REFERENCES parts
  )

  FACTS (
    order_lines.shipped_qty AS shipped_qty
      COMMENT = 'Quantity actually shipped for this line',
    order_lines.ordered_qty AS ordered_qty
      COMMENT = 'Quantity originally ordered for this line',
    order_lines.unit_price AS unit_price
      COMMENT = 'Unit price charged for this part on this line',
    order_lines.freight_cost AS freight_cost
      COMMENT = 'Freight shipping cost for this line',
    order_lines.duty_cost AS duty_cost
      COMMENT = 'Import duty cost for this line',
    order_lines.handling_cost AS handling_cost
      COMMENT = 'Handling and warehousing cost for this line',
    order_lines.line_revenue AS unit_price * shipped_qty
      COMMENT = 'Revenue for this line: unit_price multiplied by shipped_qty',
    order_lines.total_logistics_cost AS freight_cost + duty_cost + handling_cost
      COMMENT = 'Total logistics cost: sum of freight, duty, and handling',
    order_lines.fill_shipped AS LEAST(shipped_qty, ordered_qty)
      COMMENT = 'Shipped quantity capped at ordered quantity, used for fill rate',
    PRIVATE order_lines.is_on_time_receipt AS
      CASE WHEN customer_receipt_ts::DATE <= promised_date AND shipped_qty > 0 THEN 1 ELSE 0 END
      COMMENT = '1 if customer received shipment on or before promised date and line was delivered',
    PRIVATE order_lines.is_delivered AS
      CASE WHEN shipped_qty > 0 THEN 1 ELSE 0 END
      COMMENT = '1 if any quantity was shipped for this line',
    inventory.on_hand_qty AS on_hand_qty
      COMMENT = 'Units physically on hand at the time of the snapshot',
    inventory.avg_daily_usage AS avg_daily_usage
      COMMENT = 'Average units consumed per day at the time of the snapshot'
  )

  DIMENSIONS (
    order_lines.order_id AS order_id
      COMMENT = 'Unique order identifier from ERP',
    order_lines.line_id AS line_id
      COMMENT = 'Line number within an order',
    order_lines.order_date AS order_date
      COMMENT = 'Date the order was placed in the ERP system',
    order_lines.order_month AS TO_CHAR(order_date, 'YYYY-MM')
      COMMENT = 'Year and month the order was placed (YYYY-MM)',
    order_lines.promised_date AS promised_date
      COMMENT = 'Date promised to the customer for delivery',
    order_lines.promised_month AS TO_CHAR(promised_date, 'YYYY-MM')
      WITH SYNONYMS = ('month', 'period')
      COMMENT = 'Year and month of the promised delivery date (YYYY-MM). Standard reporting period for delivery metrics.',
    order_lines.promised_quarter AS YEAR(promised_date)::STRING || '-Q' || QUARTER(promised_date)::STRING
      WITH SYNONYMS = ('quarter')
      COMMENT = 'Year and quarter of the promised delivery date (e.g. 2026-Q3). Standard reporting period for delivery metrics.',
    order_lines.erp_delivered_date AS erp_delivered_date
      COMMENT = 'Date the ERP recorded as delivered, set at dispatch confirmation',
    order_lines.carrier AS carrier
      WITH SYNONYMS = ('shipping carrier', 'freight carrier')
      COMMENT = 'Name of the freight carrier used for shipment',
    order_lines.shipment_id AS shipment_id
      COMMENT = 'Unique shipment identifier from the logistics system',
    order_lines.dispatch_ts AS dispatch_ts
      COMMENT = 'Timestamp when the shipment was dispatched from the plant',
    order_lines.customer_receipt_ts AS customer_receipt_ts
      COMMENT = 'Timestamp when the customer actually received the shipment',

    parts.part_id AS part_id
      COMMENT = 'Unique part identifier',
    parts.part_name AS part_name
      COMMENT = 'Descriptive name of the part',
    parts.category AS category
      WITH SYNONYMS = ('part category', 'product category')
      COMMENT = 'Part category such as Engine, Transmission, Brake, or Exhaust',
    parts.unit_weight_kg AS unit_weight_kg
      COMMENT = 'Weight of one unit in kilograms',
    parts.lead_time_days AS lead_time_days
      COMMENT = 'Standard supplier lead time in calendar days',

    plants.plant_id AS plant_id
      COMMENT = 'Unique manufacturing plant identifier',
    plants.plant_name AS plant_name
      COMMENT = 'Name of the manufacturing plant',
    plants.plant_city AS city
      COMMENT = 'City where the plant is located',
    plants.plant_country AS country
      COMMENT = 'Country where the plant is located',

    customers.customer_id AS customer_id
      COMMENT = 'Unique customer identifier',
    customers.customer_name AS customer_name
      WITH SYNONYMS = ('customer', 'account name')
      COMMENT = 'Customer company name',
    customers.customer_city AS city
      COMMENT = 'City where the customer is headquartered',
    customers.customer_country AS country
      COMMENT = 'Country of the customer',
    customers.region AS region
      WITH SYNONYMS = ('geographic region', 'market')
      COMMENT = 'Geographic region such as North America, Europe, or Asia-Pacific',

    suppliers.erp_supplier_id AS erp_supplier_id
      COMMENT = 'Supplier identifier in the ERP system (SUP-nnn format)',
    suppliers.logistics_supplier_id AS logistics_supplier_id
      COMMENT = 'Supplier identifier in the logistics system (LS-nnnn format)',
    suppliers.supplier_name AS supplier_name
      COMMENT = 'Supplier company name from the ERP system',
    suppliers.supplier_country AS country
      COMMENT = 'Country where the supplier is located',
    suppliers.payment_terms AS payment_terms
      COMMENT = 'Agreed payment terms such as Net 30 or Net 60',
    suppliers.quality_rating AS quality_rating
      COMMENT = 'Supplier quality rating: A+, A, or B+',

    inventory.snapshot_date AS snapshot_date
      COMMENT = 'Calendar date of the inventory snapshot'
  )

  METRICS (
    order_lines.ON_TIME_DELIVERY_RATE
      AS SUM(order_lines.is_on_time_receipt) / NULLIF(SUM(order_lines.is_delivered), 0)
      WITH SYNONYMS = ('OTD', 'on-time', 'delivery performance', 'service level')
      COMMENT = 'Fraction of delivered lines where customer_receipt_ts is on or before promised_date. Reporting periods follow promised_date (use promised_month or promised_quarter to slice). The governed measure of on-time delivery.',
    order_lines.FILL_RATE
      AS SUM(order_lines.fill_shipped) / NULLIF(SUM(order_lines.ordered_qty), 0)
      COMMENT = 'Ratio of quantity shipped (capped at ordered) to total quantity ordered. Measures order completeness.',
    inventory.DAYS_OF_INVENTORY
      NON ADDITIVE BY (inventory.snapshot_date)
      AS SUM(inventory.on_hand_qty) / NULLIF(SUM(inventory.avg_daily_usage), 0)
      COMMENT = 'Days of stock on hand: total on-hand quantity divided by total average daily usage for a single snapshot date.',
    order_lines.LANDED_COST_PER_UNIT
      AS (SUM(order_lines.line_revenue) + SUM(order_lines.total_logistics_cost)) / NULLIF(SUM(order_lines.shipped_qty), 0)
      COMMENT = 'Fully loaded cost per shipped unit including purchase price, freight, duty, and handling.'
  )

  COMMENT = 'Single-truth supply chain semantic view spanning orders, shipments, inventory, and master data. Use ON_TIME_DELIVERY_RATE as the governed OTD metric based on actual customer receipt, not ERP dispatch confirmation. Reporting periods follow promised_date.'

  AI_SQL_GENERATION 'Answer only with the four governed metrics defined in this semantic view: ON_TIME_DELIVERY_RATE, FILL_RATE, DAYS_OF_INVENTORY, and LANDED_COST_PER_UNIT. Do not combine metrics to infer composite KPIs that are not explicitly defined. Always state the exact time period the answer covers in the response. When slicing delivery metrics by time, use promised_date (and its derived dimensions promised_month, promised_quarter) as the reporting period, not order_date.'

  AI_QUESTION_CATEGORIZATION 'If the user asks about a business term that is not a defined metric, dimension, or synonym in this semantic view — for example OTIF, perfect order rate, cash-to-cash cycle, or any composite KPI — do not attempt to infer an answer by combining existing metrics. Instead, respond that the term is not defined in the governed ontology, list the four available governed metrics (ON_TIME_DELIVERY_RATE, FILL_RATE, DAYS_OF_INVENTORY, LANDED_COST_PER_UNIT) and their synonyms, and ask the user which metric they would like to see.';
