# services/qualification.py
"""
Qualification Service for Real Estate Lead Qualifier.
Acts as the deterministic data bridge between upstream components (Member 1: Intake,
Member 2: Property Matching, Member 3: AI Decision Engine) and the persistence/dashboard layer.

Key Responsibilities:
- Normalizes heterogenous upstream payloads.
- Validates data integrity before persistence.
- Formats deterministic, non-fabricated broker summaries.
- Prepares normalized payloads for database persistence.
- Does NOT override or recompute AI scoring or property matching decisions.
"""

import re
import json
import uuid
from typing import Dict, Any, List, Optional, Tuple

from database.db import save_lead, save_property_matches, save_decision


def format_currency_inr(amount: Optional[float]) -> str:
    """Formats numeric amounts into Indian Rupee Lakhs / Crores string representation."""
    if amount is None:
        return "Not specified"
    try:
        val = float(amount)
        if val <= 0:
            return "Not specified"
        if val >= 10000000:
            return f"₹{val / 10000000:.2f} Cr"
        if val >= 100000:
            return f"₹{val / 100000:.2f} Lakh"
        return f"₹{val:,.0f}"
    except (ValueError, TypeError):
        return "Not specified"


def parse_numeric_budget(value: Any) -> Optional[float]:
    """Safely extracts a numeric budget from numbers or common string representations."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) if value > 0 else None

    s = str(value).strip().lower()
    if not s or s in ("none", "null", "unknown", "n/a", "not specified"):
        return None

    # Check for crore multiplier
    cr_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:cr|crore|crores)", s)
    if cr_match:
        return float(cr_match.group(1)) * 10000000.0

    # Check for lakh multiplier
    lakh_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:l|lac|lakh|lakhs)", s)
    if lakh_match:
        return float(lakh_match.group(1)) * 100000.0

    # Extract digits only or decimal numbers
    clean_num = re.sub(r"[^\d.]", "", s)
    try:
        val = float(clean_num)
        return val if val > 0 else None
    except ValueError:
        return None


def calculate_profile_completeness(lead_profile: Dict[str, Any]) -> float:
    """
    Deterministically computes a 0-100% completeness score based on the presence
    of core profile attributes.
    """
    key_fields = [
        "name", "contact", "intent", "property_type",
        "preferred_city", "max_budget", "bedrooms",
        "timeline", "financing_type"
    ]
    filled = 0
    for field in key_fields:
        val = lead_profile.get(field)
        if val is not None:
            if isinstance(val, str) and val.strip().lower() not in ("", "unknown", "n/a", "none"):
                filled += 1
            elif isinstance(val, (int, float)) and val > 0:
                filled += 1
            elif isinstance(val, (list, dict)) and len(val) > 0:
                filled += 1

    return round((filled / len(key_fields)) * 100.0, 1)


def normalize_lead_profile(lead_profile: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitizes and maps upstream lead intake fields into a standard schema.
    Handles missing fields, aliases, and string normalizations.
    """
    if not isinstance(lead_profile, dict):
        lead_profile = {}

    # Identify or generate lead_id
    lead_id = lead_profile.get("lead_id") or lead_profile.get("id")
    if not lead_id or str(lead_id).strip() in ("", "None", "null"):
        lead_id = f"LEAD_{uuid.uuid4().hex[:8].upper()}"
    else:
        lead_id = str(lead_id).strip()

    # Name and Contact
    name = lead_profile.get("name") or lead_profile.get("full_name") or lead_profile.get("lead_name")
    if isinstance(name, str):
        name = name.strip() if name.strip().lower() not in ("unknown", "none", "n/a") else None

    contact = lead_profile.get("contact") or lead_profile.get("phone") or lead_profile.get("email")
    if isinstance(contact, str):
        contact = contact.strip() if contact.strip().lower() not in ("unknown", "none", "n/a") else None

    # Intent
    intent = lead_profile.get("intent") or lead_profile.get("purpose") or "Buy"
    if isinstance(intent, str):
        intent = intent.strip().title()

    intent_level = lead_profile.get("intent_level") or lead_profile.get("urgency")
    if isinstance(intent_level, str):
        intent_level = intent_level.strip().capitalize()

    # Property Type
    prop_type = lead_profile.get("property_type") or lead_profile.get("type")
    if isinstance(prop_type, str):
        prop_type = prop_type.strip().title() if prop_type.strip().lower() not in ("unknown", "none", "n/a") else None

    # Locations
    city = lead_profile.get("preferred_city") or lead_profile.get("city")
    if isinstance(city, str):
        city = city.strip().title() if city.strip().lower() not in ("unknown", "none", "n/a") else None

    locality = lead_profile.get("preferred_locality") or lead_profile.get("locality") or lead_profile.get("location")
    if isinstance(locality, str):
        locality = locality.strip().title() if locality.strip().lower() not in ("unknown", "none", "n/a") else None

    # If 'locations' list was provided (e.g. from services.lead_scorer)
    locations = lead_profile.get("locations")
    if isinstance(locations, list) and locations:
        if not locality:
            locality = str(locations[0]).strip().title()
        alt_localities = [str(loc).strip().title() for loc in locations[1:]]
    else:
        alt_localities = lead_profile.get("alternative_localities", [])

    # Budgets
    min_budget = parse_numeric_budget(lead_profile.get("min_budget") or lead_profile.get("budget_min"))
    max_budget = parse_numeric_budget(lead_profile.get("max_budget") or lead_profile.get("budget_max") or lead_profile.get("budget"))

    # Ensure min <= max if both specified
    if min_budget is not None and max_budget is not None and min_budget > max_budget:
        min_budget, max_budget = max_budget, min_budget

    budget_flexibility = lead_profile.get("budget_flexibility")
    if isinstance(budget_flexibility, str):
        budget_flexibility = budget_flexibility.strip()

    # Bedrooms & Bathrooms
    def safe_numeric(val: Any) -> Optional[float]:
        if val is None:
            return None
        try:
            num = float(re.sub(r"[^\d.]", "", str(val)))
            return num if num >= 0 else None
        except ValueError:
            return None

    bedrooms = safe_numeric(lead_profile.get("bedrooms") or lead_profile.get("bhk"))
    bathrooms = safe_numeric(lead_profile.get("bathrooms"))
    min_area_sqft = safe_numeric(lead_profile.get("min_area_sqft") or lead_profile.get("area_sqft") or lead_profile.get("area"))

    # Timeline & Possession
    timeline = lead_profile.get("timeline")
    if isinstance(timeline, str):
        timeline = timeline.strip() if timeline.strip().lower() not in ("unknown", "none", "n/a") else None

    possession = lead_profile.get("possession_preference") or lead_profile.get("possession")
    if isinstance(possession, str):
        possession = possession.strip() if possession.strip().lower() not in ("unknown", "none", "n/a") else None

    # Financing
    financing_type = lead_profile.get("financing_type")
    if isinstance(financing_type, str):
        financing_type = financing_type.strip() if financing_type.strip().lower() not in ("unknown", "none", "n/a") else None

    loan_req = lead_profile.get("loan_required")
    if isinstance(loan_req, str):
        loan_required = loan_req.lower() in ("true", "yes", "1", "required")
    elif isinstance(loan_req, bool):
        loan_required = loan_req
    elif isinstance(loan_req, (int, float)):
        loan_required = bool(loan_req)
    else:
        loan_required = None

    normalized = {
        "lead_id": lead_id,
        "name": name,
        "contact": contact,
        "intent": intent,
        "intent_level": intent_level,
        "property_type": prop_type,
        "preferred_city": city,
        "preferred_locality": locality,
        "alternative_localities": alt_localities,
        "min_budget": min_budget,
        "max_budget": max_budget,
        "budget_flexibility": budget_flexibility,
        "bedrooms": bedrooms,
        "bathrooms": bathrooms,
        "min_area_sqft": min_area_sqft,
        "possession_preference": possession,
        "timeline": timeline,
        "financing_type": financing_type,
        "loan_required": loan_required,
        "raw_profile_json": lead_profile
    }

    normalized["profile_completeness"] = calculate_profile_completeness(normalized)
    return normalized


