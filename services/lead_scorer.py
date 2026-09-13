# services/lead_scorer.py

def calculate_lead_score(lead_profile: dict, matched_properties: list) -> int:
    """
    Calculate a lead score out of 100 based on the lead profile and available properties.
    """
    score = 0
    
    # 1. Budget Fit & Property Availability (30 points max)
    if matched_properties:
        score += 30
    
    # 2. Timeline Urgency (30 points max)
    timeline = lead_profile.get("timeline", "").lower()
    if "immediate" in timeline or "1 month" in timeline or "now" in timeline:
        score += 30
    elif "3 months" in timeline or "6 months" in timeline:
        score += 20
    elif timeline:
        score += 10
        
    # 3. Intent & Completeness (40 points max)
    # Check how many critical fields are filled out
    fields = ["budget_max", "locations", "property_type", "bedrooms", "purpose"]
    filled = sum(1 for field in fields if lead_profile.get(field))
    
    if len(fields) > 0:
        score += int((filled / len(fields)) * 40)
    
    return min(score, 100)

def get_qualification_status(score: int) -> str:
    """Returns the tier of the lead based on their numeric score."""
    if score >= 80:
        return "HOT"
    elif score >= 60:
        return "WARM"
    elif score >= 40:
        return "NURTURE"
    return "LOW PRIORITY"
