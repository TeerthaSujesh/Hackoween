"""Theil-Sen Robust Slope Estimator.

Calculates the robust rate of change (slope per year) across longitudinal points.
Theil-Sen estimator computes all pairwise slopes between distinct dates and takes
the median, making it resistant to outliers and non-normal noise.
"""

from datetime import date
from typing import List, Tuple, Union
import statistics


def calculate_theil_sen_slope(points: List[Tuple[Union[date, str], float]]) -> float:
    """Calculate the Theil-Sen median slope per year for a series of (date, value) pairs.

    Args:
        points: List of (date, value) tuples sorted or unsorted.
                date can be a datetime.date object or an ISO string 'YYYY-MM-DD'.

    Returns:
        float: Slope in units per year, rounded to 4 decimal places.
               Returns 0.0 if fewer than 2 points are provided.
    """
    if len(points) < 2:
        return 0.0

    # Parse and sort by date
    parsed_points: List[Tuple[date, float]] = []
    for d, val in points:
        parsed_d = date.fromisoformat(d) if isinstance(d, str) else d
        parsed_points.append((parsed_d, float(val)))

    parsed_points.sort(key=lambda p: p[0])

    slopes: List[float] = []
    n = len(parsed_points)

    for i in range(n):
        d_i, val_i = parsed_points[i]
        for j in range(i + 1, n):
            d_j, val_j = parsed_points[j]
            days_diff = (d_j - d_i).days
            if days_diff > 0:
                years_diff = days_diff / 365.25
                slope = (val_j - val_i) / years_diff
                slopes.append(slope)

    if not slopes:
        return 0.0

    return round(float(statistics.median(slopes)), 4)
