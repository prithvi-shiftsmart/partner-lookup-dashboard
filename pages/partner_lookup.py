"""Partner Lookup page — view a single partner's full profile."""

import dash
from dash import html, dcc, callback, Input, Output, State, no_update
import dash_ag_grid as dag
import dash_bootstrap_components as dbc
import pandas as pd
from datetime import date, timedelta

from lib.bq import run_query
from lib.constants import COMPANY_UUIDS, COMPANY_OPTIONS
from lib.formatting import (
    format_date, days_ago_text, metric_card, shift_url, partner_url,
    map_company_uuid, map_company_uuids,
)

dash.register_page(__name__, path="/partner", title="Partner Lookup")

# ═══════════════════════════════════════════════════════════════════════════════
# Layout
# ═══════════════════════════════════════════════════════════════════════════════

layout = html.Div([
    # Controls row
    html.Div([
        dbc.Row([
            dbc.Col([
                dbc.Label("Partner ID"),
                dbc.Input(
                    id="partner-id-input",
                    placeholder="e.g. dcdc0d40-7351-416d-...",
                    type="text",
                    debounce=True,
                ),
            ], width=5),
            dbc.Col([
                dbc.Label("History (days back)"),
                dbc.Input(id="days-back", type="number", value=90, min=7, max=365),
            ], width=2),
            dbc.Col([
                dbc.Label("Future (days forward)"),
                dbc.Input(id="days-forward", type="number", value=30, min=7, max=90),
            ], width=2),
            dbc.Col([
                html.Div(style={"height": "22px"}),
                dbc.Button("Load Partner", id="load-partner-btn", color="primary", className="w-100"),
            ], width=2),
        ]),
    ], className="filter-row mt-3"),

    # Loading wrapper for all content
    dcc.Loading(
        type="circle",
        children=html.Div(id="partner-content"),
    ),
])


# ═══════════════════════════════════════════════════════════════════════════════
# Callbacks
# ═══════════════════════════════════════════════════════════════════════════════

@callback(
    Output("partner-id-input", "value"),
    Input("url", "search"),
    prevent_initial_call=False,
)
def prefill_from_url(search):
    """Pre-fill partner ID from URL query param ?id=..."""
    if search:
        params = dict(p.split("=") for p in search.lstrip("?").split("&") if "=" in p)
        return params.get("id", "")
    return ""


