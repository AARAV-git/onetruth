"""OneTruth Supply Chain — Governed analytics via Cortex Analyst."""

import os
import re
import json
import uuid
import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import snowflake.connector
from snowflake.connector.errors import ProgrammingError, DatabaseError
from datetime import datetime

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
@st.cache_resource(ttl=3600)
def get_connection():
    extra = {"client_session_keep_alive": True}

    try:
        params = {**dict(st.secrets["connections"]["snowflake"]), **extra}
        return snowflake.connector.connect(**params)
    except Exception:
        pass

    try:
        params = {
            k: str(v) for k, v in st.secrets.items()
            if k in ("account", "user", "password", "warehouse", "database", "role")
        }
        if "account" in params and "user" in params:
            return snowflake.connector.connect(**{**params, **extra})
    except Exception:
        pass

    try:
        return snowflake.connector.connect(
            connection_name=CONNECTION_NAME, **extra
        )
    except Exception:
        pass

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


def _reconnect():
    get_connection.clear()
    return get_connection()


def _with_reconnect(fn):
    conn = get_connection()
    try:
        return fn(conn)
    except (ProgrammingError, DatabaseError) as e:
        cause = str(e.__cause__) if e.__cause__ else str(e)
        if "ReauthenticationRequest" in cause or "Authentication token has expired" in cause:
            conn = _reconnect()
            return fn(conn)
        raise


def use_role(conn, role_name):
    def _do(c):
        cur = c.cursor()
        cur.execute(f"USE ROLE {role_name}")
        cur.execute(f"USE WAREHOUSE {WAREHOUSE}")
        cur.close()
    _with_reconnect(_do)


def run_query(conn, sql):
    def _do(c):
        cur = c.cursor()
        cur.execute(sql)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        cur.close()
        return pd.DataFrame(rows, columns=cols)
    return _with_reconnect(_do)


def run_dml(conn, sql, params=None):
    def _do(c):
        cur = c.cursor()
        cur.execute(sql, params or [])
        cur.close()
    _with_reconnect(_do)

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
# Cortex Analyst REST call (multi-turn)
# ---------------------------------------------------------------------------
def call_analyst(conn, messages):
    def _do(c):
        token = c.rest.token
        host = c.host
        url = f"https://{host}/api/v2/cortex/analyst/message"
        headers = {
            "Authorization": f'Snowflake Token="{token}"',
            "Content-Type": "application/json",
        }
        body = {
            "messages": messages,
            "semantic_view": SEMANTIC_VIEW,
        }
        resp = requests.post(url, headers=headers, json=body, timeout=120)
        resp.raise_for_status()
        return resp.json()
    return _with_reconnect(_do)


def parse_analyst_response(resp):
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
    if not sql_text:
        return []
    found = []
    sql_upper = sql_text.upper()
    for name, meta in metrics_meta.items():
        if name in sql_upper:
            found.append((name, meta))
    return found

# ---------------------------------------------------------------------------
# Chat session persistence (Snowflake-backed)
# ---------------------------------------------------------------------------
def _serializable_history(chat_history):
    out = []
    for turn in chat_history:
        t = {k: v for k, v in turn.items() if k != "df"}
        if turn.get("df") is not None:
            t["df_json"] = turn["df"].to_json(orient="split")
        out.append(t)
    return out


def _deserialize_history(raw):
    out = []
    for turn in raw:
        t = dict(turn)
        if "df_json" in t and t["df_json"]:
            t["df"] = pd.read_json(t["df_json"], orient="split")
            del t["df_json"]
        else:
            t["df"] = None
        out.append(t)
    return out


def save_session(conn, session_id, user_name, title, chat_history, is_shared=False):
    use_role(conn, "ACCOUNTADMIN")
    payload = json.dumps(_serializable_history(chat_history))
    sql = """
    MERGE INTO ONETRUTH.APP.CHAT_SESSIONS t
    USING (SELECT %s AS sid, %s AS uname, %s AS ttl, PARSE_JSON(%s) AS msgs,
                  %s AS shared) s
    ON t.SESSION_ID = s.sid
    WHEN MATCHED THEN UPDATE SET
        TITLE = s.ttl, MESSAGES = s.msgs, UPDATED_AT = CURRENT_TIMESTAMP(),
        IS_SHARED = s.shared
    WHEN NOT MATCHED THEN INSERT (SESSION_ID, USER_NAME, TITLE, MESSAGES, IS_SHARED)
        VALUES (s.sid, s.uname, s.ttl, s.msgs, s.shared)
    """
    run_dml(conn, sql, [session_id, user_name, title, payload, is_shared])


