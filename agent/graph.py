# agent/graph.py
import os
import json
from groq import Groq
from services.lead_scorer import calculate_lead_score, get_qualification_status

def run_decision_agent(lead_profile: dict, matched_properties: list) -> dict:
    """
    Runs the LLM agent to decide the next action based on lead profile and matches.
    Returns a dictionary representing the agent's decision.
    """
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key or api_key == "your_groq_api_key_here":
        # Fallback for UI if API key is not yet set
        score = calculate_lead_score(lead_profile, matched_properties)
        return {
            "qualification_status": get_qualification_status(score),
            "score": score,
            "next_action": "ERROR: Groq API Key missing",
            "reasoning": ["Please add your Groq API key to the .env file."],
            "broker_summary": "System error."
        }

    client = Groq(api_key=api_key)
    
    # Pre-calculate deterministic score to guide the LLM
    score = calculate_lead_score(lead_profile, matched_properties)
    status = get_qualification_status(score)
    
    system_prompt = f"""
    You are an expert real estate AI agent. Your job is to review a buyer's profile and matching properties, 
    and decide the NEXT BEST ACTION. 
    
    Lead Score (Deterministic): {score}/100
    Qualification Status: {status}
    
    Rules for next action:
    - ESCALATE_TO_BROKER: If score >= 80 and at least 1 property matches well.
    - SEND_PROPERTY_SHORTLIST: If score >= 60 and properties exist.
    - REQUEST_INFORMATION: If critical information (budget, location, timeline) is missing.
    - LOW_PRIORITY: If score < 40 or no matching properties for their budget.
    
    You MUST output your response strictly as a JSON object with this exact schema:
    {{
        "qualification_status": "{status}",
        "score": {score},
        "next_action": "ESCALATE_TO_BROKER | SEND_PROPERTY_SHORTLIST | REQUEST_INFORMATION | LOW_PRIORITY",
        "reasoning": ["reason 1", "reason 2"],
        "broker_summary": "Short paragraph summarizing the lead for the human broker."
    }}
    """
    
    # We only send essential facts to the LLM to avoid overwhelming context
    user_content = json.dumps({
        "lead_profile": lead_profile,
        "matched_properties_count": len(matched_properties),
        "top_matches": [p.get("title", p.get("property_id")) for p in matched_properties[:3]]
    })
    
    try:
        response = client.chat.completions.create(
            model="llama3-8b-8192",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            response_format={"type": "json_object"},
            temperature=0.2
        )
        
        decision = json.loads(response.choices[0].message.content)
        
        # Fallback to ensure score and status aren't overwritten badly by LLM
        decision["score"] = score
        decision["qualification_status"] = status
        
        return decision
    except Exception as e:
        return {
            "qualification_status": status,
            "score": score,
            "next_action": "ERROR",
            "reasoning": [f"Failed to parse LLM output: {str(e)}"],
            "broker_summary": "Error analyzing lead."
        }
