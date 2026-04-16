"""Market Shifts page — view shifts for a given market/zone/store."""

import dash
from dash import html, dcc, callback, Input, Output, State, no_update
import dash_ag_grid as dag
import dash_bootstrap_components as dbc
import pandas as pd
from datetime import date, timedelta

from lib.bq import run_query, get_cached_zones, refresh_zones_from_bq
from lib.constants import COMPANY_OPTIONS
from lib.formatting import metric_card, format_date

dash.register_page(__name__, path="/shifts", title="Market Shifts")

# ═══════════════════════════════════════════════════════════════════════════════
# Layout
# ═══════════════════════════════════════════════════════════════════════════════

layout = html.Div([
    html.H3("Market Shifts"),

    # Filters
    html.Div([
        dbc.Row([
            dbc.Col([
                dbc.Label("Company"),
                dcc.Dropdown(
                    id="shifts-company",
                    options=[{"label": c, "value": c} for c in COMPANY_OPTIONS],
                    value="Circle K - Premium",
                ),
            ], width=2),
            dbc.Col([
                dbc.Label("Zone"),
                dcc.Dropdown(id="shifts-zone", placeholder="Select zone"),
            ], width=3),
            dbc.Col([
                dbc.Label("Store #"),
                dbc.Input(id="shifts-store", placeholder="Optional", type="text", size="sm"),
            ], width=2),
            dbc.Col([
                dbc.Label("Start"),
                dcc.DatePickerSingle(
                    id="shifts-start-date",
                    date=date.today() - timedelta(days=7),
                    display_format="YYYY-MM-DD",
                ),
            ], width=2),
            dbc.Col([
                dbc.Label("End"),
                dcc.DatePickerSingle(
                    id="shifts-end-date",
                    date=date.today() + timedelta(days=7),
                    display_format="YYYY-MM-DD",
                ),
            ], width=2),
            dbc.Col([
                html.Div(style={"height": "22px"}),
                dbc.Button("Load Shifts", id="load-shifts-btn", color="primary", className="w-100"),
            ], width=1),
        ]),
    ], className="filter-row mt-3"),

    # Status filter
    dbc.Row([
        dbc.Col([
            dcc.Dropdown(
                id="shifts-status-filter",
                options=[
                    {"label": s, "value": s}
                    for s in ["Completed", "Assigned", "Canceled", "No Show"]
                ],
                multi=True,
                placeholder="Filter by completion status",
            ),
        ], width=5),
    ], className="mb-3"),

    # Content
    dcc.Loading(
        type="circle",
        children=[
            html.Div(id="shifts-metrics"),
            html.Div(id="shifts-content"),
        ],
    ),

    # Shift detail modal
    dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle(id="shift-detail-title")),
        dbc.ModalBody(id="shift-detail-body"),
    ], id="shift-detail-modal", size="lg", is_open=False),

    dcc.Store(id="shifts-data-store"),
])


# ═══════════════════════════════════════════════════════════════════════════════
# Callbacks
# ═══════════════════════════════════════════════════════════════════════════════

@callback(
    Output("shifts-zone", "options"),
    Input("shifts-company", "value"),
)
def populate_zones(company):
    """Load zones from disk cache, or fetch from BQ if not cached."""
    if not company:
        return []
    zones = get_cached_zones(company)
    if zones is None:
        zones = refresh_zones_from_bq(company)
    # zones is already [{"label": "City | Zone", "value": "zone_desc"}, ...]
    return zones if zones else []


@callback(
    Output("shifts-data-store", "data"),
    Input("load-shifts-btn", "n_clicks"),
    State("shifts-company", "value"),
    State("shifts-zone", "value"),
    State("shifts-store", "value"),
    State("shifts-start-date", "date"),
    State("shifts-end-date", "date"),
    prevent_initial_call=True,
)
def load_shifts(n_clicks, company, zone, store, start_date, end_date):
    if not company:
        return None

    where_parts = [
        f"company_name = '{company}'",
        f"shift_date BETWEEN '{start_date}' AND '{end_date}'",
    ]

    if zone:
        where_parts.append(f"""location.store_cluster IN (
            SELECT DISTINCT store_cluster FROM `growth.supply_model_daily_position`
            WHERE zone_description = '{zone}' AND company_name = '{company}'
        )""")

    if store and store.strip():
        where_parts.append(f"location.external_id = '{store.strip()}'")

    sql = f"""
        SELECT
            company_name, shift_date, shift_id, shift_title,
            shift.type AS shift_type,
            CAST(shift.start AS STRING) AS shift_time,
            CAST(shift.`end` AS STRING) AS shift_end,
            location.external_id AS store_number,
            location.store_cluster AS zone,
            location.saved_location_name AS store_name,
            partner_id,
            CONCAT(IFNULL(partner.first_name,''), ' ', IFNULL(partner.last_name,'')) AS partner_name,
            assignment_status,
            CASE
                WHEN assignment.is_completed THEN 'Completed'
                WHEN assignment.is_noshow THEN 'No Show'
                WHEN assignment.is_canceled THEN 'Canceled'
                ELSE 'Assigned'
            END AS completion_status,
            payment.rate,
            payment.base_amount AS base_pay,
            IFNULL(payment.shift_bonus_amount, 0) AS bonus,
            payment.total_amount AS total_pay,
            payment.approval_status AS payment_approval,
            payment.status AS payment_status
        FROM `bi.fct_shift_assignments`
        WHERE {" AND ".join(where_parts)}
        ORDER BY shift_date, shift.start
        LIMIT 2000
    """

    df = run_query(sql)
    if df.empty:
        return None

    for col in df.columns:
        if hasattr(df[col], "dt"):
            df[col] = df[col].apply(lambda x: str(x) if pd.notna(x) else None)

    return df.to_dict("records")


