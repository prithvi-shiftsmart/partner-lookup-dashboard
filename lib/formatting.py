"""Link builders and display formatters for cross-page navigation."""

from dash import html, dcc
from lib.constants import COMPANY_UUIDS
import pandas as pd


def partner_url(partner_id):
    """Build URL to partner lookup page."""
    return f"/partner?id={partner_id}"


def shift_url(shift_id):
    """Build URL to shift detail on market shifts page."""
    return f"/shifts?shift_id={shift_id}"


def market_shifts_url(company=None, zone=None, store=None):
    """Build URL to market shifts page with optional filters."""
    params = []
    if company:
        params.append(f"company={company}")
    if zone:
        params.append(f"zone={zone}")
    if store:
        params.append(f"store={store}")
    return "/shifts?" + "&".join(params) if params else "/shifts"


def zone_summary_url(company=None):
    """Build URL to zone/store summary page."""
    if company:
        return f"/zones?company={company}"
    return "/zones"


def map_company_uuid(uuid_val):
    """Map a company UUID to its display name."""
    return COMPANY_UUIDS.get(str(uuid_val), str(uuid_val)[:8] + "...")


def map_company_uuids(uuid_list):
    """Map a list of company UUIDs to display names."""
    if uuid_list is None:
        return "N/A"
    return ", ".join([map_company_uuid(u) for u in uuid_list])


def format_date(val, include_time=False):
    """Format a date/datetime value for display."""
    if val is None or pd.isna(val):
        return "—"
    s = str(val)
    if s in ("None", "NaT", "nan", ""):
        return "—"
    return s[:19] if include_time else s[:10]


def days_ago_text(dt_val):
    """Return a human-readable 'X days ago' string."""
    if dt_val is None or pd.isna(dt_val):
        return "Unknown"
    try:
        delta = (pd.Timestamp.now() - pd.Timestamp(dt_val)).days
        if delta == 0:
            return "Today"
        elif delta == 1:
            return "Yesterday"
        else:
            return f"{delta}d ago"
    except Exception:
        return "Unknown"


def metric_card(label, value, delta=None, delta_color=None):
    """Build a styled metric card as a Dash component."""
    children = [
        html.Div(label, className="metric-label"),
        html.Div(str(value), className="metric-value"),
    ]
    if delta is not None:
        color_class = f"metric-delta-{delta_color}" if delta_color else "metric-delta"
        children.append(html.Div(str(delta), className=color_class))

    return html.Div(children, className="metric-card")