def load_session(conn, session_id):
    use_role(conn, "ACCOUNTADMIN")
    df = run_query(conn, f"""
        SELECT SESSION_ID, USER_NAME, TITLE, MESSAGES, IS_SHARED
        FROM ONETRUTH.APP.CHAT_SESSIONS
        WHERE SESSION_ID = '{session_id}'
    """)
    if df.empty:
        return None
    row = df.iloc[0]
    msgs_raw = row["MESSAGES"]
    if isinstance(msgs_raw, str):
        msgs_raw = json.loads(msgs_raw)
    return {
        "session_id": row["SESSION_ID"],
        "user_name": row["USER_NAME"],
        "title": row["TITLE"],
        "messages": _deserialize_history(msgs_raw),
        "is_shared": row["IS_SHARED"],
    }


def list_sessions(conn, user_name):
    use_role(conn, "ACCOUNTADMIN")
    df = run_query(conn, f"""
        SELECT SESSION_ID, TITLE, UPDATED_AT
        FROM ONETRUTH.APP.CHAT_SESSIONS
        WHERE USER_NAME = '{user_name}'
        ORDER BY UPDATED_AT DESC
        LIMIT 30
    """)
    return df


def delete_session(conn, session_id):
    use_role(conn, "ACCOUNTADMIN")
    run_dml(conn, f"DELETE FROM ONETRUTH.APP.CHAT_SESSIONS WHERE SESSION_ID = '{session_id}'")


# ---------------------------------------------------------------------------
# Auto-chart: detect shape and render the best visualization
# ---------------------------------------------------------------------------
TIME_PATTERNS = re.compile(
    r"(DATE|MONTH|QUARTER|YEAR|WEEK|PERIOD|TIME)", re.IGNORECASE
)

def auto_visualize(result_df, container):
    if result_df.empty:
        container.warning("Query returned no rows.")
        return

    nrows, ncols = result_df.shape

    if nrows == 1 and ncols == 1:
        val = result_df.iloc[0, 0]
        col_name = result_df.columns[0]
        if isinstance(val, (int, float)) and abs(val) <= 1:
            container.metric(col_name.replace("_", " ").title(), f"{val * 100:.1f}%")
        else:
            container.metric(
                col_name.replace("_", " ").title(),
                f"{val:,.2f}" if isinstance(val, float) else str(val),
            )
        return

    if nrows == 1:
        cols = container.columns(min(ncols, 4))
        for i, c in enumerate(result_df.columns):
            val = result_df.iloc[0, i]
            label = c.replace("_", " ").title()
            with cols[i % len(cols)]:
                if isinstance(val, (int, float)) and abs(val) <= 1 and "RATE" in c.upper():
                    st.metric(label, f"{val * 100:.1f}%")
                elif isinstance(val, float):
                    st.metric(label, f"{val:,.2f}")
                else:
                    st.metric(label, str(val))
        return

    str_cols = [c for c in result_df.columns if result_df[c].dtype == "object"]
    num_cols = [c for c in result_df.columns if pd.api.types.is_numeric_dtype(result_df[c])]
    time_cols = [c for c in str_cols if TIME_PATTERNS.search(c)]

    if time_cols and num_cols:
        x_col = time_cols[0]
        df_sorted = result_df.sort_values(x_col)
        fig = px.line(
            df_sorted, x=x_col, y=num_cols,
            markers=True, template="plotly_white",
            color_discrete_sequence=CHART_PALETTE,
        )
        fig.update_layout(height=420, xaxis_title=None)
        container.plotly_chart(fig, use_container_width=True)
        with container.expander("Data table"):
            st.dataframe(df_sorted, use_container_width=True)
        return

    if str_cols and num_cols and nrows <= 50:
        x_col = str_cols[0]
        fig = px.bar(
            result_df, x=x_col, y=num_cols,
            barmode="group", template="plotly_white",
            text_auto=".2s",
            color_discrete_sequence=CHART_PALETTE,
        )
        fig.update_layout(height=420, xaxis_title=None)
        container.plotly_chart(fig, use_container_width=True)
        with container.expander("Data table"):
            st.dataframe(result_df, use_container_width=True)
        return

    container.dataframe(result_df, use_container_width=True)

# ---------------------------------------------------------------------------
# Theme colors
# ---------------------------------------------------------------------------
BRAND = "#29B5E8"
ACCENT = "#0D9373"
WARN   = "#FF6F61"
PURPLE = "#7C3AED"
GOLD   = "#F59E0B"
NAVY   = "#0F172A"
CHART_PALETTE = [BRAND, ACCENT, PURPLE, GOLD, WARN, "#38BDF8"]

# ---------------------------------------------------------------------------
# Page config & custom CSS
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="OneTruth Supply Chain",
    page_icon="https://www.snowflake.com/favicon.ico",
    layout="wide",
)

