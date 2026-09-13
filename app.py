# app.py
"""
Real Estate Lead Qualifier — Master Integration Entry Point
Unifies all four independently developed team components into a single, cohesive application:
- Member 1: AI Lead Intake & Understanding (agent.schemas, agent.prompts, ui.lead_intake)
- Member 2: Property Matching Engine (services.property_matcher, ui.property_matching)
- Member 3: AI Decision Engine & Scorer (agent.graph, services.lead_scorer, ui.decision_agent)
- Member 4: Qualification Service, SQLite Persistence & Broker Dashboard (services.qualification, database.db, ui.dashboard)
"""

import os
import sys
from pathlib import Path

# Ensure project root is at the front of sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st
from dotenv import load_dotenv

# Load environment variables
load_dotenv(override=True)

# Domain Imports from Team Components
from agent.schemas import LeadProfile
from agent.prompts import extract_lead_requirements
from services.property_matcher import find_matches
from services.lead_scorer import calculate_lead_score, get_qualification_status
from agent.graph import run_decision_agent
from services.qualification import process_and_store_lead, format_currency_inr
from database.db import initialize_database, get_dashboard_statistics, get_lead

# UI Component Imports
from ui.lead_intake import render_lead_intake, init_intake_state
from ui.property_matching import render_property_matches
from ui.decision_agent import render_decision_agent
from ui.dashboard import render_dashboard


def init_app_state():
    """Initializes shared session state variables across all components."""
    # Initialize database with auto-seeding if empty
    try:
        initialize_database()
    except Exception as e:
        st.error(f"Database initialization notice: {e}")

    # Initialize Member 1 intake state
    init_intake_state()

    # Shared properties and decision states
    if "matched_properties" not in st.session_state:
        st.session_state["matched_properties"] = []

    if "decision_data" not in st.session_state:
        st.session_state["decision_data"] = None

    if "active_tab_index" not in st.session_state:
        st.session_state["active_tab_index"] = 0


def execute_full_pipeline(lead_profile: LeadProfile) -> dict:
    """
    Executes the complete end-to-end qualification pipeline programmatically:
    Intake Profile -> Property Matcher -> AI Decision Agent -> SQLite Persistence.
    """
    profile_dict = lead_profile.model_dump()
    # Ensure 'locations' alias is provided for Member 3's baseline scorer
    if profile_dict.get("preferred_locations") and not profile_dict.get("locations"):
        profile_dict["locations"] = profile_dict["preferred_locations"]

    # 1. Match Properties
    matches = find_matches(requirements=profile_dict, min_score=40.0)
    st.session_state["matched_properties"] = matches

    # 2. Run AI Decision Agent
    decision = run_decision_agent(lead_profile=profile_dict, matched_properties=matches)
    st.session_state["decision_data"] = decision

    # 3. Process & Persist via Member 4 Qualification Bridge
    result = process_and_store_lead(
        lead_profile=profile_dict,
        property_matches=matches,
        decision=decision
    )

    return {
        "matches": matches,
        "decision": decision,
        "result": result
    }


