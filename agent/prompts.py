import os
import json
import re
from typing import List, Dict, Optional
from dotenv import load_dotenv
from agent.schemas import LeadProfile, ExtractedLeadInfo, ExtractionResult

# Load environment variables
load_dotenv(override=True)

SYSTEM_INTAKE_PROMPT = """You are a smart, friendly, and professional Real Estate Lead Intake Assistant.
Your goal is to converse with prospective property buyers, understand their housing requirements, and extract structured criteria.

The essential criteria you need to capture are:
1. name: Buyer's name (if mentioned)
2. budget_min & budget_max: In INR as raw numbers (e.g., 50 Lakhs = 5000000, 1.5 Cr = 15000000, 80L = 8000000). If they say "under 80 lakhs", budget_max=8000000, budget_min=null.
3. preferred_locations: List of specific localities, neighborhoods, or cities (e.g., ["Kakkanad", "Edappally", "Marine Drive"]).
4. property_type: "Apartment", "Villa", "Independent House", "Penthouse", or "Plot".
5. bedrooms: Number of bedrooms / BHK as an integer (e.g., 2, 3, 4).
6. timeline: Purchase timeline, e.g., "immediate", "within_1_month", "within_3_months", "within_6_months", or "exploring".
7. purpose: "self_use" or "investment".

Instructions:
- Analyze the entire conversation history along with the user's latest message.
- Update and extract all confirmed details into `extracted_info`. Do not invent or assume details that were not stated. Never invent missing values.
- If any required information is missing, continue asking the buyer.
- Do not mark the lead as complete until all six required criteria have been collected.
- Only proceed to property matching after all six criteria are available.
- List any of the 6 core criteria that are still unknown in `missing_fields` (choose from: "Budget Range", "Preferred Location(s)", "Property Type", "Bedrooms (BHK)", "Purchase Timeline", "Purpose (Self-use / Investment)").
- Generate a warm, concise conversational `assistant_reply` (1-2 sentences). Acknowledge what the user just specified and politely ask for the missing details.

You MUST respond strictly with a valid JSON object in this exact schema:
{
  "extracted_info": {
    "name": string or null,
    "budget_min": number or null,
    "budget_max": number or null,
    "preferred_locations": [string],
    "property_type": string or null,
    "bedrooms": number or null,
    "timeline": string or null,
    "purpose": string or null
  },
  "missing_fields": [string],
  "assistant_reply": "Friendly conversational response asking for missing details or confirming complete info"
}
"""


def merge_extracted_into_profile(current: LeadProfile, extracted: ExtractedLeadInfo) -> LeadProfile:
    """Merges newly extracted data into an existing LeadProfile without overwriting with None."""
    updated = current.model_copy()

    if extracted.name:
        updated.name = extracted.name
    if extracted.budget_min is not None:
        updated.budget_min = extracted.budget_min
    if extracted.budget_max is not None:
        updated.budget_max = extracted.budget_max

    if extracted.preferred_locations:
        # Merge locations uniquely while preserving order
        combined_locations = list(dict.fromkeys(updated.preferred_locations + extracted.preferred_locations))
        updated.preferred_locations = combined_locations

    if extracted.property_type:
        updated.property_type = extracted.property_type
    if extracted.bedrooms is not None:
        updated.bedrooms = extracted.bedrooms
    if extracted.timeline:
        updated.timeline = extracted.timeline
    if extracted.purpose:
        updated.purpose = extracted.purpose

    return updated


