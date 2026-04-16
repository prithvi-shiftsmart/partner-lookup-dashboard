"""Shared constants for the Partner Dashboard."""

# ── Company UUID → Name mapping ──
COMPANY_UUIDS = {
    "da532ea5-9fed-46cf-a5cc-6dd7721411b6": "Circle K - Premium",
    "26983819-c423-4f57-90dc-f62c018d1eb6": "PepsiCo Beverages",
    "a9eb903d-3493-43f7-a180-be8eda4a9668": "PepsiCo Foods",
    "14824b29-7224-48a1-9d30-a62d1b8ed614": "Dollar General",
}

COMPANY_OPTIONS = [
    "Circle K - Premium",
    "PepsiCo Beverages",
    "PepsiCo Foods",
    "Dollar General",
]

# ── CKP Funnel — Cohort display mapping ──
# partner_cohort code → (display_label, L1_group, triage_action)
COHORT_MAP = {
    "01_s1c_assigned_champion":          ("Champion (5+ weekly shifts)", "S1C, Assigned", "Maximize output"),
    "02_s1c_assigned_non_m1_s3c":        ("Non-M1, S3C", "S1C, Assigned", "Work more"),
    "03_s1c_assigned_m1_s3c":            ("M1, S3C", "S1C, Assigned", "Work more"),
    "04_s1c_assigned_not_s3c":           ("Not S3C", "S1C, Assigned", "Work more"),
    "05_s1c_not_assigned_sent_seen":     ("Sent, Seen", "S1C, Not Assigned", "Pick up shifts (seen)"),
    "06_s1c_not_assigned_sent_not_seen": ("Sent, Not Seen", "S1C, Not Assigned", "Pick up shifts (not seen)"),
    "07_s1c_not_assigned_not_sent":      ("Not Sent", "S1C, Not Assigned", "Show shifts"),
    "08_bgc_passed_s1a_assigned":        ("S1A, Currently Assigned", "BGC Passed, Not S1C", "S1A (shift coming)"),
    "09_bgc_passed_sent_seen":           ("Sent, Seen", "BGC Passed, Not S1C", "Pick up shifts (BGC clear)"),
    "10_bgc_passed_sent_not_seen":       ("Sent, Not Seen", "BGC Passed, Not S1C", "Pick up shifts (BGC clear)"),
    "11_bgc_passed_not_sent":            ("Not Sent", "BGC Passed, Not S1C", "Show shifts (BGC clear)"),
    "12_op_bgc_consider":                ("Consider", "OP, Not BGC Finalized", "Escalate to Kate"),
    "13_op_bgc_pending_gt24h":           ("Pending > 24H", "OP, Not BGC Finalized", "BGC stuck (>24h)"),
    "14_op_bgc_pending_lt24h":           ("Pending < 24H", "OP, Not BGC Finalized", "BGC processing (<24h)"),
    "15_op_bgc_not_submitted":           ("Not Submitted", "OP, Not BGC Finalized", "Submit BGC"),
    "16_oa_not_op":                      ("All", "OA, Not OP", "Complete orientation"),
    "17_not_oa_non_ckp_s1c":             ("Non CKP S1C", "Not OA", "Cross-sell to CKP"),
    "18_not_oa_active_24h":              ("Active 24hrs No OA", "Not OA", "OA (active)"),
    "19_not_oa_active_72h":              ("Active 72hrs No OA", "Not OA", "OA (active)"),
    "20_not_oa_active_7d":               ("Active 7 Days No OA", "Not OA", "OA (active)"),
    "21_not_oa_active_7d_plus":          ("Active +7 Days No OA", "Not OA", "OA (inactive)"),
    "22_former_failed_bgc":              ("Failed BGC", "Former", "No action (failed BGC)"),
    "23_former_deactivated":             ("Deactivated", "Former", "No action"),
    "24_former_suspended":               ("Suspended", "Former", "No action"),
    "25_former_failed_bgc":              ("Failed BGC (Override)", "Former", "No action (failed BGC)"),
}

# ── L1 group ordering and colors ──
# (group_key, display_label, bg_color, text_color)
L1_GROUPS = [
    ("S1C, Assigned",           "#1a2a3a", "#a3c4d9"),
    ("S1C, Not Assigned",       "#1a2a3a", "#7fb3d4"),
    ("BGC Passed, Not S1C",     "#1a3a2a", "#a3d9b1"),
    ("OP, Not BGC Finalized",   "#3a3520", "#d9cfa3"),
    ("OA, Not OP",              "#2a2040", "#c4a3d9"),
    ("Not OA",                  "#302030", "#b090c0"),
    ("Former",                  "#3a1a1a", "#d9a3a3"),
]

# ── CRM cohort filter options ──
CRM_COHORT_OPTIONS = [
    "C1: Subscale Deep Dives",
    "C2a: FR<80 (Any)",
    "C2b: StoreSmart Alpha",
    "C2c: T25, FR 80-90%",
    "C2d: CL Launch N3W",
    "C3a: Scale, Health Low/Med",
    "C3b: Subscale, Health Low/Med",
    "C3c: Scale, No Health, Zone FR 80-95%",
    "C3d: Subscale, No Health, Zone FR 80-90%",
]

# ── Row highlight colors (dark mode) ──
GREEN_BG = "#1a3a2a"
GREEN_FG = "#a3d9b1"
RED_BG = "#3a1a1a"
RED_FG = "#d9a3a3"
YELLOW_BG = "#3a3520"
YELLOW_FG = "#d9cfa3"
BLUE_BG = "#1a2a3a"
BLUE_FG = "#a3c4d9"