@callback(
    Output("shifts-metrics", "children"),
    Output("shifts-content", "children"),
    Input("shifts-data-store", "data"),
    Input("shifts-status-filter", "value"),
)
def render_shifts(data, status_filter):
    if not data:
        return "", dbc.Alert("Select filters and click Load Shifts.", color="info")

    df = pd.DataFrame(data)

    if status_filter:
        df = df[df["completion_status"].isin(status_filter)]

    if df.empty:
        return "", dbc.Alert("No shifts match the selected filters.", color="warning")

    # Metrics
    total = len(df)
    completed = len(df[df["completion_status"] == "Completed"])
    noshows = len(df[df["completion_status"] == "No Show"])
    fill_rate = completed / total * 100 if total > 0 else 0
    total_pay = df["total_pay"].sum()

    metrics = html.Div([
        metric_card("Total Shifts", f"{total:,}"),
        metric_card("Completed", f"{completed:,}"),
        metric_card("Fill Rate", f"{fill_rate:.1f}%"),
        metric_card("No Shows", f"{noshows:,}"),
        metric_card("Total Pay", f"${total_pay:,.2f}" if pd.notna(total_pay) else "$0"),
    ], className="metrics-row mt-3")

    # Build display data with links
    display_df = df.copy()

    display_df["partner_link"] = display_df.apply(
        lambda r: f"[{r.get('partner_name','').strip()}](/partner?id={r['partner_id']})"
        if r.get("partner_id") and r.get("partner_name", "").strip()
        else "—",
        axis=1
    )

    display_df["store_link"] = display_df.apply(
        lambda r: f"[{r.get('store_number','')}](/shifts?company={r.get('company_name','')}&store={r.get('store_number','')})"
        if r.get("store_number")
        else "—",
        axis=1
    )

    display_df["shift_link"] = display_df.apply(
        lambda r: f"[Detail](/shifts?shift_id={r['shift_id']})"
        if r.get("shift_id")
        else "",
        axis=1
    )

    # Format times
    for col in ["shift_time", "shift_end"]:
        display_df[col] = display_df[col].apply(lambda x: str(x)[:16] if x else "—")

    columns = [
        {"field": "company_name", "headerName": "Company", "width": 150},
        {"field": "shift_date", "headerName": "Date", "width": 110},
        {"field": "store_link", "headerName": "Store", "cellRenderer": "markdown", "width": 100},
        {"field": "store_name", "headerName": "Store Name", "width": 160},
        {"field": "shift_title", "headerName": "Shift", "width": 180},
        {"field": "shift_type", "headerName": "Type", "width": 100},
        {"field": "shift_time", "headerName": "Start", "width": 140},
        {"field": "shift_end", "headerName": "End", "width": 140},
        {"field": "rate", "headerName": "Rate", "width": 80,
         "valueFormatter": {"function": "params.value ? '$' + Number(params.value).toFixed(2) : '—'"}},
        {"field": "base_pay", "headerName": "Base Pay", "width": 95,
         "valueFormatter": {"function": "params.value ? '$' + Number(params.value).toFixed(2) : '—'"}},
        {"field": "bonus", "headerName": "Bonus", "width": 80,
         "valueFormatter": {"function": "params.value ? '$' + Number(params.value).toFixed(2) : '—'"}},
        {"field": "total_pay", "headerName": "Total Pay", "width": 100,
         "valueFormatter": {"function": "params.value ? '$' + Number(params.value).toFixed(2) : '—'"}},
        {"field": "payment_approval", "headerName": "Pay Approval", "width": 120},
        {"field": "payment_status", "headerName": "Pay Status", "width": 100},
        {"field": "assignment_status", "headerName": "Assignment", "width": 110},
        {"field": "partner_link", "headerName": "Partner", "cellRenderer": "markdown", "width": 180},
        {"field": "completion_status", "headerName": "Completion", "width": 110},
        {"field": "shift_link", "headerName": "", "cellRenderer": "markdown", "width": 70},
    ]

    content = html.Div([
        html.Small(f"Showing {len(display_df):,} shifts", className="text-muted mb-2 d-block"),
        dag.AgGrid(
            id="shifts-grid",
            rowData=display_df.to_dict("records"),
            columnDefs=columns,
            defaultColDef={"resizable": True, "sortable": True, "filter": "agSetColumnFilter", "minWidth": 60},
            dashGridOptions={
                "pagination": True,
                "paginationPageSize": 50,
                "animateRows": True,
            },
            style={"height": "600px"},
            className="ag-theme-alpine-dark",
            csvExportParams={"fileName": "market_shifts.csv"},
        ),
    ])

    return metrics, content


