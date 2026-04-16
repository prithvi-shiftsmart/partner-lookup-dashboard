"""Zone / Store Summary page — shifts aggregated by zone and store."""

import dash
from dash import html, dcc, callback, Input, Output, State, no_update
import dash_ag_grid as dag
import dash_bootstrap_components as dbc
import pandas as pd
from datetime import date, timedelta

from lib.bq import run_query, get_cached_zones, refresh_zones_from_bq
from lib.constants import COMPANY_OPTIONS
from lib.formatting import metric_card

dash.register_page(__name__, path="/zones", title="Zone / Store Summary")

layout = html.Div([
    html.H3("Zone / Store Summary"),

    # Filters
    html.Div([
        dbc.Row([
            dbc.Col([
                dbc.Label("Company"),
                dcc.Dropdown(
                    id="zones-company",
                    options=[{"label": c, "value": c} for c in COMPANY_OPTIONS],
                    value="Circle K - Premium",
                ),
            ], width=3),
            dbc.Col([
                dbc.Label("Start"),
                dcc.DatePickerSingle(
                    id="zones-start-date",
                    date=date.today() - timedelta(days=7),
                    display_format="YYYY-MM-DD",
                ),
            ], width=2),
            dbc.Col([
                dbc.Label("End"),
                dcc.DatePickerSingle(
                    id="zones-end-date",
                    date=date.today(),
                    display_format="YYYY-MM-DD",
                ),
            ], width=2),
            dbc.Col([
                dbc.Label("Zone"),
                dcc.Dropdown(id="zones-zone-filter", placeholder="All zones"),
            ], width=3),
            dbc.Col([
                html.Div(style={"height": "22px"}),
                dbc.Button("Load", id="load-zones-btn", color="primary", className="w-100"),
            ], width=2),
        ]),
    ], className="filter-row mt-3"),

    dcc.Loading(
        type="circle",
        children=[
            html.Div(id="zones-metrics"),
            html.Div(id="zones-summary"),
            html.Div(id="zones-store-detail"),
        ],
    ),

    dcc.Store(id="zones-data-store"),
])


@callback(
    Output("zones-zone-filter", "options"),
    Input("zones-company", "value"),
)
def populate_zone_filter(company):
    if not company:
        return []
    zones = get_cached_zones(company)
    if zones is None:
        zones = refresh_zones_from_bq(company)
    return zones if zones else []


@callback(
    Output("zones-data-store", "data"),
    Input("load-zones-btn", "n_clicks"),
    State("zones-company", "value"),
    State("zones-start-date", "date"),
    State("zones-end-date", "date"),
    State("zones-zone-filter", "value"),
    prevent_initial_call=True,
)
def load_zone_data(n_clicks, company, start_date, end_date, zone_filter):
    if not company:
        return None

    zone_where = ""
    if zone_filter:
        zone_where = f"""AND location.store_cluster IN (
            SELECT DISTINCT store_cluster FROM `growth.supply_model_daily_position`
            WHERE zone_description = '{zone_filter}' AND company_name = '{company}'
        )"""

    df = run_query(f"""
        SELECT
            location.store_cluster AS zone_hex,
            location.external_id AS store_number,
            location.saved_location_name AS store_name,
            assignment_status,
            assignment.is_completed,
            assignment.is_noshow,
            assignment.is_canceled,
            payment.total_amount,
            payment.rate,
            partner_id
        FROM `bi.fct_shift_assignments`
        WHERE company_name = '{company}'
            AND shift_date BETWEEN '{start_date}' AND '{end_date}'
            {zone_where}
    """)

    if df.empty:
        return None
    return df.to_dict("records")


