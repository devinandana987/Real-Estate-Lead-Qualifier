"""
services/property_matcher.py

Deterministic and explainable property matching and filtering backend.
Matches structured lead requirements against properties in the dataset.
Follows Member 2 specifications:
- Pure Python logic (no LLM dependency, no external APIs).
- Prioritizes Available properties (Sold and Hold excluded by default).
- Deterministic scoring: Location (30%), Budget (30%), Property Type (20%), Bedrooms (20%).
- Gracefully handles missing requirements and malformed data.
- Detects budget mismatches and property type mismatches to avoid false positive matches.
"""

import os
import re
import csv
from typing import List, Dict, Any, Optional

# Default CSV path relative to project root
DEFAULT_CSV_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "properties.csv",
)

def _parse_number(val: Any) -> Optional[float]:
    """Safely parses numeric float from int, float, or string."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val) if val > 0 else None
    
    val_str = str(val).strip().lower().replace(",", "")
    if not val_str:
        return None
    
    # Handle Indian numbering shorthand if present (e.g. 75 lakh, 1.5 cr)
    lakh_match = re.search(r"([\d.]+)\s*(?:lakh|lac|l)", val_str)
    if lakh_match:
        try:
            return float(lakh_match.group(1)) * 100000.0
        except ValueError:
            pass
            
    cr_match = re.search(r"([\d.]+)\s*(?:cr|crore)", val_str)
    if cr_match:
        try:
            return float(cr_match.group(1)) * 10000000.0
        except ValueError:
            pass
            
    # Extract raw numeric sequence
    num_match = re.search(r"[\d.]+", val_str)
    if num_match:
        try:
            return float(num_match.group(0))
        except ValueError:
            return None
    return None

def _parse_int(val: Any) -> Optional[int]:
    """Safely extracts integer value (e.g. from 3, '3', '3 BHK')."""
    if val is None:
        return None
    if isinstance(val, int):
        return val if val > 0 else None
    if isinstance(val, float):
        return int(val) if val > 0 else None
    
    val_str = str(val).strip()
    match = re.search(r"\d+", val_str)
    if match:
        try:
            return int(match.group(0))
        except ValueError:
            return None
    return None

def _parse_locations(val: Any) -> List[str]:
    """Normalizes location input into a list of lowercase location strings."""
    if not val:
        return []
    if isinstance(val, (list, tuple, set)):
        return [str(x).strip().lower() for x in val if str(x).strip()]
    if isinstance(val, str):
        parts = re.split(r"[,/|;]+", val)
        return [p.strip().lower() for p in parts if p.strip()]
    return []

def load_properties(filepath: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Loads properties from CSV, or falls back to data/generate_data.py if missing.
    Returns list of property dictionaries with properly typed fields.
    """
    path = filepath or DEFAULT_CSV_PATH
    properties: List[Dict[str, Any]] = []

    if os.path.exists(path) and os.path.getsize(path) > 0:
        try:
            with open(path, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        prop = {
                            "property_id": str(row.get("property_id", "")).strip(),
                            "title": str(row.get("title", "")).strip(),
                            "location": str(row.get("location", "")).strip(),
                            "property_type": str(row.get("property_type", "")).strip(),
                            "bedrooms": int(float(row.get("bedrooms", 0) or 0)),
                            "bathrooms": int(float(row.get("bathrooms", 0) or 0)),
                            "price": float(row.get("price", 0.0) or 0.0),
                            "possession_date": str(row.get("possession_date", "")).strip(),
                            "status": str(row.get("status", "Available")).strip(),
                            "amenities": str(row.get("amenities", "")).strip(),
                            "investment_score": float(row.get("investment_score", 0.0) or 0.0),
                            "family_score": float(row.get("family_score", 0.0) or 0.0),
                        }
                        if prop["property_id"]:
                            properties.append(prop)
                    except Exception:
                        continue
            if properties:
                return properties
        except Exception:
            pass

    # Fallback if CSV is empty or not found: import from data.generate_data
    try:
        from data.generate_data import PROPERTIES_DATA
        return [dict(p) for p in PROPERTIES_DATA]
    except Exception:
        return []

def score_property(
    prop: Dict[str, Any],
    req_locs: List[str],
    b_min: Optional[float],
    b_max: Optional[float],
    req_type: Optional[str],
    req_beds: Optional[int],
) -> tuple[float, str]:
    """
    Calculates deterministic match score (0 - 100) and short explanation.
    Weights:
    - Location: 30%
    - Budget: 30%
    - Property Type: 20%
    - Bedrooms: 20%
    """
    prop_loc = prop.get("location", "").strip().lower()
    prop_price = float(prop.get("price", 0.0))
    prop_type = prop.get("property_type", "").strip().lower()
    prop_beds = int(prop.get("bedrooms", 0))

    explanations: List[str] = []

    # 1. Location Matching (30 points)
    if not req_locs:
        loc_score = 30.0
    else:
        matched_loc = None
        exact = False
        for l in req_locs:
            if l == prop_loc:
                matched_loc = l
                exact = True
                break
            elif l in prop_loc or prop_loc in l:
                matched_loc = l

        if exact:
            loc_score = 30.0
            explanations.append("Location match")
        elif matched_loc:
            loc_score = 25.0
            explanations.append(f"Near {matched_loc.title()}")
        else:
            loc_score = 0.0
            explanations.append(f"Location mismatch ({prop.get('location')})")

    # 2. Budget Matching (30 points)
    budget_score = 30.0
    severe_budget_mismatch = False

    if b_max is not None:
        if b_min is not None and b_min <= prop_price <= b_max:
            budget_score = 30.0
            explanations.append("Budget fit")
        elif b_min is None and prop_price <= b_max:
            budget_score = 30.0
            explanations.append("Budget fit")
        elif prop_price > b_max:
            over_pct = (prop_price - b_max) / b_max
            if over_pct <= 0.05:
                budget_score = 20.0
                explanations.append("Slightly over budget (<=5%)")
            elif over_pct <= 0.15:
                budget_score = 10.0
                explanations.append("Over budget (~10-15%)")
            else:
                budget_score = 0.0
                severe_budget_mismatch = True
                explanations.append(f"Over budget by {int(round(over_pct * 100))}%")
        elif b_min is not None and prop_price < b_min:
            under_pct = (b_min - prop_price) / b_min
            if under_pct <= 0.20:
                budget_score = 25.0
                explanations.append("Below min budget")
            else:
                budget_score = 20.0
                explanations.append("Significantly below min budget")
    elif b_min is not None:
        if prop_price >= b_min:
            budget_score = 30.0
            explanations.append("Budget fit")
        else:
            under_pct = (b_min - prop_price) / b_min
            if under_pct <= 0.20:
                budget_score = 22.0
                explanations.append("Slightly below min budget")
            else:
                budget_score = 15.0
                explanations.append("Below min budget")

    # 3. Property Type Matching (20 points)
    type_mismatch = False
    if not req_type or req_type in ["any", "all", "either"]:
        type_score = 20.0
    else:
        req_t = req_type.strip().lower()
        if req_t in prop_type or prop_type in req_t:
            type_score = 20.0
            explanations.append("Property type match")
        else:
            type_score = 0.0
            type_mismatch = True
            explanations.append(f"Type mismatch ({prop.get('property_type')})")

    # 4. Bedroom Matching (20 points)
    if req_beds is None:
        bed_score = 20.0
    else:
        diff = abs(prop_beds - req_beds)
        if diff == 0:
            bed_score = 20.0
            explanations.append("Bedroom count matches")
        elif prop_beds == req_beds + 1:
            bed_score = 14.0
            explanations.append(f"{prop_beds} BHK (+1 room)")
        elif prop_beds == req_beds - 1:
            bed_score = 10.0
            explanations.append(f"{prop_beds} BHK (-1 room)")
        else:
            bed_score = 0.0
            explanations.append(f"{prop_beds} BHK mismatch")

    total_score = loc_score + budget_score + type_score + bed_score

    # Hard constraints & penalty handling for extreme mismatches:
    # 1. If property type was explicitly requested and mismatches, cap score at 35%
    if type_mismatch:
        total_score = min(total_score, 35.0)

    # 2. If price severely exceeds max budget (> 50% over budget), cap score at 35%
    if severe_budget_mismatch and b_max is not None:
        if prop_price > 1.5 * b_max:
            total_score = min(total_score, 35.0)

    # Explanation summary string
    if not explanations:
        explanation_str = "Suitable property"
    else:
        explanation_str = "; ".join(explanations) + "."

    return round(total_score, 1), explanation_str

def find_matches(
    requirements: Optional[Dict[str, Any]] = None,
    properties: Optional[List[Dict[str, Any]]] = None,
    min_score: float = 40.0,
    top_n: Optional[int] = None,
    include_unavailable: bool = False,
) -> List[Dict[str, Any]]:
    """
    Finds and ranks matching properties for the given lead requirements.

    Args:
        requirements: Dictionary containing optional lead criteria:
                      - budget_min, budget_max
                      - preferred_locations / locations / location
                      - property_type
                      - bedrooms / bhk
                      - purpose / timeline (optional)
        properties: Optional list of property dicts. If None, loads from CSV.
        min_score: Minimum match score (0-100) to consider as a suitable match. Default 40.0.
        top_n: Optional limit for number of results to return.
        include_unavailable: If False (default), filters out 'Sold' and 'Hold' properties.

    Returns:
        List of matching property dicts sorted descending by match score.
        Each property includes match_score, match_percentage, and explanation.
    """
    req = requirements or {}

    # Load properties if not provided
    if properties is None:
        property_pool = load_properties()
    else:
        property_pool = properties

    if not property_pool:
        return []

    # 1. Primary Filtering: Availability
    if not include_unavailable:
        active_properties = [
            p for p in property_pool
            if str(p.get("status", "")).strip().lower() == "available"
        ]
    else:
        active_properties = list(property_pool)

    if not active_properties:
        return []

    # 2. Parse Requirements Tolerantly
    b_min = _parse_number(req.get("budget_min"))
    b_max = _parse_number(req.get("budget_max"))
    
    # Handle inverted budget ranges if both provided
    if b_min is not None and b_max is not None and b_min > b_max:
        b_min, b_max = b_max, b_min

    loc_raw = req.get("preferred_locations") or req.get("locations") or req.get("location")
    req_locs = _parse_locations(loc_raw)

    req_type = req.get("property_type")
    if req_type and isinstance(req_type, str):
        req_type = req_type.strip()
    else:
        req_type = None

    req_beds = _parse_int(req.get("bedrooms") or req.get("bhk"))

    # If no search criteria were specified, return empty list
    has_any_criteria = (
        b_min is not None
        or b_max is not None
        or len(req_locs) > 0
        or req_type is not None
        or req_beds is not None
    )
    if not has_any_criteria:
        return []

    # 3. Score and Rank Properties
    matched_results: List[Dict[str, Any]] = []

    for prop in active_properties:
        score, explanation = score_property(
            prop=prop,
            req_locs=req_locs,
            b_min=b_min,
            b_max=b_max,
            req_type=req_type,
            req_beds=req_beds,
        )

        if score >= min_score:
            # Build result copy with match metadata
            result_item = dict(prop)
            result_item["match_score"] = score
            result_item["match_percentage"] = f"{int(round(score))}%"
            result_item["match_explanation"] = explanation
            result_item["explanation"] = explanation
            matched_results.append(result_item)

    # Sort descending by match_score, using family_score and investment_score as secondary ties
    matched_results.sort(
        key=lambda x: (
            x["match_score"],
            x.get("family_score", 0.0),
            x.get("investment_score", 0.0),
        ),
        reverse=True,
    )

    if top_n is not None and top_n > 0:
        return matched_results[:top_n]

    return matched_results