@callback(
    Output("shift-detail-modal", "is_open"),
    Output("shift-detail-title", "children"),
    Output("shift-detail-body", "children"),
    Input("url", "search"),
    prevent_initial_call=True,
)
def show_shift_detail(search):
    if not search:
        return False, "", ""

    params = dict(p.split("=", 1) for p in search.lstrip("?").split("&") if "=" in p)
    shift_id = params.get("shift_id")
    if not shift_id:
        return False, "", ""

    df = run_query(f"""
        SELECT
            company_name, shift_date, shift_id, shift_title,
            shift.type AS shift_type,
            CAST(shift.start AS STRING) AS shift_start,
            CAST(shift.`end` AS STRING) AS shift_end,
            shift.duration,
            location.external_id AS store_number,
            location.saved_location_name AS store_name,
            location.store_cluster AS zone,
            partner_id,
            CONCAT(IFNULL(partner.first_name,''), ' ', IFNULL(partner.last_name,'')) AS partner_name,
            assignment_status,
            assignment.is_completed, assignment.is_noshow, assignment.is_canceled,
            payment.rate, payment.base_amount, payment.shift_bonus_amount,
            payment.total_amount, payment.approval_status, payment.status AS payment_status,
            CAST(attendance.check_in_at AS STRING) AS check_in,
            CAST(attendance.check_out_at AS STRING) AS check_out
        FROM `bi.fct_shift_assignments`
        WHERE shift_id = '{shift_id}'
        LIMIT 1
    """)

    if df.empty:
        return True, "Shift Not Found", dbc.Alert(f"No data for shift {shift_id}.", color="warning")

    r = df.iloc[0]
    pid = r.get("partner_id", "")
    pname = r.get("partner_name", "").strip()

    body = dbc.Row([
        dbc.Col([
            html.H6("Shift Info", className="text-accent"),
            _detail_row("Title", r.get("shift_title")),
            _detail_row("Type", r.get("shift_type")),
            _detail_row("Date", r.get("shift_date")),
            _detail_row("Time", f"{format_date(r.get('shift_start'), True)} → {format_date(r.get('shift_end'), True)}"),
            _detail_row("Duration", f"{r.get('duration', '—')} hrs"),
        ], width=4),
        dbc.Col([
            html.H6("Location", className="text-accent"),
            _detail_row("Store", r.get("store_number")),
            _detail_row("Name", r.get("store_name")),
            _detail_row("Zone", r.get("zone")),
        ], width=4),
        dbc.Col([
            html.H6("Assignment", className="text-accent"),
            _detail_row("Status", r.get("assignment_status")),
            html.Div([
                html.Small("Partner: ", className="text-muted"),
                dcc.Link(pname, href=f"/partner?id={pid}", target="_blank") if pid else html.Span("—"),
            ], className="mb-1"),
            _detail_row("Check-in", format_date(r.get("check_in"), True)),
            _detail_row("Check-out", format_date(r.get("check_out"), True)),
            html.Hr(),
            html.H6("Payment", className="text-accent"),
            _detail_row("Rate", f"${r.get('rate', 0):.2f}/hr" if pd.notna(r.get("rate")) else "—"),
            _detail_row("Base", f"${r.get('base_amount', 0):.2f}" if pd.notna(r.get("base_amount")) else "—"),
            _detail_row("Bonus", f"${r.get('shift_bonus_amount', 0):.2f}" if pd.notna(r.get("shift_bonus_amount")) else "—"),
            _detail_row("Total", f"${r.get('total_amount', 0):.2f}" if pd.notna(r.get("total_amount")) else "—"),
            _detail_row("Approval", r.get("approval_status")),
            _detail_row("Status", r.get("payment_status")),
        ], width=4),
    ])

    return True, f"Shift: {r.get('shift_title', shift_id)}", body


def _detail_row(label, value):
    return html.Div([
        html.Small(f"{label}: ", className="text-muted"),
        html.Span(str(value) if value and str(value) not in ("None", "nan") else "—"),
    ], style={"fontSize": "0.85rem", "marginBottom": "4px"})
