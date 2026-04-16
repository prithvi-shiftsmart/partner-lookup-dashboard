"""BigQuery client and query helpers."""

from google.cloud import bigquery
from google.auth.exceptions import RefreshError
import pandas as pd
import hashlib
import json
import time
import os

_client = None
_cache = {}
CACHE_TTL = 3600  # 1 hour

# Persistent zone list cache file
ZONE_CACHE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".zone_cache.json")


def get_client():
    """Get or create a BigQuery client."""
    global _client
    if _client is None:
        _client = bigquery.Client(project="shiftsmart-api")
    return _client


def clear_client():
    global _client
    _client = None


def _cache_key(sql):
    return hashlib.md5(sql.encode()).hexdigest()


def run_query(sql, use_cache=True):
    """Run a BigQuery query and return a DataFrame. Caches results for CACHE_TTL seconds."""
    key = _cache_key(sql)

    if use_cache and key in _cache:
        result, ts = _cache[key]
        if time.time() - ts < CACHE_TTL:
            return result.copy()
        else:
            del _cache[key]

    try:
        client = get_client()
        df = client.query(sql).to_dataframe()
        if use_cache:
            _cache[key] = (df, time.time())
        return df
    except RefreshError:
        clear_client()
        return pd.DataFrame()
    except Exception as e:
        print(f"BigQuery error: {e}")
        return pd.DataFrame()


def clear_cache():
    global _cache
    _cache = {}


# ── Zone list persistence ──

def load_zone_list():
    """Load cached zone list from disk."""
    if os.path.exists(ZONE_CACHE_PATH):
        try:
            with open(ZONE_CACHE_PATH, "r") as f:
                data = json.load(f)
            return data
        except Exception:
            return {}
    return {}


def save_zone_list(company, zones):
    """Save zone list to disk cache."""
    data = load_zone_list()
    data[company] = {"zones": zones, "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")}
    try:
        with open(ZONE_CACHE_PATH, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Failed to save zone cache: {e}")


def get_cached_zones(company):
    """Get zones for a company from disk cache, or return None if not cached.

    Returns list of dicts: [{"label": "City | Zone", "value": "zone_description"}, ...]
    Old-format caches (plain strings) are auto-converted.
    """
    data = load_zone_list()
    if company in data:
        zones = data[company].get("zones", [])
        if not zones:
            return None
        # Handle old format: list of plain strings
        if isinstance(zones[0], str):
            return None  # Force re-fetch with new city|zone format
        return zones
    return None


def refresh_zones_from_bq(company):
    """Fetch city-zone pairs from BigQuery and save to disk cache.

    Returns list of dicts: [{"label": "City | Zone", "value": "zone_description"}, ...]
    """
    df = run_query(f"""
        SELECT DISTINCT
            zone_description,
            hex_city_description,
            MAX(shifts) AS max_shifts
        FROM `growth.supply_model_daily_position`
        WHERE company_name = '{company}' AND position = 'All'
            AND date = (SELECT MAX(date) FROM `growth.supply_model_daily_position`
                        WHERE company_name = '{company}' AND position = 'All')
            AND shifts > 0
        GROUP BY zone_description, hex_city_description
        ORDER BY hex_city_description, zone_description
    """, use_cache=False)
    if df.empty:
        return []

    # Also pull store cities to enrich the display
    store_cities_df = run_query(f"""
        SELECT DISTINCT
            d.hex AS store_cluster,
            d.city AS store_city
        FROM `bi.dim_locations` d
        WHERE d.company_name = '{company}' AND d.is_active = TRUE
            AND d.city IS NOT NULL
    """, use_cache=False)

    # Build a map: zone_description -> set of store cities
    zone_store_cities = {}
    if not store_cities_df.empty:
        # Join via supply_model_daily_position.store_cluster
        zone_hex_df = run_query(f"""
            SELECT DISTINCT zone_description, store_cluster
            FROM `growth.supply_model_daily_position`
            WHERE company_name = '{company}' AND position = 'All'
                AND date >= DATE_SUB(CURRENT_DATE, INTERVAL 7 DAY)
                AND shifts > 0
        """, use_cache=False)

        if not zone_hex_df.empty:
            merged = zone_hex_df.merge(store_cities_df, on="store_cluster", how="left")
            for _, row in merged.iterrows():
                zd = row.get("zone_description")
                sc = row.get("store_city")
                if zd and sc and str(sc) not in ("None", "nan"):
                    zone_store_cities.setdefault(zd, set()).add(str(sc))

    # Build dropdown options: "City (StoreCities) | Zone"
    zones = []
    for _, row in df.iterrows():
        zd = row["zone_description"]
        city = row.get("hex_city_description", "")

        # Add store city names if they differ from hex city
        extra_cities = zone_store_cities.get(zd, set())
        # Remove the hex city itself (already shown)
        hex_city_base = str(city).replace("_", " ").rsplit(" ", 1)[0] if city else ""
        extra_cities_filtered = sorted([c for c in extra_cities if c.lower() != hex_city_base.lower()])

        if extra_cities_filtered:
            label = f"{city} | {zd} (incl. {', '.join(extra_cities_filtered[:3])})"
        else:
            label = f"{city} | {zd}"

        zones.append({"label": label, "value": zd})

    save_zone_list(company, zones)
    return zones
