"""
Partner Lookup Dashboard
========================
Streamlit app to look up a partner by ID and see:
  1. Shifts sent — split into past and future, accepted highlighted green
  2. Active bonuses — opted-in highlighted green, not opted in yellow
  3. Shift assignments — list + calendar view

Run: streamlit run partner_dashboard.py
"""

import streamlit as st
import pandas as pd
from google.cloud import bigquery
from google.auth.exceptions import RefreshError
from datetime import date, timedelta
import calendar
import subprocess

st.set_page_config(
    page_title="Partner Lookup",
    page_icon="👤",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS for dark-mode polish ──
st.markdown("""
<style>
    /* Tighten up metric cards */
    [data-testid="stMetric"] {
        background-color: #1A1F2B;
        border: 1px solid #2A3040;
        border-radius: 8px;
        padding: 12px 16px;
    }
    [data-testid="stMetricLabel"] {
        font-size: 0.75rem;
        color: #8899AA;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    [data-testid="stMetricValue"] {
        font-size: 1.25rem;
        font-weight: 600;
    }

    /* Section spacing */
    .block-container { padding-top: 2rem; }
    [data-testid="stVerticalBlock"] > div:has(> [data-testid="stMetric"]) {
        gap: 0.5rem;
    }

    /* Sidebar styling */
    [data-testid="stSidebar"] {
        background-color: #141820;
    }
    [data-testid="stSidebar"] hr { margin: 1rem 0; }

    /* Tab styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 6px 6px 0 0;
        padding: 8px 20px;
    }

    /* Divider spacing */
    hr { margin: 1.5rem 0 !important; }

    /* Contact info row */
    .contact-row {
        display: flex;
        gap: 24px;
        padding: 8px 0;
        color: #B0BEC5;
        font-size: 0.9rem;
    }
    .contact-row span { color: #E0E0E0; }

    /* Legend pills */
    .legend {
        display: flex;
        gap: 12px;
        margin-bottom: 8px;
        font-size: 0.8rem;
    }
    .legend-item {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 2px 10px;
        border-radius: 12px;
        font-weight: 500;
    }
    .legend-green { background: #1a3a2a; color: #a3d9b1; }
    .legend-red { background: #3a1a1a; color: #d9a3a3; }
    .legend-yellow { background: #3a3520; color: #d9cfa3; }
    .legend-blue { background: #1a2a3a; color: #a3c4d9; }
</style>
""", unsafe_allow_html=True)

# ── BQ client ──
@st.cache_resource
def get_client():
    return bigquery.Client(project="shiftsmart-api")

def run_query(sql):
    try:
        client = get_client()
        return client.query(sql).to_dataframe()
    except RefreshError:
        st.cache_resource.clear()
        st.session_state["auth_needed"] = True
        return pd.DataFrame()

# ── Auth check ──
if st.session_state.get("auth_needed"):
    st.error("Google Cloud authentication expired.")
    st.markdown("Click below to re-authenticate, then **refresh this page** once the browser flow completes.")
    if st.button("Re-authenticate with Google"):
        with st.spinner("Launching browser for Google auth..."):
            result = subprocess.Popen(
                ["gcloud", "auth", "application-default", "login"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            st.info("A browser window should have opened. Complete the login, then click the button below.")
    if st.button("I've completed login — refresh"):
        st.session_state["auth_needed"] = False
        st.cache_resource.clear()
        st.rerun()
    st.stop()

# ── Company UUID mapping (for usershifts table) ──
COMPANY_UUIDS = {
    "da532ea5-9fed-46cf-a5cc-6dd7721411b6": "Circle K - Premium",
    "26983819-c423-4f57-90dc-f62c018d1eb6": "PepsiCo Beverages",
    "a9eb903d-3493-43f7-a180-be8eda4a9668": "PepsiCo Foods",
    "14824b29-7224-48a1-9d30-a62d1b8ed614": "Dollar General",
}

# ── Row highlighting helpers (dark-mode friendly) ──
GREEN = "background-color: #1a3a2a; color: #a3d9b1"
RED = "background-color: #3a1a1a; color: #d9a3a3"
YELLOW = "background-color: #3a3520; color: #d9cfa3"

def highlight_accepted_shifts(row):
    status = str(row.get("status", "")).lower()
    assigned = str(row.get("assigned_at", ""))
    if status in ("assigned", "completed", "accepted") or (assigned not in ("", "None", "nan", "NaT")):
        return [GREEN] * len(row)
    elif status in ("canceled", "declined"):
        return [RED] * len(row)
    return [""] * len(row)

def highlight_bonuses(row):
    completed = row.get("status", "")
    opted = row.get("opted_in", "")
    if completed == "Complete":
        return [GREEN] * len(row)
    elif opted == "Yes":
        return [GREEN] * len(row)
    elif opted == "No":
        return [YELLOW] * len(row)
    return [""] * len(row)

# ── Sidebar ──
with st.sidebar:
    st.markdown("## Partner Lookup")
    st.caption("Enter a partner ID to view their shifts, bonuses, and assignments.")
    partner_id = st.text_input("Partner ID", value="", placeholder="e.g. dcdc0d40-7351-416d-...")
    st.divider()
    st.markdown("##### Date Range")
    days_back = st.slider("History (days back)", 7, 365, 90)
    days_forward = st.slider("Future (days forward)", 7, 90, 30)
    st.divider()
    st.caption(f"Showing: {(date.today() - timedelta(days=days_back)).strftime('%b %d')} → {(date.today() + timedelta(days=days_forward)).strftime('%b %d, %Y')}")

if not partner_id:
    st.markdown("## Partner Dashboard")
    st.info("Enter a Partner ID in the sidebar to get started.")
    st.stop()

start_date = date.today() - timedelta(days=days_back)
end_date = date.today() + timedelta(days=days_forward)

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1: Partner Info
# ══════════════════════════════════════════════════════════════════════════════
partner_info_sql = f"""
SELECT
  partner_id, first_name, last_name, email, phone_number,
  company_name, msa, op_date, last_active_at,
  total_shifts_last_4w, weeks_worked_last_4w
FROM `growth.int_master_partner_throughput`
WHERE partner_id = '{partner_id}'
"""
partner_info = run_query(partner_info_sql)

# Background check status
bgc_sql = f"""
SELECT status, result, CAST(updatedAt AS STRING) AS updated_at
FROM `shiftsmart_data.bq_background_checks`
WHERE userId = '{partner_id}'
QUALIFY ROW_NUMBER() OVER (ORDER BY updatedAt DESC) = 1
"""
bgc_info = run_query(bgc_sql)

if partner_info.empty:
    st.markdown("## Partner Dashboard")
    st.warning(f"Partner `{partner_id}` not found.")
    st.stop()

row = partner_info.iloc[0]
first = row.get("first_name", "")
last = row.get("last_name", "")
company = row.get("company_name", "N/A")

# Title with partner name
st.markdown(f"## {first} {last}")
st.caption(f"`{partner_id}`")

# Contact info row
email = row.get("email", "")
phone = row.get("phone_number", "")
msa = row.get("msa", "")
contact_parts = []
if phone: contact_parts.append(f"Phone: **{phone}**")
if email: contact_parts.append(f"Email: **{email}**")
if msa: contact_parts.append(f"MSA: **{msa}**")
if contact_parts:
    st.markdown(" · ".join(contact_parts))

st.markdown("")

# Metric cards
cols = st.columns(5)
cols[0].metric("Company", company)
cols[1].metric("Last Active", str(row.get("last_active_at", "N/A"))[:10])
op_date = row.get("op_date")
cols[2].metric("OP Date", str(op_date)[:10] if pd.notna(op_date) else "Not oriented")

shifts_4w = row.get("total_shifts_last_4w", 0)
weeks_4w = row.get("weeks_worked_last_4w", 0)
cols[3].metric("Shifts (4 wk)", int(shifts_4w) if pd.notna(shifts_4w) else 0,
               delta=f"{int(weeks_4w)} weeks active" if pd.notna(weeks_4w) and weeks_4w > 0 else None)

if bgc_info.empty:
    cols[4].metric("Background Check", "No Record")
else:
    bgc_row = bgc_info.iloc[0]
    bgc_result = str(bgc_row.get("result", "")).strip()
    bgc_status = str(bgc_row.get("status", "")).strip()
    if bgc_result == "clear":
        cols[4].metric("Background Check", "Clear", delta="Passed", delta_color="normal")
    elif bgc_result == "consider":
        cols[4].metric("Background Check", "Consider", delta="Review needed", delta_color="inverse")
    elif bgc_result == "pending":
        cols[4].metric("Background Check", "Pending", delta=bgc_status)
    else:
        cols[4].metric("Background Check", bgc_status or "Unknown")

if len(partner_info) > 1:
    with st.expander(f"Active in {len(partner_info)} companies", expanded=False):
        st.dataframe(
            partner_info[["company_name", "op_date", "last_active_at", "total_shifts_last_4w"]],
            use_container_width=True, hide_index=True
        )

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2: Shifts Sent (bq_usershifts_deduped) — Past + Future
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("### Shifts Sent")
st.markdown("""<div class="legend">
    <span class="legend-item legend-green">Accepted / Assigned</span>
    <span class="legend-item legend-red">Canceled / Declined</span>
</div>""", unsafe_allow_html=True)

sent_sql = f"""
SELECT
  company,
  title,
  status,
  CAST(start AS STRING) AS shift_start,
  CAST(`end` AS STRING) AS shift_end,
  duration,
  rate,
  CAST(sent_at AS STRING) AS sent_at,
  CAST(seen_at AS STRING) AS seen_at,
  CAST(assigned_at AS STRING) AS assigned_at,
  CAST(confirmed_at AS STRING) AS confirmed_at,
  CAST(completed_at AS STRING) AS completed_at,
  CAST(canceled_at AS STRING) AS canceled_at,
  CAST(declined_at AS STRING) AS declined_at
FROM `shiftsmart_data.bq_usershifts_deduped`
WHERE
  user = '{partner_id}'
  AND start >= CAST('{start_date}' AS DATETIME)
  AND start < CAST('{end_date}' AS DATETIME)
ORDER BY start
"""

with st.spinner("Loading shifts..."):
    sent_shifts = run_query(sent_sql)

if sent_shifts.empty:
    st.info("No shifts sent to this partner in this date range.")
else:
    # Map company UUIDs
    sent_shifts["company_name"] = sent_shifts["company"].map(COMPANY_UUIDS).fillna(sent_shifts["company"].str[:8] + "...")

    # Default filter: Sent, Accepted, Assigned, Completed
    default_statuses = ["Sent", "Accepted", "Assigned", "Completed"]
    all_statuses = sorted(sent_shifts["status"].unique().tolist())
    default_selection = [s for s in default_statuses if s in all_statuses]

    selected_statuses = st.multiselect(
        "Filter by status",
        options=all_statuses,
        default=default_selection,
        key="sent_status"
    )
    if selected_statuses:
        filtered_sent = sent_shifts[sent_shifts["status"].isin(selected_statuses)]
    else:
        filtered_sent = sent_shifts.copy()

    # Summary metrics
    mcols = st.columns(5)
    mcols[0].metric("Total Shown", len(filtered_sent))
    mcols[1].metric("Accepted/Assigned", len(filtered_sent[
        filtered_sent["status"].isin(["Assigned", "Accepted", "Completed"])
        | (filtered_sent["assigned_at"].notna() & (filtered_sent["assigned_at"] != "None"))
    ]))
    mcols[2].metric("Seen", len(filtered_sent[filtered_sent["seen_at"].notna() & (filtered_sent["seen_at"] != "None")]))
    mcols[3].metric("Completed", len(filtered_sent[filtered_sent["completed_at"].notna() & (filtered_sent["completed_at"] != "None")]))
    mcols[4].metric("Declined/Canceled", len(filtered_sent[
        filtered_sent["status"].isin(["Canceled", "Declined"])
    ]))

    display_cols = ["company_name", "title", "status", "shift_start",
                    "rate", "sent_at", "seen_at", "assigned_at",
                    "confirmed_at", "completed_at", "canceled_at", "declined_at"]

    # Split into past and future based on shift_start
    filtered_sent["_start_dt"] = pd.to_datetime(filtered_sent["shift_start"], errors="coerce")
    now = pd.Timestamp.now()

    past_shifts = filtered_sent[filtered_sent["_start_dt"] < now].sort_values("_start_dt", ascending=False)
    future_shifts = filtered_sent[filtered_sent["_start_dt"] >= now].sort_values("_start_dt", ascending=True)

    tab_future, tab_past = st.tabs([
        f"Upcoming ({len(future_shifts)})",
        f"Past ({len(past_shifts)})"
    ])

    with tab_future:
        if future_shifts.empty:
            st.info("No upcoming shifts.")
        else:
            styled = future_shifts[display_cols].style.apply(highlight_accepted_shifts, axis=1)
            st.dataframe(styled, use_container_width=True, hide_index=True)

    with tab_past:
        if past_shifts.empty:
            st.info("No past shifts in this date range.")
        else:
            styled = past_shifts[display_cols].style.apply(highlight_accepted_shifts, axis=1)
            st.dataframe(styled, use_container_width=True, hide_index=True)

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3: Bonuses
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("### Bonuses")
st.markdown("""<div class="legend">
    <span class="legend-item legend-green">Opted In / Complete</span>
    <span class="legend-item legend-yellow">Eligible — Not Opted In</span>
</div>""", unsafe_allow_html=True)

bonus_sql = f"""
WITH partner_bonuses AS (
  SELECT DISTINCT eu.uuid AS bonus_id
  FROM `shiftsmart_data.bq_payment_bonus_eligible_users` eu
  WHERE eu.user_id = '{partner_id}'
),

bonus_info AS (
  SELECT DISTINCT
    bp.paymentBonusId,
    bp.title AS bonus_name,
    bp.bonusType AS bonus_type,
    bp.amount,
    bp.count AS shifts_required,
    CAST(bp.validFrom AS STRING) AS valid_from,
    CAST(bp.validTo AS STRING) AS valid_to,
    bp.companies AS company_uuids,
    bp.daysToComplete AS days_to_complete
  FROM `shiftsmart_data.bq_payment_bonus_progress` bp
  WHERE bp.paymentBonusId IN (SELECT bonus_id FROM partner_bonuses)
  QUALIFY ROW_NUMBER() OVER (PARTITION BY bp.paymentBonusId ORDER BY bp.updatedAt DESC) = 1
),

partner_progress AS (
  SELECT
    bp.paymentBonusId,
    bp.countProgress AS shifts_completed,
    bp.isComplete AS completed,
    bp.isViewedByWorker AS viewed_by_partner
  FROM `shiftsmart_data.bq_payment_bonus_progress` bp
  WHERE bp.paymentBonusId IN (SELECT bonus_id FROM partner_bonuses)
    AND bp.userId = '{partner_id}'
)

SELECT
  bi.bonus_name,
  bi.bonus_type,
  bi.amount,
  bi.shifts_required,
  IFNULL(pp.shifts_completed, 0) AS shifts_completed,
  IFNULL(pp.completed, false) AS completed,
  pp.viewed_by_partner,
  bi.valid_from,
  bi.valid_to,
  bi.company_uuids,
  bi.days_to_complete
FROM bonus_info bi
LEFT JOIN partner_progress pp
  ON bi.paymentBonusId = pp.paymentBonusId
ORDER BY bi.valid_from DESC
"""

with st.spinner("Loading bonuses..."):
    bonuses = run_query(bonus_sql)

if bonuses.empty:
    st.info("No bonuses found for this partner.")
else:
    def map_companies(uuid_list):
        if uuid_list is None:
            return "N/A"
        return ", ".join([COMPANY_UUIDS.get(u, u[:8] + "...") for u in uuid_list])

    bonuses["companies"] = bonuses["company_uuids"].apply(map_companies)
    bonuses["progress"] = bonuses.apply(
        lambda r: f"{r['shifts_completed'] or 0}/{r['shifts_required'] or '?'}", axis=1
    )
    bonuses["opted_in"] = bonuses["viewed_by_partner"].apply(
        lambda v: "Yes" if v is True else ("No" if v is False else "No")
    )
    bonuses["status"] = bonuses["completed"].apply(
        lambda v: "Complete" if v else "In Progress"
    )

    # Summary metrics
    bcols = st.columns(4)
    bcols[0].metric("Total Bonuses", len(bonuses))
    bcols[1].metric("Opted In", len(bonuses[bonuses["opted_in"] == "Yes"]))
    bcols[2].metric("Not Opted In", len(bonuses[bonuses["opted_in"] == "No"]))
    bcols[3].metric("Completed", len(bonuses[bonuses["status"] == "Complete"]))

    display_cols = ["bonus_name", "bonus_type", "amount", "progress", "status",
                    "opted_in", "valid_from", "valid_to", "companies"]
    styled_bonuses = bonuses[display_cols].style.apply(highlight_bonuses, axis=1)
    st.dataframe(styled_bonuses, use_container_width=True, hide_index=True)

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4: Shift Assignments (fct_shift_assignments) — List + Calendar
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("### Shift Assignments")

assigned_sql = f"""
SELECT
  company_name,
  shift_date,
  shift_id,
  assignment_status,
  shift.type AS shift_type,
  shift.is_remote,
  CAST(shift.start AS STRING) AS shift_start,
  CAST(shift.`end` AS STRING) AS shift_end,
  shift.duration,
  location.external_id AS store_number
FROM `bi.fct_shift_assignments`
WHERE
  partner_id = '{partner_id}'
  AND shift_date BETWEEN '{start_date}' AND '{end_date}'
ORDER BY shift_date DESC
"""

with st.spinner("Loading assignments..."):
    assignments = run_query(assigned_sql)

if assignments.empty:
    st.info("No shift assignments found in this date range.")
else:
    companies = ["All"] + sorted(assignments["company_name"].unique().tolist())
    selected_company = st.selectbox("Filter by company", companies, key="assign_company")
    if selected_company != "All":
        assignments = assignments[assignments["company_name"] == selected_company]

    tab_list, tab_cal = st.tabs(["List View", "Calendar View"])

    with tab_list:
        st.dataframe(assignments, use_container_width=True, hide_index=True)

    with tab_cal:
        if assignments.empty:
            st.info("No assignments to display.")
        else:
            assignments["shift_date"] = pd.to_datetime(assignments["shift_date"]).dt.date

            cal_start = assignments["shift_date"].min()
            cal_end = assignments["shift_date"].max()

            by_date = assignments.groupby("shift_date").apply(
                lambda g: g[["company_name", "shift_type", "assignment_status", "store_number"]].to_dict("records"),
                include_groups=False
            ).to_dict()

            current = cal_start.replace(day=1)
            end_month = cal_end.replace(day=1)

            while current <= end_month:
                year, month = current.year, current.month
                st.subheader(f"{calendar.month_name[month]} {year}")

                header_cols = st.columns(7)
                for i, day_name in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]):
                    header_cols[i].markdown(f"**{day_name}**")

                cal_grid = calendar.monthcalendar(year, month)
                for week in cal_grid:
                    week_cols = st.columns(7)
                    for i, day in enumerate(week):
                        if day == 0:
                            week_cols[i].write("")
                        else:
                            d = date(year, month, day)
                            if d in by_date:
                                shifts = by_date[d]
                                count = len(shifts)
                                statuses = set(s["assignment_status"] for s in shifts)
                                if "Completed" in statuses:
                                    color = "green"
                                elif "Canceled" in statuses or "NoShow" in statuses:
                                    color = "red"
                                else:
                                    color = "blue"
                                week_cols[i].markdown(
                                    f":{color}[**{day}** ({count})]"
                                )
                                for s in shifts:
                                    week_cols[i].caption(
                                        f"{s['company_name'][:3]} | {s['assignment_status']}"
                                    )
                            else:
                                week_cols[i].markdown(f"<span style='color:#555'>{day}</span>", unsafe_allow_html=True)

                if month == 12:
                    current = current.replace(year=year + 1, month=1)
                else:
                    current = current.replace(month=month + 1)

# ── Footer ──
st.divider()
st.caption(f"Data as of {date.today().strftime('%B %d, %Y')} · Steady State Supply · Priority Markets")
