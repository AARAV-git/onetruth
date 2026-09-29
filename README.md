<div align="center">

# 🏭 OneTruth

### Governed Supply Chain Analytics on Snowflake

*One semantic view. One definition of "on time." Every team, every role, one truth.*

[![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white)](https://share.streamlit.io/deploy?repository=AARAV-git/onetruth&branch=main&mainModule=app/app.py)
[![Snowflake](https://img.shields.io/badge/Snowflake-29B5E8?style=for-the-badge&logo=snowflake&logoColor=white)](https://www.snowflake.com)
[![Cortex Analyst](https://img.shields.io/badge/Cortex_Analyst-8B5CF6?style=for-the-badge&logo=snowflake&logoColor=white)](#-cortex-analyst-integration)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)](LICENSE)

---

</div>

## 🎯 The Problem

> *"What's our on-time delivery rate?"*

Ask three supply chain teams and you'll get three different answers:

| Team | Their OTD | How they measure it |
|:-----|:---------:|:--------------------|
| **Planning** | 91.6% | ERP dispatch confirmation vs promised date |
| **Logistics** | 82.8% | Gate-in timestamp vs promised date |
| **Procurement** | 62.9% | Order-level: every line must be on-time AND in-full |
| **🎯 Governed** | **78.4%** | **Customer receipt vs promised date — the truth** |

OneTruth eliminates this ambiguity with a **single governed semantic view** backed by Snowflake's Cortex Analyst.

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                     Streamlit App                            │
│  ┌──────────┐  ┌──────────────────┐  ┌───────────────────┐  │
│  │   Ask    │  │ Before OneTruth  │  │   Consistency     │  │
│  │  tab     │  │     tab          │  │      tab          │  │
│  └────┬─────┘  └────────┬─────────┘  └────────┬──────────┘  │
│       │                 │                      │             │
└───────┼─────────────────┼──────────────────────┼─────────────┘
        │                 │                      │
        ▼                 ▼                      ▼
  ┌───────────┐    ┌────────────┐    ┌─────────────────────┐
  │  Cortex   │    │  SQL Query │    │  SEMANTIC_VIEW()    │
  │  Analyst  │    │            │    │  × 3 roles          │
  │  REST API │    │            │    │                     │
  └─────┬─────┘    └──────┬─────┘    └──────────┬──────────┘
        │                 │                      │
        └────────┬────────┴──────────────────────┘
                 ▼
  ┌──────────────────────────────────────────────────────────┐
  │          SUPPLY_CHAIN_SV  (Semantic View)                │
  │   4 metrics · 33 dimensions · 6 relationships            │
  │   AI guardrails · masking policies · RBAC                │
  ├──────────────────────────────────────────────────────────┤
  │  ORDER_LINES_V │ PARTS │ PLANTS │ CUSTOMERS │ INVENTORY │
  │  SUPPLIERS_V   │  (bridged via SUPPLIER_XREF)           │
  └──────────────────────────────────────────────────────────┘
```

---

## ✨ Features

<table>
<tr>
<td width="50%">

### 🤖 Natural Language Analytics
Ask questions in plain English. Cortex Analyst translates them into governed SQL — no ad-hoc queries, no definition drift.

### 🛡️ AI Guardrails
Custom `AI_QUESTION_CATEGORIZATION` instructions reject undefined composite KPIs (OTIF, perfect order rate) and redirect users to the four governed metrics.

</td>
<td width="50%">

### 🔒 Column-Level Masking
Logistics sees delivery data but not costs. Planning and Procurement see everything. One masking policy, enforced transparently through the semantic view.

### 📊 Governance Proof
The Consistency tab proves all three roles get the identical OTD — governance in action, not just policy on paper.

</td>
</tr>
</table>

---

## 📦 Governed Metrics

| Metric | Definition | Synonyms |
|:-------|:-----------|:---------|
| **ON_TIME_DELIVERY_RATE** | Delivered lines where `customer_receipt_ts ≤ promised_date` | OTD, on-time, delivery performance, service level |
| **FILL_RATE** | `SUM(LEAST(shipped, ordered)) / SUM(ordered)` | — |
| **DAYS_OF_INVENTORY** | `SUM(on_hand) / SUM(avg_daily_usage)` per snapshot date | — |
| **LANDED_COST_PER_UNIT** | `(revenue + freight + duty + handling) / shipped_qty` | — |

> 💡 If you ask about a term not in this list (e.g., *"What is our OTIF?"*), Cortex Analyst will **refuse**, list the governed metrics, and ask which one you meant.

---

## 🚀 Quick Start

### 1. Set up Snowflake objects

```bash
# Run the numbered SQL files in order (01 → 20)
# See sql/README.md for the full run order
```

### 2. Launch the app locally

```bash
cd app
pip install -r requirements.txt
streamlit run app.py
```

### 3. Deploy to Streamlit Community Cloud

[![Deploy to Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://share.streamlit.io/deploy?repository=AARAV-git/onetruth&branch=main&mainModule=app/app.py)

> Configure your Snowflake credentials in the Streamlit Cloud **Secrets** panel using `[connections.snowflake]` format.

---

## 📁 Project Structure

```
onetruth/
├── 📄 README.md              ← you are here
├── 📄 .gitignore
│
├── 🎨 app/
│   ├── app.py                ← Streamlit app (3 tabs)
│   ├── requirements.txt
│   ├── .gitignore
│   └── README.md
│
└── 🗃️ sql/
    ├── README.md             ← run-order guide
    ├── 01_setup.sql          ← database, schemas, warehouse
    ├── 02–07_dim_*.sql       ← dimension tables (plants, parts, customers, suppliers)
    ├── 08–12_gen_*.sql       ← synthetic data generation (HASH-seeded, deterministic)
    ├── 13_shift_dates.sql    ← align to 2026 calendar
    ├── 14–15_view_*.sql      ← helper views (order_lines, suppliers)
    ├── 16_view_persona.sql   ← "before governance" — 4 conflicting OTD numbers
    ├── 17_semantic_view.sql  ← the governed semantic view
    └── 18–20_rbac_*.sql      ← roles, masking policies, grants
```

---

## 🔐 RBAC & Masking

| Role | Sees cost data? | OTD result |
|:-----|:---------------:|:----------:|
| `PLANNING_ROLE` | ✅ Yes | 78.4% |
| `PROCUREMENT_ROLE` | ✅ Yes | 78.4% |
| `LOGISTICS_ROLE` | 🚫 NULL | 78.4% |

The masking policy on `unit_price`, `freight_cost`, `duty_cost`, and `handling_cost` propagates through views into the semantic view — `LANDED_COST_PER_UNIT` returns `NULL` for Logistics while OTD remains identical for everyone.

---

## 🧪 Synthetic Data

| Property | Value |
|:---------|:------|
| Order lines | 4,500 across 1,431 orders |
| Date range | 2026-04-03 → 2026-09-30 |
| Plants / Parts / Customers / Suppliers | 3 / 40 / 25 / 15 |
| On-time by ERP (inflated) | 91.8% |
| On-time by customer receipt (truth) | 79.4% |
| Partial shipments | 9.3% |
| Random seed | Deterministic via `HASH()` — fully reproducible |

---

## 🛠️ Tech Stack

| Layer | Technology |
|:------|:-----------|
| **Analytics engine** | Snowflake Semantic Views + Cortex Analyst REST API |
| **Governance** | `AI_SQL_GENERATION` + `AI_QUESTION_CATEGORIZATION` guardrails |
| **Access control** | RBAC roles + column-level masking policies |
| **Frontend** | Streamlit + Plotly |
| **Data generation** | Pure SQL with `HASH()`-seeded deterministic random |

---

<div align="center">

### Built with ❄️ Snowflake + 🤖 Cortex Analyst

*Generated with [Snowflake CoCo](https://docs.snowflake.com/en/user-guide/cortex-code/cortex-code)*

</div>
