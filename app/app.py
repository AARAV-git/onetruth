"""OneTruth Supply Chain — Governed analytics via Cortex Analyst."""

import os
import re
import json
import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
import snowflake.connector

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SEMANTIC_VIEW = "ONETRUTH.SEMANTIC.SUPPLY_CHAIN_SV"
CONNECTION_NAME = os.environ.get("SNOWFLAKE_CONNECTION_NAME", "OR68348")
WAREHOUSE = "ONETRUTH_WH"

ROLES = {
    "Planning": "PLANNING_ROLE",
    "Procurement": "PROCUREMENT_ROLE",
    "Logistics": "LOGISTICS_ROLE",
}

OTD_QUERY = """
SELECT * FROM SEMANTIC_VIEW(
    ONETRUTH.SEMANTIC.SUPPLY_CHAIN_SV
    DIMENSIONS order_lines.promised_quarter
    METRICS order_lines.ON_TIME_DELIVERY_RATE
)
WHERE promised_quarter = '2026-Q3'
"""

# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------
@st.cache_resource
def get_connection():
    # Method 1: [connections.snowflake] section in secrets
    try:
        params = dict(st.secrets["connections"]["snowflake"])
        return snowflake.connector.connect(**params)
    except Exception:
        pass

    # Method 2: flat secrets (account, user, password at top level)
    try:
        params = {
            k: str(v) for k, v in st.secrets.items()
            if k in ("account", "user", "password", "warehouse", "database", "role")
        }
        if "account" in params and "user" in params:
            return snowflake.connector.connect(**params)
    except Exception:
        pass

    # Method 3: local ~/.snowflake/connections.toml
    try:
        return snowflake.connector.connect(connection_name=CONNECTION_NAME)
    except Exception:
        pass

    # All methods failed — show debug info
    try:
        available = list(st.secrets.keys())
    except Exception:
        available = ["(no secrets found)"]
    st.error(
        f"**Cannot connect to Snowflake.**\n\n"
        f"Secrets keys found: `{available}`\n\n"
        "Paste this in **Manage app → Settings → Secrets**:\n\n"
        "```toml\n"
        "[connections.snowflake]\n"
        'account = "SQPCNWB-OR68348"\n'
        'user = "sunnypathak979"\n'
        'password = "your_password"\n'
        'warehouse = "ONETRUTH_WH"\n'
        'database = "ONETRUTH"\n'
        'role = "ACCOUNTADMIN"\n'
        "```"
    )
    st.stop()


def use_role(conn, role_name):
    cur = conn.cursor()
    cur.execute(f"USE ROLE {role_name}")
    cur.execute(f"USE WAREHOUSE {WAREHOUSE}")
    cur.close()


def run_query(conn, sql):
    cur = conn.cursor()
    cur.execute(sql)
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    cur.close()
    return pd.DataFrame(rows, columns=cols)

# ---------------------------------------------------------------------------
# Metric metadata (cached once)
# ---------------------------------------------------------------------------
@st.cache_data(ttl=600)
def load_metric_metadata():
    conn = get_connection()
    use_role(conn, "ACCOUNTADMIN")
    df = run_query(conn, f"SHOW SEMANTIC METRICS IN {SEMANTIC_VIEW}")
    metrics = {}
    for _, row in df.iterrows():
        name = row.get("name", "")
        metrics[name.upper()] = {
            "table": row.get("table_name", ""),
            "comment": row.get("comment", ""),
            "synonyms": row.get("synonyms", ""),
        }
    return metrics

# ---------------------------------------------------------------------------
# Cortex Analyst REST call
# ---------------------------------------------------------------------------
def call_analyst(conn, question):
    token = conn.rest.token
    host = conn.host
    url = f"https://{host}/api/v2/cortex/analyst/message"
    headers = {
        "Authorization": f'Snowflake Token="{token}"',
        "Content-Type": "application/json",
    }
    body = {
        "messages": [
            {"role": "user", "content": [{"type": "text", "text": question}]}
        ],
        "semantic_view": SEMANTIC_VIEW,
    }
    resp = requests.post(url, headers=headers, json=body, timeout=120)
    resp.raise_for_status()
    return resp.json()