@callback(
    Output("partner-content", "children"),
    Input("load-partner-btn", "n_clicks"),
    State("partner-id-input", "value"),
    State("days-back", "value"),
    State("days-forward", "value"),
    prevent_initial_call=True,
)
def load_partner(n_clicks, partner_id, days_back, days_forward):
    if not partner_id or not partner_id.strip():
        return dbc.Alert("Enter a Partner ID to get started.", color="info")

    partner_id = partner_id.strip()
    days_back = int(days_back or 90)
    days_forward = int(days_forward or 30)
    start_date = date.today() - timedelta(days=days_back)
    end_date = date.today() + timedelta(days=days_forward)

    # ── Query partner info ──
    partner_info = run_query(f"""
        SELECT
            partner_id, first_name, last_name, email, phone_number,
            company_name, msa, op_date, last_active_at,
            total_shifts_last_4w, weeks_worked_last_4w,
            partner_lat, partner_lng, user_company_status
        FROM `growth.int_master_partner_throughput`
        WHERE partner_id = '{partner_id}'
    """)

    if partner_info.empty:
        return dbc.Alert(f"Partner `{partner_id}` not found.", color="warning")

    row = partner_info.iloc[0]
    first = row.get("first_name", "")
    last = row.get("last_name", "")

    # ── Query BGC ──
    bgc_info = run_query(f"""
        WITH bgc_latest AS (
            SELECT partner_id, bgc_status_raw, bgc_result, bgc_submitted_at, bgc_created_at
            FROM (
                SELECT userId AS partner_id,
                    status AS bgc_status_raw,
                    COALESCE(result,
                        CASE
                            WHEN status = 'report_clear' THEN 'clear'
                            WHEN status = 'report_consider' THEN 'consider'
                            WHEN status = 'report_pending' THEN 'pending'
                            WHEN status = 'report_suspended' THEN 'suspended'
                            WHEN status = 'report_cancelled' THEN 'cancelled'
                            WHEN status IN ('invitation_expired','invitation_pending','invitation_completed') THEN 'pending'
                            ELSE 'no_bgc'
                        END
                    ) AS bgc_result,
                    updatedAt AS bgc_submitted_at, createdAt AS bgc_created_at,
                    ROW_NUMBER() OVER (PARTITION BY userId ORDER BY updatedAt DESC) AS rn
                FROM `shiftsmart-api.shiftsmart_data.bq_background_checks`
                WHERE userId = '{partner_id}'
            ) WHERE rn = 1
        ),
        bgc_adjudication AS (
            SELECT partner_id, bgc_adjudication_event, bgc_adjudication_date
            FROM (
                SELECT userId AS partner_id,
                    COALESCE(webhookEventType, CASE status WHEN 'report_clear' THEN 'report.engaged' END) AS bgc_adjudication_event,
                    updatedAt AS bgc_adjudication_date,
                    ROW_NUMBER() OVER (PARTITION BY userId ORDER BY updatedAt DESC) AS rn
                FROM `shiftsmart-api.shiftsmart_data.bq_background_checks`
                WHERE userId = '{partner_id}'
                    AND ((DATE(updatedAt) >= '2025-07-31' AND (
                        (result = 'consider' AND webhookEventType = 'report.engaged')
                        OR webhookEventType = 'report.pre_adverse_action'
                        OR webhookEventType = 'report.post_adverse_action'
                    )) OR (DATE(updatedAt) < '2025-07-31' AND webhookEventType IN (
                        'report.engaged','report.pre_adverse_action','report.post_adverse_action'
                    )))
            ) WHERE rn = 1
        )
        SELECT
            b.bgc_result,
            CAST(b.bgc_created_at AS STRING) AS bgc_started_at,
            CAST(b.bgc_submitted_at AS STRING) AS bgc_updated_at,
            a.bgc_adjudication_event,
            CAST(a.bgc_adjudication_date AS STRING) AS bgc_adjudication_date,
            CASE
                WHEN a.bgc_adjudication_event = 'report.engaged' THEN 'Cleared (Adjudicated)'
                WHEN a.bgc_adjudication_event IN ('report.pre_adverse_action','report.post_adverse_action') THEN 'Failed (Post-Adverse)'
                WHEN b.bgc_result = 'clear' THEN 'Clear'
                WHEN b.bgc_result = 'consider' THEN 'Consider (Pending Review)'
                WHEN b.bgc_result = 'pending' THEN 'Pending'
                WHEN b.bgc_result = 'suspended' THEN 'Suspended'
                WHEN b.bgc_result = 'cancelled' THEN 'Cancelled'
                ELSE 'Not Submitted'
            END AS bgc_display_status,
            CASE WHEN (b.bgc_result = 'clear' AND a.bgc_adjudication_event IS NULL) OR a.bgc_adjudication_event = 'report.engaged' THEN TRUE ELSE FALSE END AS bgc_passed
        FROM bgc_latest b
        LEFT JOIN bgc_adjudication a ON b.partner_id = a.partner_id
    """)

    # ── Query deactivation ──
    deact_info = run_query(f"""
        SELECT ds, is_banned, is_deactivated, deactivation_level, deactivation_company,
            internal_reason, CAST(reactivation_date AS STRING) AS reactivation_date
        FROM `partner.dim_partner_deactivations`
        WHERE partner_id = '{partner_id}'
        ORDER BY ds DESC
    """)

    # ── Query pools/tags ──
    tags_info = run_query(f"""
        SELECT tag, title, CAST(updatedAt AS STRING) AS updated_at
        FROM `shiftsmart_data.bq_usercerts_deduped`
        WHERE CAST(user AS STRING) = '{partner_id}'
        ORDER BY title
    """)

    # ── Query roles/certs ──
    roles_info = run_query(f"""
        SELECT reporting_company, assessment_status,
            CAST(ts_account_created AS STRING) AS account_created
        FROM `bi.fct_partner_assessment_status`
        WHERE user_id = '{partner_id}'
    """)

    # ── Query shifts sent ──
    sent_shifts = run_query(f"""
        SELECT
            company, title, status,
            CAST(start AS STRING) AS shift_start,
            CAST(`end` AS STRING) AS shift_end,
            duration, rate,
            CAST(sent_at AS STRING) AS sent_at,
            CAST(seen_at AS STRING) AS seen_at,
            CAST(assigned_at AS STRING) AS assigned_at,
            CAST(confirmed_at AS STRING) AS confirmed_at,
            CAST(completed_at AS STRING) AS completed_at,
            CAST(canceled_at AS STRING) AS canceled_at,
            CAST(declined_at AS STRING) AS declined_at,
            payment_status
        FROM `shiftsmart_data.bq_usershifts_deduped`
        WHERE user = '{partner_id}'
            AND start >= CAST('{start_date}' AS DATETIME)
            AND start < CAST('{end_date}' AS DATETIME)
        ORDER BY start
    """)

    # ── Query bonuses ──
    bonuses = run_query(f"""
        WITH partner_bonuses AS (
            SELECT DISTINCT eu.uuid AS bonus_id
            FROM `shiftsmart_data.bq_payment_bonus_eligible_users` eu
            WHERE eu.user_id = '{partner_id}'
        ),
        bonus_info AS (
            SELECT DISTINCT bp.paymentBonusId, bp.title AS bonus_name, bp.bonusType AS bonus_type,
                bp.amount, bp.count AS shifts_required,
                CAST(bp.validFrom AS STRING) AS valid_from, CAST(bp.validTo AS STRING) AS valid_to,
                bp.companies AS company_uuids, bp.daysToComplete AS days_to_complete
            FROM `shiftsmart_data.bq_payment_bonus_progress` bp
            WHERE bp.paymentBonusId IN (SELECT bonus_id FROM partner_bonuses)
            QUALIFY ROW_NUMBER() OVER (PARTITION BY bp.paymentBonusId ORDER BY bp.updatedAt DESC) = 1
        ),
        partner_progress AS (
            SELECT bp.paymentBonusId, bp.countProgress AS shifts_completed,
                bp.isComplete AS completed, bp.isViewedByWorker AS viewed_by_partner
            FROM `shiftsmart_data.bq_payment_bonus_progress` bp
            WHERE bp.paymentBonusId IN (SELECT bonus_id FROM partner_bonuses)
                AND bp.userId = '{partner_id}'
        )
        SELECT bi.bonus_name, bi.bonus_type, bi.amount, bi.shifts_required,
            IFNULL(pp.shifts_completed, 0) AS shifts_completed,
            IFNULL(pp.completed, false) AS completed,
            pp.viewed_by_partner, bi.valid_from, bi.valid_to, bi.company_uuids
        FROM bonus_info bi
        LEFT JOIN partner_progress pp ON bi.paymentBonusId = pp.paymentBonusId
        ORDER BY bi.valid_from DESC
    """)

    # ── Query shift assignments (with payment) ──
    assignments = run_query(f"""
        SELECT
            company_name, shift_date, shift_id, assignment_status,
            shift.type AS shift_type, shift.is_remote,
            CAST(shift.start AS STRING) AS shift_start,
            CAST(shift.`end` AS STRING) AS shift_end,
            shift.duration,
            location.external_id AS store_number,
            payment.status AS payment_status,
            payment.approval_status AS payment_approval,
            payment.rate AS payment_rate,
            payment.base_amount,
            payment.shift_bonus_amount,
            payment.total_amount
        FROM `bi.fct_shift_assignments`
        WHERE partner_id = '{partner_id}'
            AND shift_date BETWEEN '{start_date}' AND '{end_date}'
        ORDER BY shift_date DESC
    """)

    # ── Nearby stores ──
    partner_lat = row.get("partner_lat")
    partner_lng = row.get("partner_lng")
    nearby_stores = pd.DataFrame()
    if pd.notna(partner_lat) and pd.notna(partner_lng):
        nearby_stores = run_query(f"""
            WITH partner_loc AS (
                SELECT ST_GEOGPOINT({partner_lng}, {partner_lat}) AS partner_geo
            ),
            stores_with_dist AS (
                SELECT d.company_name, d.external_id AS store_number, d.city, d.state_code,
                    ROUND(ST_DISTANCE(p.partner_geo, ST_GEOGPOINT(d.lng, d.lat)) / 1609.34, 1) AS distance_miles
                FROM `bi.dim_locations` d CROSS JOIN partner_loc p
                WHERE d.is_active = TRUE
                    AND d.company_name IN ('Circle K - Premium','PepsiCo Beverages','PepsiCo Foods')
                    AND d.lat IS NOT NULL AND d.lng IS NOT NULL
            ),
            ranked AS (
                SELECT *, ROW_NUMBER() OVER (PARTITION BY company_name ORDER BY distance_miles) AS rn,
                    COUNTIF(distance_miles <= 25) OVER (PARTITION BY company_name) AS stores_within_25mi
                FROM stores_with_dist
            )
            SELECT company_name, store_number, city, state_code, distance_miles, stores_within_25mi
            FROM ranked WHERE rn <= 5
            ORDER BY company_name, distance_miles
        """)

    # ═══════════════════════════════════════════════════════════════════════════
    # Build the page content
    # ═══════════════════════════════════════════════════════════════════════════
    sections = []

    # ── Header ──
    company = row.get("company_name", "N/A")
    email = row.get("email", "")
    phone = row.get("phone_number", "")
    msa = row.get("msa", "")
    last_active = row.get("last_active_at")
    op_date = row.get("op_date")
    shifts_4w = row.get("total_shifts_last_4w", 0)

    sections.append(html.H3(f"{first} {last}"))
    sections.append(html.Small(partner_id, className="text-secondary"))

    contact_parts = []
    if phone:
        contact_parts.append(f"Phone: {phone}")
    if email:
        contact_parts.append(f"Email: {email}")
    if msa:
        contact_parts.append(f"MSA: {msa}")
    if contact_parts:
        sections.append(html.Div(" · ".join(contact_parts), className="contact-info mt-2"))

    # Metric cards
    last_active_str = format_date(last_active)
    last_active_delta = days_ago_text(last_active)
    da_color = "normal" if last_active_delta in ("Today", "Yesterday") or (
        isinstance(last_active, pd.Timestamp) and (pd.Timestamp.now() - last_active).days <= 7
    ) else "inverse"

    bgc_display = "No Record"
    bgc_delta = None
    bgc_delta_color = None
    if not bgc_info.empty:
        br = bgc_info.iloc[0]
        bgc_display = str(br.get("bgc_display_status", "Unknown"))
        adj = str(br.get("bgc_adjudication_event", ""))
        if adj == "report.engaged":
            bgc_delta, bgc_delta_color = "Cleared", "normal"
        elif adj in ("report.pre_adverse_action", "report.post_adverse_action"):
            bgc_delta, bgc_delta_color = "Failed", "inverse"
        elif br.get("bgc_passed"):
            bgc_delta, bgc_delta_color = "Passed", "normal"
        elif str(br.get("bgc_result", "")) == "consider":
            bgc_delta, bgc_delta_color = "Review needed", "inverse"
        elif str(br.get("bgc_result", "")) == "pending":
            bgc_delta, bgc_delta_color = "In progress", "off"

    sections.append(html.Div([
        metric_card("Company", company),
        metric_card("Last Active", last_active_str, delta=last_active_delta, delta_color=da_color),
        metric_card("OP Date", format_date(op_date) if pd.notna(op_date) else "Not oriented"),
        metric_card("Shifts (4 wk)", int(shifts_4w) if pd.notna(shifts_4w) else 0),
        metric_card("Background Check", bgc_display, delta=bgc_delta, delta_color=bgc_delta_color),
    ], className="metrics-row mt-3"))

    # Multi-company info
    if len(partner_info) > 1:
        multi_df = partner_info[["company_name", "op_date", "last_active_at", "total_shifts_last_4w"]].copy()
        multi_df["op_date"] = multi_df["op_date"].apply(format_date)
        multi_df["last_active_at"] = multi_df["last_active_at"].apply(format_date)
        sections.append(
            dbc.Accordion([
                dbc.AccordionItem(
                    _build_grid("multi-company-table", multi_df),
                    title=f"Active in {len(partner_info)} companies",
                )
            ], start_collapsed=True, className="mt-2")
        )

    sections.append(html.Hr())

    # ── Deactivation Status ──
    sections.append(html.Div("Deactivation Status", className="section-header"))
    if not deact_info.empty:
        latest = deact_info.iloc[0]
        is_banned = latest.get("is_banned", False)
        is_deactivated = latest.get("is_deactivated", False)
        status_label = "BANNED" if is_banned else ("Deactivated" if is_deactivated else "Active")
        deact_level = latest.get("deactivation_level", "N/A")
        deact_company = COMPANY_UUIDS.get(str(latest.get("deactivation_company", "")), "N/A")
        react_date = format_date(latest.get("reactivation_date"))
        deact_reason = latest.get("internal_reason", "")

        sections.append(html.Div([
            metric_card("Status", status_label),
            metric_card("Level", str(deact_level) if deact_level and str(deact_level) != "None" else "N/A"),
            metric_card("Company", deact_company),
            metric_card("Last Reactivated", react_date if react_date != "—" else "Never"),
        ], className="metrics-row"))

        if deact_reason and str(deact_reason) not in ("", "None"):
            sections.append(html.Small(f"Reason: {deact_reason}", className="text-secondary"))

        if len(deact_info) > 1:
            deact_display = deact_info.copy()
            deact_display["deactivation_company"] = deact_display["deactivation_company"].apply(
                lambda x: COMPANY_UUIDS.get(str(x), str(x)[:20] if x and str(x) != "None" else "N/A")
            )
            sections.append(
                dbc.Accordion([
                    dbc.AccordionItem(
                        _build_grid("deact-history-table", deact_display),
                        title=f"Deactivation history ({len(deact_info)} records)",
                    )
                ], start_collapsed=True, className="mt-2")
            )
    else:
        sections.append(dbc.Alert("No deactivation records — partner is in good standing.", color="success"))

    sections.append(html.Hr())

    # ── Pools & Tags ──
    sections.append(html.Div("Pools & Certifications", className="section-header"))
    if not tags_info.empty:
        sections.append(html.Div("Certifications / Tags", className="section-subheader"))
        sections.append(_build_grid("tags-table", tags_info))
    if not roles_info.empty:
        sections.append(html.Div("Assessment Status", className="section-subheader mt-3"))
        roles_info["account_created"] = roles_info["account_created"].apply(lambda x: format_date(x))
        sections.append(_build_grid("roles-table", roles_info))
    if tags_info.empty and roles_info.empty:
        sections.append(html.Small("No pool or certification data found.", className="text-secondary"))

    sections.append(html.Hr())

    # ── Nearby Stores ──
    sections.append(html.Div("Nearby Stores", className="section-header"))
    if not nearby_stores.empty:
        store_companies = ["Circle K - Premium", "PepsiCo Beverages", "PepsiCo Foods"]
        store_cols = []
        for comp in store_companies:
            comp_data = nearby_stores[nearby_stores["company_name"] == comp]
            if comp_data.empty:
                store_cols.append(dbc.Col([
                    html.Strong(comp.replace(" - Premium", "")),
                    html.Br(),
                    html.Small("No active stores", className="text-secondary"),
                ], width=4))
            else:
                within_25 = int(comp_data.iloc[0].get("stores_within_25mi", 0))
                display_df = comp_data[["store_number", "distance_miles", "city", "state_code"]].copy()
                display_df.columns = ["Store", "Miles", "City", "State"]
                store_cols.append(dbc.Col([
                    html.Strong(comp.replace(" - Premium", "")),
                    html.Small(f" — {within_25} within 25mi", className="text-secondary"),
                    _build_grid(f"stores-{comp[:3].lower()}", display_df),
                ], width=4))
        sections.append(dbc.Row(store_cols))
    elif pd.isna(partner_lat) or pd.isna(partner_lng):
        sections.append(html.Small("No coordinates available for this partner.", className="text-secondary"))
    else:
        sections.append(html.Small("No active stores found nearby.", className="text-secondary"))

    sections.append(html.Hr())

    # ── Shifts Sent ──
    sections.append(html.Div("Shifts Sent", className="section-header"))
    sections.append(html.Div([
        html.Span("Accepted / Assigned", className="legend-item legend-green"),
        html.Span("Canceled / Declined", className="legend-item legend-red"),
    ], className="legend"))

    if not sent_shifts.empty:
        sent_shifts["company_name"] = sent_shifts["company"].map(COMPANY_UUIDS).fillna(
            sent_shifts["company"].str[:8] + "..."
        )
        sent_shifts["_start_dt"] = pd.to_datetime(sent_shifts["shift_start"], errors="coerce")
        now = pd.Timestamp.now()

        past = sent_shifts[sent_shifts["_start_dt"] < now].sort_values("_start_dt", ascending=False)
        future = sent_shifts[sent_shifts["_start_dt"] >= now].sort_values("_start_dt", ascending=True)

        display_cols = ["company_name", "title", "status", "shift_start", "rate",
                        "sent_at", "seen_at", "assigned_at", "completed_at", "payment_status"]

        # Summary metrics
        total = len(sent_shifts)
        accepted = len(sent_shifts[sent_shifts["status"].isin(["Assigned", "Accepted", "Completed"])])
        seen = len(sent_shifts[sent_shifts["seen_at"].notna() & (sent_shifts["seen_at"] != "None")])
        completed = len(sent_shifts[sent_shifts["completed_at"].notna() & (sent_shifts["completed_at"] != "None")])
        declined = len(sent_shifts[sent_shifts["status"].isin(["Canceled", "Declined"])])

        sections.append(html.Div([
            metric_card("Total", total),
            metric_card("Accepted", accepted),
            metric_card("Seen", seen),
            metric_card("Completed", completed),
            metric_card("Declined/Canceled", declined),
        ], className="metrics-row"))

        show_cols = [c for c in display_cols if c in sent_shifts.columns]
        tabs_content = []
        if not future.empty:
            tabs_content.append(dbc.Tab(
                _build_grid("shifts-future-table", future[show_cols]),
                label=f"Upcoming ({len(future)})",
            ))
        if not past.empty:
            tabs_content.append(dbc.Tab(
                _build_grid("shifts-past-table", past[show_cols]),
                label=f"Past ({len(past)})",
            ))
        sections.append(dbc.Tabs(tabs_content))
    else:
        sections.append(html.Small("No shifts sent in this date range.", className="text-secondary"))

    sections.append(html.Hr())

    # ── Bonuses ──
    sections.append(html.Div("Bonuses", className="section-header"))
    if not bonuses.empty:
        bonuses["companies"] = bonuses["company_uuids"].apply(map_company_uuids)
        bonuses["progress"] = bonuses.apply(
            lambda r: f"{int(r['shifts_completed']) if pd.notna(r['shifts_completed']) else 0}"
                      f"/{int(r['shifts_required']) if pd.notna(r['shifts_required']) else '?'}",
            axis=1
        )
        bonuses["opted_in"] = bonuses["viewed_by_partner"].apply(
            lambda v: "Yes" if v is True else "No"
        )
        bonuses["status"] = bonuses["completed"].apply(
            lambda v: "Complete" if v else "In Progress"
        )
        bonus_cols = ["bonus_name", "bonus_type", "amount", "progress", "status",
                      "opted_in", "valid_from", "valid_to", "companies"]

        sections.append(html.Div([
            metric_card("Total Bonuses", len(bonuses)),
            metric_card("Opted In", len(bonuses[bonuses["opted_in"] == "Yes"])),
            metric_card("Completed", len(bonuses[bonuses["status"] == "Complete"])),
        ], className="metrics-row"))
        sections.append(_build_grid("bonuses-table", bonuses[bonus_cols]))
    else:
        sections.append(html.Small("No bonuses found.", className="text-secondary"))

    sections.append(html.Hr())

    # ── Shift Assignments (with payment) ──
    sections.append(html.Div("Shift Assignments", className="section-header"))
    if not assignments.empty:
        # Payment summary
        total_pay = assignments["total_amount"].sum()
        avg_rate = assignments["payment_rate"].mean()
        sections.append(html.Div([
            metric_card("Assignments", len(assignments)),
            metric_card("Total Pay", f"${total_pay:,.2f}" if pd.notna(total_pay) else "$0"),
            metric_card("Avg Rate", f"${avg_rate:,.2f}/hr" if pd.notna(avg_rate) else "—"),
        ], className="metrics-row"))

        # Add shift link column as markdown
        assignments["shift_link"] = assignments["shift_id"].apply(
            lambda sid: f"[View](/shifts?shift_id={sid})" if pd.notna(sid) else ""
        )

        assign_cols = [
            {"field": "company_name", "headerName": "Company", "width": 150},
            {"field": "shift_date", "headerName": "Date", "width": 110},
            {"field": "assignment_status", "headerName": "Status", "width": 110},
            {"field": "shift_type", "headerName": "Type", "width": 100},
            {"field": "shift_start", "headerName": "Start", "width": 140},
            {"field": "shift_end", "headerName": "End", "width": 140},
            {"field": "store_number", "headerName": "Store", "width": 90},
            {"field": "payment_status", "headerName": "Pay Status", "width": 100},
            {"field": "payment_approval", "headerName": "Pay Approval", "width": 110},
            {"field": "payment_rate", "headerName": "Rate", "width": 80,
             "valueFormatter": {"function": "params.value ? '$' + Number(params.value).toFixed(2) : '—'"}},
            {"field": "base_amount", "headerName": "Base", "width": 90,
             "valueFormatter": {"function": "params.value ? '$' + Number(params.value).toFixed(2) : '—'"}},
            {"field": "total_amount", "headerName": "Total", "width": 90,
             "valueFormatter": {"function": "params.value ? '$' + Number(params.value).toFixed(2) : '—'"}},
            {"field": "shift_link", "headerName": "", "cellRenderer": "markdown", "width": 70},
        ]

        sections.append(dag.AgGrid(
            id="assignments-grid",
            rowData=assignments.to_dict("records"),
            columnDefs=assign_cols,
            defaultColDef={"resizable": True, "sortable": True, "filter": "agSetColumnFilter", "minWidth": 60},
            dashGridOptions={"pagination": True, "paginationPageSize": 25, "animateRows": True},
            style={"height": "400px"},
            className="ag-theme-alpine-dark",
        ))
    else:
        sections.append(html.Small("No shift assignments in this date range.", className="text-secondary"))

    return html.Div(sections)


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _build_grid(grid_id, df, link_columns=None, height=None):
    """Build a styled AG Grid from a DataFrame."""
    if df.empty:
        return html.Small("No data.", className="text-muted")

    display_df = df.copy()
    for col in display_df.columns:
        display_df[col] = display_df[col].apply(
            lambda x: "" if pd.isna(x) or str(x) in ("None", "NaT", "nan") else x
        )

    col_defs = []
    for col in display_df.columns:
        if col.startswith("_"):
            continue
        col_def = {
            "field": col,
            "headerName": col.replace("_", " ").title(),
            "resizable": True,
            "sortable": True,
            "filter": "agSetColumnFilter",
        }
        if link_columns and col in link_columns:
            col_def["headerName"] = link_columns[col]
            col_def["cellRenderer"] = "markdown"
            display_df[col] = display_df[col].apply(
                lambda x: f"[View]({x})" if x else ""
            )
        col_defs.append(col_def)

    grid_opts = {"pagination": True, "paginationPageSize": 25, "animateRows": True}
    if height is None:
        grid_opts["domLayout"] = "autoHeight"

    return dag.AgGrid(
        id=grid_id,
        rowData=display_df.to_dict("records"),
        columnDefs=col_defs,
        defaultColDef={"resizable": True, "sortable": True, "filter": "agSetColumnFilter", "minWidth": 70},
        dashGridOptions=grid_opts,
        style={"height": f"{height}px"} if height else {},
        className="ag-theme-alpine-dark",
    )
