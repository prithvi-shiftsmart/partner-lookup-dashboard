"""Shared AG Grid table builder for all pages."""

import dash_ag_grid as dag
import pandas as pd
from lib.formatting import partner_url


def _clean_dataframe(df):
    """Clean a DataFrame for display — convert NaT/None/nan to empty strings."""
    display = df.copy()
    for col in display.columns:
        display[col] = display[col].apply(
            lambda x: "" if pd.isna(x) or str(x) in ("None", "NaT", "nan") else x
        )
    return display


def build_grid(grid_id, df, column_defs=None, height=500, row_selection=None,
               page_size=50, auto_size=False):
    """Build a styled AG Grid table.

    Args:
        grid_id: unique DOM id
        df: pandas DataFrame
        column_defs: list of AG Grid columnDefs dicts. If None, auto-generated.
        height: grid height in px
        row_selection: "single" or "multiple" or None
        page_size: rows per page
        auto_size: whether to auto-size columns to fit
    """
    if df.empty:
        return None

    display = _clean_dataframe(df)

    if column_defs is None:
        column_defs = []
        for col in display.columns:
            if col.startswith("_"):
                continue
            col_def = {
                "field": col,
                "headerName": col.replace("_", " ").title(),
                "resizable": True,
                "sortable": True,
                "filter": True,
            }
            column_defs.append(col_def)

    default_col_def = {
        "resizable": True,
        "sortable": True,
        "filter": True,
        "minWidth": 80,
    }

    grid = dag.AgGrid(
        id=grid_id,
        rowData=display.to_dict("records"),
        columnDefs=column_defs,
        defaultColDef=default_col_def,
        dashGridOptions={
            "pagination": True,
            "paginationPageSize": page_size,
            "animateRows": True,
            "rowSelection": row_selection or "single",
            "domLayout": "normal",
        },
        style={"height": f"{height}px"},
        className="ag-theme-alpine-dark",
    )
    return grid


def partner_link_col(field="partner_link", header="Partner", width=180):
    """Column def for a clickable partner link using markdown."""
    return {
        "field": field,
        "headerName": header,
        "cellRenderer": "markdown",
        "resizable": True,
        "sortable": True,
        "filter": True,
        "width": width,
    }


def link_col(field, header="Link", width=100):
    """Column def for a generic markdown link."""
    return {
        "field": field,
        "headerName": header,
        "cellRenderer": "markdown",
        "resizable": True,
        "width": width,
    }


def currency_col(field, header=None, width=100):
    """Column def for a currency field."""
    return {
        "field": field,
        "headerName": header or field.replace("_", " ").title(),
        "resizable": True,
        "sortable": True,
        "filter": "agNumberColumnFilter",
        "width": width,
        "valueFormatter": {"function": "params.value ? '$' + Number(params.value).toFixed(2) : '—'"},
    }


def pct_col(field, header=None, width=90):
    """Column def for a percentage field."""
    return {
        "field": field,
        "headerName": header or field.replace("_", " ").title(),
        "resizable": True,
        "sortable": True,
        "width": width,
        "valueFormatter": {"function": "params.value ? Number(params.value).toFixed(1) + '%' : '—'"},
    }