def _heuristic_fallback_extraction(user_message: str, current_profile: LeadProfile) -> ExtractionResult:
    """Fallback extraction when Groq API key is not configured or offline.
    Uses pattern matching to guarantee a functional demo under any network/API state.
    """
    text = user_message.lower()
    extracted = ExtractedLeadInfo()

    # 1. Bedrooms / BHK
    bhk_match = re.search(r'(\d+)\s*(?:bhk|bedroom|bed)', text)
    if bhk_match:
        extracted.bedrooms = int(bhk_match.group(1))

    # 2. Property Type
    if "villa" in text:
        extracted.property_type = "Villa"
    elif "apartment" in text or "flat" in text or "condo" in text:
        extracted.property_type = "Apartment"
    elif "penthouse" in text:
        extracted.property_type = "Penthouse"
    elif "plot" in text or "land" in text:
        extracted.property_type = "Plot"
    elif "house" in text:
        extracted.property_type = "Independent House"

    # 3. Locations (common Kerala / Kochi & general tech localities)
    known_locations = [
        "Kakkanad", "Edappally", "Marine Drive", "Aluva", "Vyttila", 
        "Kaloor", "Palarivattom", "Tripunithura", "Panampilly Nagar", 
        "Fort Kochi", "Kadavanthra", "Whitefield", "Indiranagar", "HSR Layout"
    ]
    matched_locs = [loc for loc in known_locations if loc.lower() in text]
    if matched_locs:
        extracted.preferred_locations = matched_locs

    # 4. Budget extraction (handles Lakhs and Crores)
    # e.g., "50 to 80 lakhs", "under 1.5 cr", "80L"
    cr_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:cr|crore|crores)', text)
    lakh_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:l|lakh|lakhs|lac|lacs)', text)

    range_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:-|to)\s*(\d+(?:\.\d+)?)\s*(?:l|lakh|lakhs|cr|crore)', text)
    if range_match:
        mult = 10000000 if "cr" in text else 100000
        extracted.budget_min = float(range_match.group(1)) * mult
        extracted.budget_max = float(range_match.group(2)) * mult
    elif cr_match:
        extracted.budget_max = float(cr_match.group(1)) * 10000000
    elif lakh_match:
        extracted.budget_max = float(lakh_match.group(1)) * 100000

    # 5. Timeline
    if "immediate" in text or "ready to move" in text or "asap" in text:
        extracted.timeline = "immediate"
    elif "1 month" in text:
        extracted.timeline = "within_1_month"
    elif "3 month" in text:
        extracted.timeline = "within_3_months"
    elif "6 month" in text:
        extracted.timeline = "within_6_months"
    elif "explore" in text or "just looking" in text:
        extracted.timeline = "exploring"

    # 6. Purpose
    if "invest" in text or "rental" in text:
        extracted.purpose = "investment"
    elif "self" in text or "family" in text or "live" in text or "stay" in text:
        extracted.purpose = "self_use"

    # Merge with current profile
    updated_profile = merge_extracted_into_profile(current_profile, extracted)
    missing = updated_profile.get_missing_fields()

    # Generate helpful reply
    if not missing:
        reply = "Wonderful! I have all your core preferences recorded. Let's find your matching properties!"
    else:
        next_to_ask = missing[0]
        if next_to_ask == "Budget Range":
            reply = "Great! What approximate budget range (in Lakhs or Crores) are you considering?"
        elif next_to_ask == "Preferred Location(s)":
            reply = "Got it! Which areas or neighborhoods do you prefer?"
        elif next_to_ask == "Purchase Timeline":
            reply = "Understood. How soon are you planning to make the purchase (e.g., immediate, within 3 months, or within 6 months)?"
        elif next_to_ask == "Purpose (Self-use / Investment)":
            reply = "Noted. Is this property intended for your own family's use, or as an investment?"
        else:
            reply = f"Thank you! Could you also share your preference for {next_to_ask}?"

    return ExtractionResult(
        extracted_info=extracted,
        updated_profile=updated_profile,
        missing_fields=missing,
        assistant_reply=reply,
        is_complete=len(missing) == 0
    )


def extract_lead_requirements(
    chat_history: List[Dict[str, str]], 
    current_profile: Optional[LeadProfile] = None
) -> ExtractionResult:
    """Takes conversation history and updates the structured LeadProfile using Groq LLM
    or the intelligent fallback if the API key is not configured.
    """
    if current_profile is None:
        current_profile = LeadProfile(lead_id="L-001")

    api_key = os.getenv("GROQ_API_KEY", "").strip()
    is_dummy_key = not api_key or api_key == "your_groq_api_key_here"

    latest_user_msg = next((m["content"] for m in reversed(chat_history) if m["role"] == "user"), "")

    if is_dummy_key:
        return _heuristic_fallback_extraction(latest_user_msg, current_profile)

    try:
        from groq import Groq
        client = Groq(api_key=api_key)

        # Context summary of what has been captured so far
        context_summary = f"""Current Known Profile State:
- Name: {current_profile.name or 'Unknown'}
- Budget Min: {current_profile.budget_min or 'Unknown'}
- Budget Max: {current_profile.budget_max or 'Unknown'}
- Locations: {', '.join(current_profile.preferred_locations) if current_profile.preferred_locations else 'None'}
- Property Type: {current_profile.property_type or 'Unknown'}
- Bedrooms: {current_profile.bedrooms or 'Unknown'}
- Timeline: {current_profile.timeline or 'Unknown'}
- Purpose: {current_profile.purpose or 'Unknown'}
"""

        messages = [
            {"role": "system", "content": SYSTEM_INTAKE_PROMPT},
            {"role": "system", "content": context_summary}
        ]
        # Include conversation history (last 8 messages for context)
        for msg in chat_history[-8:]:
            messages.append({"role": msg["role"], "content": msg["content"]})

        # Try models in order of capability on Groq
        models_to_try = [
            "qwen/qwen3.8-27b",
            "qwen/qwen3.6-27b",
            "openai/gpt-oss-120b",
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
        ]
        response = None
        last_err = None

        for model_name in models_to_try:
            try:
                response = client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=0.2,
                    max_tokens=600
                )
                if response:
                    break
            except Exception as e:
                last_err = e
                continue

        if not response:
            raise last_err or Exception("Failed to query Groq models")

        raw_content = response.choices[0].message.content
        data = json.loads(raw_content)

        extracted_dict = data.get("extracted_info", {})
        extracted_info = ExtractedLeadInfo(**extracted_dict)

        updated_profile = merge_extracted_into_profile(current_profile, extracted_info)
        missing_fields = updated_profile.get_missing_fields()
        assistant_reply = data.get("assistant_reply") or "Thank you for the information! Let me review your requirements."

        return ExtractionResult(
            extracted_info=extracted_info,
            updated_profile=updated_profile,
            missing_fields=missing_fields,
            assistant_reply=assistant_reply,
            is_complete=len(missing_fields) == 0
        )

    except Exception as exc:
        # Gracefully fall back to local heuristic so conversation never breaks
        fallback = _heuristic_fallback_extraction(latest_user_msg, current_profile)
        return fallback
