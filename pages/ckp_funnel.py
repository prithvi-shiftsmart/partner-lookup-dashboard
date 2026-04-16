"""CKP Partner Funnel page — cohort summary + interactive partner roster."""

import dash
from dash import html, dcc, callback, Input, Output, State, no_update
import dash_ag_grid as dag
import dash_bootstrap_components as dbc
import pandas as pd

from lib.bq import run_query
from lib.constants import COHORT_MAP, L1_GROUPS, CRM_COHORT_OPTIONS
from lib.formatting import metric_card, format_date

dash.register_page(__name__, path="/funnel", title="CKP Partner Funnel")

# ═══════════════════════════════════════════════════════════════════════════════
# SQL — falls back gracefully if Drive-backed tables are inaccessible
# ═══════════════════════════════════════════════════════════════════════════════

FUNNEL_SQL = """
SELECT
    p.partner_id, first_name, last_name, phone_number, email,
    city_description AS city, zone_description, closest_store_cluster,
    ROUND(closest_store_proximity_miles, 1) AS closest_store_miles,
    created_date AS dl_date, oa_date, oa_shift_type, op_date, op_shift_type,
    s1a_date, s1c_date, m1_date, last_active_at,
    churn_status, ROUND(churn_probability, 3) AS churn_probability,
    shifts_worked_last_7d, shifts_assigned_next_7d,
    days_since_last_shift_worked, total_shifts_last_4w, volume_label_current,
    currently_suspended, currently_deactivated, is_fraud_partner,
    ROUND(rolling_l50shifts_reliability_score, 3) AS reliability_score,
    ROUND(evfr_score, 3) AS evfr_score,
    ROUND(pct_shift_success, 3) AS pct_shift_success,
    partner_role_tier,
    CASE WHEN LOWER(partner_role_tier) LIKE '%m1%' THEN 1 ELSE 0 END AS is_m1,
    bgc_result, bgc_adjudication_event,
    work_shifts_sent_l7d, work_shifts_accepted_l7d,
    work_shifts_sent_next_7d, work_shifts_seen_next_7d,
    lifetime_ckp_food_shifts,
    ckp_food_completed_flag AS completed_ckp_shifts,
    priority_cohort_l1, priority_cohort_l2,
    partner_cohort
FROM `growth.int_master_partner_throughput` p
WHERE company_name = 'Circle K - Premium'
    AND priority_cohort_l2 IN (
        'C1: Subscale Deep Dives', 'C2a: FR<80 (Any)', 'C2b: StoreSmart Alpha',
        'C2c: T25, FR 80-90%', 'C2d: CL Launch N3W',
        'C3a: Scale, Health Low/Med', 'C3b: Subscale, Health Low/Med',
        'C3c: Scale, No Health, Zone FR 80-95%', 'C3d: Subscale, No Health, Zone FR 80-90%'
    )
    AND last_active_at >= DATETIME_SUB(CURRENT_DATETIME('America/New_York'), INTERVAL 14 DAY)
ORDER BY partner_cohort ASC, city, closest_store_miles ASC
"""

# Full query with Drive-backed tables for overrides
FUNNEL_SQL_FULL = """
WITH cleared_users AS (
    SELECT DISTINCT CAST(user AS STRING) AS partner_id, title AS cert_title
    FROM `shiftsmart-api.shiftsmart_data.bq_usercerts_deduped`
    WHERE tag = '2d0ec64c-6b29-40a9-a1d2-a4942c437bf3'
)
SELECT
    p.partner_id, first_name, last_name, phone_number, email,
    city_description AS city, zone_description, closest_store_cluster,
    ROUND(closest_store_proximity_miles, 1) AS closest_store_miles,
    created_date AS dl_date, oa_date, oa_shift_type, op_date, op_shift_type,
    s1a_date, s1c_date, m1_date, last_active_at,
    churn_status, ROUND(churn_probability, 3) AS churn_probability,
    shifts_worked_last_7d, shifts_assigned_next_7d,
    days_since_last_shift_worked, total_shifts_last_4w, volume_label_current,
    currently_suspended, currently_deactivated, is_fraud_partner,
    ROUND(rolling_l50shifts_reliability_score, 3) AS reliability_score,
    ROUND(evfr_score, 3) AS evfr_score,
    ROUND(pct_shift_success, 3) AS pct_shift_success,
    partner_role_tier,
    CASE WHEN LOWER(partner_role_tier) LIKE '%m1%' THEN 1 ELSE 0 END AS is_m1,
    bgc_result,
    CASE WHEN o.partner_id IS NOT NULL THEN 'report.pre_adverse_action'
         ELSE bgc_adjudication_event END AS bgc_adjudication_event,
    work_shifts_sent_l7d, work_shifts_accepted_l7d,
    work_shifts_sent_next_7d, work_shifts_seen_next_7d,
    lifetime_ckp_food_shifts,
    ckp_food_completed_flag AS completed_ckp_shifts,
    priority_cohort_l1, priority_cohort_l2,
    CASE
        WHEN o.partner_id IS NOT NULL THEN '25_former_failed_bgc'
        WHEN c.partner_id IS NOT NULL AND partner_cohort = '12_op_bgc_consider'
            THEN IF(IFNULL(work_shifts_sent_next_7d,0)>0,'10_bgc_passed_sent_not_seen','11_bgc_passed_not_sent')
        ELSE partner_cohort
    END AS partner_cohort
FROM `growth.int_master_partner_throughput` p
LEFT JOIN `growth.bgc_pre_adverse_action_override` o ON p.partner_id = o.partner_id
LEFT JOIN cleared_users c ON p.partner_id = c.partner_id
WHERE company_name = 'Circle K - Premium'
    AND priority_cohort_l2 IN (
        'C1: Subscale Deep Dives', 'C2a: FR<80 (Any)', 'C2b: StoreSmart Alpha',
        'C2c: T25, FR 80-90%', 'C2d: CL Launch N3W',
        'C3a: Scale, Health Low/Med', 'C3b: Subscale, Health Low/Med',
        'C3c: Scale, No Health, Zone FR 80-95%', 'C3d: Subscale, No Health, Zone FR 80-90%'
    )
    AND last_active_at >= DATETIME_SUB(CURRENT_DATETIME('America/New_York'), INTERVAL 14 DAY)
ORDER BY partner_cohort ASC, city, closest_store_miles ASC
"""


