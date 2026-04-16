"""
Partner Dashboard — Dash App
=============================
Run: python3 dash_app.py
"""

import dash
from dash import Dash, html, dcc, page_container, clientside_callback, Output, Input
import dash_bootstrap_components as dbc

app = Dash(
    __name__,
    use_pages=True,
    pages_folder="pages",
    external_stylesheets=[dbc.themes.DARKLY],
    suppress_callback_exceptions=True,
    title="Partner Dashboard",
)

server = app.server

app.layout = html.Div([
    dcc.Location(id="url", refresh="callback-nav"),

    # Navbar
    dbc.Navbar(
        dbc.Container([
            dbc.NavbarBrand("Partner Dashboard", href="/partner", className="me-4"),
            dbc.Nav([
                dbc.NavItem(dbc.NavLink("Partner Lookup", href="/partner")),
                dbc.NavItem(dbc.NavLink("CKP Funnel", href="/funnel")),
                dbc.NavItem(dbc.NavLink("Market Shifts", href="/shifts")),
                dbc.NavItem(dbc.NavLink("Zone / Store", href="/zones")),
                dbc.NavItem(dbc.NavLink("Settings", href="/settings")),
            ], navbar=True, className="me-auto"),
            html.Button(
                "Light Mode",
                id="theme-toggle-btn",
                className="theme-toggle",
                n_clicks=0,
            ),
        ], fluid=True),
        color="dark",
        dark=True,
        className="mb-0",
    ),

    # Page content
    html.Div(page_container, className="page-content"),

    # Footer
    html.Div(
        "Steady State Supply · Priority Markets",
        className="footer",
    ),
], id="app-container")

# Client-side theme toggle
clientside_callback(
    """
    function(n_clicks) {
        if (!n_clicks) {
            var saved = localStorage.getItem('dashboard-theme') || 'dark';
            document.documentElement.setAttribute('data-theme', saved);
            return saved === 'light' ? 'Dark Mode' : 'Light Mode';
        }
        var current = document.documentElement.getAttribute('data-theme') || 'dark';
        var next = current === 'dark' ? 'light' : 'dark';
        document.documentElement.setAttribute('data-theme', next);
        localStorage.setItem('dashboard-theme', next);
        document.querySelectorAll('.ag-theme-alpine-dark, .ag-theme-alpine').forEach(function(el) {
            el.classList.remove('ag-theme-alpine-dark', 'ag-theme-alpine');
            el.classList.add(next === 'dark' ? 'ag-theme-alpine-dark' : 'ag-theme-alpine');
        });
        return next === 'light' ? 'Dark Mode' : 'Light Mode';
    }
    """,
    Output("theme-toggle-btn", "children"),
    Input("theme-toggle-btn", "n_clicks"),
)


if __name__ == "__main__":
    app.run(debug=True, port=8503)
