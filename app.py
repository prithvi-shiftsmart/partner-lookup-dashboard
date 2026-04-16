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

# ═══════════════════════════════════════════════════════════════════════════════
# CKP PARTNER FUNNEL v5 — Two-Level Cohorting (CRM Cohorts)
# ═══════════════════════════════════════════════════════════════════════════════

# Cohort definitions: (sort_key, cohort_combo, display_label, L1_group_key)
COHORT_DEFS = [
    ("01", "01_s1c_assigned_champion",          "Champion (5+ weekly shifts)",    "s1c_assigned"),
    ("02", "02_s1c_assigned_non_m1_s3c",        "Non-M1, S3C",                   "s1c_assigned"),
    ("03", "03_s1c_assigned_m1_s3c",            "M1, S3C",                       "s1c_assigned"),
    ("04", "04_s1c_assigned_not_s3c",           "Not S3C",                       "s1c_assigned"),
    ("05", "05_s1c_not_assigned_sent_seen",     "Sent, Seen",                    "s1c_not_assigned"),
    ("06", "06_s1c_not_assigned_sent_not_seen", "Sent, Not Seen",                "s1c_not_assigned"),
    ("07", "07_s1c_not_assigned_not_sent",      "Not Sent",                      "s1c_not_assigned"),
    ("08", "08_bgc_passed_s1a_assigned",        "S1A, Currently Assigned",       "bgc_passed"),
    ("09", "09_bgc_passed_sent_seen",           "Sent, Seen",                    "bgc_passed"),
    ("10", "10_bgc_passed_sent_not_seen",       "Sent, Not Seen",                "bgc_passed"),
    ("11", "11_bgc_passed_not_sent",            "Not Sent",                      "bgc_passed"),
    ("12", "12_op_bgc_consider",                "Consider",                      "op_not_bgc"),
    ("13", "13_op_bgc_pending_gt24h",           "Pending > 24H",                 "op_not_bgc"),
    ("14", "14_op_bgc_pending_lt24h",           "Pending < 24H",                 "op_not_bgc"),
    ("15", "15_op_bgc_not_submitted",           "Not Submitted",                 "op_not_bgc"),
    ("16", "16_oa_not_op",                      "All",                           "oa_not_op"),
    ("17", "17_not_oa_non_ckp_s1c",             "Non CKP S1C",                   "not_oa"),
    ("18", "18_not_oa_active_24h",              "Active 24hrs No OA",            "not_oa"),
    ("19", "19_not_oa_active_72h",              "Active 72hrs No OA",            "not_oa"),
    ("20", "20_not_oa_active_7d",               "Active 7 Days No OA",           "not_oa"),
    ("21", "21_not_oa_active_7d_plus",          "Active +7 Days No OA",          "not_oa"),
    ("22", "22_former_failed_bgc",              "Failed BGC",                    "former"),
    ("23", "23_former_deactivated",             "Deactivated",                   "former"),
    ("24", "24_former_suspended",               "Suspended",                     "former"),
]

L1_GROUPS = [
    ("s1c_assigned",     "S1C, Assigned"),
    ("s1c_not_assigned", "S1C, Not Assigned"),
    ("bgc_passed",       "BGC Passed, Not S1C"),
    ("op_not_bgc",       "OP, Not BGC Finalized"),
    ("oa_not_op",        "OA, Not OP"),
    ("not_oa",           "Not OA"),
    ("former",           "Former"),
]

GROUP_COLORS = {
    "s1c_assigned":     ("#1a2a3a", "#a3c4d9"),   # blue
    "s1c_not_assigned": ("#1a2a3a", "#7fb3d4"),   # blue (darker)
    "bgc_passed":       ("#1a3a2a", "#a3d9b1"),   # green
    "op_not_bgc":       ("#3a3520", "#d9cfa3"),   # yellow
    "oa_not_op":        ("#2a2040", "#c4a3d9"),   # purple
    "not_oa":           ("#302030", "#b090c0"),   # dim purple
    "former":           ("#3a1a1a", "#d9a3a3"),   # red
}

CRM_COHORT_OPTIONS = ["(All)", "C1: Subscale Deep Dives", "C2a: FR<80 (Any)",
                      "C2b: StoreSmart Alpha", "C2c: T25, FR 80-90%"]