# ═══════════════════════════════════════════════════════════════════════════════
# Layout
# ═══════════════════════════════════════════════════════════════════════════════

layout = html.Div([
    html.H3("CKP Partner Funnel"),
    html.Small("Partners active in L14D across priority markets.", className="text-muted"),

    # Filters
    html.Div([
        dbc.Row([
            dbc.Col([
                dbc.Label("Market Cohort"),
                dcc.Dropdown(
                    id="funnel-crm-filter",
                    options=[{"label": c, "value": c} for c in CRM_COHORT_OPTIONS],
                    multi=True,
                    placeholder="All cohorts",
                ),
            ], width=5),
            dbc.Col([
                dbc.Label("Zone"),
                dcc.Dropdown(id="funnel-zone-filter", placeholder="All zones"),
            ], width=3),
            dbc.Col([
                dbc.Label("City"),
                dcc.Dropdown(id="funnel-city-filter", placeholder="All cities"),
            ], width=2),
            dbc.Col([
                html.Div(style={"height": "22px"}),
                dbc.Button("Load Funnel", id="load-funnel-btn", color="primary", className="w-100"),
            ], width=2),
        ]),
    ], className="filter-row mt-3"),

    # Loading wrapper
    dcc.Loading(
        type="circle",
        children=[
            html.Div(id="funnel-metrics"),
            html.Div(id="funnel-summary"),
            html.Div(id="funnel-roster"),
        ],
    ),

    dcc.Store(id="funnel-data-store"),
])


# ═══════════════════════════════════════════════════════════════════════════════
# Callbacks
# ═══════════════════════════════════════════════════════════════════════════════

@callback(
    Output("funnel-data-store", "data"),
    Output("funnel-zone-filter", "options"),
    Output("funnel-city-filter", "options"),
    Input("load-funnel-btn", "n_clicks"),
    prevent_initial_call=True,
)
def load_funnel_data(n_clicks):
    """Load funnel data — try full query first, fall back to simple if Drive tables fail."""
    df = run_query(FUNNEL_SQL_FULL)
    if df.empty:
        # Fallback: query without Drive-backed tables
        df = run_query(FUNNEL_SQL)

    if df.empty:
        return None, [], []

    # Serialize dates for JSON
    for col in df.columns:
        if hasattr(df[col], "dt"):
            df[col] = df[col].apply(lambda x: str(x) if pd.notna(x) else None)
        elif df[col].dtype == "object":
            df[col] = df[col].apply(lambda x: str(x) if pd.notna(x) and str(x) not in ("None", "NaT") else None)

    zones = sorted(df["zone_description"].dropna().unique().tolist())
    cities = sorted(df["city"].dropna().unique().tolist())

    return (
        df.to_dict("records"),
        [{"label": z, "value": z} for z in zones],
        [{"label": c, "value": c} for c in cities],
    )


