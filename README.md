<div align="center">

# OneTruth

### One Metric. One Truth. Zero Ambiguity.

**Governed Supply Chain Analytics powered by Snowflake Semantic Views + Cortex Analyst**

[![Live Demo](https://img.shields.io/badge/Live_Demo-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white)](https://aarav-git-onetruth.streamlit.app)
[![Snowflake](https://img.shields.io/badge/Snowflake-29B5E8?style=for-the-badge&logo=snowflake&logoColor=white)](https://www.snowflake.com)
[![Cortex Analyst](https://img.shields.io/badge/Cortex_Analyst-8B5CF6?style=for-the-badge&logo=snowflake&logoColor=white)](#cortex-analyst--ai-guardrails)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)](LICENSE)

**Team NeuroForge** — Sunny Pathak (Lead) · Saurav Sharma · Himanshi Sharma

---

</div>

## TL;DR for Evaluators

> Three supply chain teams report three different "on-time delivery" numbers (91.6%, 82.8%, 62.9%). **OneTruth** eliminates this by enforcing a **single governed semantic view** — every role, every query, one number: **78.4%** (the truth, based on actual customer receipt).

**What makes this different:**
- Natural language queries via Cortex Analyst — no SQL knowledge needed
- AI guardrails that **refuse** ungoverned metrics and redirect to the 4 approved KPIs
- Column-level masking that's **visually provable** in the app
- Persistent chat sessions stored in Snowflake — ChatGPT-style UX
- Downloadable CSV + PDF reports on every query result

---

## The Problem

> *"What's our on-time delivery rate?"*

| Team | Their OTD | How they measure it |
|:-----|:---------:|:--------------------|
| **Planning** | 91.6% | ERP dispatch confirmation vs promised date |
| **Logistics** | 82.8% | Gate-in timestamp vs promised date |
| **Procurement** | 62.9% | Order-level: every line on-time AND in-full |
| **OneTruth** | **78.4%** | **Customer receipt vs promised date** |

The first three are all "correct" by their own definition — but they're answering different questions. OneTruth enforces a single governed definition through a Snowflake Semantic View, and Cortex Analyst ensures every user — regardless of role — gets the same answer.

---

## Demo Walkthrough (6 Tabs)

### 1. Dashboard
Executive KPI overview — 4 governed metric cards, monthly OTD + Fill Rate trend, bottom-10 customers by OTD. **Download CSV or PDF** with one click.

### 2. Ask (ChatGPT-style)
- Sign in with your name
- Pick a suggested prompt or type your own question
- Multi-turn conversation — follow-ups like *"now break that down by carrier"* work
- Every result auto-renders as a chart (bar/line/metric) with **Download CSV + PDF** buttons
- Sessions persist in Snowflake — resume, share via URL, or delete

### 3. Before OneTruth
Bar chart showing the 4 conflicting OTD numbers side-by-side. This is the "before" picture — the chaos of ungoverned metrics.

### 4. Consistency
The **same** `ON_TIME_DELIVERY_RATE` queried under Planning, Procurement, and Logistics roles — all return **78.4%**. Governance in action, not just policy on paper.

### 5. Masking
`LANDED_COST_PER_UNIT` queried under each role. Planning and Procurement see **$165.42**. Logistics sees **NULL**. A raw column table below shows exactly which cost columns are masked. Visual proof of column-level security.

### 6. Analytics
Platform-wide and per-user chat usage metrics — sessions, messages, leaderboard, activity over time. Shows adoption and engagement.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      Streamlit App (6 tabs)                      │
│  Dashboard │ Ask │ Before OneTruth │ Consistency │ Masking │ Analytics │
└──────┬──────────┬──────────────────────┬────────────────────────┘
       │          │                      │
       ▼          ▼                      ▼
 ┌───────────┐  ┌────────────┐  ┌──────────────────┐
 │  Cortex   │  │  Direct    │  │  SEMANTIC_VIEW() │
 │  Analyst  │  │  SQL       │  │  × 3 RBAC roles  │
 │  REST API │  │  Queries   │  │                  │
 └─────┬─────┘  └──────┬─────┘  └────────┬─────────┘
       └────────┬───────┴─────────────────┘
                ▼
 ┌─────────────────────────────────────────────────────────────┐
 │            SUPPLY_CHAIN_SV  (Semantic View)                 │
 │   4 governed metrics · 33 dimensions · 6 relationships      │
 │   AI_SQL_GENERATION + AI_QUESTION_CATEGORIZATION guardrails │
 ├─────────────────────────────────────────────────────────────┤
 │  ORDER_LINES_V │ PARTS │ PLANTS │ CUSTOMERS │ INVENTORY    │
 │  SUPPLIERS_V   │  (bridged via SUPPLIER_XREF)              │
 ├─────────────────────────────────────────────────────────────┤
 │  MASK_COST_FROM_LOGISTICS  (column-level masking policy)    │
 │  PLANNING_ROLE │ PROCUREMENT_ROLE │ LOGISTICS_ROLE  (RBAC)  │
 ├─────────────────────────────────────────────────────────────┤
 │  CHAT_SESSIONS  (persistent chat storage in Snowflake)      │
 └─────────────────────────────────────────────────────────────┘
```

---

## Governed Metrics

| Metric | Definition | Synonyms |
|:-------|:-----------|:---------|
| **ON_TIME_DELIVERY_RATE** | Delivered lines where `customer_receipt_ts <= promised_date` | OTD, on-time, delivery performance, service level |
| **FILL_RATE** | `SUM(LEAST(shipped, ordered)) / SUM(ordered)` | — |
| **DAYS_OF_INVENTORY** | `SUM(on_hand) / SUM(avg_daily_usage)` per snapshot date | — |
| **LANDED_COST_PER_UNIT** | `(revenue + freight + duty + handling) / shipped_qty` | — |

> If you ask about a term not in this list (e.g., *"What is our OTIF?"*), Cortex Analyst will **refuse**, list the governed metrics, and ask which one you meant. This is by design — AI guardrails prevent definition drift.

---

## RBAC & Column-Level Masking

| Role | Sees cost data? | OTD result | Landed Cost |
|:-----|:---------------:|:----------:|:-----------:|
| `PLANNING_ROLE` | Yes | 78.4% | $165.42 |
| `PROCUREMENT_ROLE` | Yes | 78.4% | $165.42 |
| `LOGISTICS_ROLE` | **NULL** | 78.4% | **NULL** |

The masking policy `MASK_COST_FROM_LOGISTICS` returns NULL for `unit_price`, `freight_cost`, `duty_cost`, and `handling_cost` when `CURRENT_ROLE() = 'LOGISTICS_ROLE'`. This propagates through views into the semantic view — `LANDED_COST_PER_UNIT` returns NULL for Logistics while OTD remains identical for everyone.

**The Masking tab proves this visually.**

---

## Key Technical Highlights

| Feature | Implementation |
|:--------|:---------------|
| **Multi-turn chat** | Full conversation history sent to Cortex Analyst REST API — follow-ups work |
| **Auto-charting** | Detects result shape: time-series → line chart, categorical → bar chart, scalar → metric card |
| **Persistent sessions** | `CHAT_SESSIONS` table in Snowflake — save, resume, share via URL, delete |
| **Shareable chats** | `?session=<UUID>` URL opens read-only view for anyone |
| **Download reports** | CSV + styled HTML (print-to-PDF) on every query result and dashboard |
| **Session reconnect** | `client_session_keep_alive` + TTL + auto-reconnect on `ReauthenticationRequest` |
| **AI guardrails** | `AI_SQL_GENERATION` + `AI_QUESTION_CATEGORIZATION` reject ungoverned KPIs |
| **Deterministic data** | `HASH()`-seeded synthetic data — fully reproducible across environments |

---

## Quick Start

### 1. Set up Snowflake objects
```bash
# Run the numbered SQL files in order (01 → 20)
# See sql/README.md for the full run order
```

### 2. Launch locally
```bash
cd app
pip install -r requirements.txt
streamlit run app.py
```

### 3. Deploy to Streamlit Cloud

[![Deploy to Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://share.streamlit.io/deploy?repository=AARAV-git/onetruth&branch=main&mainModule=app/app.py)

> Configure Snowflake credentials in **Settings → Secrets** using `[connections.snowflake]` format.

---

## Project Structure

```
onetruth/
├── README.md
├── app/
│   ├── app.py                ← Streamlit app (6 tabs, 1600+ lines)
│   └── requirements.txt
└── sql/
    ├── 01_setup.sql          ← database, schemas, warehouse
    ├── 02–07_dim_*.sql       ← dimension tables
    ├── 08–12_gen_*.sql       ← deterministic synthetic data
    ├── 13_shift_dates.sql    ← align to 2026 calendar
    ├── 14–15_view_*.sql      ← helper views
    ├── 16_view_persona.sql   ← 4 conflicting OTD definitions
    ├── 17_semantic_view.sql  ← THE governed semantic view
    ├── 18_rbac_roles.sql     ← 3 persona roles
    ├── 19_masking_policy.sql ← column-level cost masking
    └── 20_grants.sql         ← role grants
```

---

## Synthetic Data

| Property | Value |
|:---------|:------|
| Order lines | 4,500 across 1,431 orders |
| Date range | 2026-04-03 → 2026-09-30 |
| Plants / Parts / Customers / Suppliers | 3 / 40 / 25 / 15 |
| On-time by ERP (inflated) | 91.8% |
| On-time by customer receipt (truth) | 79.4% |
| Partial shipments | 9.3% |
| Seed method | `HASH()` — deterministic and fully reproducible |

---

## Tech Stack

| Layer | Technology |
|:------|:-----------|
| **Analytics** | Snowflake Semantic Views + Cortex Analyst REST API |
| **Governance** | AI guardrails (`AI_SQL_GENERATION` + `AI_QUESTION_CATEGORIZATION`) |
| **Security** | RBAC (3 roles) + column-level masking policies |
| **Persistence** | Snowflake table (`CHAT_SESSIONS`) for chat history |
| **Frontend** | Streamlit + Plotly + Custom CSS |
| **Data** | Pure SQL with `HASH()`-seeded deterministic random generation |

---

<div align="center">

**Built by Team NeuroForge**

Sunny Pathak (Lead) · Saurav Sharma · Himanshi Sharma

Powered by Snowflake + Cortex Analyst

</div>