SUMMARY_SQL = """
DECLARE asof DATE DEFAULT CURRENT_DATE('America/New_York');

WITH
store_cohorts AS (
  SELECT
    zone_desc AS zone_description, store_num, priority_cohort_l2,
    CASE priority_cohort_l2
      WHEN 'C1: Subscale Deep Dives' THEN 1
      WHEN 'C2a: FR<80 (Any)' THEN 2
      WHEN 'C2b: StoreSmart Alpha' THEN 3
      WHEN 'C2c: T25, FR 80-90%' THEN 4
      ELSE 99
    END AS l2_priority
  FROM `client.circle_k_store_crm`
  WHERE priority_cohort_l1 IN ('C1: Root Cause Diagnosis', 'C2: Unblock Partner Funnel')
),
zone_cohort AS (
  SELECT zone_description,
    ARRAY_AGG(priority_cohort_l2 ORDER BY l2_priority LIMIT 1)[OFFSET(0)] AS zone_cohort_l2
  FROM store_cohorts GROUP BY zone_description
),
target_markets AS (
  SELECT zc.zone_description, zc.zone_cohort_l2 AS priority_cohort_l2
  FROM zone_cohort zc
  JOIN `growth.supply_model_daily_position` sm ON zc.zone_description = sm.zone_description
  WHERE sm.company_name = 'Circle K - Premium' AND sm.position = 'All'
    AND sm.date = asof - 1 AND sm.shifts > 0
  GROUP BY zc.zone_description, zc.zone_cohort_l2
),
bgc_latest AS (
  SELECT partner_id, IFNULL(bgc_result_raw, 'no_bgc') AS bgc_result, bgc_submitted_at FROM (
    SELECT userId AS partner_id, result AS bgc_result_raw, updatedAt AS bgc_submitted_at,
      ROW_NUMBER() OVER (PARTITION BY userId ORDER BY updatedAt DESC) AS rn
    FROM `shiftsmart-api.shiftsmart_data.bq_background_checks`
  ) WHERE rn = 1
),
bgc_adjudication AS (
  SELECT partner_id, bgc_adjudication_event FROM (
    SELECT userId AS partner_id, webhookEventType AS bgc_adjudication_event,
      ROW_NUMBER() OVER (PARTITION BY userId ORDER BY updatedAt DESC) AS rn
    FROM `shiftsmart-api.shiftsmart_data.bq_background_checks`
    WHERE DATE(updatedAt) >= '2025-07-31'
      AND ((result = 'consider' AND webhookEventType = 'report.engaged')
        OR webhookEventType = 'report.pre_adverse_action'
        OR webhookEventType = 'report.post_adverse_action')
  ) WHERE rn = 1
),
shift_dispatch AS (
  SELECT us.user AS partner_id,
    COUNTIF(LOWER(us.title) NOT LIKE '%%orientation%%' AND LOWER(us.title) NOT LIKE '%%shadow%%'
      AND us.start >= CAST(asof AS DATETIME) AND us.start < CAST(asof + 7 AS DATETIME)) AS work_shifts_sent_next_7d,
    COUNTIF(LOWER(us.title) NOT LIKE '%%orientation%%' AND LOWER(us.title) NOT LIKE '%%shadow%%'
      AND us.start >= CAST(asof AS DATETIME) AND us.start < CAST(asof + 7 AS DATETIME)
      AND us.seen_at IS NOT NULL) AS work_shifts_seen_next_7d
  FROM `shiftsmart-api.shiftsmart_data.bq_usershifts_deduped` us
  INNER JOIN (
    SELECT DISTINCT p.partner_id FROM `growth.int_master_partner_throughput` p
    INNER JOIN target_markets t ON p.zone_description = t.zone_description
    WHERE p.company_name = 'Circle K - Premium'
  ) scope ON us.user = scope.partner_id
  WHERE us.start >= CAST(asof - 7 AS DATETIME) AND us.start < CAST(asof + 7 AS DATETIME) AND us.sent_at IS NOT NULL
  GROUP BY us.user
),
partner_reliability AS (
  SELECT user AS partner_id, partner_role_tier
  FROM `bi.dim_partner_aggregate_reliability` WHERE ds = CURRENT_DATE('US/Eastern')
),
completed_shifts AS (
  SELECT a.partner_id, COUNTIF(a.assignment_status = 'Completed') AS completed_ckp_shifts
  FROM `bi.fct_shift_assignments` a
  WHERE a.company_name = 'Circle K - Premium' AND a.shift_date >= '2020-01-01'
    AND (a.shift.type != 'orientation' OR a.shift.type IS NULL) AND a.partner_id IS NOT NULL
  GROUP BY a.partner_id
),
non_ckp_s1c AS (
  SELECT DISTINCT partner_id FROM `growth.int_master_partner_throughput`
  WHERE company_name != 'Circle K - Premium' AND s1c_date IS NOT NULL
),
cohorted AS (
  SELECT t.priority_cohort_l2,
    CASE
      WHEN p.currently_suspended = TRUE THEN '24_former_suspended'
      WHEN p.currently_deactivated = TRUE OR p.is_fraud_partner = TRUE THEN '23_former_deactivated'
      WHEN adj.bgc_adjudication_event IN ('report.pre_adverse_action', 'report.post_adverse_action') THEN '22_former_failed_bgc'
      WHEN p.s1c_date IS NOT NULL AND p.shifts_assigned_next_7d > 0 AND p.shifts_worked_last_7d >= 5 THEN '01_s1c_assigned_champion'
      WHEN p.s1c_date IS NOT NULL AND p.shifts_assigned_next_7d > 0 AND COALESCE(cs.completed_ckp_shifts, 0) >= 3 AND (rel.partner_role_tier NOT LIKE '%%M1%%Active%%' OR rel.partner_role_tier IS NULL) THEN '02_s1c_assigned_non_m1_s3c'
      WHEN p.s1c_date IS NOT NULL AND p.shifts_assigned_next_7d > 0 AND COALESCE(cs.completed_ckp_shifts, 0) >= 3 AND rel.partner_role_tier LIKE '%%M1%%Active%%' THEN '03_s1c_assigned_m1_s3c'
      WHEN p.s1c_date IS NOT NULL AND p.shifts_assigned_next_7d > 0 THEN '04_s1c_assigned_not_s3c'
      WHEN p.s1c_date IS NOT NULL AND p.shifts_assigned_next_7d = 0 AND COALESCE(sd.work_shifts_sent_next_7d, 0) > 0 AND COALESCE(sd.work_shifts_seen_next_7d, 0) > 0 THEN '05_s1c_not_assigned_sent_seen'
      WHEN p.s1c_date IS NOT NULL AND p.shifts_assigned_next_7d = 0 AND COALESCE(sd.work_shifts_sent_next_7d, 0) > 0 AND COALESCE(sd.work_shifts_seen_next_7d, 0) = 0 THEN '06_s1c_not_assigned_sent_not_seen'
      WHEN p.s1c_date IS NOT NULL AND p.shifts_assigned_next_7d = 0 THEN '07_s1c_not_assigned_not_sent'
      WHEN p.op_date IS NOT NULL AND p.s1c_date IS NULL AND ((IFNULL(bgc.bgc_result, 'no_bgc') = 'clear' AND adj.bgc_adjudication_event IS NULL) OR adj.bgc_adjudication_event = 'report.engaged') AND p.shifts_assigned_next_7d > 0 THEN '08_bgc_passed_s1a_assigned'
      WHEN p.op_date IS NOT NULL AND p.s1c_date IS NULL AND ((IFNULL(bgc.bgc_result, 'no_bgc') = 'clear' AND adj.bgc_adjudication_event IS NULL) OR adj.bgc_adjudication_event = 'report.engaged') AND COALESCE(sd.work_shifts_sent_next_7d, 0) > 0 AND COALESCE(sd.work_shifts_seen_next_7d, 0) > 0 THEN '09_bgc_passed_sent_seen'
      WHEN p.op_date IS NOT NULL AND p.s1c_date IS NULL AND ((IFNULL(bgc.bgc_result, 'no_bgc') = 'clear' AND adj.bgc_adjudication_event IS NULL) OR adj.bgc_adjudication_event = 'report.engaged') AND COALESCE(sd.work_shifts_sent_next_7d, 0) > 0 AND COALESCE(sd.work_shifts_seen_next_7d, 0) = 0 THEN '10_bgc_passed_sent_not_seen'
      WHEN p.op_date IS NOT NULL AND p.s1c_date IS NULL AND ((IFNULL(bgc.bgc_result, 'no_bgc') = 'clear' AND adj.bgc_adjudication_event IS NULL) OR adj.bgc_adjudication_event = 'report.engaged') THEN '11_bgc_passed_not_sent'
      WHEN p.op_date IS NOT NULL AND p.s1c_date IS NULL AND bgc.bgc_result = 'consider' AND adj.bgc_adjudication_event IS NULL THEN '12_op_bgc_consider'
      WHEN p.op_date IS NOT NULL AND p.s1c_date IS NULL AND bgc.bgc_result = 'pending' AND bgc.bgc_submitted_at < DATETIME_SUB(CURRENT_DATETIME('America/New_York'), INTERVAL 24 HOUR) THEN '13_op_bgc_pending_gt24h'
      WHEN p.op_date IS NOT NULL AND p.s1c_date IS NULL AND bgc.bgc_result = 'pending' THEN '14_op_bgc_pending_lt24h'
      WHEN p.op_date IS NOT NULL AND p.s1c_date IS NULL THEN '15_op_bgc_not_submitted'
      WHEN p.oa_date IS NOT NULL AND p.op_date IS NULL THEN '16_oa_not_op'
      WHEN p.oa_date IS NULL AND ncs.partner_id IS NOT NULL THEN '17_not_oa_non_ckp_s1c'
      WHEN p.oa_date IS NULL AND p.last_active_at >= DATETIME_SUB(CURRENT_DATETIME('America/New_York'), INTERVAL 24 HOUR) THEN '18_not_oa_active_24h'
      WHEN p.oa_date IS NULL AND p.last_active_at >= DATETIME_SUB(CURRENT_DATETIME('America/New_York'), INTERVAL 3 DAY) THEN '19_not_oa_active_72h'
      WHEN p.oa_date IS NULL AND p.last_active_at >= DATETIME_SUB(CURRENT_DATETIME('America/New_York'), INTERVAL 7 DAY) THEN '20_not_oa_active_7d'
      WHEN p.oa_date IS NULL THEN '21_not_oa_active_7d_plus'
      ELSE '99_unclassified'
    END AS cohort,
    CASE
      WHEN p.currently_suspended OR p.currently_deactivated OR p.is_fraud_partner THEN 'No action'
      WHEN adj.bgc_adjudication_event IN ('report.pre_adverse_action', 'report.post_adverse_action') THEN 'No action (failed BGC)'
      WHEN p.s1c_date IS NOT NULL AND p.shifts_assigned_next_7d > 0 AND p.shifts_worked_last_7d >= 5 THEN 'Maximize output'
      WHEN p.s1c_date IS NOT NULL AND p.shifts_assigned_next_7d > 0 THEN 'Work more'
      WHEN p.s1c_date IS NOT NULL AND p.shifts_assigned_next_7d = 0 AND COALESCE(sd.work_shifts_sent_next_7d, 0) > 0 AND COALESCE(sd.work_shifts_seen_next_7d, 0) > 0 THEN 'Pick up shifts (seen)'
      WHEN p.s1c_date IS NOT NULL AND p.shifts_assigned_next_7d = 0 AND COALESCE(sd.work_shifts_sent_next_7d, 0) > 0 AND COALESCE(sd.work_shifts_seen_next_7d, 0) = 0 THEN 'Pick up shifts (not seen)'
      WHEN p.s1c_date IS NOT NULL AND p.shifts_assigned_next_7d = 0 THEN 'Show shifts'
      WHEN p.op_date IS NOT NULL AND p.s1c_date IS NULL AND ((IFNULL(bgc.bgc_result, 'no_bgc') = 'clear' AND adj.bgc_adjudication_event IS NULL) OR adj.bgc_adjudication_event = 'report.engaged') AND p.shifts_assigned_next_7d > 0 THEN 'S1A (shift coming)'
      WHEN p.op_date IS NOT NULL AND p.s1c_date IS NULL AND ((IFNULL(bgc.bgc_result, 'no_bgc') = 'clear' AND adj.bgc_adjudication_event IS NULL) OR adj.bgc_adjudication_event = 'report.engaged') AND COALESCE(sd.work_shifts_sent_next_7d, 0) > 0 THEN 'Pick up shifts (BGC clear)'
      WHEN p.op_date IS NOT NULL AND p.s1c_date IS NULL AND ((IFNULL(bgc.bgc_result, 'no_bgc') = 'clear' AND adj.bgc_adjudication_event IS NULL) OR adj.bgc_adjudication_event = 'report.engaged') THEN 'Show shifts (BGC clear)'
      WHEN p.op_date IS NOT NULL AND p.s1c_date IS NULL AND bgc.bgc_result = 'consider' AND adj.bgc_adjudication_event IS NULL THEN 'Escalate to Kate'
      WHEN p.op_date IS NOT NULL AND p.s1c_date IS NULL AND bgc.bgc_result = 'pending' AND bgc.bgc_submitted_at < DATETIME_SUB(CURRENT_DATETIME('America/New_York'), INTERVAL 24 HOUR) THEN 'BGC stuck (>24h)'
      WHEN p.op_date IS NOT NULL AND p.s1c_date IS NULL AND bgc.bgc_result = 'pending' THEN 'BGC processing (<24h)'
      WHEN p.op_date IS NOT NULL AND p.s1c_date IS NULL THEN 'Submit BGC'
      WHEN p.oa_date IS NOT NULL AND p.op_date IS NULL THEN 'Complete orientation'
      WHEN p.oa_date IS NULL AND ncs.partner_id IS NOT NULL THEN 'Cross-sell to CKP'
      WHEN p.oa_date IS NULL AND p.last_active_at >= DATETIME_SUB(CURRENT_DATETIME('America/New_York'), INTERVAL 7 DAY) THEN 'OA (active)'
      ELSE 'OA (inactive)'
    END AS triage_action
  FROM `growth.int_master_partner_throughput` p
  INNER JOIN target_markets t ON p.zone_description = t.zone_description
  LEFT JOIN bgc_latest bgc ON p.partner_id = bgc.partner_id
  LEFT JOIN bgc_adjudication adj ON p.partner_id = adj.partner_id
  LEFT JOIN shift_dispatch sd ON p.partner_id = sd.partner_id
  LEFT JOIN partner_reliability rel ON p.partner_id = rel.partner_id
  LEFT JOIN completed_shifts cs ON p.partner_id = cs.partner_id
  LEFT JOIN non_ckp_s1c ncs ON p.partner_id = ncs.partner_id
  WHERE p.company_name = 'Circle K - Premium'
    AND p.last_active_at >= DATETIME_SUB(CURRENT_DATETIME('America/New_York'), INTERVAL 14 DAY)
),
all_cohorts AS (
  SELECT cohort, triage_action FROM UNNEST([
    STRUCT('01_s1c_assigned_champion' AS cohort, 'Maximize output' AS triage_action),
    STRUCT('02_s1c_assigned_non_m1_s3c', 'Work more'),
    STRUCT('03_s1c_assigned_m1_s3c', 'Work more'),
    STRUCT('04_s1c_assigned_not_s3c', 'Work more'),
    STRUCT('05_s1c_not_assigned_sent_seen', 'Pick up shifts (seen)'),
    STRUCT('06_s1c_not_assigned_sent_not_seen', 'Pick up shifts (not seen)'),
    STRUCT('07_s1c_not_assigned_not_sent', 'Show shifts'),
    STRUCT('08_bgc_passed_s1a_assigned', 'S1A (shift coming)'),
    STRUCT('09_bgc_passed_sent_seen', 'Pick up shifts (BGC clear)'),
    STRUCT('10_bgc_passed_sent_not_seen', 'Pick up shifts (BGC clear)'),
    STRUCT('11_bgc_passed_not_sent', 'Show shifts (BGC clear)'),
    STRUCT('12_op_bgc_consider', 'Escalate to Kate'),
    STRUCT('13_op_bgc_pending_gt24h', 'BGC stuck (>24h)'),
    STRUCT('14_op_bgc_pending_lt24h', 'BGC processing (<24h)'),
    STRUCT('15_op_bgc_not_submitted', 'Submit BGC'),
    STRUCT('16_oa_not_op', 'Complete orientation'),
    STRUCT('17_not_oa_non_ckp_s1c', 'Cross-sell to CKP'),
    STRUCT('18_not_oa_active_24h', 'OA (active)'),
    STRUCT('19_not_oa_active_72h', 'OA (active)'),
    STRUCT('20_not_oa_active_7d', 'OA (active)'),
    STRUCT('21_not_oa_active_7d_plus', 'OA (inactive)'),
    STRUCT('22_former_failed_bgc', 'No action (failed BGC)'),
    STRUCT('23_former_deactivated', 'No action'),
    STRUCT('24_former_suspended', 'No action')
  ])
),
totals AS (
  SELECT cohort, COUNT(*) AS total_partners,
    COUNTIF(priority_cohort_l2 = 'C1: Subscale Deep Dives') AS c1_subscale,
    COUNTIF(priority_cohort_l2 = 'C2a: FR<80 (Any)') AS c2a_fr_below_80,
    COUNTIF(priority_cohort_l2 = 'C2b: StoreSmart Alpha') AS c2b_storesmart,
    COUNTIF(priority_cohort_l2 = 'C2c: T25, FR 80-90%%') AS c2c_t25_fr_80_90
  FROM cohorted GROUP BY cohort
)
SELECT ac.cohort, ac.triage_action,
  COALESCE(t.total_partners, 0) AS total,
  COALESCE(t.c1_subscale, 0) AS c1_subscale,
  COALESCE(t.c2a_fr_below_80, 0) AS c2a_fr_below_80,
  COALESCE(t.c2b_storesmart, 0) AS c2b_storesmart,
  COALESCE(t.c2c_t25_fr_80_90, 0) AS c2c_t25_fr_80_90
FROM all_cohorts ac
LEFT JOIN totals t ON ac.cohort = t.cohort
ORDER BY ac.cohort ASC
"""

