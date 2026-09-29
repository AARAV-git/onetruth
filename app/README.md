# OneTruth Supply Chain — Streamlit App

Governed supply-chain analytics powered by Cortex Analyst and a single semantic view.

## Prerequisites

- Python 3.9+
- Snowflake connection configured in `~/.snowflake/connections.toml`
  (the app reads connection `OR68348` by default — set `SNOWFLAKE_CONNECTION_NAME` to override)
- The `ONETRUTH` database, semantic view, and RBAC roles created by the SQL scripts in `../sql/`

## Install

```bash
cd onetruth/app
pip install -r requirements.txt
```

## Run

```bash
streamlit run app.py
```

A browser tab opens. The app authenticates via your existing Snowflake connection (OAuth).

## Tabs

| Tab | Purpose |
|-----|---------|
| **Ask** | Pick a persona (Planning / Procurement / Logistics), ask a natural-language question, see the governed answer with full evidence (SQL, metric definition, period). |
| **Before OneTruth** | Bar chart showing how each team measured Q3 on-time delivery before governance — four conflicting numbers from one view. |
| **Consistency** | Proves the semantic view returns the same OTD regardless of which role queries it. |
