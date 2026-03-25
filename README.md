# Partner Lookup Dashboard

Streamlit app for looking up ShiftSmart partners by ID. Shows shifts sent, active bonuses, shift assignments with a calendar view, and background check status.

## Features

- **Partner Info** — Name, company, last active date, OP date, 4-week shift history
- **Background Check** — Status from Checkr (Clear / Consider / Pending)
- **Shifts Sent** — All shifts sent to the partner, split into upcoming and past, with status highlighting
- **Bonuses** — DxGy and other bonus offers, opt-in status, completion progress
- **Shift Assignments** — List and calendar views from `fct_shift_assignments`
- **Auto Re-auth** — In-app button to re-authenticate when Google Cloud credentials expire

## Prerequisites

1. **Python 3.9+**
2. **Google Cloud SDK** (`gcloud`) installed and on your PATH
3. **BigQuery access** to the `shiftsmart-api` project

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/prithvi-shiftsmart/partner-lookup-dashboard.git
cd partner-lookup-dashboard
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Authenticate with Google Cloud

```bash
gcloud auth application-default login
```

This opens a browser window. Sign in with your Shiftsmart Google account. The credentials are cached locally and used by the BigQuery client.

### 4. Run the dashboard

```bash
streamlit run app.py
```

The app will open at **http://localhost:8502**.

## Usage

1. Enter a **Partner ID** in the sidebar (UUID format)
2. Adjust the **date range** sliders to control how far back/forward to look
3. Browse the four sections: Partner Info, Shifts Sent, Bonuses, Shift Assignments
4. Use the **status filter** on Shifts Sent to narrow results
5. Use the **Calendar View** tab on Shift Assignments to see shifts on a monthly grid

### Re-authentication

If your Google Cloud credentials expire, the dashboard will show an error with a **"Re-authenticate with Google"** button. Click it, complete the browser login, then click **"I've completed login — refresh"**.

## Data Sources

| Section | Table |
|---------|-------|
| Partner Info | `growth.int_master_partner_throughput` |
| Background Check | `shiftsmart_data.bq_background_checks` |
| Shifts Sent | `shiftsmart_data.bq_usershifts_deduped` |
| Bonuses | `shiftsmart_data.bq_payment_bonus_eligible_users`, `bq_payment_bonus_progress` |
| Assignments | `bi.fct_shift_assignments` |
| Partner Tier | `bi.dim_partner_aggregate_reliability` |

## Configuration

The Streamlit theme is configured in `.streamlit/config.toml` (dark mode by default, port 8502).
