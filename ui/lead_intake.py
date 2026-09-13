import os
import sys
from pathlib import Path

# Ensure project root is on sys.path when running standalone (e.g., streamlit run ui/lead_intake.py)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st
import pandas as pd
from agent.schemas import LeadProfile
from agent.prompts import extract_lead_requirements


def init_intake_state():
    """Initializes session state variables required for Lead Intake."""
    if "lead_id_counter" not in st.session_state:
        st.session_state["lead_id_counter"] = 101

    if "lead_profile" not in st.session_state:
        lead_id = f"L{st.session_state['lead_id_counter']:03d}"
        st.session_state["lead_profile"] = LeadProfile(lead_id=lead_id)

    if "messages" not in st.session_state:
        st.session_state["messages"] = [
            {
                "role": "assistant",
                "content": "👋 **Hello! I'm your AI Real Estate Advisor.** Tell me what kind of home you are looking for—such as your preferred area, budget, BHK, and timeline—and I will extract your requirements and find matching properties!"
            }
        ]

    if "missing_fields" not in st.session_state:
        st.session_state["missing_fields"] = st.session_state["lead_profile"].get_missing_fields()


def reset_lead_intake():
    """Resets the intake session for a new lead."""
    st.session_state["lead_id_counter"] += 1
    new_id = f"L{st.session_state['lead_id_counter']:03d}"
    st.session_state["lead_profile"] = LeadProfile(lead_id=new_id)
    st.session_state["missing_fields"] = st.session_state["lead_profile"].get_missing_fields()
    st.session_state["messages"] = [
        {
            "role": "assistant",
            "content": f"New consultation started for **Lead {new_id}**. What property requirements can I note down for you today?"
        }
    ]


def process_user_input(user_text: str):
    """Processes incoming user message through the intake extractor."""
    if not user_text or not user_text.strip():
        return

    # Add user message
    st.session_state["messages"].append({"role": "user", "content": user_text.strip()})

    # Run extraction
    result = extract_lead_requirements(
        chat_history=st.session_state["messages"],
        current_profile=st.session_state["lead_profile"]
    )

    # Update state
    st.session_state["lead_profile"] = result.updated_profile
    st.session_state["missing_fields"] = result.missing_fields

    # Add assistant response
    st.session_state["messages"].append({
        "role": "assistant",
        "content": result.assistant_reply
    })