@callback(
    Output("zones-metrics", "children"),
    Output("zones-summary", "children"),
    Input("zones-data-store", "data"),
    State("zones-company", "value"),
)
def render_zone_summary(data, company):
    if not data:
        return "", dbc.Alert("Select filters and click Load.", color="info")

    df = pd.DataFrame(data)

    total = len(df)
    completed = int(df["is_completed"].sum())
    noshows = int(df["is_noshow"].sum())
    fill_rate = completed / total * 100 if total > 0 else 0
    total_pay = df["total_amount"].sum()

    metrics = html.Div([
        metric_card("Total Shifts", f"{total:,}"),
        metric_card("Completed", f"{completed:,}"),
        metric_card("Fill Rate", f"{fill_rate:.1f}%"),
        metric_card("No Shows", f"{noshows:,}"),
        metric_card("Total Pay", f"${total_pay:,.2f}" if pd.notna(total_pay) else "$0"),
        metric_card("Partners", f"{df['partner_id'].nunique():,}"),
        metric_card("Stores", f"{df['store_number'].nunique():,}"),
    ], className="metrics-row mt-3")

    # Zone aggregation
    zone_agg = df.groupby("zone_hex").agg(
        total_shifts=("zone_hex", "size"),
        completed=("is_completed", "sum"),
        noshows=("is_noshow", "sum"),
        canceled=("is_canceled", "sum"),
        total_pay=("total_amount", "sum"),
        avg_rate=("rate", "mean"),
        unique_partners=("partner_id", "nunique"),
        store_count=("store_number", "nunique"),
    ).reset_index()

    zone_agg["fill_rate"] = (zone_agg["completed"] / zone_agg["total_shifts"] * 100).round(1)
    zone_agg["avg_rate"] = zone_agg["avg_rate"].round(2)
    zone_agg = zone_agg.sort_values("total_shifts", ascending=False)

    # Links
    zone_agg["shifts_link"] = zone_agg["zone_hex"].apply(
        lambda z: f"[View Shifts](/shifts?company={company}&zone={z})"
    )

    columns = [
        {"field": "zone_hex", "headerName": "Zone", "width": 180},
        {"field": "total_shifts", "headerName": "Shifts", "width": 90},
        {"field": "completed", "headerName": "Completed", "width": 100},
        {"field": "fill_rate", "headerName": "Fill Rate %", "width": 100},
        {"field": "noshows", "headerName": "No Shows", "width": 95},
        {"field": "canceled", "headerName": "Canceled", "width": 90},
        {"field": "total_pay", "headerName": "Total Pay", "width": 110,
         "valueFormatter": {"function": "params.value ? '$' + Number(params.value).toFixed(2) : '—'"}},
        {"field": "avg_rate", "headerName": "Avg Rate", "width": 90,
         "valueFormatter": {"function": "params.value ? '$' + Number(params.value).toFixed(2) : '—'"}},
        {"field": "unique_partners", "headerName": "Partners", "width": 90},
        {"field": "store_count", "headerName": "Stores", "width": 80},
        {"field": "shifts_link", "headerName": "", "cellRenderer": "markdown", "width": 110},
    ]

    summary = html.Div([
        html.Div("Zone Summary", className="section-header"),
        html.Small(f"{len(zone_agg)} zones", className="text-muted"),
        dag.AgGrid(
            id="zones-grid",
            rowData=zone_agg.to_dict("records"),
            columnDefs=columns,
            defaultColDef={"resizable": True, "sortable": True, "filter": "agSetColumnFilter", "minWidth": 60},
            dashGridOptions={
                "pagination": True,
                "paginationPageSize": 50,
                "animateRows": True,
                "rowSelection": "single",
            },
            style={"height": "500px"},
            className="ag-theme-alpine-dark",
            csvExportParams={"fileName": "zone_summary.csv"},
        ),
    ], className="mt-3")

    return metrics, summary


@callback(
    Output("zones-store-detail", "children"),
    Input("zones-grid", "selectedRows"),
    State("zones-data-store", "data"),
    State("zones-company", "value"),
)
def show_store_detail(selected_rows, raw_data, company):
    if not selected_rows or not raw_data:
        return ""

    selected_zone = selected_rows[0]["zone_hex"]
    df = pd.DataFrame(raw_data)
    zone_df = df[df["zone_hex"] == selected_zone]

    if zone_df.empty:
        return ""

    store_agg = zone_df.groupby(["store_number", "store_name"]).agg(
        total_shifts=("store_number", "size"),
        completed=("is_completed", "sum"),
        noshows=("is_noshow", "sum"),
        total_pay=("total_amount", "sum"),
        unique_partners=("partner_id", "nunique"),
    ).reset_index()

    store_agg["fill_rate"] = (store_agg["completed"] / store_agg["total_shifts"] * 100).round(1)
    store_agg = store_agg.sort_values("total_shifts", ascending=False)

    store_agg["shifts_link"] = store_agg["store_number"].apply(
        lambda s: f"[View Shifts](/shifts?company={company}&store={s})"
    )

    columns = [
        {"field": "store_number", "headerName": "Store", "width": 100},
        {"field": "store_name", "headerName": "Store Name", "width": 200},
        {"field": "total_shifts", "headerName": "Shifts", "width": 80},
        {"field": "completed", "headerName": "Completed", "width": 100},
        {"field": "fill_rate", "headerName": "Fill Rate %", "width": 100},
        {"field": "noshows", "headerName": "No Shows", "width": 95},
        {"field": "total_pay", "headerName": "Total Pay", "width": 110,
         "valueFormatter": {"function": "params.value ? '$' + Number(params.value).toFixed(2) : '—'"}},
        {"field": "unique_partners", "headerName": "Partners", "width": 90},
        {"field": "shifts_link", "headerName": "", "cellRenderer": "markdown", "width": 110},
    ]

    return html.Div([
        html.Div(f"Store Detail — {selected_zone}", className="section-header"),
        html.Small(f"{len(store_agg)} stores", className="text-muted"),
        dag.AgGrid(
            rowData=store_agg.to_dict("records"),
            columnDefs=columns,
            defaultColDef={"resizable": True, "sortable": True, "filter": "agSetColumnFilter", "minWidth": 60},
            dashGridOptions={"domLayout": "autoHeight", "pagination": True, "paginationPageSize": 25},
            className="ag-theme-alpine-dark",
        ),
    ], className="mt-3")
