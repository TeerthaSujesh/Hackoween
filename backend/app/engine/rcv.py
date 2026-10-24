"""Reference Change Value (RCV) Calculations.

Deterministic implementation of biological variation and RCV for laboratory markers.
Formula:
    RCV = 2.77 * sqrt(CV_I^2 + CV_A^2)
where:
    CV_I = within-subject biological variation (%)
    CV_A = analytical variation (%)
    2.77 = sqrt(2) * 1.96 (for 95% two-sided confidence limit)
"""

import math
from typing import Dict, Tuple

# Biological variation parameters (EFLM Biological Variation Database)
# CV_I and CV_A as percentage points
BIOLOGICAL_VARIATION: Dict[str, Dict[str, float]] = {
    "creatinine": {"cvi": 4.5, "cva": 2.5},
    "hba1c": {"cvi": 1.5, "cva": 2.0},
    "fasting_glucose": {"cvi": 5.0, "cva": 2.5},
    "hb": {"cvi": 2.8, "cva": 1.5},
    "mcv": {"cvi": 1.3, "cva": 1.2},
    "rdw": {"cvi": 3.5, "cva": 2.5},
}

# Standard reference intervals by sex: (low, high)
REFERENCE_RANGES: Dict[str, Dict[str, Tuple[float, float]]] = {
    "creatinine": {"M": (0.7, 1.3), "F": (0.5, 1.1)},
    "hba1c": {"M": (4.0, 5.6), "F": (4.0, 5.6)},
    "fasting_glucose": {"M": (70.0, 99.0), "F": (70.0, 99.0)},
    "hb": {"M": (13.0, 17.0), "F": (12.0, 15.0)},
    "mcv": {"M": (80.0, 100.0), "F": (80.0, 100.0)},
    "rdw": {"M": (11.5, 14.5), "F": (11.5, 14.5)},
}


def get_rcv_threshold(marker: str) -> float:
    """Return the 95% two-sided RCV percentage threshold for a marker.

    Returns:
        float: RCV percentage threshold rounded to 2 decimal places.
    """
    params = BIOLOGICAL_VARIATION.get(marker)
    if not params:
        raise ValueError(f"Unknown marker '{marker}' for RCV calculation.")

    cvi = params["cvi"]
    cva = params["cva"]
    rcv = 2.77 * math.sqrt(cvi**2 + cva**2)
    return round(rcv, 2)


def calculate_percent_change(baseline: float, current: float) -> float:
    """Calculate directional percentage change from baseline to current.

    Formula:
        ((current - baseline) / baseline) * 100

    Returns:
        float: Percentage change rounded to 2 decimal places.
    """
    if baseline <= 0:
        raise ValueError("Baseline value must be strictly positive to compute percent change.")
    return round(((current - baseline) / baseline) * 100.0, 2)


def is_rcv_exceeded(marker: str, baseline: float, current: float) -> Tuple[bool, float, float]:
    """Determine if change from baseline exceeds the 95% RCV threshold.

    Returns:
        Tuple[bool, float, float]: (exceeded, delta_percent, rcv_threshold)
    """
    rcv_thresh = get_rcv_threshold(marker)
    delta_pct = calculate_percent_change(baseline, current)
    exceeded = abs(delta_pct) >= rcv_thresh
    return exceeded, delta_pct, rcv_thresh