ROSTER_SQL = """
DECLARE asof DATE DEFAULT CURRENT_DATE('America/New_York');

WITH
store_cohorts AS (
  SELECT
    zone_desc AS zone_description, store_num, priority_cohort_l1, priority_cohort_l2,
    CASE priority_cohort_l2
      WHEN 'C1: Subscale Deep Dives' THEN 1
      WHEN 'C2a: FR<80 (Any)' THEN 2
      WHEN 'C2b: StoreSmart Alpha' THEN 3
      WHEN 'C2c: T25, FR 80-90%' THEN 4
      ELSE 99
    END AS l2_priority
  FROM `client.circle_k_store_crm`
  WHERE priority_cohort_l1 IN ('C1: Root Cause Diagnosis', 'C2: Unblock Partner Funnel')
),
zone_cohort AS (
  SELECT zone_description,
    ARRAY_AGG(priority_cohort_l1 ORDER BY l2_priority LIMIT 1)[OFFSET(0)] AS zone_cohort_l1,
    ARRAY_AGG(priority_cohort_l2 ORDER BY l2_priority LIMIT 1)[OFFSET(0)] AS zone_cohort_l2
  FROM store_cohorts GROUP BY zone_description
),
target_markets AS (
  SELECT zc.zone_description, MAX(sm.hex_city_description) AS city,
    SAFE_DIVIDE(SUM(sm.filled), SUM(sm.shifts)) AS fill_rate_l7d,
    SUM(sm.shifts) AS total_shifts_l7d, SUM(sm.filled) AS filled_shifts_l7d,
    zc.zone_cohort_l2 AS priority_cohort_l2
  FROM zone_cohort zc
  JOIN `growth.supply_model_daily_position` sm ON zc.zone_description = sm.zone_description
  WHERE sm.company_name = 'Circle K - Premium' AND sm.position = 'All'
    AND sm.date = asof - 1 AND sm.shifts > 0
  GROUP BY zc.zone_description, zc.zone_cohort_l2
),
bgc_latest AS (
  SELECT partner_id, bgc_status_raw, bgc_result_raw, IFNULL(bgc_result_raw, 'no_bgc') AS bgc_result, bgc_submitted_at FROM (
    SELECT userId AS partner_id, status AS bgc_status_raw, result AS bgc_result_raw, updatedAt AS bgc_submitted_at,
      ROW_NUMBER() OVER (PARTITION BY userId ORDER BY updatedAt DESC) AS rn
    FROM `shiftsmart-api.shiftsmart_data.bq_background_checks`
  ) WHERE rn = 1
),
bgc_adjudication AS (
  SELECT partner_id, bgc_adjudication_event, bgc_adjudication_date FROM (
    SELECT userId AS partner_id, webhookEventType AS bgc_adjudication_event, updatedAt AS bgc_adjudication_date,
      ROW_NUMBER() OVER (PARTITION BY userId ORDER BY updatedAt DESC) AS rn
    FROM `shiftsmart-api.shiftsmart_data.bq_background_checks`
    WHERE DATE(updatedAt) >= '2025-07-31'
      AND ((result = 'consider' AND webhookEventType = 'report.engaged')
        OR webhookEventType = 'report.pre_adverse_action'
        OR webhookEventType = 'report.post_adverse_action')
  ) WHERE rn = 1
),
shift_dispatch AS (
  SELECT us.user AS partner_id,
    COUNTIF(us.sent_at >= CAST(asof - 7 AS DATETIME)) AS total_shifts_sent_l7d,
    COUNTIF(LOWER(us.title) NOT LIKE '%%orientation%%' AND LOWER(us.title) NOT LIKE '%%shadow%%'
      AND us.sent_at >= CAST(asof - 7 AS DATETIME)) AS work_shifts_sent_l7d,
    COUNTIF(LOWER(us.title) NOT LIKE '%%orientation%%' AND LOWER(us.title) NOT LIKE '%%shadow%%'
      AND us.assigned_at IS NOT NULL AND us.sent_at >= CAST(asof - 7 AS DATETIME)) AS work_shifts_accepted_l7d,
    COUNTIF(LOWER(us.title) NOT LIKE '%%orientation%%' AND LOWER(us.title) NOT LIKE '%%shadow%%'
      AND us.start >= CAST(asof AS DATETIME) AND us.start < CAST(asof + 7 AS DATETIME)) AS work_shifts_sent_next_7d,
    COUNTIF(LOWER(us.title) NOT LIKE '%%orientation%%' AND LOWER(us.title) NOT LIKE '%%shadow%%'
      AND us.start >= CAST(asof AS DATETIME) AND us.start < CAST(asof + 7 AS DATETIME)
      AND us.seen_at IS NOT NULL) AS work_shifts_seen_next_7d
  FROM `shiftsmart-api.shiftsmart_data.bq_usershifts_deduped` us
  INNER JOIN (
    SELECT DISTINCT p.partner_id FROM `growth.int_master_partner_throughput` p
    INNER JOIN target_markets t ON p.zone_description = t.zone_description
    WHERE p.company_name = 'Circle K - Premium'
  ) scope ON us.user = scope.partner_id
  WHERE us.start >= CAST(asof - 7 AS DATETIME) AND us.start < CAST(asof + 7 AS DATETIME) AND us.sent_at IS NOT NULL
  GROUP BY us.user
),
partner_reliability AS (
  SELECT user AS partner_id, rolling_lifetime_ckp_closed_loop_cook_shifts AS lifetime_ckp_shifts, partner_role_tier
  FROM `bi.dim_partner_aggregate_reliability` WHERE ds = CURRENT_DATE('US/Eastern')
),
completed_shifts AS (
  SELECT a.partner_id, COUNTIF(a.assignment_status = 'Completed') AS completed_ckp_shifts
  FROM `bi.fct_shift_assignments` a
  WHERE a.company_name = 'Circle K - Premium' AND a.shift_date >= '2020-01-01'
    AND (a.shift.type != 'orientation' OR a.shift.type IS NULL) AND a.partner_id IS NOT NULL
  GROUP BY a.partner_id
),
non_ckp_s1c AS (
  SELECT DISTINCT partner_id FROM `growth.int_master_partner_throughput`
  WHERE company_name != 'Circle K - Premium' AND s1c_date IS NOT NULL
),
cohorted AS (
  SELECT
    p.partner_id, p.first_name, p.last_name, p.phone_number, p.email,
    t.city, p.zone_description, ROUND(p.closest_store_proximity_miles, 1) AS closest_store_miles,
    ROUND(t.fill_rate_l7d, 3) AS fill_rate_l7d,
    p.created_date AS dl_date, p.oa_date, p.op_date, p.s1a_date, p.s1c_date, p.m1_date,
    p.last_active_at, p.churn_status, ROUND(p.churn_probability, 3) AS churn_probability,
    p.shifts_worked_last_7d, p.shifts_assigned_next_7d, p.days_since_last_shift_worked,
    p.total_shifts_last_4w, p.volume_label_current,
    ROUND(p.evfr_score, 3) AS evfr_score, ROUND(p.pct_shift_success, 3) AS pct_shift_success,
    rel.partner_role_tier AS m1_tier,
    CASE WHEN rel.partner_role_tier LIKE '%%M1%%Active%%' THEN TRUE ELSE FALSE END AS is_m1,
    IFNULL(bgc.bgc_result, 'no_bgc') AS bgc_status, bgc.bgc_submitted_at,
    adj.bgc_adjudication_event,
    COALESCE(sd.work_shifts_sent_l7d, 0) AS work_shifts_sent_l7d,
    COALESCE(sd.work_shifts_accepted_l7d, 0) AS work_shifts_accepted_l7d,
    COALESCE(sd.work_shifts_sent_next_7d, 0) AS work_shifts_sent_next_7d,
    COALESCE(sd.work_shifts_seen_next_7d, 0) AS work_shifts_seen_next_7d,
    COALESCE(rel.lifetime_ckp_shifts, 0) AS lifetime_ckp_shifts_worked,
    COALESCE(cs.completed_ckp_shifts, 0) AS completed_ckp_shifts,
    CASE
      WHEN p.currently_suspended = TRUE THEN 'Former'
      WHEN p.currently_deactivated = TRUE OR p.is_fraud_partner = TRUE THEN 'Former'
      WHEN adj.bgc_adjudication_event IN ('report.pre_adverse_action', 'report.post_adverse_action') THEN 'Former'
      WHEN p.s1c_date IS NOT NULL AND p.shifts_assigned_next_7d > 0 THEN 'S1C, Assigned'
      WHEN p.s1c_date IS NOT NULL AND p.shifts_assigned_next_7d = 0 THEN 'S1C, Not Assigned'
      WHEN p.op_date IS NOT NULL AND p.s1c_date IS NULL
        AND ((IFNULL(bgc.bgc_result, 'no_bgc') = 'clear' AND adj.bgc_adjudication_event IS NULL) OR adj.bgc_adjudication_event = 'report.engaged')
        THEN 'BGC Passed, Not S1C'
      WHEN p.op_date IS NOT NULL AND p.s1c_date IS NULL THEN 'OP, Not BGC Finalized'
      WHEN p.oa_date IS NOT NULL AND p.op_date IS NULL THEN 'OA, Not OP'
      WHEN p.oa_date IS NULL THEN 'Not OA'
      ELSE 'Unclassified'
    END AS cohort_l1,
    CASE
      WHEN p.currently_suspended = TRUE THEN 'Suspended'
      WHEN p.currently_deactivated = TRUE OR p.is_fraud_partner = TRUE THEN 'Deactivated'
      WHEN adj.bgc_adjudication_event IN ('report.pre_adverse_action', 'report.post_adverse_action') THEN 'Failed BGC'
      WHEN p.s1c_date IS NOT NULL AND p.shifts_assigned_next_7d > 0 AND p.shifts_worked_last_7d >= 5 THEN 'Champion (5+ weekly shifts)'
      WHEN p.s1c_date IS NOT NULL AND p.shifts_assigned_next_7d > 0 AND COALESCE(cs.completed_ckp_shifts, 0) >= 3 AND (rel.partner_role_tier NOT LIKE '%%M1%%Active%%' OR rel.partner_role_tier IS NULL) THEN 'Non-M1, S3C'
      WHEN p.s1c_date IS NOT NULL AND p.shifts_assigned_next_7d > 0 AND COALESCE(cs.completed_ckp_shifts, 0) >= 3 AND rel.partner_role_tier LIKE '%%M1%%Active%%' THEN 'M1, S3C'
      WHEN p.s1c_date IS NOT NULL AND p.shifts_assigned_next_7d > 0 THEN 'Not S3C'
      WHEN p.s1c_date IS NOT NULL AND p.shifts_assigned_next_7d = 0 AND COALESCE(sd.work_shifts_sent_next_7d, 0) > 0 AND COALESCE(sd.work_shifts_seen_next_7d, 0) > 0 THEN 'Sent, Seen'
      WHEN p.s1c_date IS NOT NULL AND p.shifts_assigned_next_7d = 0 AND COALESCE(sd.work_shifts_sent_next_7d, 0) > 0 AND COALESCE(sd.work_shifts_seen_next_7d, 0) = 0 THEN 'Sent, Not Seen'
      WHEN p.s1c_date IS NOT NULL AND p.shifts_assigned_next_7d = 0 THEN 'Not Sent'
      WHEN p.op_date IS NOT NULL AND p.s1c_date IS NULL AND ((IFNULL(bgc.bgc_result, 'no_bgc') = 'clear' AND adj.bgc_adjudication_event IS NULL) OR adj.bgc_adjudication_event = 'report.engaged') AND p.shifts_assigned_next_7d > 0 THEN 'S1A, Currently Assigned'
      WHEN p.op_date IS NOT NULL AND p.s1c_date IS NULL AND ((IFNULL(bgc.bgc_result, 'no_bgc') = 'clear' AND adj.bgc_adjudication_event IS NULL) OR adj.bgc_adjudication_event = 'report.engaged') AND COALESCE(sd.work_shifts_sent_next_7d, 0) > 0 AND COALESCE(sd.work_shifts_seen_next_7d, 0) > 0 THEN 'Sent, Seen'
      WHEN p.op_date IS NOT NULL AND p.s1c_date IS NULL AND ((IFNULL(bgc.bgc_result, 'no_bgc') = 'clear' AND adj.bgc_adjudication_event IS NULL) OR adj.bgc_adjudication_event = 'report.engaged') AND COALESCE(sd.work_shifts_sent_next_7d, 0) > 0 AND COALESCE(sd.work_shifts_seen_next_7d, 0) = 0 THEN 'Sent, Not Seen'
      WHEN p.op_date IS NOT NULL AND p.s1c_date IS NULL AND ((IFNULL(bgc.bgc_result, 'no_bgc') = 'clear' AND adj.bgc_adjudication_event IS NULL) OR adj.bgc_adjudication_event = 'report.engaged') THEN 'Not Sent'
      WHEN p.op_date IS NOT NULL AND p.s1c_date IS NULL AND bgc.bgc_result = 'consider' AND adj.bgc_adjudication_event IS NULL THEN 'Consider'
      WHEN p.op_date IS NOT NULL AND p.s1c_date IS NULL AND bgc.bgc_result = 'pending' AND bgc.bgc_submitted_at < DATETIME_SUB(CURRENT_DATETIME('America/New_York'), INTERVAL 24 HOUR) THEN 'Pending > 24H'
      WHEN p.op_date IS NOT NULL AND p.s1c_date IS NULL AND bgc.bgc_result = 'pending' THEN 'Pending < 24H'
      WHEN p.op_date IS NOT NULL AND p.s1c_date IS NULL AND IFNULL(bgc.bgc_result, 'no_bgc') IN ('no_bgc', 'cancelled') THEN 'Not Submitted'
      WHEN p.oa_date IS NOT NULL AND p.op_date IS NULL THEN 'All'
      WHEN p.oa_date IS NULL AND ncs.partner_id IS NOT NULL THEN 'Non CKP S1C'
      WHEN p.oa_date IS NULL AND p.last_active_at >= DATETIME_SUB(CURRENT_DATETIME('America/New_York'), INTERVAL 24 HOUR) THEN 'Active 24hrs No OA'
      WHEN p.oa_date IS NULL AND p.last_active_at >= DATETIME_SUB(CURRENT_DATETIME('America/New_York'), INTERVAL 3 DAY) THEN 'Active 72hrs No OA'
      WHEN p.oa_date IS NULL AND p.last_active_at >= DATETIME_SUB(CURRENT_DATETIME('America/New_York'), INTERVAL 7 DAY) THEN 'Active 7 Days No OA'
      WHEN p.oa_date IS NULL THEN 'Active +7 Days No OA'
      ELSE 'Unclassified'
    END AS cohort_l2,
    CASE
      WHEN p.currently_suspended = TRUE THEN '24_former_suspended'
      WHEN p.currently_deactivated = TRUE OR p.is_fraud_partner = TRUE THEN '23_former_deactivated'
      WHEN adj.bgc_adjudication_event IN ('report.pre_adverse_action', 'report.post_adverse_action') THEN '22_former_failed_bgc'
      WHEN p.s1c_date IS NOT NULL AND p.shifts_assigned_next_7d > 0 AND p.shifts_worked_last_7d >= 5 THEN '01_s1c_assigned_champion'
      WHEN p.s1c_date IS NOT NULL AND p.shifts_assigned_next_7d > 0 AND COALESCE(cs.completed_ckp_shifts, 0) >= 3 AND (rel.partner_role_tier NOT LIKE '%%M1%%Active%%' OR rel.partner_role_tier IS NULL) THEN '02_s1c_assigned_non_m1_s3c'
      WHEN p.s1c_date IS NOT NULL AND p.shifts_assigned_next_7d > 0 AND COALESCE(cs.completed_ckp_shifts, 0) >= 3 AND rel.partner_role_tier LIKE '%%M1%%Active%%' THEN '03_s1c_assigned_m1_s3c'
      WHEN p.s1c_date IS NOT NULL AND p.shifts_assigned_next_7d > 0 THEN '04_s1c_assigned_not_s3c'
      WHEN p.s1c_date IS NOT NULL AND p.shifts_assigned_next_7d = 0 AND COALESCE(sd.work_shifts_sent_next_7d, 0) > 0 AND COALESCE(sd.work_shifts_seen_next_7d, 0) > 0 THEN '05_s1c_not_assigned_sent_seen'
      WHEN p.s1c_date IS NOT NULL AND p.shifts_assigned_next_7d = 0 AND COALESCE(sd.work_shifts_sent_next_7d, 0) > 0 AND COALESCE(sd.work_shifts_seen_next_7d, 0) = 0 THEN '06_s1c_not_assigned_sent_not_seen'
      WHEN p.s1c_date IS NOT NULL AND p.shifts_assigned_next_7d = 0 THEN '07_s1c_not_assigned_not_sent'
      WHEN p.op_date IS NOT NULL AND p.s1c_date IS NULL AND ((IFNULL(bgc.bgc_result, 'no_bgc') = 'clear' AND adj.bgc_adjudication_event IS NULL) OR adj.bgc_adjudication_event = 'report.engaged') AND p.shifts_assigned_next_7d > 0 THEN '08_bgc_passed_s1a_assigned'
      WHEN p.op_date IS NOT NULL AND p.s1c_date IS NULL AND ((IFNULL(bgc.bgc_result, 'no_bgc') = 'clear' AND adj.bgc_adjudication_event IS NULL) OR adj.bgc_adjudication_event = 'report.engaged') AND COALESCE(sd.work_shifts_sent_next_7d, 0) > 0 AND COALESCE(sd.work_shifts_seen_next_7d, 0) > 0 THEN '09_bgc_passed_sent_seen'
      WHEN p.op_date IS NOT NULL AND p.s1c_date IS NULL AND ((IFNULL(bgc.bgc_result, 'no_bgc') = 'clear' AND adj.bgc_adjudication_event IS NULL) OR adj.bgc_adjudication_event = 'report.engaged') AND COALESCE(sd.work_shifts_sent_next_7d, 0) > 0 AND COALESCE(sd.work_shifts_seen_next_7d, 0) = 0 THEN '10_bgc_passed_sent_not_seen'
      WHEN p.op_date IS NOT NULL AND p.s1c_date IS NULL AND ((IFNULL(bgc.bgc_result, 'no_bgc') = 'clear' AND adj.bgc_adjudication_event IS NULL) OR adj.bgc_adjudication_event = 'report.engaged') THEN '11_bgc_passed_not_sent'
      WHEN p.op_date IS NOT NULL AND p.s1c_date IS NULL AND bgc.bgc_result = 'consider' AND adj.bgc_adjudication_event IS NULL THEN '12_op_bgc_consider'
      WHEN p.op_date IS NOT NULL AND p.s1c_date IS NULL AND bgc.bgc_result = 'pending' AND bgc.bgc_submitted_at < DATETIME_SUB(CURRENT_DATETIME('America/New_York'), INTERVAL 24 HOUR) THEN '13_op_bgc_pending_gt24h'
      WHEN p.op_date IS NOT NULL AND p.s1c_date IS NULL AND bgc.bgc_result = 'pending' THEN '14_op_bgc_pending_lt24h'
      WHEN p.op_date IS NOT NULL AND p.s1c_date IS NULL THEN '15_op_bgc_not_submitted'
      WHEN p.oa_date IS NOT NULL AND p.op_date IS NULL THEN '16_oa_not_op'
      WHEN p.oa_date IS NULL AND ncs.partner_id IS NOT NULL THEN '17_not_oa_non_ckp_s1c'
      WHEN p.oa_date IS NULL AND p.last_active_at >= DATETIME_SUB(CURRENT_DATETIME('America/New_York'), INTERVAL 24 HOUR) THEN '18_not_oa_active_24h'
      WHEN p.oa_date IS NULL AND p.last_active_at >= DATETIME_SUB(CURRENT_DATETIME('America/New_York'), INTERVAL 3 DAY) THEN '19_not_oa_active_72h'
      WHEN p.oa_date IS NULL AND p.last_active_at >= DATETIME_SUB(CURRENT_DATETIME('America/New_York'), INTERVAL 7 DAY) THEN '20_not_oa_active_7d'
      WHEN p.oa_date IS NULL THEN '21_not_oa_active_7d_plus'
      ELSE '99_unclassified'
    END AS cohort_combo,
    t.priority_cohort_l2
  FROM `growth.int_master_partner_throughput` p
  INNER JOIN target_markets t ON p.zone_description = t.zone_description
  LEFT JOIN bgc_latest bgc ON p.partner_id = bgc.partner_id
  LEFT JOIN shift_dispatch sd ON p.partner_id = sd.partner_id
  LEFT JOIN bgc_adjudication adj ON p.partner_id = adj.partner_id
  LEFT JOIN partner_reliability rel ON p.partner_id = rel.partner_id
  LEFT JOIN completed_shifts cs ON p.partner_id = cs.partner_id
  LEFT JOIN non_ckp_s1c ncs ON p.partner_id = ncs.partner_id
  WHERE p.company_name = 'Circle K - Premium'
    AND p.last_active_at >= DATETIME_SUB(CURRENT_DATETIME('America/New_York'), INTERVAL 14 DAY)
)
SELECT * FROM cohorted
ORDER BY cohort_combo ASC, fill_rate_l7d ASC, city, closest_store_miles ASC
"""

