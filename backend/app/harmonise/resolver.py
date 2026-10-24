"""Biomarker Harmonisation and Alias Resolver.

Maps raw extracted marker names (e.g. 'Serum Creatinine', 'Glycated Hemoglobin (HbA1c)')
to standard canonical marker codes ('creatinine', 'hba1c') and canonical units.
"""

from pathlib import Path
from typing import Dict, Optional, Tuple
import yaml

_MARKERS_CONFIG_PATH = Path(__file__).resolve().parent / "markers.yaml"
_CACHED_REGISTRY: Optional[Dict[str, Dict]] = None


def get_marker_registry() -> Dict[str, Dict]:
    """Load and cache the marker definitions from markers.yaml."""
    global _CACHED_REGISTRY
    if _CACHED_REGISTRY is not None:
        return _CACHED_REGISTRY

    if not _MARKERS_CONFIG_PATH.exists():
        _CACHED_REGISTRY = {}
        return _CACHED_REGISTRY

    with open(_MARKERS_CONFIG_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    _CACHED_REGISTRY = data.get("markers", {})
    return _CACHED_REGISTRY


def resolve_marker(raw_name: str) -> Tuple[Optional[str], Optional[str]]:
    """Resolve a raw marker string to (marker_code, canonical_unit).

    Returns:
        Tuple[Optional[str], Optional[str]]: (marker_code, canonical_unit) or (None, None)
    """
    cleaned = raw_name.strip().lower()
    registry = get_marker_registry()

    # Pass 1: Exact matches against code or alias
    for code, info in registry.items():
        if cleaned == code:
            return code, info.get("canonical_unit")
        for alias in info.get("aliases", []):
            if cleaned == str(alias).strip().lower():
                return code, info.get("canonical_unit")

    # Pass 2: More specific aliases first (longest alias contained in cleaned text)
    matches = []
    for code, info in registry.items():
        for alias in info.get("aliases", []):
            a_clean = str(alias).strip().lower()
            if a_clean in cleaned:
                matches.append((len(a_clean), code, info.get("canonical_unit")))

    if matches:
        # Sort by longest alias match first (e.g. "glycated hemoglobin" is 19 chars > "hemoglobin" 10 chars)
        matches.sort(key=lambda x: x[0], reverse=True)
        return matches[0][1], matches[0][2]

    return None, None