def parse_analyst_response(resp):
    """Extract text, sql, and suggestions from the Analyst response."""
    msg = resp.get("message", {})
    contents = msg.get("content", [])
    text_parts, sql_stmt, suggestions = [], None, []
    for c in contents:
        ctype = c.get("type", "")
        if ctype == "text":
            text_parts.append(c.get("text", ""))
        elif ctype == "sql":
            sql_stmt = c.get("statement", "")
        elif ctype == "suggestion":
            suggestions = c.get("suggestions", [])
    return "\n".join(text_parts), sql_stmt, suggestions


def extract_period(sql_text):
    """Try to extract date range from generated SQL."""
    if not sql_text:
        return "Not specified"
    dates = re.findall(r"'(\d{4}-\d{2}-\d{2})'", sql_text)
    if len(dates) >= 2:
        return f"{dates[0]} to {dates[-1]}"
    quarters = re.findall(r"'(\d{4}-Q\d)'", sql_text)
    if quarters:
        return ", ".join(quarters)
    if "DATE_TRUNC" in sql_text.upper() and "CURRENT_DATE" in sql_text.upper():
        return "Relative to today (last quarter)"
    return "All available data"


def find_metric_in_sql(sql_text, metrics_meta):
    """Match metric names from SQL to metadata."""
    if not sql_text:
        return []
    found = []
    sql_upper = sql_text.upper()
    for name, meta in metrics_meta.items():
        if name in sql_upper:
            found.append((name, meta))
    return found

# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
st.set_page_config(page_title="OneTruth Supply Chain", layout="wide")
st.title("OneTruth Supply Chain")

conn = get_connection()
metrics_meta = load_metric_metadata()

tab_ask, tab_before, tab_consistency = st.tabs(
    ["Ask", "Before OneTruth", "Consistency"]
)

# ── Tab 1: Ask ─────────────────────────────────────────────────────────────
with tab_ask:
    col_persona, col_spacer = st.columns([1, 3])
    with col_persona:
        persona = st.selectbox("Persona", list(ROLES.keys()))
    role_name = ROLES[persona]
    use_role(conn, role_name)
    st.caption(f"Active role: `{role_name}`")

    question = st.text_input(
        "Ask a question about the supply chain",
        placeholder="e.g. What was our on-time delivery last quarter?",
    )

    if question:
        with st.spinner("Asking Cortex Analyst..."):
            try:
                resp = call_analyst(conn, question)
                text, sql_stmt, suggestions = parse_analyst_response(resp)
            except Exception as e:
                st.error(f"Analyst call failed: {e}")
                text, sql_stmt, suggestions = str(e), None, []

        # -- Answer card --
        if sql_stmt:
            try:
                result_df = run_query(conn, sql_stmt)
                if result_df.shape == (1, 1):
                    val = result_df.iloc[0, 0]
                    col_name = result_df.columns[0]
                    if isinstance(val, (int, float)) and abs(val) <= 1:
                        st.metric(col_name, f"{val * 100:.1f}%")
                    else:
                        st.metric(col_name, f"{val:,.2f}" if isinstance(val, float) else str(val))
                elif result_df.shape[0] == 1:
                    cols = st.columns(len(result_df.columns))
                    for i, c in enumerate(result_df.columns):
                        val = result_df.iloc[0, i]
                        label = c.replace("_", " ").title()
                        if isinstance(val, (int, float)) and abs(val) <= 1 and "RATE" in c.upper():
                            cols[i].metric(label, f"{val * 100:.1f}%")
                        elif isinstance(val, float):
                            cols[i].metric(label, f"{val:,.2f}")
                        else:
                            cols[i].metric(label, str(val))
                else:
                    st.dataframe(result_df, use_container_width=True)
            except Exception as e:
                st.warning(f"Could not execute generated SQL: {e}")

        if text:
            is_refusal = any(
                kw in text.lower()
                for kw in ["not defined", "not allowed", "cannot", "can't answer"]
            )
            if is_refusal:
                st.warning(text)
            elif not sql_stmt:
                st.info(text)

        if suggestions:
            st.info("Cortex Analyst suggested these clarifications:")
            for s in suggestions:
                st.write(f"- {s}")

        # -- Evidence panel --
        with st.expander("Evidence", expanded=False):
            st.subheader("Generated SQL")
            if sql_stmt:
                st.code(sql_stmt, language="sql")
            else:
                st.write("No SQL generated (question was refused or clarified).")

            st.subheader("Metric definition")
            if sql_stmt:
                matched = find_metric_in_sql(sql_stmt, metrics_meta)
                if matched:
                    for name, meta in matched:
                        st.markdown(f"**{name}**: {meta['comment']}")
                else:
                    st.write("No governed metric matched in the SQL.")
            else:
                st.write("—")

            st.subheader("Period covered")
            st.write(extract_period(sql_stmt))