PRIORITY_MARKETS_SQL = """
SELECT DISTINCT sm.hex_city_description AS city_name
FROM `growth.supply_model_daily_position` sm
INNER JOIN (
  SELECT DISTINCT zone_desc AS zone_description
  FROM `client.circle_k_store_crm`
  WHERE priority_cohort_l1 IN ('C1: Root Cause Diagnosis', 'C2: Unblock Partner Funnel')
) zc ON sm.zone_description = zc.zone_description
WHERE sm.company_name = 'Circle K - Premium' AND sm.position = 'All'
  AND sm.date = (SELECT MAX(date) FROM `growth.supply_model_daily_position`
                 WHERE company_name = 'Circle K - Premium' AND position = 'All')
  AND sm.shifts > 0
ORDER BY 1
"""

@st.cache_data(ttl=3600)
def _get_priority_markets():
    """Fetch current CKP priority market list from BQ (CRM-driven). Cached 1 hour."""
    df = run_query(PRIORITY_MARKETS_SQL)
    if df.empty:
        return ["(All)"]
    return ["(All)"] + df["city_name"].tolist()


def _cohort_to_group(cohort_combo):
    """Map a cohort_combo string to its L1 group key."""
    for _, combo, _, group_key in COHORT_DEFS:
        if combo == cohort_combo:
            return group_key
    return "former"


