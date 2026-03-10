"""
Configuration for the Multi-Agency Science R&D Spend-Down Tracker.

Defines agency account mappings, SF-133 line items, reporting periods,
and OMB portal URL patterns.
"""

BASE_URL = "https://portal.max.gov/portal/document/SF133/Budget/attachments"

# SF-133 reporting period columns in the Raw Data sheet,
# mapped to fiscal-year month numbers (Oct=1, Nov=2, ..., Sep=12).
# Each entry: (raw_data_column_name, display_label, fiscal_year_month)
AMOUNT_COLUMNS = [
    ("AMT_OCT", "Oct", 1),
    ("AMT_NOV", "Nov", 2),
    ("AMT1", "Dec (Q1)", 3),
    ("AMT_JAN", "Jan", 4),
    ("AMT_FEB", "Feb", 5),
    ("AMT2", "Mar (Q2)", 6),
    ("AMT_APR", "Apr", 7),
    ("AMT_MAY", "May", 8),
    ("AMT3", "Jun (Q3)", 9),
    ("AMT_JUL", "Jul", 10),
    ("AMT_AUG", "Aug", 11),
    ("AMT4", "Sep (Q4)", 12),
]

# Calendar month labels for the fiscal year x-axis
FY_MONTH_LABELS = {
    1: "Oct", 2: "Nov", 3: "Dec", 4: "Jan", 5: "Feb", 6: "Mar",
    7: "Apr", 8: "May", 9: "Jun", 10: "Jul", 11: "Aug", 12: "Sep",
}

# Key SF-133 line items
LINE_ITEMS = {
    # Primary metric
    "obligations_unexpired": "2170",      # New obligations, unexpired accounts
    "obligations_expired": "2180",         # Obligations (upward adj), expired accounts
    "obligations_total": "2190",           # New obligations and upward adjustments (total)
    # Appropriations / budget authority
    "approp_disc": "1160",                 # Discretionary appropriation (total)
    "approp_mand": "1260",                 # Mandatory appropriation (total)
    "budget_authority": "1900",            # Budget authority total (disc + mand)
    "total_budgetary_resources": "1910",   # Total budgetary resources
    # Outlays
    "outlays_net": "4190",                 # Outlays, net (disc + mand)
    "outlays_gross_disc": "4020",          # Discretionary outlays, gross
    "outlays_gross_mand": "4110",          # Mandatory outlays, gross
    # Raw appropriation lines (before CR preclusions and other adjustments)
    "approp_disc_raw": "1100",             # Discretionary appropriation (before adj)
    "approp_mand_raw": "1200",             # Mandatory appropriation (before adj)
    "approp_precluded": "1134",            # Appropriations precluded from obligation (CR)
    "approp_reduced": "1130",              # Appropriations permanently reduced
    # Unobligated balance
    "unobligated_eoy": "2490",            # Unobligated balance, end of year
}

# The set of line numbers we need to extract from each file
TARGET_LINES = set(LINE_ITEMS.values())

# Agency definitions: how to filter SF-133 data for each tracked agency
#
# filter_type options:
#   "tracct"          — match TRACCT (single value or list, compared after stripping leading zeros)
#   "bureau"          — match BUREAU name (single value or list)
#   "bureau_exclude"  — match BUREAU, then exclude specific TRACCTs
#   "all"             — no filter (entire file)
AGENCIES = {
    "NIH": {
        "display_name": "NIH (Institutes + OD)",
        "sf133_file_key": "hhs",
        "filter_type": "bureau_exclude",
        "filter_value": "National Institutes of Health",
        "exclude_tracct": ["3966", "4554", "838"],  # Mgmt Fund, Services & Supply, Bldgs
        "color": "#2c5f8a",
    },
    "NSF": {
        "display_name": "NSF (Research & Related)",
        "sf133_file_key": "nsf",
        "filter_type": "tracct",
        "filter_value": "100",
        "color": "#d4883a",
    },
    "DOE_SC": {
        "display_name": "DOE (Office of Science)",
        "sf133_file_key": "doe",
        "filter_type": "tracct",
        "filter_value": "222",
        "color": "#2e8b7a",
    },
    "NASA_SCI": {
        "display_name": "NASA (Science)",
        "sf133_file_key": "nasa",
        "filter_type": "tracct",
        "filter_value": "120",
        "color": "#c25050",
    },
    "USDA_RD": {
        "display_name": "USDA (ARS + NIFA)",
        "sf133_file_key": "usda",
        "filter_type": "tracct",
        "filter_value": ["1400", "1500", "1502"],
        "color": "#8b6dae",
    },
}

# SF-133 file keys mapped to department-level file name fragments
# Used for auto-generating filenames for years with descriptive naming
FILE_KEY_TO_AGENCY_NAME = {
    "hhs": "Department_of_Health_and_Human_Services",
    "nsf": "National_Science_Foundation",
    "doe": "Department_of_Energy",
    "nasa": "National_Aeronautics_and_Space_Administration",
    "usda": "Department_of_Agriculture",
}

FISCAL_YEARS = list(range(2016, 2027))
CURRENT_FY = 2026
# Years drawn as individual lines (not included in the prior-year band)
HIGHLIGHT_YEARS = [2026, 2025]
# Years that go into the prior-year range band (excludes current + highlighted)
BAND_YEARS_EXCLUDE = {2026, 2025}
