import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import re
from datetime import datetime
from google.oauth2.service_account import Credentials
import gspread

st.set_page_config(page_title="Winston Quinn · Sales Dashboard", layout="wide", page_icon="🥃")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;700;900&family=DM+Sans:wght@300;400;500&display=swap');
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
.stApp { background: #0d0d0d; color: #f0ece4; }
.block-container { padding: 2rem 2.5rem; max-width: 1400px; }
h1,h2,h3 { font-family: 'Playfair Display', serif !important; color: #f0ece4 !important; }
.wq-title { font-family:'Playfair Display',serif; font-size:2.6rem; font-weight:900; color:#f0ece4; letter-spacing:-0.03em; line-height:1; }
.wq-sub { font-size:0.8rem; color:#8a7d6b; letter-spacing:0.2em; text-transform:uppercase; margin-bottom:2rem; }
.kpi-card { background:#161410; border:1px solid #2a2520; border-radius:4px; padding:1.4rem 1.6rem; position:relative; overflow:hidden; }
.kpi-card::before { content:''; position:absolute; top:0; left:0; width:3px; height:100%; background:#c9a84c; }
.kpi-label { font-size:0.68rem; color:#8a7d6b; letter-spacing:0.2em; text-transform:uppercase; margin-bottom:0.4rem; }
.kpi-value { font-family:'Playfair Display',serif; font-size:1.9rem; font-weight:700; color:#f0ece4; line-height:1; }
.kpi-delta { font-size:0.76rem; color:#8a7d6b; margin-top:0.35rem; }
.kpi-delta.up { color:#7eb87e; }
.kpi-delta.down { color:#c07070; }
.section-rule { border:none; border-top:1px solid #2a2520; margin:1.8rem 0 1.4rem; }
[data-testid="stSidebar"] { background:#0a0a0a !important; border-right:1px solid #1e1a14; }
.stTabs [data-baseweb="tab-list"] { background:transparent; border-bottom:1px solid #2a2520; gap:0; }
.stTabs [data-baseweb="tab"] { font-size:0.76rem; letter-spacing:0.12em; text-transform:uppercase; color:#5a5045 !important; padding:0.7rem 1.4rem; border-radius:0; background:transparent !important; }
.stTabs [aria-selected="true"] { color:#c9a84c !important; border-bottom:2px solid #c9a84c !important; }
</style>
""", unsafe_allow_html=True)

# ── Login ─────────────────────────────────────────────────────────────────────
def check_login():
    if st.session_state.get("authenticated"):
        return True
    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown("""
        <div style='background:#161410;border:1px solid #2a2520;border-radius:6px;
                    padding:2.5rem 2.5rem 2rem;position:relative;overflow:hidden'>
          <div style='position:absolute;top:0;left:0;width:3px;height:100%;background:#c9a84c'></div>
          <div style='font-family:Playfair Display,serif;font-size:1.8rem;font-weight:900;
                      color:#f0ece4;margin-bottom:0.2rem'>Winston Quinn</div>
          <div style='font-size:0.7rem;color:#8a7d6b;letter-spacing:0.2em;
                      text-transform:uppercase;margin-bottom:0.3rem'>Sales Dashboard</div>
        </div>
        """, unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Sign In", use_container_width=True)
            if submitted:
                if (username == st.secrets["auth"]["username"] and
                        password == st.secrets["auth"]["password"]):
                    st.session_state["authenticated"] = True
                    st.rerun()
                else:
                    st.error("Incorrect username or password.")
    return False

if not check_login():
    st.stop()

# ── Constants ─────────────────────────────────────────────────────────────────
SPREADSHEET_ID = "1arHaLL7g4Z6Ikf6oY1WC1ad9yIBEFSjY17Eg428__js"
REPS = ["Max", "Luke", "James", "WQ", "Winston Quinn", "Tristan", "Erica"]
GOLD, GREEN, RED = "#c9a84c", "#7eb87e", "#c07070"

PLOT_BASE = dict(
    plot_bgcolor="#161410", paper_bgcolor="#161410",
    font=dict(family="DM Sans", color="#a09080"),
    margin=dict(l=10, r=10, t=40, b=10),
    title_font=dict(family="Playfair Display", color="#f0ece4", size=15),
    xaxis=dict(gridcolor="#1e1a14", linecolor="#2a2520"),
    yaxis=dict(gridcolor="#1e1a14", linecolor="#2a2520"),
    colorway=[GOLD, GREEN, "#7ea8be", "#be7e9a", "#be9a7e", "#9a7ebe"],
)

def apply_layout(fig, horizontal_legend=False, **kwargs):
    fig.update_layout(**PLOT_BASE)
    if horizontal_legend:
        fig.update_layout(legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color="#a09080"), orientation="h", y=-0.22))
    else:
        fig.update_layout(legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color="#a09080")))
    if kwargs:
        fig.update_layout(**kwargs)
    return fig

# ── Google Sheets connection ───────────────────────────────────────────────────
@st.cache_resource
def get_gspread_client():
    creds = Credentials.from_service_account_info(
        dict(st.secrets["gcp_service_account"]),
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly",
                "https://www.googleapis.com/auth/drive.readonly"],
    )
    return gspread.authorize(creds)

@st.cache_data(ttl=300)
def load_all_sheets_at_once():
    """Fetch all sheet data in one batch to stay within API quota."""
    import time
    client = get_gspread_client()
    ss = client.open_by_key(SPREADSHEET_ID)
    all_worksheets = ss.worksheets()
    # Sheet 0 = Database, Sheet 1 = Duplicator, Sheet 2+ = Fortnights
    fortnight_worksheets = all_worksheets[2:]
    results = {}
    for i, ws in enumerate(fortnight_worksheets):
        if i > 0:
            time.sleep(1.2)  # stay well under 60 reads/min
        results[ws.title] = ws.get_all_values()
    return results

# ── Parser ────────────────────────────────────────────────────────────────────
def to_num(s):
    if not s: return 0.0
    try:
        cleaned = re.sub(r'[$,\s]', '', str(s))
        return float(cleaned) if cleaned else 0.0
    except (ValueError, TypeError):
        return 0.0

def parse_rows(rows, label=""):
    records = []
    date_range = label
    current_rep = None
    rep_pattern = re.compile(r'^(' + '|'.join(REPS) + r')\s*(Accounts?)?[:\s]', re.IGNORECASE)
    for cols in rows:
        if not cols: continue
        first = str(cols[0]).strip()
        # Grab date range
        if not date_range or date_range == label:
            m = re.search(r'\d{2}[/\.]\d{2}[/\.]\d{2,4}.*\d{2}[/\.]\d{2}[/\.]\d{2,4}', first)
            if m:
                date_range = first.replace(' SALES','').strip()
        # Detect rep header
        rm = rep_pattern.match(first)
        if rm:
            rep_name = rm.group(1).strip()
            if rep_name.lower() in ('wq','winston quinn'): rep_name = 'WQ'
            current_rep = rep_name
            continue
        if current_rep is None: continue
        if not first or first.lower() in ('product','customer name'): continue
        if any(x in first.upper() for x in ('ACCOUNT CORRECTION','FROM ','NOTE ')): continue
        total_raw = cols[6] if len(cols) > 6 else ''
        total = to_num(total_raw)
        if total == 0: continue
        product     = str(cols[1]).strip() if len(cols) > 1 else ''
        bottles_raw = str(cols[2]).strip() if len(cols) > 2 else '0'
        price_raw   = str(cols[5]).strip() if len(cols) > 5 else '0'
        comm_raw    = str(cols[8]).strip() if len(cols) > 8 else '0'
        records.append({
            'rep': current_rep, 'customer': first, 'product': product,
            'bottles': int(bottles_raw) if bottles_raw.isdigit() else 0,
            'price': to_num(price_raw), 'total': total, 'commission': to_num(comm_raw),
        })
    return pd.DataFrame(records), date_range

def extract_date(s):
    if not s: return None
    parts = re.findall(r'\d{2}/\d{2}/(?:\d{4}|\d{2})', s)
    for p in parts:
        for f in ('%d/%m/%Y','%d/%m/%y'):
            try: return datetime.strptime(p, f)
            except: pass
    return None

def fmt(v): return f"${v:,.2f}"

# ── Load all sheets ───────────────────────────────────────────────────────────
with st.spinner("Loading data from Google Sheets…"):
    try:
        all_sheets_data = load_all_sheets_at_once()
    except Exception as e:
        st.error(f"Could not connect to Google Sheets: {e}")
        st.stop()

all_fortnights = []
for name, rows in all_sheets_data.items():
    df, dr = parse_rows(rows, name)
    if not df.empty:
        all_fortnights.append({'label': dr or name, 'sheet': name, 'df': df, 'date': extract_date(dr or name)})

all_fortnights.sort(key=lambda x: x['date'] or datetime.min)

if not all_fortnights:
    st.warning("No fortnight data found in the spreadsheet yet.")
    st.stop()

fn_labels = [f['label'] for f in all_fortnights]

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("<div style='padding:1rem 0 1.6rem'><div style='font-family:Playfair Display,serif;font-size:1.25rem;color:#f0ece4;font-weight:700'>Winston Quinn</div><div style='font-size:0.65rem;color:#5a5045;letter-spacing:0.2em;text-transform:uppercase;margin-top:0.2rem'>Sales Dashboard</div></div>", unsafe_allow_html=True)
    current_label = st.selectbox("Current Fortnight", fn_labels, index=len(fn_labels)-1)
    compare_label = st.selectbox("Compare Against",   fn_labels, index=max(0, len(fn_labels)-2))
    st.markdown("<hr style='border-color:#1e1a14;margin:1rem 0'>", unsafe_allow_html=True)
    rep_filter = st.selectbox("Filter by Rep", ["All Reps","Max","Luke","James","WQ","Tristan","Erica"])
    st.markdown("<hr style='border-color:#1e1a14;margin:1rem 0'>", unsafe_allow_html=True)
    if st.button("⟳  Refresh Data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.markdown("<div style='font-size:0.65rem;color:#3a3530;margin-top:0.5rem'>Live from Google Sheets · refreshes every 5 min</div>", unsafe_allow_html=True)

curr_fn = next(f for f in all_fortnights if f['label']==current_label)
prev_fn = next(f for f in all_fortnights if f['label']==compare_label)
curr_df = curr_fn['df'].copy()
prev_df = prev_fn['df'].copy()
if rep_filter != "All Reps":
    curr_df = curr_df[curr_df['rep']==rep_filter]
    prev_df = prev_df[prev_df['rep']==rep_filter]

# ── Header + KPIs ─────────────────────────────────────────────────────────────
st.markdown('<div class="wq-title">Sales Dashboard</div>', unsafe_allow_html=True)
st.markdown(f'<div class="wq-sub">Winston Quinn Gin &nbsp;·&nbsp; {current_label}</div>', unsafe_allow_html=True)

curr_sales   = curr_df['total'].sum()
curr_comm    = curr_df['commission'].sum()
curr_bottles = curr_df['bottles'].sum()
prev_sales   = prev_df['total'].sum()
pct          = ((curr_sales - prev_sales) / prev_sales * 100) if prev_sales else 0
comm_rate    = (curr_comm / curr_sales * 100) if curr_sales else 0
arrow        = "↑" if pct >= 0 else "↓"
dcls         = "up" if pct >= 0 else "down"

k1,k2,k3,k4 = st.columns(4)
for col,lbl,val,sub,cls in [
    (k1,"Fortnight Sales",  fmt(curr_sales),    f"{arrow} {abs(pct):.1f}% vs {compare_label}", dcls),
    (k2,"Total Commission", fmt(curr_comm),     f"{comm_rate:.1f}% commission rate", ""),
    (k3,"Bottles Sold",     f"{curr_bottles:,}","This fortnight", ""),
    (k4,"Active Accounts",  str(curr_df['customer'].nunique()), f"{curr_df['rep'].nunique()} reps active", ""),
]:
    col.markdown(f"""<div class="kpi-card"><div class="kpi-label">{lbl}</div>
    <div class="kpi-value">{val}</div><div class="kpi-delta {cls}">{sub}</div></div>""", unsafe_allow_html=True)

st.markdown("<div class='section-rule'></div>", unsafe_allow_html=True)

tab1,tab2,tab3,tab4 = st.tabs(["📅  Monthly Sales","🍕  Sales by Customer","📈  Fortnight Comparison","💼  Current Fortnight"])

# ── Tab 1: Monthly ────────────────────────────────────────────────────────────
with tab1:
    rows = []
    for fn in all_fortnights:
        df = fn['df'].copy()
        if rep_filter != "All Reps": df = df[df['rep']==rep_filter]
        if fn['date']:
            df['date'] = fn['date']
            rows.append(df)
    if not rows:
        st.info("No dated data.")
    else:
        adf = pd.concat(rows, ignore_index=True)
        adf['month'] = adf['date'].dt.to_period('M').dt.to_timestamp()
        mon = adf.groupby('month').agg(Sales=('total','sum'), Commission=('commission','sum')).reset_index()
        mon['Month'] = mon['month'].dt.strftime('%b %Y')
        fig = go.Figure()
        fig.add_bar(x=mon['Month'], y=mon['Sales'], name='Sales', marker_color=GOLD, marker_line_width=0)
        fig.add_bar(x=mon['Month'], y=mon['Commission'], name='Commission', marker_color='#4a7c59', marker_line_width=0)
        apply_layout(fig, horizontal_legend=True, title='Sales & Commission by Month',
                     barmode='group', yaxis_tickprefix='$', xaxis_tickangle=-30, height=400)
        st.plotly_chart(fig, use_container_width=True)

        st.markdown("#### Sales by SKU (all time)")
        sku = adf.groupby('product', as_index=False)['total'].sum().sort_values('total', ascending=True)
        fig2 = px.bar(sku, x='total', y='product', orientation='h', color='total',
                      color_continuous_scale=['#2a2520',GOLD], labels={'total':'Sales ($)','product':''})
        apply_layout(fig2, height=max(280, len(sku)*30), coloraxis_showscale=False, title='')
        st.plotly_chart(fig2, use_container_width=True)

# ── Tab 2: By Customer ────────────────────────────────────────────────────────
with tab2:
    cust = curr_df.groupby('customer', as_index=False)['total'].sum().sort_values('total', ascending=False)
    tc = cust['total'].sum()
    cust['pct'] = cust['total'] / tc if tc else 0
    major = cust[cust['pct'] >= 0.02].copy()
    ms = cust[cust['pct'] < 0.02]['total'].sum()
    if ms > 0:
        major = pd.concat([major, pd.DataFrame([{'customer':'Other','total':ms,'pct':ms/tc}])], ignore_index=True)
    cl,cr = st.columns(2)
    with cl:
        fig3 = px.pie(major, names='customer', values='total', hole=0.48,
                      color_discrete_sequence=[GOLD,'#a07838','#7ea8be',GREEN,'#be7e9a','#9a7ebe','#be9a7e','#5a8a7e'])
        fig3.update_traces(textposition='outside', textinfo='percent+label', textfont_size=10)
        apply_layout(fig3, title=f'Sales by Customer — {current_label}', showlegend=False, height=450)
        st.plotly_chart(fig3, use_container_width=True)
    with cr:
        top = cust.sort_values('total', ascending=True).tail(20)
        fig4 = px.bar(top, x='total', y='customer', orientation='h', color='total',
                      color_continuous_scale=['#2a2520',GOLD], labels={'total':'Sales ($)','customer':''})
        apply_layout(fig4, title='Top Customers', coloraxis_showscale=False, height=450)
        st.plotly_chart(fig4, use_container_width=True)
    with st.expander("Full customer table"):
        t = cust[['customer','total','pct']].copy()
        t.columns = ['Customer','Sales','% Share']
        t['Sales'] = t['Sales'].map(fmt)
        t['% Share'] = t['% Share'].map(lambda x: f"{x*100:.1f}%")
        st.dataframe(t, use_container_width=True, hide_index=True)

# ── Tab 3: Fortnight Comparison ───────────────────────────────────────────────
with tab3:
    sr = []
    for fn in all_fortnights:
        df = fn['df'].copy()
        if rep_filter != "All Reps": df = df[df['rep']==rep_filter]
        sr.append({'Fortnight':fn['label'], 'Sales':df['total'].sum(),
                   'Commission':df['commission'].sum(), 'Bottles':df['bottles'].sum(),
                   'Accounts':df['customer'].nunique()})
    smry = pd.DataFrame(sr)
    smry['% Change'] = smry['Sales'].pct_change() * 100
    fig5 = go.Figure()
    fig5.add_bar(x=smry['Fortnight'], y=smry['Sales'], name='Sales',
                 marker_color=GOLD, marker_line_width=0, yaxis='y')
    fig5.add_scatter(x=smry['Fortnight'], y=smry['% Change'], name='% Change',
                     mode='lines+markers', line=dict(color=GREEN, width=2),
                     marker=dict(size=7, color=GREEN), yaxis='y2')
    fig5.update_layout(**PLOT_BASE)
    fig5.update_layout(
        title='Sales & Period-on-Period % Change', xaxis_tickangle=-30, height=400,
        yaxis=dict(title='Sales ($)', tickprefix='$', gridcolor='#1e1a14', linecolor='#2a2520'),
        yaxis2=dict(title='% Change', overlaying='y', side='right',
                    ticksuffix='%', zeroline=True, zerolinecolor='#2a2520'),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color="#a09080"), orientation="h", y=-0.22),
    )
    st.plotly_chart(fig5, use_container_width=True)

    cr2 = smry[smry['Fortnight']==current_label].iloc[0]
    pr2 = smry[smry['Fortnight']==compare_label].iloc[0]
    ds = cr2['Sales'] - pr2['Sales']
    dp = (ds / pr2['Sales'] * 100) if pr2['Sales'] else 0
    dc = cr2['Commission'] - pr2['Commission']
    db = cr2['Bottles'] - pr2['Bottles']
    st.markdown(f"<div class='section-rule'></div><h4 style='color:#f0ece4'>{current_label} vs {compare_label}</h4>", unsafe_allow_html=True)
    dc1,dc2,dc3 = st.columns(3)
    for col,lbl,val,sub,cls in [
        (dc1,"Sales Δ",      fmt(abs(ds)),       f"{'↑' if ds>=0 else '↓'} {abs(dp):.1f}%",  "up" if ds>=0 else "down"),
        (dc2,"Commission Δ", fmt(abs(dc)),        f"{'↑' if dc>=0 else '↓'} vs prior period", "up" if dc>=0 else "down"),
        (dc3,"Bottles Δ",    f"{abs(int(db)):,}", f"{'↑' if db>=0 else '↓'} bottles",         "up" if db>=0 else "down"),
    ]:
        col.markdown(f"""<div class="kpi-card"><div class="kpi-label">{lbl}</div>
        <div class="kpi-value">{val}</div><div class="kpi-delta {cls}">{sub}</div></div>""", unsafe_allow_html=True)
    st.markdown("<div class='section-rule'></div>", unsafe_allow_html=True)
    t2 = smry.copy()
    t2['Sales'] = t2['Sales'].map(fmt)
    t2['Commission'] = t2['Commission'].map(fmt)
    t2['% Change'] = t2['% Change'].map(lambda x: f"{x:+.1f}%" if pd.notna(x) else "—")
    st.dataframe(t2, use_container_width=True, hide_index=True)

# ── Tab 4: Current Fortnight ──────────────────────────────────────────────────
with tab4:
    st.markdown(f"<h4 style='color:#f0ece4'>{current_label}</h4>", unsafe_allow_html=True)
    rs = curr_df.groupby('rep').agg(
        Sales=('total','sum'), Commission=('commission','sum'),
        Bottles=('bottles','sum'), Accounts=('customer','nunique')
    ).reset_index().sort_values('Sales', ascending=False)
    rcols = st.columns(min(len(rs), 5))
    for i,(_,row) in enumerate(rs.iterrows()):
        rate = (row['Commission'] / row['Sales'] * 100) if row['Sales'] else 0
        with rcols[i % 5]:
            st.markdown(f"""<div class="kpi-card" style="text-align:center;padding:1rem">
            <div style="font-family:Playfair Display,serif;font-size:1rem;color:{GOLD};margin-bottom:0.5rem">{row['rep']}</div>
            <div class="kpi-label">Sales</div>
            <div style="font-size:1.25rem;font-family:Playfair Display,serif;color:#f0ece4">{fmt(row['Sales'])}</div>
            <div class="kpi-delta">{fmt(row['Commission'])} comm · {rate:.1f}%</div>
            <div class="kpi-delta" style="margin-top:0.15rem">{int(row['Bottles'])} btl · {int(row['Accounts'])} accts</div>
            </div>""", unsafe_allow_html=True)
    st.markdown("<div class='section-rule'></div>", unsafe_allow_html=True)
    cl2,cr2 = st.columns(2)
    with cl2:
        fig6 = px.bar(rs.sort_values('Sales'), x='Sales', y='rep', orientation='h', color='rep',
                      color_discrete_sequence=[GOLD,GREEN,'#7ea8be','#be7e9a','#be9a7e'],
                      labels={'rep':'','Sales':'Sales ($)'})
        apply_layout(fig6, title='Sales by Rep', height=260, showlegend=False)
        st.plotly_chart(fig6, use_container_width=True)
    with cr2:
        prod = curr_df.groupby('product', as_index=False)['total'].sum().sort_values('total', ascending=True)
        fig7 = px.bar(prod, x='total', y='product', orientation='h', color='total',
                      color_continuous_scale=['#2a2520',GOLD], labels={'product':'','total':'Sales ($)'})
        apply_layout(fig7, title='Sales by SKU', coloraxis_showscale=False, height=260)
        st.plotly_chart(fig7, use_container_width=True)
    st.markdown("<div class='section-rule'></div>", unsafe_allow_html=True)
    st.markdown("#### Line Detail")
    det = curr_df[['rep','customer','product','bottles','price','total','commission']].copy()
    det.columns = ['Rep','Customer','SKU','Bottles','Price','Total','Commission']
    det['Price'] = det['Price'].map(lambda x: fmt(x) if x else '—')
    det['Total'] = det['Total'].map(fmt)
    det['Commission'] = det['Commission'].map(fmt)
    det = det.sort_values(['Rep','Total'], ascending=[True,False])
    st.dataframe(det, use_container_width=True, hide_index=True)