def _render_ckp_funnel():
    """Render the CKP Partner Funnel v5 dashboard page."""

    st.markdown("## CKP Partner Funnel")
    st.caption("v5 — Two-level cohorting with CRM priority cohorts. Partners active in L14D.")

    # ── Controls ──
    market_options = _get_priority_markets()

    col_market, col_crm, col_run = st.columns([3, 3, 1])
    with col_market:
        market = st.selectbox("Market", options=market_options, index=0)
    with col_crm:
        crm_cohorts = st.multiselect("CRM Cohort", options=CRM_COHORT_OPTIONS[1:],
                                     default=[], placeholder="All cohorts")
    with col_run:
        st.markdown("<br>", unsafe_allow_html=True)
        run = st.button("Load Funnel", type="primary", use_container_width=True)

    if not run and "funnel_summary" not in st.session_state:
        st.info("Select filters and click **Load Funnel**.")
        return

    # ── Query both summary + roster ──
    if run:
        with st.spinner("Loading summary..."):
            summary_df = run_query(SUMMARY_SQL)
            st.session_state["funnel_summary"] = summary_df
        with st.spinner("Loading partner roster..."):
            roster_df = run_query(ROSTER_SQL)
            st.session_state["funnel_roster"] = roster_df
        st.session_state["funnel_market"] = market
        st.session_state["funnel_crm"] = crm_cohorts

    summary_df = st.session_state["funnel_summary"]
    roster_df = st.session_state["funnel_roster"]
    market = st.session_state.get("funnel_market", market)
    crm_cohorts = st.session_state.get("funnel_crm", crm_cohorts)

    if summary_df.empty:
        st.warning("No data returned.")
        return

    # ── Summary view — cohort counts by CRM segment ──
    st.markdown("### Summary")

    # Build display table from summary data
    display_rows = []
    for sort_key, combo, label, group_key in COHORT_DEFS:
        row = summary_df[summary_df["cohort"] == combo]
        if row.empty:
            display_rows.append({
                "Cohort": f"{sort_key}. {label}",
                "Triage Action": "",
                "Total": 0, "C1 Subscale": 0, "C2a FR<80": 0,
                "C2b StoreSmart": 0, "C2c T25": 0,
                "_group": group_key, "_combo": combo,
            })
        else:
            r = row.iloc[0]
            display_rows.append({
                "Cohort": f"{sort_key}. {label}",
                "Triage Action": r.get("triage_action", ""),
                "Total": int(r.get("total", 0)),
                "C1 Subscale": int(r.get("c1_subscale", 0)),
                "C2a FR<80": int(r.get("c2a_fr_below_80", 0)),
                "C2b StoreSmart": int(r.get("c2b_storesmart", 0)),
                "C2c T25": int(r.get("c2c_t25_fr_80_90", 0)),
                "_group": group_key, "_combo": combo,
            })

    # Show grouped summary
    grand_total = sum(r["Total"] for r in display_rows)
    for group_key, group_label in L1_GROUPS:
        group_rows = [r for r in display_rows if r["_group"] == group_key]
        group_total = sum(r["Total"] for r in group_rows)

        bg, fg = GROUP_COLORS.get(group_key, ("#1A1F2B", "#E0E0E0"))
        st.markdown(
            f"<div style='background:{bg}; color:{fg}; padding:8px 16px; "
            f"border-radius:6px; font-weight:600; margin-bottom:4px;'>"
            f"{group_label} — {group_total:,} partners</div>",
            unsafe_allow_html=True,
        )

        tbl = pd.DataFrame(group_rows)
        show_cols = ["Cohort", "Triage Action", "Total", "C1 Subscale",
                     "C2a FR<80", "C2b StoreSmart", "C2c T25"]
        st.dataframe(
            tbl[show_cols],
            use_container_width=True,
            hide_index=True,
        )

    # ── Top-level metrics ──
    st.divider()
    st.markdown("### Pipeline Metrics")
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    s1c_assigned = sum(r["Total"] for r in display_rows if r["_group"] == "s1c_assigned")
    s1c_not_assigned = sum(r["Total"] for r in display_rows if r["_group"] == "s1c_not_assigned")
    bgc_passed = sum(r["Total"] for r in display_rows if r["_group"] == "bgc_passed")
    op_pending = sum(r["Total"] for r in display_rows if r["_group"] == "op_not_bgc")
    oa_not_op = sum(r["Total"] for r in display_rows if r["_group"] == "oa_not_op")
    not_oa = sum(r["Total"] for r in display_rows if r["_group"] == "not_oa")
    m1.metric("Total Pipeline", f"{grand_total:,}")
    m2.metric("S1C Assigned", f"{s1c_assigned:,}")
    m3.metric("S1C Not Assigned", f"{s1c_not_assigned:,}")
    m4.metric("BGC Passed", f"{bgc_passed:,}")
    m5.metric("OP Pending BGC", f"{op_pending:,}")
    m6.metric("Pre-OP", f"{oa_not_op + not_oa:,}")

    # ── Partner roster drill-down ──
    st.divider()
    st.markdown("### Partner Roster")

    if roster_df.empty:
        st.warning("No roster data.")
        return

    # Apply filters to roster
    filtered = roster_df.copy()
    if market != "(All)":
        filtered = filtered[filtered["city"] == market]
    if crm_cohorts:
        filtered = filtered[filtered["priority_cohort_l2"].isin(crm_cohorts)]

    if filtered.empty:
        st.warning("No partners match the selected filters.")
        return

    crm_label = ", ".join(crm_cohorts) if crm_cohorts else "All cohorts"
    st.caption(f"**{len(filtered):,}** partners" +
               (f" in **{market}**" if market != "(All)" else "") +
               f" | **{crm_label}**")

    # Group by L1 with expandable partner lists
    for group_key, group_label in L1_GROUPS:
        cohorts_in_group = [c for c in COHORT_DEFS if c[3] == group_key]
        combo_keys = [c[1] for c in cohorts_in_group]
        group_df = filtered[filtered["cohort_combo"].isin(combo_keys)]
        group_count = len(group_df)

        if group_count == 0:
            continue

        bg, fg = GROUP_COLORS.get(group_key, ("#1A1F2B", "#E0E0E0"))
        st.markdown(
            f"<div style='background:{bg}; color:{fg}; padding:8px 16px; "
            f"border-radius:6px; font-weight:600; margin-bottom:4px;'>"
            f"{group_label} — {group_count:,} partners</div>",
            unsafe_allow_html=True,
        )

        for sort_key, combo, label, _ in cohorts_in_group:
            cohort_df = filtered[filtered["cohort_combo"] == combo]
            count = len(cohort_df)
            if count == 0:
                continue
            pct = count / len(filtered) * 100

            with st.expander(f"{label}  —  **{count:,}** ({pct:.1f}%)"):
                # Columns depend on funnel position
                base_cols = ["partner_id", "first_name", "last_name", "city",
                             "zone_description", "closest_store_miles"]

                if group_key in ("s1c_assigned", "s1c_not_assigned"):
                    detail_cols = ["s1c_date", "completed_ckp_shifts", "m1_tier",
                                   "shifts_worked_last_7d", "shifts_assigned_next_7d",
                                   "work_shifts_sent_next_7d", "work_shifts_seen_next_7d",
                                   "churn_status"]
                elif group_key == "bgc_passed":
                    detail_cols = ["op_date", "bgc_status", "s1a_date",
                                   "shifts_assigned_next_7d", "work_shifts_sent_next_7d",
                                   "work_shifts_seen_next_7d"]
                elif group_key == "op_not_bgc":
                    detail_cols = ["op_date", "bgc_status", "bgc_submitted_at",
                                   "bgc_adjudication_event"]
                elif group_key == "oa_not_op":
                    detail_cols = ["oa_date", "op_date"]
                elif group_key == "not_oa":
                    detail_cols = ["dl_date", "last_active_at"]
                else:  # former
                    detail_cols = ["bgc_adjudication_event", "churn_status"]

                contact_cols = ["email", "phone_number"]
                meta_cols = ["fill_rate_l7d", "priority_cohort_l2"]

                all_cols = base_cols + detail_cols + contact_cols + meta_cols
                show_cols = [c for c in all_cols if c in cohort_df.columns]

                sort_col = "fill_rate_l7d" if "fill_rate_l7d" in cohort_df.columns else show_cols[0]
                st.dataframe(
                    cohort_df[show_cols].sort_values(sort_col, ascending=True),
                    use_container_width=True,
                    hide_index=True,
                )


