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
- Entire app built using **Snowflake CoCo CLI** — from SQL generation to Streamlit deployment

---

## 1. Problem Brief

### What real business problem does this solve?

In supply chain organizations, **metric inconsistency** is the #1 cause of misaligned decisions. When the VP of Planning says OTD is 91.6% and the VP of Logistics says it's 82.8%, leadership loses trust in the data — and makes decisions based on whichever number supports their narrative.

This isn't a data quality problem. It's a **governance problem**: each team defines "on-time delivery" differently, queries different source columns, and applies different filters. All three numbers are technically correct — they're just answering different questions.

### Who is the target user/persona?

| Persona | Role | What they need |
|:--------|:-----|:---------------|
| **Supply Chain VP** | Executive | Single trusted KPI dashboard, downloadable reports |
| **Planning Analyst** | `PLANNING_ROLE` | Natural language access to governed metrics, full cost visibility |
| **Procurement Manager** | `PROCUREMENT_ROLE` | Supplier performance metrics, cost analysis |
| **Logistics Coordinator** | `LOGISTICS_ROLE` | Delivery performance without cost data exposure |
| **Data Governance Lead** | `ACCOUNTADMIN` | Proof that RBAC, masking, and AI guardrails work |

### What is the current pain point?

| Before OneTruth | After OneTruth |
|:----------------|:---------------|
| 3 teams, 3 different OTD numbers | 1 governed metric, identical across all roles |
| Each team writes ad-hoc SQL with different definitions | Cortex Analyst generates SQL from the semantic view — no drift |
| No way to prove masking works | Masking tab shows NULL vs real values side-by-side |
| Metrics defined in spreadsheets or tribal knowledge | 4 metrics codified in a semantic view with AI guardrails |
| Executives don't trust the numbers | Consistency tab proves all roles return 78.4% |

### Industry/domain context

**Manufacturing & Discrete Supply Chain** — the domain where OTD, fill rate, inventory days, and landed cost are the four KPIs that drive every operational review. OneTruth is built for this domain but the pattern (semantic view + AI guardrails + RBAC + masking) applies to any industry where metric governance matters: healthcare (readmission rates), finance (risk metrics), retail (conversion rates).

---

## 2. Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        USER LAYER                                        │
│                                                                          │
│   Planning Analyst    Procurement Mgr    Logistics Coord    VP / Exec    │
│   (PLANNING_ROLE)     (PROCUREMENT_ROLE) (LOGISTICS_ROLE)   (ACCOUNTADMIN)│
└──────────┬──────────────────┬──────────────────┬──────────────┬──────────┘
           │                  │                  │              │
           ▼                  ▼                  ▼              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     STREAMLIT APP (6 tabs)                                │