def render_lead_intake():
    """Main rendering function for Member 1: Lead Intake & Understanding.
    Imported into app.py or run standalone.
    """
    init_intake_state()
    profile: LeadProfile = st.session_state["lead_profile"]

    # Header section
    top_col1, top_col2 = st.columns([4, 1])
    with top_col1:
        st.subheader("🏡 AI Lead Intake & Requirement Understanding")
        st.caption("Converse naturally in chat. The AI agent extracts structured criteria and flags missing details in real-time.")
    with top_col2:
        if st.button("🔄 New Lead", use_container_width=True, help="Reset and start intake for a new buyer"):
            reset_lead_intake()
            st.rerun()

    st.markdown("---")

    # Quick prompt scenario buttons for rapid judge testing
    st.markdown("**⚡ Quick Test Scenarios:**")
    q_col1, q_col2, q_col3 = st.columns(3)
    quick_prompt = None

    with q_col1:
        if st.button("🏢 3 BHK in Kakkanad under 80L", use_container_width=True):
            quick_prompt = "Hi, I am Rahul. Looking for a 3 BHK apartment in Kakkanad under 80 lakhs for family self-use within 3 months."
    with q_col2:
        if st.button("🏡 Luxury Villa in Edappally", use_container_width=True):
            quick_prompt = "Looking for a luxury 4 BHK Villa in Edappally or Palarivattom. Budget is 2.5 Crores for investment."
    with q_col3:
        if st.button("🌊 2 BHK Marine Drive", use_container_width=True):
            quick_prompt = "Need a 2 BHK apartment in Marine Drive, budget around 60 to 75 lakhs, ready to move immediately."

    if quick_prompt:
        process_user_input(quick_prompt)
        st.rerun()

    # Main split: Left = Chat, Right = Extracted Requirements Profile
    chat_col, profile_col = st.columns([3, 2], gap="large")

    # ==================== LEFT COLUMN: CHAT INTERFACE ====================
    with chat_col:
        st.markdown(f"#### 💬 Conversation History `[{profile.lead_id}]`")
        
        # Chat messages scrollable container
        chat_container = st.container(height=420)
        with chat_container:
            for msg in st.session_state["messages"]:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])

        # Chat input box
        user_input = st.chat_input("Tell me your requirements (e.g., 'Looking for a 3 BHK in Kakkanad under 75L')...")
        if user_input:
            process_user_input(user_input)
            st.rerun()

    # ==================== RIGHT COLUMN: EXTRACTED REQUIREMENTS ====================
    with profile_col:
        st.markdown("#### 📋 Extracted Requirements")

        # Completeness Progress
        pct = profile.completeness_percentage()
        st.markdown(f"**Intake Completeness:** `{pct}%`")
        st.progress(pct / 100.0)

        # Missing Fields Notice or Ready Confirmation
        missing = profile.get_missing_fields()
        if not missing:
            st.success("✅ **All Core Requirements Captured!** Ready for property matching.")
        else:
            missing_badges = " ".join([f"`{field}`" for field in missing])
            st.warning(f"⚠️ **Pending Info:** {missing_badges}")

        # Metrics cards
        m_col1, m_col2 = st.columns(2)
        with m_col1:
            st.metric(label="Budget", value=profile.budget_display())
            st.metric(label="Property Type", value=profile.property_type or "Not Specified")
            st.metric(label="Bedrooms", value=f"{profile.bedrooms} BHK" if profile.bedrooms else "Not Specified")

        with m_col2:
            loc_str = ", ".join(profile.preferred_locations) if profile.preferred_locations else "Not Specified"
            st.metric(label="Preferred Location(s)", value=loc_str)
            st.metric(label="Timeline", value=(profile.timeline or "Not Specified").replace("_", " ").title())
            st.metric(label="Purpose", value=(profile.purpose or "Not Specified").replace("_", " ").title())

        # Structured Requirements Table (as required by Feature 1)
        st.markdown("##### 📊 Requirements Summary Table")
        table_data = [
            {"Requirement Field": "Lead ID", "Extracted Value": profile.lead_id, "Status": "✅ Confirmed"},
            {"Requirement Field": "Buyer Name", "Extracted Value": profile.name or "Anonymous", "Status": "✅ Set" if profile.name else "⚪ Optional"},
            {"Requirement Field": "Budget Range", "Extracted Value": profile.budget_display(), "Status": "✅ Captured" if (profile.budget_min or profile.budget_max) else "❌ Missing"},
            {"Requirement Field": "Locations", "Extracted Value": ", ".join(profile.preferred_locations) if profile.preferred_locations else "None", "Status": "✅ Captured" if profile.preferred_locations else "❌ Missing"},
            {"Requirement Field": "Property Type", "Extracted Value": profile.property_type or "None", "Status": "✅ Captured" if profile.property_type else "❌ Missing"},
            {"Requirement Field": "Bedrooms (BHK)", "Extracted Value": str(profile.bedrooms) if profile.bedrooms else "None", "Status": "✅ Captured" if profile.bedrooms else "❌ Missing"},
            {"Requirement Field": "Timeline", "Extracted Value": profile.timeline or "None", "Status": "✅ Captured" if profile.timeline else "❌ Missing"},
            {"Requirement Field": "Purpose", "Extracted Value": profile.purpose or "None", "Status": "✅ Captured" if profile.purpose else "❌ Missing"},
        ]
        df = pd.DataFrame(table_data)
        st.dataframe(df, use_container_width=True, hide_index=True)

        # Developer / Agent JSON trace inspection
        with st.expander("🔍 View Raw Structured JSON (Pydantic Model)"):
            st.json(profile.model_dump())


# Standalone runner for Member 1 testing
if __name__ == "__main__":
    st.set_page_config(
        page_title="Real Estate Lead Qualifier - Lead Intake",
        page_icon="🏡",
        layout="wide",
        initial_sidebar_state="collapsed"
    )
    render_lead_intake()