st.markdown(f"""
<style>
    section[data-testid="stSidebar"] {{
        background: linear-gradient(180deg, {NAVY} 0%, #1E293B 100%);
    }}
    section[data-testid="stSidebar"] * {{
        color: #E2E8F0 !important;
    }}
    section[data-testid="stSidebar"] hr {{
        border-color: rgba(255,255,255,0.12);
    }}
    div[data-testid="stMetric"] {{
        background: linear-gradient(135deg, #F8FAFC 0%, #EFF6FF 100%);
        border: 1px solid #DBEAFE;
        border-left: 4px solid {BRAND};
        border-radius: 12px;
        padding: 16px 20px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    }}
    div[data-testid="stMetric"] label {{
        color: #64748B !important;
        font-weight: 600;
        font-size: 0.8rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }}
    div[data-testid="stMetric"] div[data-testid="stMetricValue"] {{
        color: {NAVY} !important;
        font-size: 1.8rem;
        font-weight: 700;
    }}
    button[data-baseweb="tab"] {{
        font-weight: 600;
        font-size: 0.95rem;
    }}
    button[data-baseweb="tab"][aria-selected="true"] {{
        color: {BRAND} !important;
        border-bottom-color: {BRAND} !important;
    }}
    div[data-testid="stChatMessage"] {{
        border-radius: 12px;
        border: 1px solid #E2E8F0;
        margin-bottom: 8px;
    }}
    div[data-testid="stAlert"] {{
        border-radius: 10px;
    }}
    details {{
        border: 1px solid #E2E8F0 !important;
        border-radius: 10px !important;
    }}
    footer {{visibility: hidden;}}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Initialize connection
# ---------------------------------------------------------------------------
conn = get_connection()
metrics_meta = load_metric_metadata()

# ---------------------------------------------------------------------------
# Session state defaults
# ---------------------------------------------------------------------------
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "active_session_id" not in st.session_state:
    st.session_state.active_session_id = str(uuid.uuid4())
if "session_title" not in st.session_state:
    st.session_state.session_title = "New Chat"
if "readonly_mode" not in st.session_state:
    st.session_state.readonly_mode = False
if "shared_owner" not in st.session_state:
    st.session_state.shared_owner = None

# Check for shared session in URL params
qp = st.query_params
shared_sid = qp.get("session", None)
if shared_sid and shared_sid != st.session_state.get("_loaded_shared_sid"):
    data = load_session(conn, shared_sid)
    if data and data["is_shared"]:
        st.session_state.chat_history = data["messages"]
        st.session_state.active_session_id = data["session_id"]
        st.session_state.session_title = data["title"]
        st.session_state.readonly_mode = True
        st.session_state.shared_owner = data["user_name"]
        st.session_state._loaded_shared_sid = shared_sid

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown(
        f'<h1 style="margin-bottom:0; font-size:1.8rem;">OneTruth</h1>'
        f'<p style="color:{BRAND} !important; margin-top:0; font-size:0.9rem;">'
        f'Governed Supply Chain Analytics</p>',
        unsafe_allow_html=True,
    )
    st.divider()

    sidebar_user = st.session_state.get("user_name", "")
    if sidebar_user:
        st.markdown(f"Logged in as **{sidebar_user}**")
        if st.button("Log out", use_container_width=True):
            st.session_state["user_name"] = ""
            st.session_state.chat_history = []
            st.session_state.session_title = "New Chat"
            st.session_state.active_session_id = str(uuid.uuid4())
            st.rerun()
        st.divider()

        # Quick session list in sidebar
        st.markdown("**Recent Chats**")
        try:
            df_sidebar = list_sessions(conn, sidebar_user)
            if not df_sidebar.empty:
                for _, srow in df_sidebar.head(10).iterrows():
                    sid = srow["SESSION_ID"]
                    title = srow["TITLE"] or "Untitled"
                    is_active = sid == st.session_state.active_session_id
                    prefix = "> " if is_active else ""
                    if st.button(f"{prefix}{title}", key=f"sb_{sid}", use_container_width=True):
                        data = load_session(conn, sid)
                        if data:
                            st.session_state.chat_history = data["messages"]
                            st.session_state.active_session_id = sid
                            st.session_state.session_title = data["title"]
                            st.session_state.readonly_mode = False
                            st.session_state.shared_owner = None
                            st.query_params.clear()
                            st.rerun()
            else:
                st.caption("No chats yet.")
        except Exception:
            st.caption("No chats yet.")
    else:
        st.caption("Go to the **Ask** tab to sign in.")

    st.divider()
    st.markdown(
        f"**Governed Metrics**\n\n"
        f"- `ON_TIME_DELIVERY_RATE`\n"
        f"- `FILL_RATE`\n"
        f"- `DAYS_OF_INVENTORY`\n"
        f"- `LANDED_COST_PER_UNIT`"
    )
    st.divider()
    st.caption("Built with Snowflake + Cortex Analyst")

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab_dash, tab_ask, tab_before, tab_consistency, tab_masking, tab_analytics = st.tabs(
    ["Dashboard", "Ask", "Before OneTruth", "Consistency", "Masking", "Analytics"]
)

# ── Tab 1: Executive Dashboard ────────────────────────────────────────────
with tab_dash:
    st.subheader("Executive KPI Dashboard — Q3 2026")
    use_role(conn, "ACCOUNTADMIN")

    kpi_query = """
    SELECT * FROM SEMANTIC_VIEW(
        ONETRUTH.SEMANTIC.SUPPLY_CHAIN_SV
        DIMENSIONS order_lines.promised_quarter
        METRICS order_lines.ON_TIME_DELIVERY_RATE,
               order_lines.FILL_RATE,
               order_lines.LANDED_COST_PER_UNIT
    )
    WHERE promised_quarter = '2026-Q3'
    """
    try:
        df_kpi = run_query(conn, kpi_query)
        c1, c2, c3, c4 = st.columns(4)
        if not df_kpi.empty:
            row = df_kpi.iloc[0]
            otd = row.get("ON_TIME_DELIVERY_RATE")
            fill = row.get("FILL_RATE")
            landed = row.get("LANDED_COST_PER_UNIT")

            c1.metric("On-Time Delivery", f"{otd * 100:.1f}%" if otd else "N/A")
            c2.metric("Fill Rate", f"{fill * 100:.1f}%" if fill else "N/A")
            c3.metric("Landed Cost/Unit", f"${landed:,.2f}" if landed else "N/A")

            doi_query = """
            SELECT * FROM SEMANTIC_VIEW(
                ONETRUTH.SEMANTIC.SUPPLY_CHAIN_SV
                DIMENSIONS inventory.snapshot_date
                METRICS inventory.DAYS_OF_INVENTORY
            )
            ORDER BY snapshot_date DESC LIMIT 1
            """
            try:
                df_doi = run_query(conn, doi_query)
                doi = df_doi.iloc[0]["DAYS_OF_INVENTORY"] if not df_doi.empty else None
                c4.metric("Days of Inventory", f"{doi:.1f}" if doi else "N/A")
            except Exception:
                c4.metric("Days of Inventory", "N/A")
    except Exception as e:
        st.warning(f"Could not load KPIs: {e}")

    st.divider()

    trend_query = """
    SELECT * FROM SEMANTIC_VIEW(
        ONETRUTH.SEMANTIC.SUPPLY_CHAIN_SV
        DIMENSIONS order_lines.promised_month
        METRICS order_lines.ON_TIME_DELIVERY_RATE, order_lines.FILL_RATE
    )
    ORDER BY promised_month
    """
    try:
        df_trend = run_query(conn, trend_query)
        if not df_trend.empty:
            col_left, col_right = st.columns(2)
            with col_left:
                st.markdown("**Monthly Delivery Performance**")
                df_plot = df_trend.melt(
                    id_vars=["PROMISED_MONTH"],
                    value_vars=["ON_TIME_DELIVERY_RATE", "FILL_RATE"],
                    var_name="Metric", value_name="Rate",
                )
                df_plot["Rate"] = df_plot["Rate"].astype(float) * 100
                fig_trend = px.line(
                    df_plot, x="PROMISED_MONTH", y="Rate", color="Metric",
                    markers=True, template="plotly_white",
                    labels={"PROMISED_MONTH": "Month", "Rate": "%"},
                    color_discrete_sequence=[BRAND, ACCENT],
                )
                fig_trend.update_layout(height=350, legend=dict(orientation="h", y=-0.2))
                st.plotly_chart(fig_trend, use_container_width=True)

            with col_right:
                st.markdown("**Top 10 Customers by Order Volume**")
                top_cust_query = """
                SELECT * FROM SEMANTIC_VIEW(
                    ONETRUTH.SEMANTIC.SUPPLY_CHAIN_SV
                    DIMENSIONS customers.customer_name
                    METRICS order_lines.ON_TIME_DELIVERY_RATE
                )
                ORDER BY ON_TIME_DELIVERY_RATE ASC
                LIMIT 10
                """
                try:
                    df_cust = run_query(conn, top_cust_query)
                    if not df_cust.empty:
                        df_cust["OTD %"] = (df_cust["ON_TIME_DELIVERY_RATE"].astype(float) * 100).round(1)
                        fig_cust = px.bar(
                            df_cust.sort_values("OTD %"),
                            x="OTD %", y="CUSTOMER_NAME",
                            orientation="h", template="plotly_white",
                            color="OTD %",
                            color_continuous_scale=[WARN, GOLD, ACCENT],
                        )
                        fig_cust.update_layout(
                            height=350, yaxis_title=None, showlegend=False,
                            coloraxis_showscale=False,
                        )
                        st.plotly_chart(fig_cust, use_container_width=True)
                except Exception:
                    st.info("Could not load customer data.")
    except Exception as e:
        st.warning(f"Could not load trend: {e}")

# ── Tab 2: Ask (multi-turn chat with persistence) ────────────────────────
with tab_ask:
    # Shared-session read-only view (via ?session= URL)
    if st.session_state.readonly_mode:
        st.info(
            f"Viewing shared conversation by **{st.session_state.shared_owner}**. "
            "This is read-only."
        )
        for turn in st.session_state.chat_history:
            with st.chat_message(turn["role"]):
                if turn["role"] == "user":
                    st.markdown(turn["display"])
                else:
                    st.markdown(turn["display"], unsafe_allow_html=True)
                    if turn.get("df") is not None:
                        auto_visualize(turn["df"], st)
                    if turn.get("sql"):
                        with st.expander("Evidence"):
                            st.code(turn["sql"], language="sql")

    # ── Gate: must enter name first ──
    elif not st.session_state.get("user_name"):
        st.markdown("### Welcome to OneTruth Chat")
        st.write("Enter your name to start asking questions or resume a previous session.")
        with st.form("name_gate", clear_on_submit=False):
            name_input = st.text_input("Your name", placeholder="e.g. Sunny Pathak")
            submitted = st.form_submit_button("Continue", type="primary")
        if submitted and name_input.strip():
            st.session_state["user_name"] = name_input.strip()
            st.rerun()
        elif submitted:
            st.warning("Please enter your name.")

    # ── Logged in: show session picker or active chat ──
    else:
        ask_user = st.session_state["user_name"]

        # If no active chat is loaded and not ready, show the session picker
        if not st.session_state.chat_history and st.session_state.session_title == "New Chat" and not st.session_state.get("_ask_ready"):
            st.markdown(f"### Welcome back, {ask_user}")

            col_new, col_spacer = st.columns([1, 3])
            with col_new:
                if st.button("+ New Chat", type="primary", use_container_width=True):
                    st.session_state.chat_history = []
                    st.session_state.active_session_id = str(uuid.uuid4())
                    st.session_state.session_title = "New Chat"
                    st.session_state["_ask_ready"] = True
                    st.rerun()

            # Show past sessions
            try:
                df_past = list_sessions(conn, ask_user)
            except Exception:
                df_past = pd.DataFrame()

            if not df_past.empty:
                st.markdown("**Your previous sessions** — click to resume:")
                for _, srow in df_past.iterrows():
                    sid = srow["SESSION_ID"]
                    title = srow["TITLE"] or "Untitled"
                    updated = srow["UPDATED_AT"]
                    col_resume, col_del = st.columns([6, 1])
                    with col_resume:
                        if st.button(f"{title}", key=f"ask_load_{sid}", use_container_width=True):
                            data = load_session(conn, sid)
                            if data:
                                st.session_state.chat_history = data["messages"]
                                st.session_state.active_session_id = sid
                                st.session_state.session_title = data["title"]
                                st.session_state["_ask_ready"] = True
                                st.query_params.clear()
                                st.rerun()
                    with col_del:
                        if st.button("X", key=f"ask_del_{sid}"):
                            delete_session(conn, sid)
                            st.rerun()
            else:
                st.caption("No previous sessions. Click **+ New Chat** to start!")

        # ── Active chat session ──
        else:
            # Persona selector
            col_persona, col_title, col_actions = st.columns([1, 2, 2])
            with col_persona:
                persona = st.selectbox("Persona", list(ROLES.keys()))
            role_name = ROLES[persona]
            use_role(conn, role_name)
            with col_title:
                st.caption(f"Session: **{st.session_state.session_title}**")
                st.caption(f"Role: `{role_name}`")
            with col_actions:
                ac1, ac2, ac3 = st.columns(3)
                with ac1:
                    if st.button("Share"):
                        save_session(
                            conn,
                            st.session_state.active_session_id,
                            ask_user,
                            st.session_state.session_title,
                            st.session_state.chat_history,
                            is_shared=True,
                        )
                        st.success(f"Link: `?session={st.session_state.active_session_id}`")
                with ac2:
                    if st.button("New"):
                        st.session_state.chat_history = []
                        st.session_state.active_session_id = str(uuid.uuid4())
                        st.session_state.session_title = "New Chat"
                        st.session_state["_ask_ready"] = True
                        st.query_params.clear()
                        st.rerun()
                with ac3:
                    if st.button("Back"):
                        st.session_state.chat_history = []
                        st.session_state.session_title = "New Chat"
                        st.session_state["_ask_ready"] = False
                        st.query_params.clear()
                        st.rerun()

            # Render previous messages
            for turn in st.session_state.chat_history:
                with st.chat_message(turn["role"]):
                    if turn["role"] == "user":
                        st.markdown(turn["display"])
                    else:
                        st.markdown(turn["display"], unsafe_allow_html=True)
                        if turn.get("df") is not None:
                            auto_visualize(turn["df"], st)
                        if turn.get("sql"):
                            with st.expander("Evidence"):
                                st.code(turn["sql"], language="sql")
                                matched = find_metric_in_sql(turn["sql"], metrics_meta)
                                if matched:
                                    for name, meta in matched:
                                        st.markdown(f"**{name}**: {meta['comment']}")
                                st.caption(f"Period: {extract_period(turn['sql'])}")

            # Chat input
            question = st.chat_input("Ask about the supply chain...")

            if question:
                st.session_state.chat_history.append({
                    "role": "user",
                    "display": question,
                    "content": [{"type": "text", "text": question}],
                })
                with st.chat_message("user"):
                    st.markdown(question)

                # Auto-title from first question
                if st.session_state.session_title == "New Chat":
                    st.session_state.session_title = question[:60] + ("..." if len(question) > 60 else "")

                # Local answers for non-data questions
                q_lower = question.lower()
                about_keywords = [
                    "who built", "who made", "who created", "who developed",
                    "who designed", "built this", "made this", "your team",
                    "your creator", "about you", "who are you", "team member",
                    "team lead", "main developer", "main in", "neuroforge",
                    "sunny pathak", "saurav sharma", "himanshi sharma",
                    "behind this", "developed by", "created by", "made by",
                    "built by", "building you", "build you", "your developer",
                    "your builder", "who is behind", "who works on",
                ]
                is_about = any(kw in q_lower for kw in about_keywords)

                if is_about:
                    team_text = (
                        "This app was built by **Team NeuroForge**.\n\n"
                        "| Role | Name |\n"
                        "|:-----|:-----|\n"
                        "| **Team Leader & Architect** | Sunny Pathak |\n"
                        "| **Member** | Saurav Sharma |\n"
                        "| **Member** | Himanshi Sharma |\n\n"
                        "**Sunny Pathak** leads the team and is the primary architect behind "
                        "OneTruth — from the semantic view design and RBAC model to the "
                        "Cortex Analyst integration and this Streamlit app.\n\n"
                        "OneTruth demonstrates governed supply chain analytics "
                        "powered by Snowflake Semantic Views and Cortex Analyst."
                    )
                    with st.chat_message("assistant"):
                        st.markdown(team_text)
                    st.session_state.chat_history.append({
                        "role": "analyst",
                        "display": team_text,
                        "content": [{"type": "text", "text": team_text}],
                        "sql": None,
                        "df": None,
                    })
                else:
                    analyst_messages = []
                    for turn in st.session_state.chat_history:
                        if turn["role"] == "user":
                            analyst_messages.append({
                                "role": "user",
                                "content": turn["content"],
                            })
                        else:
                            analyst_messages.append({
                                "role": "analyst",
                                "content": turn["content"],
                            })

                    with st.chat_message("assistant"):
                        with st.spinner("Thinking..."):
                            try:
                                resp = call_analyst(conn, analyst_messages)
                                text, sql_stmt, suggestions = parse_analyst_response(resp)
                            except Exception as e:
                                text, sql_stmt, suggestions = f"Analyst call failed: {e}", None, []

                        result_df = None

                        if text:
                            is_refusal = any(
                                kw in text.lower()
                                for kw in ["not defined", "not allowed", "cannot", "can't answer"]
                            )
                            if is_refusal:
                                st.warning(text)
                            elif not sql_stmt:
                                st.info(text)

                        if sql_stmt:
                            try:
                                result_df = run_query(conn, sql_stmt)
                                auto_visualize(result_df, st)
                            except Exception as e:
                                st.warning(f"Could not execute SQL: {e}")

                            with st.expander("Evidence"):
                                st.code(sql_stmt, language="sql")
                                matched = find_metric_in_sql(sql_stmt, metrics_meta)
                                if matched:
                                    for name, meta in matched:
                                        st.markdown(f"**{name}**: {meta['comment']}")
                                st.caption(f"Period: {extract_period(sql_stmt)}")

                        if suggestions:
                            st.info("Suggested follow-ups:")
                            for s in suggestions:
                                st.write(f"- {s}")

                        response_content = []
                        if text:
                            response_content.append({"type": "text", "text": text})
                        if sql_stmt:
                            response_content.append({"type": "sql", "statement": sql_stmt})
                        if suggestions:
                            response_content.append({"type": "suggestion", "suggestions": suggestions})

                        st.session_state.chat_history.append({
                            "role": "analyst",
                            "display": text or "",
                            "content": response_content,
                            "sql": sql_stmt,
                            "df": result_df,
                        })

                # Auto-save after every exchange
                save_session(
                    conn,
                    st.session_state.active_session_id,
                    ask_user,
                    st.session_state.session_title,
                    st.session_state.chat_history,
                )

# ── Tab 3: Before OneTruth ───────────────────────────────────────────────
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
        colors = [BRAND, WARN, GOLD, ACCENT]
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

# ── Tab 4: Consistency ───────────────────────────────────────────────────
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

    use_role(conn, "ACCOUNTADMIN")

# ── Tab 5: Masking Demo ─────────────────────────────────────────────────
with tab_masking:
    st.subheader("Column-Level Masking — Governance you can see")
    st.write(
        "The same `LANDED_COST_PER_UNIT` metric queried under each role. "
        "Logistics sees **NULL** because cost columns are masked."
    )

    cost_query = """
    SELECT * FROM SEMANTIC_VIEW(
        ONETRUTH.SEMANTIC.SUPPLY_CHAIN_SV
        DIMENSIONS order_lines.promised_quarter
        METRICS order_lines.LANDED_COST_PER_UNIT
    )
    WHERE promised_quarter = '2026-Q3'
    """

    mask_results = {}
    for label, role in ROLES.items():
        try:
            use_role(conn, role)
            df = run_query(conn, cost_query)
            val = df.iloc[0]["LANDED_COST_PER_UNIT"] if not df.empty else None
            if val is not None and pd.notna(val):
                mask_results[label] = {"value": float(val), "masked": False}
            else:
                mask_results[label] = {"value": None, "masked": True}
        except Exception as e:
            mask_results[label] = {"value": None, "masked": True, "error": str(e)}

    cols = st.columns(3)
    for i, (label, info) in enumerate(mask_results.items()):
        with cols[i]:
            if info["masked"]:
                st.metric(f"{label}", "NULL")
                st.error("MASKED — cost columns hidden by policy")
            else:
                st.metric(f"{label}", f"${info['value']:,.2f}")
                st.success("Full access to cost data")

    st.divider()

    st.markdown("**Raw cost column visibility by role**")
    raw_cost_query = """
    SELECT
        ROUND(AVG(unit_price), 2) AS avg_unit_price,
        ROUND(AVG(freight_cost), 2) AS avg_freight_cost,
        ROUND(AVG(duty_cost), 2) AS avg_duty_cost,
        ROUND(AVG(handling_cost), 2) AS avg_handling_cost
    FROM ONETRUTH.RAW.ORDER_LINES_V
    """

    raw_data = []
    for label, role in ROLES.items():
        try:
            use_role(conn, role)
            df = run_query(conn, raw_cost_query)
            row = df.iloc[0].to_dict() if not df.empty else {}
            row["Role"] = label
            raw_data.append(row)
        except Exception:
            raw_data.append({"Role": label})

    if raw_data:
        df_raw = pd.DataFrame(raw_data)
        col_order = ["Role"] + [c for c in df_raw.columns if c != "Role"]
        df_display = df_raw[col_order].copy()
        for c in df_display.columns:
            if c != "Role":
                df_display[c] = df_display[c].apply(
                    lambda v: f"${v:,.2f}" if pd.notna(v) else "NULL (masked)"
                )
        st.dataframe(df_display, use_container_width=True, hide_index=True)

    st.caption(
        "The masking policy `MASK_COST_FROM_LOGISTICS` returns NULL for "
        "`unit_price`, `freight_cost`, `duty_cost`, and `handling_cost` "
        "when `CURRENT_ROLE() = 'LOGISTICS_ROLE'`. This propagates through "
        "views into the semantic view."
    )

    use_role(conn, "ACCOUNTADMIN")

# ── Tab 6: Analytics ─────────────────────────────────────────────────────
with tab_analytics:
    st.subheader("Chat Analytics")
    use_role(conn, "ACCOUNTADMIN")

    current_user = st.session_state.get("user_name", "")

    # ---- Load all session data ----
    try:
        df_all = run_query(conn, """
            SELECT SESSION_ID, USER_NAME, TITLE, CREATED_AT, UPDATED_AT,
                   IS_SHARED, ARRAY_SIZE(MESSAGES) AS MSG_COUNT
            FROM ONETRUTH.APP.CHAT_SESSIONS
            ORDER BY UPDATED_AT DESC
        """)
    except Exception:
        df_all = pd.DataFrame()

    if df_all.empty:
        st.info("No chat sessions yet. Start a conversation in the **Ask** tab!")
    else:
        # ----------------------------------------------------------------
        # Overall Platform Metrics
        # ----------------------------------------------------------------
        st.markdown("### Platform Overview")
        total_sessions = len(df_all)
        total_users = df_all["USER_NAME"].nunique()
        total_messages = int(df_all["MSG_COUNT"].sum()) if "MSG_COUNT" in df_all.columns else 0
        shared_count = int(df_all["IS_SHARED"].sum()) if "IS_SHARED" in df_all.columns else 0

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Sessions", f"{total_sessions}")
        m2.metric("Unique Users", f"{total_users}")
        m3.metric("Total Messages", f"{total_messages}")
        m4.metric("Shared Chats", f"{shared_count}")

        st.divider()

        col_left, col_right = st.columns(2)

        # Sessions per user (bar chart)
        with col_left:
            st.markdown("**Sessions per User**")
            df_per_user = df_all.groupby("USER_NAME").size().reset_index(name="Sessions")
            df_per_user = df_per_user.sort_values("Sessions", ascending=False).head(15)
            fig_users = px.bar(
                df_per_user, x="USER_NAME", y="Sessions",
                template="plotly_white",
                color_discrete_sequence=[BRAND],
            )
            fig_users.update_layout(height=350, xaxis_title=None, yaxis_title="Sessions")
            st.plotly_chart(fig_users, use_container_width=True)

        # Messages per user (bar chart)
        with col_right:
            st.markdown("**Messages per User**")
            if "MSG_COUNT" in df_all.columns:
                df_msg_user = df_all.groupby("USER_NAME")["MSG_COUNT"].sum().reset_index(name="Messages")
                df_msg_user = df_msg_user.sort_values("Messages", ascending=False).head(15)
                fig_msgs = px.bar(
                    df_msg_user, x="USER_NAME", y="Messages",
                    template="plotly_white",
                    color_discrete_sequence=[ACCENT],
                )
                fig_msgs.update_layout(height=350, xaxis_title=None, yaxis_title="Messages")
                st.plotly_chart(fig_msgs, use_container_width=True)

        # Sessions over time (line chart)
        if "CREATED_AT" in df_all.columns:
            st.markdown("**Sessions Created Over Time**")
            df_timeline = df_all.copy()
            df_timeline["DAY"] = pd.to_datetime(df_timeline["CREATED_AT"]).dt.date
            df_daily = df_timeline.groupby("DAY").size().reset_index(name="Sessions")
            df_daily = df_daily.sort_values("DAY")
            fig_timeline = px.area(
                df_daily, x="DAY", y="Sessions",
                template="plotly_white",
                color_discrete_sequence=[PURPLE],
            )
            fig_timeline.update_layout(height=300, xaxis_title=None)
            st.plotly_chart(fig_timeline, use_container_width=True)

        # Leaderboard table
        st.markdown("**User Leaderboard**")
        df_leader = df_all.groupby("USER_NAME").agg(
            Sessions=("SESSION_ID", "count"),
            Messages=("MSG_COUNT", "sum"),
            Shared=("IS_SHARED", "sum"),
            Last_Active=("UPDATED_AT", "max"),
        ).reset_index().sort_values("Messages", ascending=False)
        df_leader.columns = ["User", "Sessions", "Messages", "Shared", "Last Active"]
        st.dataframe(df_leader, use_container_width=True, hide_index=True)

        # ----------------------------------------------------------------
        # User-Specific Metrics
        # ----------------------------------------------------------------
        st.divider()

        if current_user:
            st.markdown(f"### Your Stats — {current_user}")
            df_me = df_all[df_all["USER_NAME"] == current_user]

            if df_me.empty:
                st.info("You have no saved sessions yet.")
            else:
                my_sessions = len(df_me)
                my_messages = int(df_me["MSG_COUNT"].sum())
                my_shared = int(df_me["IS_SHARED"].sum())
                avg_msgs = round(my_messages / my_sessions, 1) if my_sessions else 0

                u1, u2, u3, u4 = st.columns(4)
                u1.metric("Your Sessions", f"{my_sessions}")
                u2.metric("Your Messages", f"{my_messages}")
                u3.metric("Avg Msgs/Session", f"{avg_msgs}")
                u4.metric("Shared by You", f"{my_shared}")

                # Your sessions over time
                if "CREATED_AT" in df_me.columns:
                    col_me_left, col_me_right = st.columns(2)
                    with col_me_left:
                        st.markdown("**Your Activity Over Time**")
                        df_me_time = df_me.copy()
                        df_me_time["DAY"] = pd.to_datetime(df_me_time["CREATED_AT"]).dt.date
                        df_me_daily = df_me_time.groupby("DAY").size().reset_index(name="Sessions")
                        fig_me = px.bar(
                            df_me_daily.sort_values("DAY"), x="DAY", y="Sessions",
                            template="plotly_white",
                            color_discrete_sequence=[GOLD],
                        )
                        fig_me.update_layout(height=300, xaxis_title=None)
                        st.plotly_chart(fig_me, use_container_width=True)

                    with col_me_right:
                        st.markdown("**Your Recent Sessions**")
                        df_recent = df_me[["TITLE", "MSG_COUNT", "UPDATED_AT", "IS_SHARED"]].head(10).copy()
                        df_recent.columns = ["Title", "Messages", "Last Updated", "Shared"]
                        df_recent["Shared"] = df_recent["Shared"].map({True: "Yes", False: "No"})
                        st.dataframe(df_recent, use_container_width=True, hide_index=True)
        else:
            st.info("Enter your name in the sidebar to see your personal stats.")