│                                                                          │
│  ┌───────────┐ ┌─────────┐ ┌────────────┐ ┌───────────┐ ┌───────────┐  │
│  │ Dashboard │ │  Ask    │ │ Before     │ │Consistency│ │  Masking  │  │
│  │ (KPIs +   │ │(ChatGPT │ │ OneTruth   │ │(3 roles,  │ │(NULL vs   │  │
│  │  trends)  │ │ style)  │ │ (chaos)    │ │ 1 number) │ │  $value)  │  │
│  └─────┬─────┘ └────┬────┘ └─────┬──────┘ └─────┬─────┘ └─────┬─────┘  │
│        │            │            │              │              │         │
│  ┌─────┴────────────┴────────────┴──────────────┴──────────────┘         │
│  │  Auto-Chart Engine │ Download CSV+PDF │ Session Persistence           │
│  └──────────┬─────────┘                                                  │
└─────────────┼────────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     SNOWFLAKE PLATFORM                                    │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │              Cortex Analyst REST API                              │    │
│  │  Receives natural language → generates governed SQL               │    │
│  │  Multi-turn conversation history for follow-up questions          │    │
│  └──────────────────────┬───────────────────────────────────────────┘    │
│                         ▼                                                │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │           SUPPLY_CHAIN_SV (Semantic View)                        │    │
│  │                                                                  │    │
│  │  4 Governed Metrics:                                             │    │
│  │    ON_TIME_DELIVERY_RATE · FILL_RATE                             │    │
│  │    DAYS_OF_INVENTORY · LANDED_COST_PER_UNIT                      │    │
│  │                                                                  │    │
│  │  33 Dimensions · 6 Relationships · 12 Facts                      │    │
│  │                                                                  │    │
│  │  AI Guardrails:                                                  │    │
│  │    AI_SQL_GENERATION — constrains to governed metrics only        │    │
│  │    AI_QUESTION_CATEGORIZATION — rejects undefined KPIs (OTIF)     │    │
│  └──────────────────────┬───────────────────────────────────────────┘    │
│                         ▼                                                │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │                  STRUCTURED DATA SOURCES                         │    │
│  │                                                                  │    │
│  │  ORDER_LINES_V ──┐                                               │    │
│  │  (ERP orders +   │   PARTS · PLANTS · CUSTOMERS                  │    │
│  │   logistics      │   SUPPLIERS_V (bridged via SUPPLIER_XREF)     │    │
│  │   shipments)     │   INVENTORY_SNAPSHOT                          │    │
│  │                  │                                               │    │
│  │  ← Joined from: ORDERS_ERP + SHIPMENTS_LOGISTICS                │    │
│  │     (two source systems reconciled into one view)                │    │
│  └──────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │                  SECURITY & GOVERNANCE LAYER                     │    │
│  │                                                                  │    │
│  │  RBAC: PLANNING_ROLE │ PROCUREMENT_ROLE │ LOGISTICS_ROLE         │    │
│  │  Masking: MASK_COST_FROM_LOGISTICS (unit_price, freight,         │    │
│  │           duty, handling → NULL for LOGISTICS_ROLE)              │    │
│  └──────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │                  PERSISTENCE LAYER                               │    │
│  │                                                                  │    │
│  │  CHAT_SESSIONS table — stores user conversations as VARIANT      │    │
│  │  (session_id, user_name, title, messages, is_shared, timestamps) │    │
│  └──────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
```

### CoCo CLI Skills Used

| CoCo Skill | How it was used |
|:-----------|:----------------|
| **`sql-author`** | Generated all 20 SQL scripts — tables, views, semantic view, RBAC, masking policies |
| **`developing-with-streamlit-in-snowflake`** | Built the 6-tab Streamlit app with custom CSS, chat UI, and auto-charting |
| **`agent-studio`** | Designed the semantic view with AI guardrails (`AI_SQL_GENERATION`, `AI_QUESTION_CATEGORIZATION`) |
| **`data-governance`** | Configured RBAC roles, column-level masking, and privilege grants |
| **`html-authoring`** | Generated styled HTML reports for PDF download |
| **`cortex-ai-function-studio`** | Integrated Cortex Analyst REST API for multi-turn natural language queries |

### Data Sources

| Source | Type | Description |
|:-------|:-----|:------------|
| `ORDERS_ERP` | Structured (ERP system) | Order headers and lines with quantities, prices, promised dates |
| `SHIPMENTS_LOGISTICS` | Structured (Logistics TMS) | Shipment events — dispatch, gate-in, customer receipt timestamps, freight costs |
| `PARTS` / `PLANTS` / `CUSTOMERS` | Structured (Master data) | Dimension tables for parts catalog, plant locations, customer profiles |
| `SUPPLIERS_V` | Structured (Reconciled) | Unified supplier view bridging ERP (`SUP-nnn`) and logistics (`LS-nnnn`) ID schemes via `SUPPLIER_XREF` |
| `INVENTORY_SNAPSHOT` | Structured (Daily snapshot) | Daily on-hand quantity and average daily usage per plant and part |

---

## 3. Impact Statement

### Measurable Outcomes

| Metric | Before | After | Improvement |
|:-------|:-------|:------|:------------|
| **Time to answer a KPI question** | 15–30 min (write SQL, validate, format) | **< 10 seconds** (type in plain English) | **~99% reduction** |
| **Metric definitions in use** | 3+ conflicting per KPI | **1 governed definition** per KPI | **100% consistency** |
| **Cost data exposure risk** | Manual access control, easy to misconfigure | **Automatic column-level masking** — provable in-app | **Zero leakage** |
| **Report generation time** | Hours (manual Excel + PowerPoint) | **1 click** (CSV + PDF auto-generated) | **~95% reduction** |
| **Chat session persistence** | None — lost on page refresh | **Snowflake-backed** — resume, share, audit | **Full traceability** |
| **Ungoverned metric requests** | Silently produce wrong answers | **AI guardrails refuse and redirect** | **Zero drift** |

### Scalability Potential

**Horizontal scaling — more metrics, more teams:**
- The semantic view pattern scales to any number of metrics and dimensions. Adding a new governed KPI (e.g., `PERFECT_ORDER_RATE`) requires one `METRICS` line in the semantic view — Cortex Analyst picks it up immediately with no app code changes.
- Adding new roles (e.g., `FINANCE_ROLE`, `EXECUTIVE_ROLE`) requires one SQL grant + optional masking policy — the app dynamically reads roles from config.

**Vertical scaling — more data volume:**
- Snowflake's elastic compute handles billions of order lines without app changes. The semantic view pushes all computation down to Snowflake — the Streamlit layer only renders results.
- `CHAT_SESSIONS` table uses `VARIANT` for flexible schema — no migrations needed as chat features evolve.

**Cross-industry extension:**
- The architecture pattern (semantic view + AI guardrails + RBAC + masking + natural language) is domain-agnostic:

| Industry | Governed Metric Example | Masking Example |
|:---------|:-----------------------|:----------------|
| **Healthcare** | 30-day readmission rate | Mask patient PII from operational roles |
| **Finance** | Value-at-Risk (VaR) | Mask position sizes from compliance |
| **Retail** | Conversion rate | Mask revenue from store-level roles |
| **SaaS** | Net Revenue Retention | Mask individual contract values |

### Beyond the Demo

This demo uses synthetic data (4,500 order lines). In production:
- Connect to real ERP (SAP, Oracle) and logistics (TMS) systems via Snowflake connectors or Snowpipe
- Add row-level security policies for multi-tenant deployments
- Enable Snowflake tasks for automated daily refresh of inventory snapshots
- Integrate with Slack/Teams via notification integrations for KPI alerts
- Deploy as a Snowflake Native App for distribution across accounts

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

## CI/CD Pipeline

[![CI/CD](https://github.com/AARAV-git/onetruth/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/AARAV-git/onetruth/actions/workflows/ci-cd.yml)

Every push to `main` triggers a **4-stage GitHub Actions pipeline** that validates the entire stack before deployment:

```
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│  Validate    │   │  Validate    │   │  Security &  │
│  SQL Scripts │   │  Streamlit   │   │  Governance  │
│  (20 files)  │   │  App         │   │  Audit       │
└──────┬───────┘   └──────┬───────┘   └──────┬───────┘
       │                  │                  │
       └──────────┬───────┴──────────────────┘
                  ▼
         ┌──────────────┐
         │  Pipeline    │
         │  Summary     │
         └──────────────┘
