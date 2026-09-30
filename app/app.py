"""OneTruth Supply Chain — Governed analytics via Cortex Analyst."""

import os
import re
import json
import uuid
import io
import base64
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

_download_counter = [0]

def _render_download_buttons(result_df, container):
    _download_counter[0] += 1
    key_suffix = _download_counter[0]
    csv_data = result_df.to_csv(index=False)
    # Build HTML table
    html_rows = ""
    for _, r in result_df.iterrows():
        cells = "".join(f"<td>{v}</td>" for v in r.values)
        html_rows += f"<tr>{cells}</tr>"
    headers = "".join(f"<th>{c}</th>" for c in result_df.columns)
    html_data = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>OneTruth Data Export</title>
<style>body{{font-family:-apple-system,sans-serif;margin:40px;color:#1E293B;}}
h1{{color:#0EA5E9;font-size:1.5rem;}}
table{{border-collapse:collapse;width:100%;margin:12px 0;}}
th,td{{border:1px solid #CBD5E1;padding:8px 12px;text-align:left;}}
th{{background:#0EA5E9;color:white;font-weight:600;}}
tr:nth-child(even){{background:#F1F5F9;}}
.footer{{margin-top:30px;font-size:0.75rem;color:#94A3B8;text-align:center;}}</style></head>
<body><h1>OneTruth Data Export</h1>
<table><tr>{headers}</tr>{html_rows}</table>
<p class="footer">OneTruth — Team NeuroForge | Snowflake + Cortex Analyst</p>
</body></html>"""
    dl1, dl2, dl_space = container.columns([1, 1, 4])
    with dl1:
        st.download_button(
            label="Download CSV",
            data=csv_data,
            file_name="onetruth_data.csv",
            mime="text/csv",
            key=f"dl_csv_{key_suffix}",
        )
    with dl2:
        st.download_button(
            label="Download PDF",
            data=html_data,
            file_name="onetruth_data.html",
            mime="text/html",
            key=f"dl_html_{key_suffix}",
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
        _render_download_buttons(result_df, container)
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
        _render_download_buttons(result_df, container)
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
        _render_download_buttons(result_df, container)
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
        _render_download_buttons(result_df, container)
        with container.expander("Data table"):
            st.dataframe(result_df, use_container_width=True)
        return

    container.dataframe(result_df, use_container_width=True)
    _render_download_buttons(result_df, container)

# ---------------------------------------------------------------------------
# Theme colors
# ---------------------------------------------------------------------------
BRAND      = "#0EA5E9"      # Sky 500 — vivid Snowflake blue
BRAND_DARK = "#0284C7"      # Sky 600 — deeper blue for gradients
ACCENT     = "#059669"      # Emerald 600 — richer green
WARN       = "#E11D48"      # Rose 600 — stronger red
PURPLE     = "#7C3AED"      # Violet 600 — vivid purple
GOLD       = "#D97706"      # Amber 600 — deeper gold
NAVY       = "#020617"      # Slate 950 — near-black headings
SLATE      = "#1E293B"      # Slate 800 — dark body text
MUTED      = "#64748B"      # Slate 500 — readable captions
BG_MAIN    = "#CBD5E1"      # Slate 300 — muted page background
BG_CARD    = "#D5DCE6"       # Dull gray — soft cards
BORDER     = "#94A3B8"      # Slate 400 — visible borders
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
    /* ---- Page background & text ---- */
    .stApp {{
        background-color: {BG_MAIN};
    }}
    .stApp h1, .stApp h2, .stApp h3, .stApp h4 {{
        color: {NAVY} !important;
    }}
    .stApp p, .stApp span, .stApp li, .stApp label, .stApp div {{
        color: {SLATE};
    }}
    .stApp .stMarkdown p {{
        color: {SLATE};
    }}

    /* ---- Sidebar ---- */
    section[data-testid="stSidebar"] {{
        background: linear-gradient(180deg, {NAVY} 0%, #1E293B 100%);
    }}
    section[data-testid="stSidebar"] * {{
        color: #CBD5E1 !important;
    }}
    section[data-testid="stSidebar"] h1,
    section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] h3,
    section[data-testid="stSidebar"] strong {{
        color: #F1F5F9 !important;
    }}
    section[data-testid="stSidebar"] hr {{
        border-color: rgba(255,255,255,0.08);
    }}
    section[data-testid="stSidebar"] button {{
        background: rgba(255,255,255,0.06) !important;
        border: 1px solid rgba(255,255,255,0.1) !important;
        border-radius: 8px !important;
        color: #E2E8F0 !important;
        transition: background 0.2s;
    }}
    section[data-testid="stSidebar"] button:hover {{
        background: rgba(255,255,255,0.12) !important;
    }}

    /* ---- Metric cards ---- */
    div[data-testid="stMetric"] {{
        background: {BG_CARD};
        border: 1px solid {BORDER};
        border-left: 5px solid {BRAND};
        border-radius: 12px;
        padding: 18px 22px;
        box-shadow: 0 2px 6px rgba(0,0,0,0.08);
    }}
    div[data-testid="stMetric"] label {{
        color: {MUTED} !important;
        font-weight: 700;
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 0.06em;
    }}
    div[data-testid="stMetric"] div[data-testid="stMetricValue"] {{
        color: {NAVY} !important;
        font-size: 1.75rem;
        font-weight: 800;
    }}
    div[data-testid="stMetric"] div[data-testid="stMetricDelta"] {{
        color: {SLATE} !important;
    }}

    /* ---- Tabs ---- */
    div[data-testid="stTabs"] button[data-baseweb="tab"] {{
        font-weight: 600;
        font-size: 0.9rem;
        color: {SLATE} !important;
        padding: 10px 20px;
    }}
    div[data-testid="stTabs"] button[data-baseweb="tab"][aria-selected="true"] {{
        color: {BRAND} !important;
        border-bottom: 3px solid {BRAND} !important;
    }}

    /* ---- Selectbox / inputs ---- */
    div[data-testid="stSelectbox"] label,
    div[data-testid="stTextInput"] label {{
        color: {SLATE} !important;
    }}
    div[data-testid="stSelectbox"] div[data-baseweb="select"] > div {{
        color: {NAVY} !important;
        background: {BG_CARD} !important;
    }}

    /* ---- Caption text ---- */
    .stCaption, small {{
        color: {MUTED} !important;
    }}

    /* ---- Chat messages ---- */
    div[data-testid="stChatMessage"] {{
        border: none;
        padding: 12px 8px;
        margin-bottom: 2px;
        background: transparent !important;
        border-bottom: 1px solid rgba(148,163,184,0.2);
    }}
    /* All chat text uses dark color for readability */
    div[data-testid="stChatMessage"] p,
    div[data-testid="stChatMessage"] span,
    div[data-testid="stChatMessage"] li,
    div[data-testid="stChatMessage"] strong {{
        color: {NAVY} !important;
    }}
    div[data-testid="stChatMessage"] strong {{
        font-weight: 700 !important;
    }}

    /* ---- Chat input bar ---- */
    div[data-testid="stChatInput"] {{
        border: 2px solid {BORDER} !important;
        border-radius: 28px !important;
        background: {NAVY} !important;
        box-shadow: 0 2px 12px rgba(0,0,0,0.12) !important;
        transition: border-color 0.2s;
    }}
    div[data-testid="stChatInput"]:focus-within {{
        border-color: {BRAND} !important;
        box-shadow: 0 2px 16px rgba(14,165,233,0.25) !important;
    }}
    div[data-testid="stChatInput"] textarea {{
        color: #FFFFFF !important;
        caret-color: {BRAND} !important;
    }}
    div[data-testid="stChatInput"] textarea::placeholder {{
        color: {MUTED} !important;
    }}

    /* ---- Primary buttons ---- */
    button[kind="primary"] {{
        background: linear-gradient(135deg, {BRAND} 0%, {BRAND_DARK} 100%) !important;
        border: none !important;
        border-radius: 10px !important;
        font-weight: 700 !important;
        color: white !important;
        box-shadow: 0 3px 10px rgba(14,165,233,0.35) !important;
        transition: transform 0.15s, box-shadow 0.15s;
    }}
    button[kind="primary"]:hover {{
        transform: translateY(-1px);
        box-shadow: 0 5px 18px rgba(14,165,233,0.45) !important;
    }}

    /* ---- Secondary buttons ---- */
    button[kind="secondary"] {{
        border: 2px solid {BORDER} !important;
        border-radius: 10px !important;
        color: {NAVY} !important;
        font-weight: 600 !important;
        background: {BG_CARD} !important;
        transition: background 0.15s, border-color 0.15s;
    }}
    button[kind="secondary"]:hover {{
        background: {BG_MAIN} !important;
        border-color: {BRAND} !important;
        color: {BRAND} !important;
    }}

    /* ---- Alert badges ---- */
    div[data-testid="stAlert"] {{
        border-radius: 10px;
        border-left-width: 4px;
    }}

    /* ---- Expander ---- */
    details {{
        border: 1px solid {BORDER} !important;
        border-radius: 10px !important;
        background: {BG_CARD} !important;
    }}
    details summary {{
        font-weight: 600;
        color: {SLATE} !important;
    }}
    details summary span {{
        color: {SLATE} !important;
    }}

    /* ---- Code blocks ---- */
    pre {{
        background: #0F172A !important;
        border-radius: 8px !important;
        padding: 14px !important;
        border: 1px solid #334155 !important;
    }}
    pre code {{
        color: #F8FAFC !important;
        font-size: 0.85rem !important;
    }}
    pre code .token.keyword,
    pre code .hljs-keyword {{
        color: #38BDF8 !important;
    }}
    pre code .token.string,
    pre code .hljs-string {{
        color: #FB923C !important;
    }}
    pre code .token.function,
    pre code .hljs-title {{
        color: #38BDF8 !important;
    }}
    pre code .token.number,
    pre code .hljs-number {{
        color: #FB923C !important;
    }}
    pre code .token.operator {{
        color: #F8FAFC !important;
    }}
    pre code .token.comment,
    pre code .hljs-comment {{
        color: #64748B !important;
    }}
    /* Force all code text white if syntax highlighting is missing */
    div[data-testid="stCode"] pre {{
        background: #0F172A !important;
    }}
    div[data-testid="stCode"] pre code,
    div[data-testid="stCode"] pre code span {{
        color: #F8FAFC !important;
    }}
    code {{
        color: #38BDF8 !important;
        background: rgba(56,189,248,0.1) !important;
        padding: 2px 6px;
        border-radius: 4px;
    }}

    /* ---- Dataframe ---- */
    div[data-testid="stDataFrame"] {{
        border: 1px solid {BORDER};
        border-radius: 10px;
        overflow: hidden;
    }}

    /* ---- Divider ---- */
    hr {{
        border-color: {BORDER} !important;
    }}

    /* ---- Footer ---- */
    footer {{visibility: hidden;}}

    /* ---- Suggestion cards on welcome screen ---- */
    .stButton > button {{
        transition: all 0.15s ease;
    }}
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
        f'<div style="text-align:center; padding: 8px 0 4px 0;">'
        f'<h1 style="margin:0; font-size:1.6rem; color:#F1F5F9 !important; font-weight:700;">OneTruth</h1>'
        f'<p style="margin:4px 0 0 0; font-size:0.8rem; color:{BRAND} !important; letter-spacing:0.08em; text-transform:uppercase;">Supply Chain Analytics</p>'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.divider()

    sidebar_user = st.session_state.get("user_name", "")
    if sidebar_user:
        st.markdown(
            f'<p style="font-size:0.85rem; color:#94A3B8 !important;">Signed in as</p>'
            f'<p style="font-size:1rem; color:#F1F5F9 !important; font-weight:600; margin-top:-8px;">{sidebar_user}</p>',
            unsafe_allow_html=True,
        )
        if st.button("Sign out", use_container_width=True):
            st.session_state["user_name"] = ""
            st.session_state.chat_history = []
            st.session_state.session_title = "New Chat"
            st.session_state.active_session_id = str(uuid.uuid4())
            st.rerun()
        st.divider()

        st.markdown('<p style="font-size:0.75rem; text-transform:uppercase; letter-spacing:0.08em; color:#64748B !important; font-weight:600;">Recent Chats</p>', unsafe_allow_html=True)
        try:
            df_sidebar = list_sessions(conn, sidebar_user)
            if not df_sidebar.empty:
                for _, srow in df_sidebar.head(8).iterrows():
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
                            st.session_state["_ask_ready"] = True
                            st.query_params.clear()
                            st.rerun()
            else:
                st.caption("No chats yet.")
        except Exception:
            st.caption("No chats yet.")
    else:
        st.markdown(
            f'<p style="font-size:0.85rem; color:#94A3B8 !important; text-align:center; padding:12px 0;">Go to the <strong style="color:{BRAND} !important;">Ask</strong> tab to sign in</p>',
            unsafe_allow_html=True,
        )

    st.divider()
    st.markdown(
        f'<p style="font-size:0.7rem; text-transform:uppercase; letter-spacing:0.08em; color:#64748B !important; font-weight:600;">Governed Metrics</p>',
        unsafe_allow_html=True,
    )
    for metric_name in ["ON_TIME_DELIVERY_RATE", "FILL_RATE", "DAYS_OF_INVENTORY", "LANDED_COST_PER_UNIT"]:
        st.markdown(
            f'<p style="font-size:0.8rem; color:#CBD5E1 !important; margin:2px 0; padding:4px 8px; background:rgba(255,255,255,0.04); border-radius:6px; font-family:monospace;">{metric_name}</p>',
            unsafe_allow_html=True,
        )
    st.divider()
    st.markdown(
        f'<p style="font-size:0.7rem; color:#64748B !important; text-align:center;">Built with Snowflake + Cortex Analyst</p>',
        unsafe_allow_html=True,
    )

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

    # ── Download buttons ──
    st.divider()
    st.markdown("**Download Report**")

    # Build CSV from all available dashboard data
    try:
        csv_parts = []

        # KPI summary
        if "df_kpi" in dir() and df_kpi is not None and not df_kpi.empty:
            csv_parts.append("=== Q3 2026 KPI Summary ===")
            csv_parts.append(df_kpi.to_csv(index=False))

        # Monthly trend
        if "df_trend" in dir() and df_trend is not None and not df_trend.empty:
            csv_parts.append("\n=== Monthly Trend ===")
            csv_parts.append(df_trend.to_csv(index=False))

        # Customer OTD
        if "df_cust" in dir() and df_cust is not None and not df_cust.empty:
            csv_parts.append("\n=== Customer OTD ===")
            csv_parts.append(df_cust.to_csv(index=False))

        csv_content = "\n".join(csv_parts) if csv_parts else "No data available"
    except Exception:
        csv_content = "No data available"

    # Build HTML report for PDF-style download
    try:
        html_rows = []
        if "df_kpi" in dir() and df_kpi is not None and not df_kpi.empty:
            row = df_kpi.iloc[0]
            otd_v = f"{float(row.get('ON_TIME_DELIVERY_RATE', 0)) * 100:.1f}%"
            fill_v = f"{float(row.get('FILL_RATE', 0)) * 100:.1f}%"
            landed_v = f"${float(row.get('LANDED_COST_PER_UNIT', 0)):,.2f}"
            html_rows.append(f"<tr><td>On-Time Delivery</td><td>{otd_v}</td></tr>")
            html_rows.append(f"<tr><td>Fill Rate</td><td>{fill_v}</td></tr>")
            html_rows.append(f"<tr><td>Landed Cost/Unit</td><td>{landed_v}</td></tr>")
        if "doi" in dir() and doi is not None:
            html_rows.append(f"<tr><td>Days of Inventory</td><td>{doi:.1f}</td></tr>")

        kpi_table = "".join(html_rows)

        trend_rows = ""
        if "df_trend" in dir() and df_trend is not None and not df_trend.empty:
            for _, r in df_trend.iterrows():
                month = r.get("PROMISED_MONTH", "")
                otd_r = f"{float(r.get('ON_TIME_DELIVERY_RATE', 0)) * 100:.1f}%"
                fill_r = f"{float(r.get('FILL_RATE', 0)) * 100:.1f}%"
                trend_rows += f"<tr><td>{month}</td><td>{otd_r}</td><td>{fill_r}</td></tr>"

        html_report = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>OneTruth Supply Chain Report — Q3 2026</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 40px; color: #1E293B; }}
  h1 {{ color: #0EA5E9; font-size: 1.8rem; }}
  h2 {{ color: #334155; font-size: 1.3rem; margin-top: 30px; border-bottom: 2px solid #0EA5E9; padding-bottom: 6px; }}
  table {{ border-collapse: collapse; width: 100%; margin: 12px 0; }}
  th, td {{ border: 1px solid #CBD5E1; padding: 10px 14px; text-align: left; }}
  th {{ background: #0EA5E9; color: white; font-weight: 600; }}
  tr:nth-child(even) {{ background: #F1F5F9; }}
  .footer {{ margin-top: 40px; font-size: 0.8rem; color: #94A3B8; text-align: center; }}
  .badge {{ display: inline-block; background: #0EA5E9; color: white; padding: 2px 10px; border-radius: 12px; font-size: 0.8rem; }}
</style>
</head>
<body>
<h1>OneTruth Supply Chain Report</h1>
<p><span class="badge">Q3 2026</span> &nbsp; Generated by Team NeuroForge</p>

<h2>KPI Summary</h2>
<table>
  <tr><th>Metric</th><th>Value</th></tr>
  {kpi_table}
</table>

<h2>Monthly Delivery Trend</h2>
<table>
  <tr><th>Month</th><th>OTD Rate</th><th>Fill Rate</th></tr>
  {trend_rows}
</table>

<p class="footer">OneTruth — Governed Supply Chain Analytics | Built with Snowflake + Cortex Analyst</p>
</body>
</html>"""
    except Exception:
        html_report = "<html><body><p>Report generation failed.</p></body></html>"

    dl1, dl2, dl3 = st.columns(3)
    with dl1:
        st.download_button(
            label="Download CSV",
            data=csv_content,
            file_name="onetruth_report_q3_2026.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with dl2:
        st.download_button(
            label="Download PDF Report",
            data=html_report,
            file_name="onetruth_report_q3_2026.html",
            mime="text/html",
            use_container_width=True,
        )
    with dl3:
        st.caption("PDF: open the HTML file in your browser and print to PDF.")

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
        st.markdown("")
        st.markdown("")
        col_pad1, col_center, col_pad2 = st.columns([1, 2, 1])
        with col_center:
            st.markdown(
                f'<h2 style="text-align:center; color:{NAVY};">Welcome to OneTruth</h2>'
                f'<p style="text-align:center; color:#64748B;">Enter your name to get started</p>',
                unsafe_allow_html=True,
            )
            with st.form("name_gate", clear_on_submit=False):
                name_input = st.text_input(
                    "Your name", placeholder="e.g. Sunny Pathak",
                    label_visibility="collapsed",
                )
                submitted = st.form_submit_button("Continue", type="primary", use_container_width=True)
            if submitted and name_input.strip():
                st.session_state["user_name"] = name_input.strip()
                st.rerun()
            elif submitted:
                st.warning("Please enter your name.")

    # ── Logged in: show session picker or active chat ──
    else:
        ask_user = st.session_state["user_name"]

        # Session picker (no active chat)
        if not st.session_state.chat_history and st.session_state.session_title == "New Chat" and not st.session_state.get("_ask_ready"):
            st.markdown("")
            col_pad1, col_center, col_pad2 = st.columns([1, 2, 1])
            with col_center:
                st.markdown(
                    f'<h2 style="text-align:center; color:{NAVY};">Hi, {ask_user}</h2>'
                    f'<p style="text-align:center; color:#64748B;">What would you like to know about the supply chain?</p>',
                    unsafe_allow_html=True,
                )

                # Suggested prompts
                SUGGESTIONS = [
                    "What was our on-time delivery rate last quarter?",
                    "Show fill rate by carrier",
                    "Which customers have the lowest OTD?",
                    "What is our landed cost per unit for Q3?",
                ]
                sg_cols = st.columns(2)
                for idx, sug in enumerate(SUGGESTIONS):
                    with sg_cols[idx % 2]:
                        if st.button(sug, key=f"sug_{idx}", use_container_width=True):
                            st.session_state["_ask_ready"] = True
                            st.session_state["_prefill_question"] = sug
                            st.rerun()

                st.markdown("")
                if st.button("+ Start a new chat", type="primary", use_container_width=True):
                    st.session_state.chat_history = []
                    st.session_state.active_session_id = str(uuid.uuid4())
                    st.session_state.session_title = "New Chat"
                    st.session_state["_ask_ready"] = True
                    st.rerun()

            # Past sessions below
            try:
                df_past = list_sessions(conn, ask_user)
            except Exception:
                df_past = pd.DataFrame()

            if not df_past.empty:
                st.markdown("")
                st.markdown("**Recent conversations**")
                for _, srow in df_past.iterrows():
                    sid = srow["SESSION_ID"]
                    title = srow["TITLE"] or "Untitled"
                    col_resume, col_del = st.columns([8, 1])
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

        # ── Active chat session ──
        else:
            # Minimal top bar
            col_role, col_spacer, col_actions = st.columns([2, 3, 3])
            with col_role:
                persona = st.selectbox("Persona", list(ROLES.keys()), label_visibility="collapsed")
                role_name = ROLES[persona]
                use_role(conn, role_name)
            with col_actions:
                ac1, ac2, ac3, ac4 = st.columns(4)
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
                        st.toast(f"Shared! Link: ?session={st.session_state.active_session_id}")
                with ac2:
                    # Export chat
                    if st.session_state.chat_history:
                        chat_csv_rows = []
                        chat_html_msgs = ""
                        for turn in st.session_state.chat_history:
                            role = turn["role"]
                            msg = turn.get("display", "")
                            sql = turn.get("sql", "")
                            chat_csv_rows.append({"Role": role, "Message": msg, "SQL": sql})
                            label = "You" if role == "user" else "OneTruth"
                            color = "#0EA5E9" if role == "user" else "#059669"
                            chat_html_msgs += f'<div style="margin:12px 0;"><strong style="color:{color};">{label}</strong><p>{msg}</p>'
                            if sql:
                                chat_html_msgs += f'<pre style="background:#0F172A; color:#F8FAFC; padding:10px; border-radius:6px; font-size:0.85rem;">{sql}</pre>'
                            chat_html_msgs += "</div>"
                        df_chat_export = pd.DataFrame(chat_csv_rows)
                        chat_html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{st.session_state.session_title}</title>
<style>body{{font-family:-apple-system,sans-serif;margin:40px;color:#1E293B;}}
h1{{color:#0EA5E9;}} .badge{{background:#0EA5E9;color:white;padding:2px 10px;border-radius:12px;font-size:0.8rem;}}
.footer{{margin-top:40px;font-size:0.8rem;color:#94A3B8;text-align:center;}}</style></head>
<body><h1>OneTruth Chat Export</h1>
<p><span class="badge">{st.session_state.session_title}</span></p>
{chat_html_msgs}
<p class="footer">OneTruth — Team NeuroForge | Snowflake + Cortex Analyst</p>
</body></html>"""
                        dl_csv, dl_html = st.columns(2)
                        with dl_csv:
                            st.download_button(
                                label="CSV",
                                data=df_chat_export.to_csv(index=False),
                                file_name=f"chat_{st.session_state.session_title[:30]}.csv",
                                mime="text/csv",
                            )
                        with dl_html:
                            st.download_button(
                                label="PDF",
                                data=chat_html,
                                file_name=f"chat_{st.session_state.session_title[:30]}.html",
                                mime="text/html",
                            )
                with ac3:
                    if st.button("New"):
                        st.session_state.chat_history = []
                        st.session_state.active_session_id = str(uuid.uuid4())
                        st.session_state.session_title = "New Chat"
                        st.session_state["_ask_ready"] = True
                        st.query_params.clear()
                        st.rerun()
                with ac4:
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
            question = st.chat_input("Message OneTruth...")

            # Handle prefilled question from suggestion buttons
            if not question and st.session_state.get("_prefill_question"):
                question = st.session_state.pop("_prefill_question")

            if question:
                st.session_state.chat_history.append({
                    "role": "user",
                    "display": question,
                    "content": [{"type": "text", "text": question}],
                })
                with st.chat_message("user"):
                    st.markdown(question)

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
