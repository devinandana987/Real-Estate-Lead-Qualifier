# app.py
"""
Real Estate Property Finder & Requirement Intake (User / Client Portal)
Combines:
- Member 1: AI Lead Intake & Conversational Requirement Extraction (ui.lead_intake)
- Member 2: Property Matching Engine (services.property_matcher, ui.property_matching)
- Automated Background Persistence: Stores qualified inquiries into SQLite (database.db)
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

from agent.schemas import LeadProfile
from services.property_matcher import find_matches
from services.qualification import process_and_store_lead
from database.db import initialize_database
from ui.lead_intake import render_lead_intake, init_intake_state
from ui.property_matching import render_property_matches


def init_user_app():
    """Initializes database and session state for the client portal."""
    try:
        initialize_database()
    except Exception as e:
        st.error(f"Database initialization error: {e}")

    init_intake_state()

    if "user_matches" not in st.session_state:
        st.session_state["user_matches"] = None

    if "show_matches" not in st.session_state:
        st.session_state["show_matches"] = False


def main():
    st.set_page_config(
        page_title="Real Estate Property Finder",
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

    init_user_app()
    active_profile: LeadProfile = st.session_state.get("lead_profile")

    # Clean, professional header (no emojis, no hackathon build box)
    st.title("Real Estate Property Finder & Requirement Intake")
    st.caption("Describe your property preferences below. Our system extracts structured criteria and identifies matching inventory.")
    st.markdown("---")

    # =========================================================================
    # SECTION 1: CONVERSATIONAL INTAKE & STRUCTURED PROFILE (MEMBER 1)
    # =========================================================================
    render_lead_intake()

    st.markdown("---")

    # =========================================================================
    # SECTION 2: MATCHING TRIGGER & INLINE RESULTS DISPLAY (MEMBER 2)
    # =========================================================================
    st.markdown("### Property Inventory Matching")
    
    col_msg, col_btn = st.columns([3, 1])
    with col_msg:
        st.write("Search available property inventory matching your active requirement profile.")
    with col_btn:
        if st.button("Find Matching Properties", use_container_width=True, type="primary"):
            active_profile = st.session_state.get("lead_profile")
            has_requirements = False
            if active_profile:
                has_requirements = bool(
                    active_profile.budget_min
                    or active_profile.budget_max
                    or (active_profile.preferred_locations and len(active_profile.preferred_locations) > 0)
                    or active_profile.property_type
                    or (active_profile.bedrooms is not None and active_profile.bedrooms > 0)
                )

            if not has_requirements:
                st.session_state["show_matches"] = False
                st.session_state["user_matches"] = []
                st.session_state["matching_warning"] = "Please specify your property requirements (such as location, budget, bedroom count, or property type) in the consultation chat above before searching for matches."
            else:
                st.session_state["matching_warning"] = None
                p_dict = active_profile.model_dump()
                matches = find_matches(requirements=p_dict, min_score=40.0)
                st.session_state["user_matches"] = matches
                st.session_state["show_matches"] = True

                # Persist lead and matches in SQLite for broker visibility
                try:
                    process_and_store_lead(
                        lead_profile=p_dict,
                        property_matches=matches,
                        decision=None
                    )
                except Exception:
                    pass

    # Show warning if user clicked without requirements
    if st.session_state.get("matching_warning"):
        st.warning(st.session_state["matching_warning"])

    # Display matches inline below intake contents
    if st.session_state.get("show_matches"):
        matches = st.session_state.get("user_matches") or []
        if matches:
            st.success(f"Found {len(matches)} suitable properties matching your profile.")
        render_property_matches(matches)


if __name__ == "__main__":
    main()