```

### Pipeline Jobs

| Job | What it checks | Fails if |
|:----|:---------------|:---------|
| **Validate SQL** | File naming convention, semantic view definition, RBAC roles, masking policy, AI guardrails (`AI_SQL_GENERATION`, `AI_QUESTION_CATEGORIZATION`) | Any SQL file is empty, missing semantic view, missing guardrails |
| **Validate App** | Python syntax, required imports (streamlit, snowflake, plotly, pandas), app structure (tabs, chat, auto-chart, sessions, downloads, masking demo, team identity) | Syntax error, missing critical feature |
| **Security Audit** | No hardcoded passwords/API keys, uses `st.secrets`, RBAC role count, masking policy count, grant statements | Hardcoded credentials found |
| **Pipeline Summary** | Aggregates all results, prints governance stats | Any upstream job fails |

### Running the Pipeline

The pipeline runs automatically on every push. You can also trigger it manually:

```bash
# Via GitHub CLI
gh workflow run ci-cd.yml

# Or click "Run workflow" in the Actions tab
```

### View Results

```bash
# Check latest run
gh run list --limit 1

# View logs on failure
gh run view <run_id> --log-failed
```

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
├── .github/
│   └── workflows/
│       └── ci-cd.yml            ← 4-stage GitHub Actions pipeline
├── app/
│   ├── app.py                   ← Streamlit app (6 tabs, 1600+ lines)
│   └── requirements.txt
└── sql/
    ├── 01_setup.sql             ← database, schemas, warehouse
    ├── 02–07_dim_*.sql          ← dimension tables
    ├── 08–12_gen_*.sql          ← deterministic synthetic data
    ├── 13_shift_dates.sql       ← align to 2026 calendar
    ├── 14–15_view_*.sql         ← helper views
    ├── 16_view_persona.sql      ← 4 conflicting OTD definitions
    ├── 17_semantic_view.sql     ← THE governed semantic view
    ├── 18_rbac_roles.sql        ← 3 persona roles
    ├── 19_masking_policy.sql    ← column-level cost masking
    └── 20_grants.sql            ← role grants
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
| **Development** | Built entirely using Snowflake CoCo CLI |

---

<div align="center">

**Built by Team NeuroForge**

Sunny Pathak (Lead) · Saurav Sharma · Himanshi Sharma

Powered by Snowflake + Cortex Analyst + CoCo CLI

</div>