def normalize_decision(decision: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Extracts and standardizes the AI Decision Engine output while strictly preserving
    the upstream values without re-scoring or overriding.
    """
    if not isinstance(decision, dict):
        return {
            "lead_score": None,
            "lead_quality": "UNASSIGNED",
            "next_action": "PENDING_DECISION",
            "decision_reason": None,
            "broker_summary": None
        }

    # Score: preserve upstream score
    raw_score = decision.get("lead_score") if decision.get("lead_score") is not None else decision.get("score")
    score: Optional[float] = None
    if raw_score is not None:
        try:
            val = float(raw_score)
            score = max(0.0, min(100.0, val))
        except (ValueError, TypeError):
            score = None

    # Quality / Status: preserve upstream tier
    quality = (
        decision.get("lead_quality")
        or decision.get("qualification_status")
        or decision.get("tier")
        or "UNASSIGNED"
    )
    if isinstance(quality, str):
        quality = quality.strip().upper()

    # Next Action: preserve upstream action
    action = decision.get("next_action") or decision.get("action") or "CONTINUE_QUALIFICATION"
    if isinstance(action, str):
        action = action.strip().upper()

    # Reasoning / Reason
    reason = decision.get("decision_reason") or decision.get("reasoning") or decision.get("reason")
    if isinstance(reason, list):
        formatted_reason = "\n".join(f"- {str(r)}" for r in reason)
    elif reason is not None:
        formatted_reason = str(reason).strip()
    else:
        formatted_reason = None

    # Upstream broker summary if already provided
    broker_summary = decision.get("broker_summary")
    if isinstance(broker_summary, str) and broker_summary.strip().lower() not in ("none", "null", ""):
        broker_summary = broker_summary.strip()
    else:
        broker_summary = None

    return {
        "lead_score": score,
        "lead_quality": quality,
        "next_action": action,
        "decision_reason": formatted_reason,
        "broker_summary": broker_summary
    }


def normalize_property_matches(matches: Optional[List[Dict[str, Any]]], lead_id: str = "") -> List[Dict[str, Any]]:
    """
    Standardizes the list of matched properties produced by Member 2.
    Does not alter or recompute match percentages.
    """
    if not matches or not isinstance(matches, list):
        return []

    normalized_matches = []
    for idx, m in enumerate(matches):
        if not isinstance(m, dict):
            continue

        prop_id = m.get("property_id") or m.get("id") or f"PROP_{idx+1}"
        title = m.get("title") or m.get("name") or f"Property {prop_id}"
        price = parse_numeric_budget(m.get("price"))
        location = m.get("location") or m.get("locality") or m.get("city")

        # Extract match percentage
        raw_pct = m.get("match_percentage") or m.get("match_score") or m.get("score")
        match_pct: Optional[float] = None
        if raw_pct is not None:
            try:
                p_val = float(raw_pct)
                # If score is given as fraction 0.0 - 1.0, scale to 100%
                if 0.0 < p_val <= 1.0:
                    p_val *= 100.0
                match_pct = round(max(0.0, min(100.0, p_val)), 1)
            except (ValueError, TypeError):
                match_pct = None

        match_reason = m.get("match_reason") or m.get("reason")

        normalized_matches.append({
            "lead_id": str(lead_id).strip(),
            "property_id": str(prop_id),
            "title": str(title),
            "price": price,
            "location": str(location) if location else None,
            "match_percentage": match_pct,
            "match_reason": str(match_reason) if match_reason else None
        })

    # Sort descending by match percentage
    normalized_matches.sort(key=lambda x: (x["match_percentage"] is not None, x["match_percentage"] or 0), reverse=True)
    return normalized_matches


def generate_broker_summary(
    lead_profile: Dict[str, Any],
    decision: Optional[Dict[str, Any]] = None,
    property_matches: Optional[List[Dict[str, Any]]] = None
) -> str:
    """
    Generates a deterministic, structured broker-friendly summary.
    STRICT RULE: Only relies on available structured data. Never fabricates facts.
    Missing fields are marked as 'Not specified'.
    """
    p = normalize_lead_profile(lead_profile)
    d = normalize_decision(decision)
    m = normalize_property_matches(property_matches, p["lead_id"])

    # 1. Lead Identity
    name = p["name"] if p["name"] else "Anonymous Lead"
    contact = f" ({p['contact']})" if p["contact"] else ""
    intent = p["intent"] if p["intent"] else "Looking to purchase"

    # 2. Property Requirement Specification
    prop_type = p["property_type"] or "Property"
    bhk = f"{int(p['bedrooms'])} BHK " if p["bedrooms"] else ""
    req_phrase = f"{bhk}{prop_type}".strip()

    # Location phrase
    loc_parts = []
    if p["preferred_locality"]:
        loc_parts.append(p["preferred_locality"])
    if p["preferred_city"]:
        loc_parts.append(p["preferred_city"])
    location_phrase = ", ".join(loc_parts) if loc_parts else "Location not specified"

    # Budget phrase
    if p["min_budget"] and p["max_budget"]:
        budget_phrase = f"{format_currency_inr(p['min_budget'])} – {format_currency_inr(p['max_budget'])}"
    elif p["max_budget"]:
        budget_phrase = f"Up to {format_currency_inr(p['max_budget'])}"
    elif p["min_budget"]:
        budget_phrase = f"From {format_currency_inr(p['min_budget'])}"
    else:
        budget_phrase = "Not specified"

    # Timeline phrase
    timeline_phrase = p["timeline"] if p["timeline"] else "Not specified"

    # Financing phrase
    financing_parts = []
    if p["financing_type"]:
        financing_parts.append(p["financing_type"])
    if p["loan_required"] is True:
        financing_parts.append("Bank Loan required")
    elif p["loan_required"] is False:
        financing_parts.append("Self-funded")
    financing_phrase = ", ".join(financing_parts) if financing_parts else "Not specified"

    # 3. Decision Highlights
    score_str = f"{int(d['lead_score'])}/100" if d['lead_score'] is not None else "Pending"
    quality_str = d["lead_quality"]
    action_str = d["next_action"]

    # Construct the summary text
    lines = [
        f"**Lead:** {name}{contact}",
        f"**Intent:** {intent} | **Requirement:** {req_phrase} in {location_phrase}",
        f"**Budget:** {budget_phrase} | **Timeline:** {timeline_phrase} | **Financing:** {financing_phrase}",
        f"**Profile Completeness:** {p['profile_completeness']}%",
        "",
        f"**Lead Quality:** {quality_str} | **Lead Score:** {score_str}",
        f"**Recommended Action:** `{action_str}`"
    ]

    # Reasoning section
    if d["decision_reason"]:
        lines.append("")
        lines.append("**Decision Reasoning:**")
        lines.append(d["decision_reason"])

    # Top Matches section
    if m:
        lines.append("")
        lines.append(f"**Top Property Matches ({len(m)} found):**")
        for prop in m[:3]:
            title = prop["title"]
            pct = f" ({prop['match_percentage']}% match)" if prop["match_percentage"] is not None else ""
            price = f" — {format_currency_inr(prop['price'])}" if prop["price"] else ""
            lines.append(f"- {title}{pct}{price}")
    else:
        lines.append("")
        lines.append("**Top Property Matches:** None matched yet.")

    return "\n".join(lines)


def prepare_final_lead_record(
    lead_profile: Dict[str, Any],
    decision: Optional[Dict[str, Any]] = None,
    property_matches: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Assembles a complete, normalized lead record dictionary ready for database persistence.
    """
    p = normalize_lead_profile(lead_profile)
    d = normalize_decision(decision)

    # Use upstream summary if present, else generate deterministic summary
    broker_summary = d.get("broker_summary")
    if not broker_summary:
        broker_summary = generate_broker_summary(p, d, property_matches)

    record = dict(p)
    record.update({
        "lead_score": d["lead_score"],
        "lead_quality": d["lead_quality"],
        "next_action": d["next_action"],
        "decision_reason": d["decision_reason"],
        "broker_summary": broker_summary,
        "status": lead_profile.get("status", "NEW")
    })

    return record


def validate_lead_data(lead_record: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Performs defensive validation on a lead record before persistence.
    Returns (is_valid: bool, validation_errors: List[str]).
    """
    errors: List[str] = []

    lead_id = lead_record.get("lead_id")
    if not lead_id or not str(lead_id).strip():
        errors.append("Validation Error: Missing mandatory 'lead_id'.")

    score = lead_record.get("lead_score")
    if score is not None:
        try:
            s_val = float(score)
            if s_val < 0 or s_val > 100:
                errors.append(f"Validation Error: 'lead_score' ({s_val}) is outside the valid range [0, 100].")
        except (ValueError, TypeError):
            errors.append(f"Validation Error: 'lead_score' ({score}) is not a valid number.")

    quality = lead_record.get("lead_quality")
    valid_qualities = {"HOT", "WARM", "NURTURE", "COLD", "LOW PRIORITY", "LOW_PRIORITY", "UNASSIGNED"}
    if quality and str(quality).upper() not in valid_qualities:
        # Non-fatal warning or normalization
        pass

    return (len(errors) == 0, errors)


def process_and_store_lead(
    lead_profile: Dict[str, Any],
    property_matches: Optional[List[Dict[str, Any]]] = None,
    decision: Optional[Dict[str, Any]] = None,
    db_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Primary orchestration API for Member 4.
    Ingests already-produced outputs from Members 1, 2, and 3, validates them,
    generates the broker summary, and safely persists lead, decision, and match records into SQLite.

    Returns a result dictionary:
    {
        "success": bool,
        "lead_id": str,
        "record": dict,
        "matches_count": int,
        "errors": List[str]
    }
    """
    final_record = prepare_final_lead_record(lead_profile, decision, property_matches)
    is_valid, errors = validate_lead_data(final_record)

    if not is_valid:
        return {
            "success": False,
            "lead_id": final_record.get("lead_id", ""),
            "record": final_record,
            "matches_count": 0,
            "errors": errors
        }

    lead_id = final_record["lead_id"]

    try:
        # 1. Save main lead record
        save_lead(final_record, db_path=db_path)

        # 2. Save property matches if supplied
        normalized_matches = normalize_property_matches(property_matches, lead_id)
        if normalized_matches:
            save_property_matches(lead_id, normalized_matches, db_path=db_path)

        # 3. Save decision fields explicitly if provided
        if decision:
            save_decision(lead_id, decision, db_path=db_path)

        return {
            "success": True,
            "lead_id": lead_id,
            "record": final_record,
            "matches_count": len(normalized_matches),
            "errors": []
        }
    except Exception as e:
        return {
            "success": False,
            "lead_id": lead_id,
            "record": final_record,
            "matches_count": 0,
            "errors": [f"Database storage error: {str(e)}"]
        }
