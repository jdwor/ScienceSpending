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
        "display_name": "NSF (R&RA + EDU)",
        "sf133_file_key": "nsf",
        "filter_type": "tracct",
        "filter_value": ["100", "106"],
        "color": "#d4883a",
    },
    "DOE_SC": {
        "display_name": "DOE (SC + ARPA-E)",
        "sf133_file_key": "doe",
        "filter_type": "tracct",
        "filter_value": ["222", "337"],
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

FISCAL_YEARS = list(range(2016, 2027))
CURRENT_FY = 2026
# Years drawn as individual lines (not included in the prior-year band)
HIGHLIGHT_YEARS = [2026, 2025]
# Years that go into the prior-year range band (excludes current + highlighted)
BAND_YEARS_EXCLUDE = {2026, 2025}

# ---------------------------------------------------------------------------
# Sub-Agency Mappings
# ---------------------------------------------------------------------------

# NIH Institute/Center TRACCT codes (from SF-133 HHS file)
NIH_IC_TRACCTS = {
    "NCI": "849", "NHLBI": "872", "NIDCR": "873", "NIDDK": "884",
    "NINDS": "886", "NIAID": "885", "NIGMS": "851", "NICHD": "844",
    "NEI": "887", "NIEHS": "862", "NIA": "843", "NIAMS": "888",
    "NIDCD": "890", "NIMH": "892", "NIDA": "893", "NIAAA": "894",
    "NINR": "889", "NHGRI": "891", "NIBIB": "898", "NIMHD": "897",
    "NCCIH": "896", "NCATS": "875", "NLM": "807", "FIC": "819", "OD": "846",
}

NIH_IC_DISPLAY_NAMES = {
    "NCI": "National Cancer Institute",
    "NHLBI": "National Heart, Lung, and Blood Institute",
    "NIDCR": "National Institute of Dental and Craniofacial Research",
    "NIDDK": "National Institute of Diabetes and Digestive and Kidney Diseases",
    "NINDS": "National Institute of Neurological Disorders and Stroke",
    "NIAID": "National Institute of Allergy and Infectious Diseases",
    "NIGMS": "National Institute of General Medical Sciences",
    "NICHD": "Eunice Kennedy Shriver NICHD",
    "NEI": "National Eye Institute",
    "NIEHS": "National Institute of Environmental Health Sciences",
    "NIA": "National Institute on Aging",
    "NIAMS": "National Institute of Arthritis and Musculoskeletal and Skin Diseases",
    "NIDCD": "National Institute on Deafness and Other Communication Disorders",
    "NIMH": "National Institute of Mental Health",
    "NIDA": "National Institute on Drug Abuse",
    "NIAAA": "National Institute on Alcohol Abuse and Alcoholism",
    "NINR": "National Institute of Nursing Research",
    "NHGRI": "National Human Genome Research Institute",
    "NIBIB": "National Institute of Biomedical Imaging and Bioengineering",
    "NIMHD": "National Institute on Minority Health and Health Disparities",
    "NCCIH": "National Center for Complementary and Integrative Health",
    "NCATS": "National Center for Advancing Translational Sciences",
    "NLM": "National Library of Medicine",
    "FIC": "Fogarty International Center",
    "OD": "Office of the Director",
}

# NSF CFDA-to-directorate mapping
NSF_CFDA_DIRECTORATES = {
    "47.041": {"key": "NSF_ENG", "name": "Engineering"},
    "47.049": {"key": "NSF_MPS", "name": "Math & Physical Sciences"},
    "47.050": {"key": "NSF_GEO", "name": "Geosciences"},
    "47.070": {"key": "NSF_CISE", "name": "Computer & Information Science"},
    "47.074": {"key": "NSF_BIO", "name": "Biological Sciences"},
    "47.075": {"key": "NSF_SBE", "name": "Social, Behavioral & Economic Sciences"},
    "47.076": {"key": "NSF_EDU_AWD", "name": "STEM Education"},
    "47.083": {"key": "NSF_IA", "name": "Integrative Activities"},
    "47.084": {"key": "NSF_TIP", "name": "Technology, Innovation & Partnerships"},
}

# ---------------------------------------------------------------------------
# Sub-Agency AGENCIES entries (obligations via SF-133)
# ---------------------------------------------------------------------------

# DOE sub-agencies
AGENCIES["DOE_SC_SCI"] = {
    "display_name": "Office of Science",
    "sf133_file_key": "doe",
    "filter_type": "tracct",
    "filter_value": "222",
    "color": "#2e8b7a",
    "parent": "DOE_SC",
}
AGENCIES["DOE_ARPA_E"] = {
    "display_name": "ARPA-E",
    "sf133_file_key": "doe",
    "filter_type": "tracct",
    "filter_value": "337",
    "color": "#2e8b7a",
    "parent": "DOE_SC",
}

# USDA sub-agencies
AGENCIES["USDA_NIFA"] = {
    "display_name": "NIFA",
    "sf133_file_key": "usda",
    "filter_type": "tracct",
    "filter_value": "1400",
    "color": "#8b6dae",
    "parent": "USDA_RD",
}
AGENCIES["USDA_ARS"] = {
    "display_name": "ARS",
    "sf133_file_key": "usda",
    "filter_type": "tracct",
    "filter_value": ["1500", "1502"],
    "color": "#8b6dae",
    "parent": "USDA_RD",
}

# NSF sub-agencies (obligations only — awards use directorate split)
AGENCIES["NSF_RRA"] = {
    "display_name": "Research & Related Activities",
    "sf133_file_key": "nsf",
    "filter_type": "tracct",
    "filter_value": "100",
    "color": "#d4883a",
    "parent": "NSF",
}
AGENCIES["NSF_EDU"] = {
    "display_name": "STEM Education",
    "sf133_file_key": "nsf",
    "filter_type": "tracct",
    "filter_value": "106",
    "color": "#d4883a",
    "parent": "NSF",
}

# NIH sub-agencies (per institute)
for _ic, _tracct in NIH_IC_TRACCTS.items():
    AGENCIES[f"NIH_{_ic}"] = {
        "display_name": _ic,
        "sf133_file_key": "hhs",
        "filter_type": "tracct",
        "filter_value": _tracct,
        "color": "#2c5f8a",
        "parent": "NIH",
    }


# ---------------------------------------------------------------------------
# Awards Pipeline
# ---------------------------------------------------------------------------

AWARDS_FISCAL_YEARS = list(range(2016, 2027))

# NIH Reporter API
NIH_REPORTER_URL = "https://api.reporter.nih.gov/v2/projects/search"
NIH_REPORTER_RATE_LIMIT = 1.0  # seconds between requests
NIH_REPORTER_PAGE_SIZE = 500
NIH_REPORTER_MAX_OFFSET = 14999
NIH_COMPETING_TYPES = ["1", "2"]  # Type 1 (New) + Type 2 (Competing Renewal)
NIH_ALL_TYPES = ["1", "2", "5"]   # + Type 5 (Non-Competing Continuation)
# FY2016 Type 5 data from NIH Reporter is significantly lower than USASpending
# figures for the same year (~$16.5B vs ~$23.5B), unlike FY2017+ which align
# closely, suggesting a data integrity issue in the earlier Reporter records.
NIH_ALL_AWARDS_FISCAL_YEARS = list(range(2017, 2027))

# NIH IC abbreviations — used to partition queries and stay under API limits
NIH_IC_CODES = [
    "NCI", "NHLBI", "NIDCR", "NIDDK", "NINDS", "NIAID", "NIGMS",
    "NICHD", "NEI", "NIEHS", "NIA", "NIAMS", "NIDCD", "NIMH",
    "NIDA", "NIAAA", "NINR", "NHGRI", "NIBIB", "NIMHD", "NCCIH",
    "NCATS", "NLM", "FIC", "CIT", "CSR", "OD",
]

# NSF Awards API
NSF_AWARDS_URL = "https://api.nsf.gov/services/v1/awards.json"
NSF_PAGE_SIZE = 25
NSF_MAX_RESULTS = 3000
# NSF directorate CFDAs (R&RA + STEM Education + TIP + Integrative Activities)
NSF_AWARD_CFDAS = [
    "47.041", "47.049", "47.050", "47.070", "47.074", "47.075",
    "47.076", "47.083", "47.084",
]

# USASpending API
USASPENDING_TIME_URL = (
    "https://api.usaspending.gov/api/v2/search/spending_over_time/"
)
USASPENDING_AWARD_SEARCH_URL = (
    "https://api.usaspending.gov/api/v2/search/spending_by_award/"
)
USASPENDING_AWARD_TYPE_CODES = ["04", "05"]  # Project grants + Cooperative agreements

# Per-agency awards configuration
AWARDS_CONFIG = {
    "NIH": {
        "source": "nih_reporter",
        "metric_label": "New & Competing Awards",
        "metric_label_short": "Awards",
    },
    "NSF": {
        "source": "nsf_awards",
        "metric_label": "New Awards (all directorates)",
        "metric_label_short": "Awards",
    },
    "DOE_SC": {
        "source": "usaspending",
        "metric_label": "New Grant Awards",
        "metric_label_short": "Awards",
        "cfda": ["81.049", "81.135"],
        "agency_name": "Department of Energy",
        "agency_tier": "toptier",
    },
    "NASA_SCI": {
        "source": "usaspending",
        "metric_label": "New Grant Awards",
        "metric_label_short": "Awards",
        "cfda": ["43.001", "43.013"],
        "agency_name": "National Aeronautics and Space Administration",
        "agency_tier": "toptier",
    },
    "USDA_RD": {
        "source": "usaspending",
        "metric_label": "New Grant Awards",
        "metric_label_short": "Awards",
        "cfda": ["10.310"],
        "agency_name": "Department of Agriculture",
        "agency_tier": "toptier",
    },
}

# Sub-agency awards entries
# DOE sub-agencies (USASpending, per-CFDA)
AWARDS_CONFIG["DOE_SC_SCI"] = {
    "source": "usaspending",
    "metric_label": "New Grant Awards (Office of Science)",
    "metric_label_short": "Awards",
    "cfda": ["81.049"],
    "agency_name": "Department of Energy",
    "agency_tier": "toptier",
    "parent": "DOE_SC",
}
AWARDS_CONFIG["DOE_ARPA_E"] = {
    "source": "usaspending",
    "metric_label": "New Grant Awards (ARPA-E)",
    "metric_label_short": "Awards",
    "cfda": ["81.135"],
    "agency_name": "Department of Energy",
    "agency_tier": "toptier",
    "parent": "DOE_SC",
}

# USDA sub-agency (NIFA only — ARS is intramural, no awards data)
AWARDS_CONFIG["USDA_NIFA"] = {
    "source": "usaspending",
    "metric_label": "New Grant Awards (NIFA)",
    "metric_label_short": "Awards",
    "cfda": ["10.310"],
    "agency_name": "Department of Agriculture",
    "agency_tier": "toptier",
    "parent": "USDA_RD",
}

# NSF directorate sub-agencies (per-CFDA filter on existing NSF Awards data)
for _cfda, _dir in NSF_CFDA_DIRECTORATES.items():
    AWARDS_CONFIG[_dir["key"]] = {
        "source": "nsf_awards",
        "display_name": _dir["name"],
        "metric_label": f"New Awards ({_dir['name']})",
        "metric_label_short": "Awards",
        "cfda_filter": _cfda,
        "parent": "NSF",
    }

# NIH IC sub-agencies (per-IC filter on existing NIH Reporter data)
for _ic in NIH_IC_TRACCTS:
    AWARDS_CONFIG[f"NIH_{_ic}"] = {
        "source": "nih_reporter",
        "display_name": _ic,
        "metric_label": f"New & Competing Awards ({_ic})",
        "metric_label_short": "Awards",
        "ic_filter": _ic,
        "parent": "NIH",
    }

# "All Awards" config — includes continuations and renewals alongside new awards
ALL_AWARDS_CONFIG = {
    "NIH": {
        "source": "nih_reporter",
        "metric_label": "All Awards (New + Continuing)",
        "metric_label_short": "Awards",
    },
    "NSF": {
        "source": "usaspending",
        "metric_label": "All Awards (all directorates)",
        "metric_label_short": "Awards",
    },
    "DOE_SC": {
        **AWARDS_CONFIG["DOE_SC"],
        "metric_label": "All Grant Obligations",
    },
    "NASA_SCI": {
        **AWARDS_CONFIG["NASA_SCI"],
        "metric_label": "All Grant Obligations",
    },
    "USDA_RD": {
        **AWARDS_CONFIG["USDA_RD"],
        "metric_label": "All Grant Obligations",
    },
    # DOE sub-agencies
    "DOE_SC_SCI": {
        **AWARDS_CONFIG["DOE_SC_SCI"],
        "metric_label": "All Grant Obligations (Office of Science)",
    },
    "DOE_ARPA_E": {
        **AWARDS_CONFIG["DOE_ARPA_E"],
        "metric_label": "All Grant Obligations (ARPA-E)",
    },
    # USDA sub-agency
    "USDA_NIFA": {
        **AWARDS_CONFIG["USDA_NIFA"],
        "metric_label": "All Grant Obligations (NIFA)",
    },
}

# NSF directorate sub-agencies for all-awards (USASpending per-CFDA)
for _cfda, _dir in NSF_CFDA_DIRECTORATES.items():
    ALL_AWARDS_CONFIG[_dir["key"]] = {
        "source": "usaspending",
        "display_name": _dir["name"],
        "metric_label": f"All Awards ({_dir['name']})",
        "metric_label_short": "Awards",
        "parent": "NSF",
    }

# NIH IC sub-agencies for all-awards (same ic_filter, different source label)
for _ic in NIH_IC_TRACCTS:
    ALL_AWARDS_CONFIG[f"NIH_{_ic}"] = {
        "source": "nih_reporter",
        "display_name": _ic,
        "metric_label": f"All Awards ({_ic})",
        "metric_label_short": "Awards",
        "ic_filter": _ic,
        "parent": "NIH",
    }
