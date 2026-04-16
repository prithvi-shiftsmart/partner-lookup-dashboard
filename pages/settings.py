"""Settings page — refresh zone cache, clear query cache, re-auth."""

import dash
from dash import html, dcc, callback, Input, Output, State
import dash_bootstrap_components as dbc

from lib.bq import (
    clear_cache, clear_client, load_zone_list, refresh_zones_from_bq,
)
from lib.constants import COMPANY_OPTIONS

dash.register_page(__name__, path="/settings", title="Settings")

layout = html.Div([
    html.H3("Settings"),

    dbc.Row([
        # Zone cache management
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("Zone List Cache"),
                dbc.CardBody([
                    html.P(
                        "Zone lists are cached to disk so they load instantly. "
                        "Refresh when zones change in BigQuery.",
                        className="text-secondary",
                        style={"fontSize": "0.85rem"},
                    ),
                    dcc.Dropdown(
                        id="settings-company",
                        options=[{"label": c, "value": c} for c in COMPANY_OPTIONS],
                        value="Circle K - Premium",
                        className="mb-3",
                    ),
                    dbc.Button(
                        "Refresh Zone List",
                        id="refresh-zones-btn",
                        color="primary",
                        className="me-2",
                    ),
                    html.Div(id="zone-refresh-status", className="mt-3"),
                    html.Hr(),
                    html.Div("Current cached zones:", className="section-subheader"),
                    html.Div(id="zone-cache-display"),
                ]),
            ]),
        ], width=6),

        # Cache & auth
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("Query Cache"),
                dbc.CardBody([
                    html.P(
                        "Clear the in-memory query cache to force fresh data from BigQuery.",
                        className="text-secondary",
                        style={"fontSize": "0.85rem"},
                    ),
                    dbc.Button(
                        "Clear Query Cache",
                        id="clear-cache-btn",
                        color="outline-secondary",
                    ),
                    html.Div(id="cache-clear-status", className="mt-3"),
                ]),
            ], className="mb-3"),
            dbc.Card([
                dbc.CardHeader("Google Cloud Auth"),
                dbc.CardBody([
                    html.P(
                        "If queries fail with auth errors, re-authenticate. "
                        "Run this in your terminal:",
                        className="text-secondary",
                        style={"fontSize": "0.85rem"},
                    ),
                    dbc.Card(
                        dbc.CardBody(
                            html.Code(
                                "gcloud auth application-default login "
                                "--scopes=https://www.googleapis.com/auth/bigquery,"
                                "https://www.googleapis.com/auth/drive.readonly,"
                                "https://www.googleapis.com/auth/cloud-platform",
                                style={"fontSize": "0.8rem", "wordBreak": "break-all"},
                            ),
                        ),
                        className="mb-3",
                    ),
                    dbc.Button(
                        "Reset BQ Client",
                        id="reset-client-btn",
                        color="outline-secondary",
                    ),
                    html.Div(id="client-reset-status", className="mt-3"),
                ]),
            ]),
        ], width=6),
    ], className="mt-3"),
])


@callback(
    Output("zone-refresh-status", "children"),
    Output("zone-cache-display", "children"),
    Input("refresh-zones-btn", "n_clicks"),
    State("settings-company", "value"),
    prevent_initial_call=True,
)
def refresh_zones(n_clicks, company):
    if not company:
        return dbc.Alert("Select a company first.", color="warning"), ""

    zones = refresh_zones_from_bq(company)
    if zones:
        return (
            dbc.Alert(f"Refreshed {len(zones)} zones for {company}.", color="success"),
            _render_zone_cache(),
        )
    return dbc.Alert("No zones returned from BigQuery.", color="warning"), _render_zone_cache()


@callback(
    Output("cache-clear-status", "children"),
    Input("clear-cache-btn", "n_clicks"),
    prevent_initial_call=True,
)
def on_clear_cache(n_clicks):
    clear_cache()
    return dbc.Alert("Query cache cleared.", color="success")


@callback(
    Output("client-reset-status", "children"),
    Input("reset-client-btn", "n_clicks"),
    prevent_initial_call=True,
)
def on_reset_client(n_clicks):
    clear_client()
    clear_cache()
    return dbc.Alert("BQ client reset. Next query will use fresh credentials.", color="success")


@callback(
    Output("zone-cache-display", "children", allow_duplicate=True),
    Input("url", "pathname"),
    prevent_initial_call="initial_duplicate",
)
def load_zone_display(pathname):
    return _render_zone_cache()


def _render_zone_cache():
    data = load_zone_list()
    if not data:
        return html.Small("No zones cached yet. Click Refresh.", className="text-muted")

    items = []
    for company, info in data.items():
        zones = info.get("zones", [])
        updated = info.get("updated_at", "?")
        # zones may be list of strings (old format) or list of dicts (new format)
        if zones and isinstance(zones[0], dict):
            zone_labels = [z.get("label", z.get("value", "?")) for z in zones]
        else:
            zone_labels = zones

        items.append(
            dbc.AccordionItem(
                html.Div([
                    html.Small(f"Updated: {updated}", className="text-muted d-block mb-2"),
                    html.Div(
                        ", ".join(zone_labels[:20]) + (f" ... +{len(zone_labels)-20} more" if len(zone_labels) > 20 else ""),
                        style={"fontSize": "0.8rem", "color": "var(--text-secondary)"},
                    ),
                ]),
                title=f"{company} — {len(zones)} zones",
            )
        )
    return dbc.Accordion(items, start_collapsed=True)