@callback(
    Output("funnel-metrics", "children"),
    Output("funnel-summary", "children"),
    Output("funnel-roster", "children"),
    Input("funnel-data-store", "data"),
    Input("funnel-crm-filter", "value"),
    Input("funnel-zone-filter", "value"),
    Input("funnel-city-filter", "value"),
)
def render_funnel(data, crm_filter, zone_filter, city_filter):
    if not data:
        return "", dbc.Alert("Click Load Funnel to begin.", color="info"), ""

    df = pd.DataFrame(data)

    # Apply filters
    if crm_filter:
        df = df[df["priority_cohort_l2"].isin(crm_filter)]
    if zone_filter:
        df = df[df["zone_description"] == zone_filter]
    if city_filter:
        df = df[df["city"] == city_filter]

    if df.empty:
        return "", dbc.Alert("No partners match the selected filters.", color="warning"), ""

    # ── Pipeline metrics ──
    def count_l1(group_name):
        codes = [code for code, (_, grp, _) in COHORT_MAP.items() if grp == group_name]
        return len(df[df["partner_cohort"].isin(codes)])

    total = len(df)
    metrics = html.Div([
        metric_card("Total Pipeline", f"{total:,}"),
        metric_card("S1C Assigned", f"{count_l1('S1C, Assigned'):,}"),
        metric_card("S1C Not Assigned", f"{count_l1('S1C, Not Assigned'):,}"),
        metric_card("BGC Passed", f"{count_l1('BGC Passed, Not S1C'):,}"),
        metric_card("OP Pending BGC", f"{count_l1('OP, Not BGC Finalized'):,}"),
        metric_card("Pre-OP", f"{count_l1('OA, Not OP') + count_l1('Not OA'):,}"),
    ], className="metrics-row mt-3")

    # ── Cohort summary ──
    summary_items = []
    for group_name, bg_color, fg_color in L1_GROUPS:
        group_codes = sorted([
            (code, label, action)
            for code, (label, grp, action) in COHORT_MAP.items()
            if grp == group_name
        ])

        group_count = len(df[df["partner_cohort"].isin([c for c, _, _ in group_codes])])
        if group_count == 0:
            continue

        summary_items.append(
            html.Div(
                f"{group_name} — {group_count:,} partners",
                className="cohort-group-header",
                style={"backgroundColor": bg_color, "color": fg_color},
            )
        )

        rows = []
        for code, label, action in group_codes:
            count = len(df[df["partner_cohort"] == code])
            if count == 0:
                continue
            rows.append({"Cohort": label, "Action": action, "Partners": count, "%": round(count / total * 100, 1)})

        if rows:
            summary_items.append(
                dag.AgGrid(
                    rowData=rows,
                    columnDefs=[
                        {"field": "Cohort", "flex": 2},
                        {"field": "Action", "flex": 2},
                        {"field": "Partners", "width": 100},
                        {"field": "%", "width": 80},
                    ],
                    defaultColDef={"resizable": True, "sortable": True},
                    dashGridOptions={"domLayout": "autoHeight", "suppressPaginationPanel": True},
                    className="ag-theme-alpine-dark",
                    style={"marginBottom": "8px"},
                )
            )

    summary = html.Div(summary_items, className="mt-3")

    # ── Partner roster ──
    display_df = df.copy()

    # Partner link as markdown
    display_df["partner"] = display_df.apply(
        lambda r: f"[{r.get('first_name', '')} {r.get('last_name', '')}](/partner?id={r['partner_id']})",
        axis=1
    )

    # Format dates
    for col in ["dl_date", "oa_date", "op_date", "s1a_date", "s1c_date", "m1_date", "last_active_at"]:
        if col in display_df.columns:
            display_df[col] = display_df[col].apply(format_date)

    roster_cols = [
        {"field": "partner", "headerName": "Partner", "cellRenderer": "markdown", "width": 180, "pinned": "left"},
        {"field": "city", "headerName": "City", "width": 140},
        {"field": "zone_description", "headerName": "Zone", "width": 160},
        {"field": "closest_store_miles", "headerName": "Miles", "width": 80},
        {"field": "partner_cohort", "headerName": "Cohort", "width": 200},
        {"field": "op_date", "headerName": "OP Date", "width": 110},
        {"field": "s1c_date", "headerName": "S1C Date", "width": 110},
        {"field": "last_active_at", "headerName": "Last Active", "width": 110},
        {"field": "shifts_worked_last_7d", "headerName": "Shifts L7D", "width": 95},
        {"field": "shifts_assigned_next_7d", "headerName": "Assigned N7D", "width": 110},
        {"field": "work_shifts_sent_next_7d", "headerName": "Sent N7D", "width": 95},
        {"field": "work_shifts_seen_next_7d", "headerName": "Seen N7D", "width": 95},
        {"field": "bgc_result", "headerName": "BGC", "width": 90},
        {"field": "partner_role_tier", "headerName": "M1 Tier", "width": 130},
        {"field": "churn_status", "headerName": "Churn", "width": 100},
        {"field": "priority_cohort_l2", "headerName": "CRM Cohort", "width": 180},
    ]

    roster = html.Div([
        html.Div("Partner Roster", className="section-header"),
        html.Small(f"{len(display_df):,} partners", className="text-muted"),
        dag.AgGrid(
            id="funnel-roster-grid",
            rowData=display_df.to_dict("records"),
            columnDefs=roster_cols,
            defaultColDef={"resizable": True, "sortable": True, "filter": "agSetColumnFilter", "minWidth": 70},
            dashGridOptions={
                "pagination": True,
                "paginationPageSize": 50,
                "animateRows": True,
            },
            style={"height": "600px"},
            className="ag-theme-alpine-dark",
            csvExportParams={"fileName": "ckp_funnel_roster.csv"},
        ),
    ], className="mt-3")

    return metrics, summary, roster