def main():
    st.set_page_config(
        page_title="Real Estate Lead Qualifier — Multi-Agent CRM",
        page_icon="🏢",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    init_app_state()
    active_profile: LeadProfile = st.session_state.get("lead_profile")

    # =========================================================================
    # SIDEBAR: System Status, Active Lead Card & 1-Click Pipeline Demo
    # =========================================================================
    with st.sidebar:
        st.markdown("## 🏢 Lead Qualifier")
        st.caption("Integrated Hackathon Multi-Agent System")

        st.markdown("---")
        st.markdown("### 👤 Active Lead Overview")
        if active_profile:
            st.markdown(f"**Lead ID:** `{active_profile.lead_id}`")
            st.markdown(f"**Name:** {active_profile.name or 'Anonymous'}")
            st.markdown(f"**Budget:** {active_profile.budget_display()}")
            locs = ", ".join(active_profile.preferred_locations) if active_profile.preferred_locations else "None specified"
            st.markdown(f"**Locations:** {locs}")
            bhk_str = f"{active_profile.bedrooms} BHK" if active_profile.bedrooms else "Not specified"
            st.markdown(f"**Config:** {bhk_str} ({active_profile.property_type or 'Any'})")
            st.markdown(f"**Timeline:** {(active_profile.timeline or 'Not specified').replace('_', ' ').title()}")
            st.markdown(f"**Completeness:** `{active_profile.completeness_percentage()}%`")
            st.progress(active_profile.completeness_percentage() / 100.0)

        st.markdown("---")
        st.markdown("### ⚡ Rapid Demo Scenarios")
        st.caption("Instantly test end-to-end matching, AI scoring, and persistence:")

        if st.button("🚀 Demo 1: Rahul (3BHK Kakkanad 80L)", use_container_width=True):
            st.session_state["lead_profile"] = LeadProfile(
                lead_id="L-DEMO-01",
                name="Rahul Menon",
                budget_min=6500000.0,
                budget_max=8000000.0,
                preferred_locations=["Kakkanad", "Edappally"],
                property_type="Apartment",
                bedrooms=3,
                timeline="immediate",
                purpose="self_use"
            )
            with st.spinner("Running full pipeline (Matcher ➔ AI Agent ➔ Database)..."):
                pipeline_out = execute_full_pipeline(st.session_state["lead_profile"])
                st.success(f"Lead saved! Matches: {len(pipeline_out['matches'])} | Action: {pipeline_out['decision'].get('next_action')}")
                st.rerun()

        if st.button("🏡 Demo 2: Dr. Joseph (Villa 2 Cr)", use_container_width=True):
            st.session_state["lead_profile"] = LeadProfile(
                lead_id="L-DEMO-02",
                name="Dr. Joseph Varghese",
                budget_min=15000000.0,
                budget_max=20000000.0,
                preferred_locations=["Kakkanad", "Tripunithura"],
                property_type="Villa",
                bedrooms=4,
                timeline="immediate",
                purpose="self_use"
            )
            with st.spinner("Running full pipeline (Matcher ➔ AI Agent ➔ Database)..."):
                pipeline_out = execute_full_pipeline(st.session_state["lead_profile"])
                st.success(f"Lead saved! Matches: {len(pipeline_out['matches'])} | Action: {pipeline_out['decision'].get('next_action')}")
                st.rerun()

        if st.button("⚠️ Demo 3: Incomplete Lead (Missing Budget)", use_container_width=True):
            st.session_state["lead_profile"] = LeadProfile(
                lead_id="L-DEMO-03",
                name="Vikram Sethu",
                preferred_locations=["Kakkanad"],
                property_type="Apartment",
                bedrooms=3,
                timeline="immediate",
                purpose="self_use"
            )
            with st.spinner("Running full pipeline..."):
                pipeline_out = execute_full_pipeline(st.session_state["lead_profile"])
                st.warning(f"Evaluated! Action: {pipeline_out['decision'].get('next_action')} (Request Information)")
                st.rerun()

        st.markdown("---")
        st.markdown("### 📊 Database Quick Stats")
        try:
            db_stats = get_dashboard_statistics()
            st.metric("Total Leads in CRM", db_stats.get("total_leads", 0))
            st.metric("🔥 Hot Leads", db_stats.get("hot_leads", 0))
            st.metric("🚀 Escalated", db_stats.get("escalated_leads", 0))
        except Exception:
            pass

    # =========================================================================
    # MAIN APPLICATION HEADER
    # =========================================================================
    header_col1, header_col2 = st.columns([3, 1])
    with header_col1:
        st.title("🏢 Real Estate Lead Qualifier")
        st.markdown(
            "**Multi-Agent AI Pipeline**: Conversational Intake ➔ Deterministic Property Matching "
            "➔ LLM Decision Engine ➔ SQLite Persistence ➔ Broker Operations CRM"
        )
    with header_col2:
        st.write("")
        st.info("💡 **Team Hackathon Build**\n\nAll 4 Member modules active.")

    # =========================================================================
    # PRIMARY NAVIGATION TABS (All 4 Team Modules)
    # =========================================================================
    tab1, tab2, tab3, tab4 = st.tabs([
        "🏡 1. AI Lead Intake (Chat & Extract)",
        "🏠 2. Property Matching Engine",
        "🤖 3. AI Decision Engine & Scorer",
        "🏢 4. Broker Management Dashboard"
    ])

    # -------------------------------------------------------------------------
    # TAB 1: MEMBER 1 — LEAD INTAKE & REQUIREMENT UNDERSTANDING
    # -------------------------------------------------------------------------
    with tab1:
        render_lead_intake()

        st.markdown("---")
        # Action button to advance to Property Matching
        intake_col1, intake_col2 = st.columns([3, 1])
        with intake_col1:
            if active_profile and active_profile.completeness_percentage() > 0:
                st.info(f"Active Lead `{active_profile.lead_id}` requirements are ready. Move to matching to inspect available inventory.")
        with intake_col2:
            if st.button("Find Matching Properties ➔", use_container_width=True, type="primary"):
                # Automatically calculate matches
                p_dict = active_profile.model_dump()
                st.session_state["matched_properties"] = find_matches(requirements=p_dict)
                st.success(f"Matched {len(st.session_state['matched_properties'])} properties! Switch to Tab 2 to view details.")

    # -------------------------------------------------------------------------
    # TAB 2: MEMBER 2 — PROPERTY MATCHING ENGINE
    # -------------------------------------------------------------------------
    with tab2:
        st.markdown("### 🏠 Property Matching & Inventory Search")
        st.caption("Matches active lead criteria against our curated Kerala properties dataset using deterministic multi-attribute scoring.")

        if not active_profile:
            st.warning("No active lead found. Please converse in Tab 1 first or select a Demo Lead from the sidebar.")
        else:
            p_dict = active_profile.model_dump()

            # Refresh matching button
            m_top1, m_top2 = st.columns([3, 1])
            with m_top1:
                st.markdown(f"**Matching for:** `{active_profile.lead_id}` ({active_profile.name or 'Anonymous'}) | "
                            f"**Budget:** {active_profile.budget_display()} | **Locations:** {', '.join(active_profile.preferred_locations) or 'Any'}")
            with m_top2:
                if st.button("🔄 Recalculate Matches", use_container_width=True):
                    st.session_state["matched_properties"] = find_matches(requirements=p_dict, min_score=40.0)
                    st.rerun()

            # Compute if not yet in state
            if not st.session_state.get("matched_properties"):
                st.session_state["matched_properties"] = find_matches(requirements=p_dict, min_score=40.0)

            matches = st.session_state["matched_properties"]
            render_property_matches(matches)

            st.markdown("---")
            nav_col1, nav_col2 = st.columns([3, 1])
            with nav_col1:
                st.write("")
            with nav_col2:
                if st.button("Evaluate with AI Decision Agent ➔", use_container_width=True, type="primary"):
                    st.session_state["decision_data"] = run_decision_agent(
                        lead_profile=p_dict,
                        matched_properties=matches
                    )
                    st.success("Decision evaluated! Switch to Tab 3 to view agent reasoning.")

    # -------------------------------------------------------------------------
    # TAB 3: MEMBER 3 — AI DECISION ENGINE & QUALIFICATION
    # -------------------------------------------------------------------------
    with tab3:
        st.markdown("### 🤖 AI Qualification & Next Best Action Agent")
        st.caption("Evaluates buyer urgency, intent, inventory fit, and recommends an automated next action with human broker briefings.")

        if not active_profile:
            st.warning("No active lead found. Please start with Tab 1 or select a Demo Lead from the sidebar.")
        else:
            p_dict = active_profile.model_dump()
            matches = st.session_state.get("matched_properties") or []

            eval_col1, eval_col2 = st.columns([3, 1])
            with eval_col1:
                st.markdown(f"**Lead Profile:** `{active_profile.lead_id}` | **Matches Available:** {len(matches)}")
            with eval_col2:
                if st.button("🧠 Run AI Decision Agent", use_container_width=True):
                    with st.spinner("AI evaluating lead qualification and next action..."):
                        st.session_state["decision_data"] = run_decision_agent(
                            lead_profile=p_dict,
                            matched_properties=matches
                        )
                        st.rerun()

            # Render decision UI if available
            decision_data = st.session_state.get("decision_data")
            if decision_data:
                render_decision_agent(decision_data)

                st.markdown("---")
                save_col1, save_col2 = st.columns([3, 1])
                with save_col1:
                    st.info("Commit this qualified lead, AI trace, and property matches to the SQLite database.")
                with save_col2:
                    if st.button("💾 Save Lead to CRM Database", use_container_width=True, type="primary"):
                        save_result = process_and_store_lead(
                            lead_profile=p_dict,
                            property_matches=matches,
                            decision=decision_data
                        )
                        if save_result.get("success"):
                            st.success(f"✅ Lead `{active_profile.lead_id}` safely saved to SQLite CRM! Switch to Tab 4 to view.")
                        else:
                            st.error(f"❌ Storage error: {save_result.get('errors')}")
            else:
                st.info("Click **'Run AI Decision Agent'** above to evaluate this lead.")

    # -------------------------------------------------------------------------
    # TAB 4: MEMBER 4 — BROKER MANAGEMENT DASHBOARD
    # -------------------------------------------------------------------------
    with tab4:
        render_dashboard()


if __name__ == "__main__":
    main()