# ── Sidebar ──
with st.sidebar:
    page = st.radio("Dashboard", ["Partner Lookup", "CKP Partner Funnel"], label_visibility="collapsed")
    st.divider()

    if page == "Partner Lookup":
        st.markdown("## Partner Lookup")
        st.caption("Enter a partner ID to view their shifts, bonuses, and assignments.")
        partner_id = st.text_input("Partner ID", value="", placeholder="e.g. dcdc0d40-7351-416d-...")
        st.divider()
        st.markdown("##### Date Range")
        days_back = st.slider("History (days back)", 7, 365, 90)
        days_forward = st.slider("Future (days forward)", 7, 90, 30)
        st.divider()
        st.caption(f"Showing: {(date.today() - timedelta(days=days_back)).strftime('%b %d')} → {(date.today() + timedelta(days=days_forward)).strftime('%b %d, %Y')}")
    else:
        partner_id = None
        days_back = 90
        days_forward = 30

    # ── Re-auth button (both pages) ──
    st.divider()
    if st.button("Re-authenticate GCloud", use_container_width=True):
        with st.spinner("Launching browser for Google auth..."):
            subprocess.Popen(
                ["gcloud", "auth", "application-default", "login"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            st.info("Browser opened. Complete login, then click below.")
        if st.button("Done — refresh", use_container_width=True):
            st.cache_resource.clear()
            st.cache_data.clear()
            st.session_state.pop("auth_needed", None)
            st.rerun()

# ═══════════════════════════════════════════════════════════════════════════════
# CKP PARTNER FUNNEL PAGE
# ═══════════════════════════════════════════════════════════════════════════════
if page == "CKP Partner Funnel":
    _render_ckp_funnel()
    st.stop()

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
  total_shifts_last_4w, weeks_worked_last_4w,
  partner_lat, partner_lng, user_company_status
FROM `growth.int_master_partner_throughput`
WHERE partner_id = '{partner_id}'
"""
partner_info = run_query(partner_info_sql)

# Background check status — v5 logic + legacy status column fallback
bgc_sql = f"""
WITH
-- Normalize: result column is NULL for older records, status column has the value
-- status format: report_clear, report_consider, report_suspended, etc.
bgc_latest AS (
  SELECT partner_id, bgc_status_raw, bgc_result, bgc_submitted_at, bgc_created_at
  FROM (
    SELECT
      userId AS partner_id,
      status AS bgc_status_raw,
      COALESCE(
        result,
        CASE
          WHEN status = 'report_clear' THEN 'clear'
          WHEN status = 'report_consider' THEN 'consider'
          WHEN status = 'report_pending' THEN 'pending'
          WHEN status = 'report_suspended' THEN 'suspended'
          WHEN status = 'report_cancelled' THEN 'cancelled'
          WHEN status IN ('invitation_expired', 'invitation_pending', 'invitation_completed') THEN 'pending'
          ELSE 'no_bgc'
        END
      ) AS bgc_result,
      updatedAt AS bgc_submitted_at,
      createdAt AS bgc_created_at,
      ROW_NUMBER() OVER (PARTITION BY userId ORDER BY updatedAt DESC) AS rn
    FROM `shiftsmart-api.shiftsmart_data.bq_background_checks`
    WHERE userId = '{partner_id}'
  ) WHERE rn = 1
),
-- Adjudication: check both new-format (webhookEventType) and legacy (status column)
bgc_adjudication AS (
  SELECT partner_id, bgc_adjudication_event, bgc_adjudication_date
  FROM (
    SELECT
      userId AS partner_id,
      COALESCE(webhookEventType,
        CASE status
          WHEN 'report_clear' THEN 'report.engaged'
        END
      ) AS bgc_adjudication_event,
      updatedAt AS bgc_adjudication_date,
      ROW_NUMBER() OVER (PARTITION BY userId ORDER BY updatedAt DESC) AS rn
    FROM `shiftsmart-api.shiftsmart_data.bq_background_checks`
    WHERE userId = '{partner_id}'
      AND (
        -- New format (post July 2025)
        (DATE(updatedAt) >= '2025-07-31' AND (
          (result = 'consider' AND webhookEventType = 'report.engaged')
          OR webhookEventType = 'report.pre_adverse_action'
          OR webhookEventType = 'report.post_adverse_action'
        ))
        -- Legacy format (pre July 2025): adverse action events
        OR (DATE(updatedAt) < '2025-07-31' AND webhookEventType IN (
          'report.engaged', 'report.pre_adverse_action', 'report.post_adverse_action'
        ))
      )
  ) WHERE rn = 1
)
SELECT
  b.bgc_status_raw,
  b.bgc_result,
  CAST(b.bgc_created_at AS STRING) AS bgc_started_at,
  CAST(b.bgc_submitted_at AS STRING) AS bgc_updated_at,
  a.bgc_adjudication_event,
  CAST(a.bgc_adjudication_date AS STRING) AS bgc_adjudication_date,
  CASE
    WHEN a.bgc_adjudication_event = 'report.engaged' THEN 'Cleared (Adjudicated)'
    WHEN a.bgc_adjudication_event IN ('report.pre_adverse_action', 'report.post_adverse_action')
      THEN 'Failed (Post-Adverse)'
    WHEN b.bgc_result = 'clear' THEN 'Clear'
    WHEN b.bgc_result = 'consider' THEN 'Consider (Pending Review)'
    WHEN b.bgc_result = 'pending' THEN 'Pending'
    WHEN b.bgc_result = 'suspended' THEN 'Suspended'
    WHEN b.bgc_result = 'cancelled' THEN 'Cancelled'
    ELSE 'Not Submitted'
  END AS bgc_display_status,
  CASE
    WHEN (b.bgc_result = 'clear' AND a.bgc_adjudication_event IS NULL)
      OR a.bgc_adjudication_event = 'report.engaged'
    THEN TRUE ELSE FALSE
  END AS bgc_passed
FROM bgc_latest b
LEFT JOIN bgc_adjudication a ON b.partner_id = a.partner_id
"""
bgc_info = run_query(bgc_sql)

# Deactivation status
deact_sql = f"""
SELECT
  ds,
  is_banned,
  is_deactivated,
  deactivation_level,
  deactivation_company,
  internal_reason,
  CAST(reactivation_date AS STRING) AS reactivation_date
FROM `partner.dim_partner_deactivations`
WHERE partner_id = '{partner_id}'
ORDER BY ds DESC
"""
deact_info = run_query(deact_sql)

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
    bgc_display = str(bgc_row.get("bgc_display_status", "Unknown")).strip()
    bgc_result = str(bgc_row.get("bgc_result", "")).strip()
    bgc_passed = bgc_row.get("bgc_passed", False)
    adj_event = str(bgc_row.get("bgc_adjudication_event", "")).strip()

    if adj_event == "report.engaged":
        cols[4].metric("Background Check", bgc_display, delta="Was Consider → Cleared", delta_color="normal")
    elif adj_event in ("report.pre_adverse_action", "report.post_adverse_action"):
        cols[4].metric("Background Check", bgc_display, delta="Failed", delta_color="inverse")
    elif bgc_passed:
        cols[4].metric("Background Check", bgc_display, delta="Passed", delta_color="normal")
    elif bgc_result == "consider":
        cols[4].metric("Background Check", bgc_display, delta="Review needed", delta_color="inverse")
    elif bgc_result == "pending":
        cols[4].metric("Background Check", bgc_display, delta="In progress", delta_color="off")
    else:
        cols[4].metric("Background Check", bgc_display)

    # BGC date details
    bgc_started = str(bgc_row.get("bgc_started_at", "")).strip()
    bgc_updated = str(bgc_row.get("bgc_updated_at", "")).strip()
    adj_date = str(bgc_row.get("bgc_adjudication_date", "")).strip()

    bgc_dates = []
    if bgc_started and bgc_started not in ("", "None", "nan", "NaT"):
        bgc_dates.append(f"Started: **{bgc_started[:10]}**")
    if bgc_updated and bgc_updated not in ("", "None", "nan", "NaT"):
        bgc_dates.append(f"Last Updated: **{bgc_updated[:10]}**")
    if adj_event and adj_event not in ("", "None", "nan"):
        adj_label = {"report.engaged": "Cleared", "report.pre_adverse_action": "Pre-Adverse",
                     "report.post_adverse_action": "Post-Adverse"}.get(adj_event, adj_event)
        adj_dt = adj_date[:10] if adj_date and adj_date not in ("", "None", "nan", "NaT") else "?"
        bgc_dates.append(f"Adjudication: **{adj_label}** ({adj_dt})")
    if bgc_dates:
        st.caption("BGC: " + " · ".join(bgc_dates))

if len(partner_info) > 1:
    with st.expander(f"Active in {len(partner_info)} companies", expanded=False):
        st.dataframe(
            partner_info[["company_name", "op_date", "last_active_at", "total_shifts_last_4w"]],
            use_container_width=True, hide_index=True
        )

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1B: Deactivation & Reactivation Status
# ══════════════════════════════════════════════════════════════════════════════
if not deact_info.empty:
    st.markdown("")
    st.markdown("##### Deactivation Status")
    # Most recent deactivation record
    latest = deact_info.iloc[0]
    is_banned = latest.get("is_banned", False)
    is_deactivated = latest.get("is_deactivated", False)
    deact_level = latest.get("deactivation_level", "")
    deact_company = latest.get("deactivation_company", "")
    deact_reason = latest.get("internal_reason", "")
    react_date = latest.get("reactivation_date", "")

    dcols = st.columns(4)
    if is_banned:
        dcols[0].metric("Status", "BANNED")
    elif is_deactivated:
        dcols[0].metric("Status", "Deactivated")
    else:
        dcols[0].metric("Status", "Active")

    dcols[1].metric("Level", str(deact_level) if deact_level and str(deact_level) != "None" else "N/A")

    # Map company UUID to name if possible
    deact_company_display = COMPANY_UUIDS.get(str(deact_company), str(deact_company)[:20] if deact_company and str(deact_company) != "None" else "N/A")
    dcols[2].metric("Company", deact_company_display)

    react_display = str(react_date)[:10] if react_date and str(react_date) not in ("", "None", "nan", "NaT") else "Never"
    dcols[3].metric("Last Reactivated", react_display)

    if deact_reason and str(deact_reason) not in ("", "None"):
        st.caption(f"Reason: {deact_reason}")

    # Show full history if multiple records
    if len(deact_info) > 1:
        with st.expander(f"Deactivation history ({len(deact_info)} records)", expanded=False):
            display_deact = deact_info.copy()
            display_deact["deactivation_company"] = display_deact["deactivation_company"].apply(
                lambda x: COMPANY_UUIDS.get(str(x), str(x)[:20] if x and str(x) != "None" else "N/A")
            )
            st.dataframe(display_deact, use_container_width=True, hide_index=True)
else:
    st.markdown("")
    st.markdown("##### Deactivation Status")
    st.success("No deactivation records found — partner is in good standing.")

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1C: Nearby Active Stores (CKP, Pepsi Bev, Pepsi Food)
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("### Nearby Stores")

partner_lat = row.get("partner_lat")
partner_lng = row.get("partner_lng")

NEARBY_COMPANIES = [
    "Circle K - Premium",
    "PepsiCo Beverages",
    "PepsiCo Foods",
]

if pd.notna(partner_lat) and pd.notna(partner_lng):
    # Single query: get 5 closest active stores per company + total within 25mi
    nearby_sql = f"""
    WITH partner_loc AS (
      SELECT ST_GEOGPOINT({partner_lng}, {partner_lat}) AS partner_geo
    ),
    stores_with_dist AS (
      SELECT
        d.company_name,
        d.external_id AS store_number,
        d.city,
        d.state_code,
        ROUND(ST_DISTANCE(p.partner_geo, ST_GEOGPOINT(d.lng, d.lat)) / 1609.34, 1) AS distance_miles,
        d.lat AS store_lat,
        d.lng AS store_lng
      FROM `bi.dim_locations` d
      CROSS JOIN partner_loc p
      WHERE d.is_active = TRUE
        AND d.company_name IN ('Circle K - Premium', 'PepsiCo Beverages', 'PepsiCo Foods')
        AND d.lat IS NOT NULL AND d.lng IS NOT NULL
    ),
    ranked AS (
      SELECT *,
        ROW_NUMBER() OVER (PARTITION BY company_name ORDER BY distance_miles) AS rn,
        COUNT(*) OVER (PARTITION BY company_name) AS total_active_stores,
        COUNTIF(distance_miles <= 25) OVER (PARTITION BY company_name) AS stores_within_25mi
      FROM stores_with_dist
    )
    SELECT
      company_name, store_number, city, state_code,
      distance_miles, total_active_stores, stores_within_25mi
    FROM ranked
    WHERE rn <= 5
    ORDER BY company_name, distance_miles
    """

    with st.spinner("Loading nearby stores..."):
        nearby_stores = run_query(nearby_sql)

    if nearby_stores.empty:
        st.info("No active stores found for CKP, Pepsi Bev, or Pepsi Food.")
    else:
        # Get store numbers for shift lookup
        store_numbers = nearby_stores["store_number"].unique().tolist()
        store_list = ",".join([f"'{s}'" for s in store_numbers])

        # Query L7D shifts and next upcoming shift for these stores
        store_shifts_sql = f"""
        SELECT
          location.external_id AS store_number,
          company_name,
          COUNTIF(shift_date BETWEEN DATE_SUB(CURRENT_DATE, INTERVAL 7 DAY) AND CURRENT_DATE) AS l7d_shifts,
          MIN(CASE WHEN shift_date >= CURRENT_DATE THEN shift_date END) AS next_shift_date
        FROM `bi.fct_shift_assignments`
        WHERE location.external_id IN ({store_list})
          AND company_name IN ('Circle K - Premium', 'PepsiCo Beverages', 'PepsiCo Foods')
          AND shift_date BETWEEN DATE_SUB(CURRENT_DATE, INTERVAL 7 DAY) AND DATE_ADD(CURRENT_DATE, INTERVAL 30 DAY)
        GROUP BY 1, 2
        """
        store_shifts = run_query(store_shifts_sql)

        # Summary metrics: stores within 25mi per company
        summary_cols = st.columns(3)
        for i, comp in enumerate(NEARBY_COMPANIES):
            comp_data = nearby_stores[nearby_stores["company_name"] == comp]
            if not comp_data.empty:
                within_25 = comp_data.iloc[0]["stores_within_25mi"]
                summary_cols[i].metric(
                    comp.replace(" - Premium", ""),
                    f"{int(within_25)} stores within 25mi"
                )
            else:
                summary_cols[i].metric(comp.replace(" - Premium", ""), "0 stores within 25mi")

        st.markdown("")

        # Three columns — one per company — with 5 closest stores
        store_cols = st.columns(3)
        for i, comp in enumerate(NEARBY_COMPANIES):
            with store_cols[i]:
                st.markdown(f"**{comp.replace(' - Premium', '')}**")
                comp_stores = nearby_stores[nearby_stores["company_name"] == comp].copy()
                if comp_stores.empty:
                    st.caption("No active stores")
                    continue

                # Merge shift data
                if not store_shifts.empty:
                    shifts_for_comp = store_shifts[store_shifts["company_name"] == comp]
                    comp_stores = comp_stores.merge(
                        shifts_for_comp[["store_number", "l7d_shifts", "next_shift_date"]],
                        on="store_number", how="left"
                    )
                else:
                    comp_stores["l7d_shifts"] = 0
                    comp_stores["next_shift_date"] = None

                comp_stores["l7d_shifts"] = comp_stores["l7d_shifts"].fillna(0).astype(int)
                comp_stores["next_shift_date"] = comp_stores["next_shift_date"].apply(
                    lambda x: str(x)[:10] if pd.notna(x) and str(x) not in ("None", "NaT") else "—"
                )
                comp_stores["location"] = comp_stores["city"] + ", " + comp_stores["state_code"]

                display = comp_stores[["store_number", "distance_miles", "location", "l7d_shifts", "next_shift_date"]].copy()
                display.columns = ["Store", "Miles", "Location", "L7D Shifts", "Next Shift"]
                st.dataframe(display, use_container_width=True, hide_index=True)
else:
    st.warning("No coordinates available for this partner — cannot calculate nearby stores.")

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
        lambda r: f"{int(r['shifts_completed']) if pd.notna(r['shifts_completed']) else 0}/{int(r['shifts_required']) if pd.notna(r['shifts_required']) else '?'}", axis=1
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