# ── Tab 2: Before OneTruth ─────────────────────────────────────────────────
with tab_before:
    st.subheader("Q3 2026 On-Time Delivery — Four teams, four numbers")
    use_role(conn, "ACCOUNTADMIN")
    df_persona = run_query(
        conn, "SELECT * FROM ONETRUTH.APP.PERSONA_BEFORE_ONETRUTH"
    )
    if not df_persona.empty:
        labels = ["Planning", "Logistics", "Procurement (OTIF)", "Governed"]
        values = [
            float(df_persona.iloc[0]["PLANNING_OTD"]),
            float(df_persona.iloc[0]["LOGISTICS_OTD"]),
            float(df_persona.iloc[0]["PROCUREMENT_OTD_OTIF"]),
            float(df_persona.iloc[0]["GOVERNED_OTD"]),
        ]
        colors = ["#636EFA", "#EF553B", "#FFA15A", "#00CC96"]
        fig = go.Figure(
            go.Bar(
                x=labels,
                y=values,
                marker_color=colors,
                text=[f"{v}%" for v in values],
                textposition="outside",
            )
        )
        fig.update_layout(
            yaxis_title="On-Time %",
            yaxis_range=[0, 105],
            template="plotly_white",
            height=420,
        )
        st.plotly_chart(fig, use_container_width=True)
        st.caption(
            "Each bar uses a different definition of 'on time'. "
            "The Governed bar uses customer_receipt_ts — the only metric "
            "in the semantic view."
        )
    else:
        st.warning("No data returned from PERSONA_BEFORE_ONETRUTH.")

# ── Tab 3: Consistency ─────────────────────────────────────────────────────
with tab_consistency:
    st.subheader("Same metric, every role — governance in action")
    st.write(
        "The semantic view's `ON_TIME_DELIVERY_RATE` for Q3 2026, "
        "queried under each persona role:"
    )

    results = {}
    for label, role in ROLES.items():
        try:
            use_role(conn, role)
            df = run_query(conn, OTD_QUERY)
            val = round(float(df.iloc[0]["ON_TIME_DELIVERY_RATE"]) * 100, 1)
        except Exception as e:
            val = f"Error: {e}"
        results[label] = val

    cols = st.columns(3)
    vals = list(results.values())
    all_match = len(set(v for v in vals if isinstance(v, (int, float)))) == 1

    for i, (label, val) in enumerate(results.items()):
        with cols[i]:
            if isinstance(val, (int, float)):
                st.metric(f"{label}", f"{val}%")
            else:
                st.error(val)

    if all_match:
        st.success("All three roles return the identical governed OTD.")
    else:
        st.error("Mismatch detected — check role privileges and masking policies.")

    # Reset to ACCOUNTADMIN
    use_role(conn, "ACCOUNTADMIN")
