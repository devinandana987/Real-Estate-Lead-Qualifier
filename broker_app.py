# broker_app.py
"""
Broker Operations & Lead Management Portal
Combines:
- Member 3: AI Decision Engine & Scorer (agent.graph, services.lead_scorer, ui.decision_agent)
- Member 4: SQLite Persistence Layer & Broker Management Dashboard (database.db, ui.dashboard)
Can be launched independently:
    python -m streamlit run broker_app.py
"""

import os
import sys
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st
from dotenv import load_dotenv

# Load environment variables
load_dotenv(override=True)

from database.db import (
    initialize_database,
    get_dashboard_statistics,
    get_leads,
    get_lead,
    get_lead_matches,
    save_decision
)
from services.property_matcher import find_matches
from agent.graph import run_decision_agent
from ui.dashboard import render_dashboard
from ui.decision_agent import render_decision_agent


def main():
    st.set_page_config(
        page_title="Broker Operations Portal",
        layout="wide",
        initial_sidebar_state="collapsed"
    )

    # Professional CSS: completely hides deploy button, header decorations, and sidebar
    st.markdown("""
    <style>
    /* Hide Streamlit Deploy button and standard header chrome */
    .stDeployButton, [data-testid="stAppDeployButton"] {
        display: none !important;
    }
    #MainMenu, footer {
        visibility: hidden !important;
    }
    /* Hide sidebar and toggle control */
    [data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] {
        display: none !important;
    }
    header[data-testid="stHeader"] {
        background-color: transparent !important;
        height: 0px !important;
    }
    .block-container {
        padding-top: 1.5rem !important;
        padding-bottom: 3rem !important;
    }
    </style>
    """, unsafe_allow_html=True)

    # Initialize database
    try:
        initialize_database()
    except Exception as e:
        st.error(f"Database connection notice: {e}")

    # Professional Header (no emojis, no team hackathon build box)
    st.title("Broker Operations & Lead Management Portal")
    st.caption("Centralized console for reviewing incoming leads, AI qualification scores, property matches, and sales pipeline workflows.")
    st.markdown("---")

    # =========================================================================
    # NAVIGATION TABS (Broker-Facing Components)
    # =========================================================================
    tab_dashboard, tab_decision = st.tabs([
        "Leads Registry & CRM Pipeline",
        "AI Decision & Qualification Engine"
    ])

    # -------------------------------------------------------------------------
    # TAB 1: BROKER MANAGEMENT DASHBOARD (MEMBER 4)
    # -------------------------------------------------------------------------
    with tab_dashboard:
        render_dashboard()

    # -------------------------------------------------------------------------
    # TAB 2: AI DECISION ENGINE & EVALUATION (MEMBER 3)
    # -------------------------------------------------------------------------
    with tab_decision:
        st.subheader("AI Decision Engine & Evaluation")
        st.caption("Inspect and execute the AI Decision Agent for any lead currently registered in the database.")

        # Fetch available leads
        all_leads = get_leads(limit=200)
        if not all_leads:
            st.info("No leads available in the database. Client inquiries submitted through the User Portal will appear here.")
        else:
            lead_choices = [
                f"{l['lead_id']} - {l.get('name') or 'Anonymous'} ({l.get('lead_quality') or 'UNASSIGNED'}, Score: {l.get('lead_score') or 0})"
                for l in all_leads
            ]
            selected_choice = st.selectbox("Select Lead to Evaluate:", options=lead_choices, index=0)
            selected_lead_id = selected_choice.split(" - ")[0].strip()

            target_lead = get_lead(selected_lead_id)
            if target_lead:
                # Fetch existing property matches or recalculate if needed
                stored_matches = get_lead_matches(selected_lead_id)
                if not stored_matches:
                    stored_matches = find_matches(requirements=target_lead, min_score=40.0)

                d_col1, d_col2 = st.columns([3, 1])
                with d_col1:
                    st.markdown(f"**Lead:** `{target_lead['lead_id']}` | **Name:** {target_lead.get('name') or 'Anonymous'} | "
                                f"**Location:** {target_lead.get('preferred_locality') or ''} {target_lead.get('preferred_city') or ''} | "
                                f"**Matches:** {len(stored_matches)}")
                with d_col2:
                    run_eval = st.button("Run AI Decision Agent", use_container_width=True, type="primary")

                if run_eval or st.session_state.get(f"decision_{selected_lead_id}"):
                    if run_eval:
                        with st.spinner("AI evaluating buyer intent, inventory fit, and recommended next action..."):
                            decision_result = run_decision_agent(
                                lead_profile=target_lead,
                                matched_properties=stored_matches
                            )
                            st.session_state[f"decision_{selected_lead_id}"] = decision_result
                            # Persist updated decision into database
                            save_decision(selected_lead_id, decision_result)

                    active_decision = st.session_state.get(f"decision_{selected_lead_id}")
                    if active_decision:
                        render_decision_agent(active_decision)
                else:
                    # If the lead already has decision recorded in database, show current state
                    if target_lead.get("next_action"):
                        existing_decision = {
                            "score": target_lead.get("lead_score") or 0,
                            "qualification_status": target_lead.get("lead_quality") or "UNASSIGNED",
                            "next_action": target_lead.get("next_action") or "PENDING",
                            "reasoning": [target_lead.get("decision_reason")] if target_lead.get("decision_reason") else [],
                            "broker_summary": target_lead.get("broker_summary") or "No briefing recorded."
                        }
                        render_decision_agent(existing_decision)
                    else:
                        st.info("Click 'Run AI Decision Agent' to evaluate this lead.")


if __name__ == "__main__":
    main()
