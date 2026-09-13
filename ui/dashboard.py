# ui/dashboard.py
"""
Broker-facing Lead Management Dashboard for Real Estate Lead Qualifier.
Standalone Streamlit UI component providing aggregated statistics, filterable lead tables,
deep lead requirement inspections, matched property displays, and status workflows.
"""

from typing import Optional, Dict, Any, List
import streamlit as st
import pandas as pd

from database.db import (
    get_dashboard_statistics,
    get_leads,
    get_lead,
    get_lead_matches,
    update_lead,
    initialize_database
)
from services.qualification import format_currency_inr


def render_action_badge(action: Optional[str]):
    """Renders visual callout according to recommended next action."""
    action_str = str(action or "PENDING").upper()
    if "ESCALATE" in action_str:
        st.success(f"**RECOMMENDED ACTION:**\n\n### {action_str}")
    elif "SHORTLIST" in action_str:
        st.info(f"**RECOMMENDED ACTION:**\n\n### {action_str}")
    elif "REQUEST" in action_str or "CONTINUE" in action_str:
        st.warning(f"**RECOMMENDED ACTION:**\n\n### {action_str}")
    elif "LOW" in action_str or "DISCARD" in action_str:
        st.error(f"**RECOMMENDED ACTION:**\n\n### {action_str}")
    else:
        st.info(f"**RECOMMENDED ACTION:**\n\n### {action_str}")


def render_dashboard(db_path: Optional[str] = None):
    """
    Main entry point for rendering the Broker Dashboard.
    Can be imported by app.py or tested independently.
    """
    st.markdown("## Broker Lead Management Dashboard")
    st.caption("Review incoming leads, AI qualification scores, property matches, and broker recommendations.")

    # Safe database initialization
    try:
        initialize_database(db_path)
        stats = get_dashboard_statistics(db_path)
    except Exception as e:
        st.error(f"Unable to connect to the database: {str(e)}")
        return

    # -------------------------------------------------------------
    # 1. SUMMARY METRICS ROW
    # -------------------------------------------------------------
    m_col1, m_col2, m_col3, m_col4, m_col5, m_col6 = st.columns(6)
    with m_col1:
        st.metric("Total Leads", stats.get("total_leads", 0))
    with m_col2:
        st.metric("Hot Leads", stats.get("hot_leads", 0))
    with m_col3:
        st.metric("Warm Leads", stats.get("warm_leads", 0))
    with m_col4:
        st.metric("Cold / Low", stats.get("cold_leads", 0))
    with m_col5:
        st.metric("Escalated", stats.get("escalated_leads", 0))
    with m_col6:
        st.metric("Pending Follow-up", stats.get("pending_followups", 0))

    st.markdown("---")

    # -------------------------------------------------------------
    # 2. FILTERS AND SEARCH CONTROLS
    # -------------------------------------------------------------
    f_col1, f_col2, f_col3, f_col4 = st.columns([2, 1, 1, 1])

    with f_col1:
        search_query = st.text_input("Search Leads", placeholder="Search by Lead ID, Name, City, or Contact...")
    with f_col2:
        quality_filter = st.selectbox(
            "Quality Tier",
            options=["ALL", "HOT", "WARM", "NURTURE", "LOW PRIORITY", "UNASSIGNED"],
            index=0
        )
    with f_col3:
        action_filter = st.selectbox(
            "Recommended Action",
            options=[
                "ALL",
                "ESCALATE_TO_BROKER",
                "SEND_PROPERTY_SHORTLIST",
                "REQUEST_INFORMATION",
                "CONTINUE_QUALIFICATION",
                "FOLLOW_UP_LATER",
                "LOW_PRIORITY",
                "DISCARD"
            ],
            index=0
        )
    with f_col4:
        status_filter = st.selectbox(
            "Lead Status",
            options=["ALL", "NEW", "IN_REVIEW", "CONTACTED", "MEETING_SCHEDULED", "CLOSED", "ARCHIVED"],
            index=0
        )

    # -------------------------------------------------------------
    # 3. RETRIEVE AND DISPLAY LEADS TABLE
    # -------------------------------------------------------------
    leads = get_leads(
        status=status_filter if status_filter != "ALL" else None,
        lead_quality=quality_filter if quality_filter != "ALL" else None,
        next_action=action_filter if action_filter != "ALL" else None,
        search=search_query if search_query.strip() else None,
        limit=200,
        db_path=db_path
    )

    if not leads:
        if stats.get("total_leads", 0) == 0:
            st.info("No leads found in the database yet. Processed leads will automatically appear here.")
        else:
            st.warning("No leads match the selected filter criteria. Try clearing the filters.")
        return

    # Prepare tabular representation for quick scanning
    table_rows = []
    for l in leads:
        min_b = l.get("min_budget")
        max_b = l.get("max_budget")
        if min_b and max_b:
            budget_display = f"{format_currency_inr(min_b)} - {format_currency_inr(max_b)}"
        elif max_b:
            budget_display = f"Up to {format_currency_inr(max_b)}"
        elif min_b:
            budget_display = f"From {format_currency_inr(min_b)}"
        else:
            budget_display = "Not specified"

        loc_parts = [p for p in [l.get("preferred_locality"), l.get("preferred_city")] if p]
        loc_display = ", ".join(loc_parts) if loc_parts else "Not specified"

        table_rows.append({
            "Lead ID": l.get("lead_id"),
            "Name": l.get("name") or "Anonymous",
            "Intent": l.get("intent") or "Buy",
            "Score": f"{int(l.get('lead_score'))}/100" if l.get("lead_score") is not None else "-",
            "Quality": l.get("lead_quality") or "UNASSIGNED",
            "Location": loc_display,
            "Budget": budget_display,
            "Timeline": l.get("timeline") or "Not specified",
            "Next Action": l.get("next_action") or "PENDING",
            "Status": l.get("status") or "NEW",
            "Created": str(l.get("created_at", ""))[:16]
        })

    df_leads = pd.DataFrame(table_rows)
    st.subheader(f"Leads Registry ({len(df_leads)})")
    st.dataframe(df_leads, use_container_width=True, hide_index=True)

    st.markdown("---")

    # -------------------------------------------------------------
    # 4. LEAD DETAIL VIEW
    # -------------------------------------------------------------
    st.subheader("Lead Specification & Actions")

    # Selectbox to pick a lead
    lead_options = [
        f"{l['lead_id']} - {l.get('name') or 'Anonymous'} ({l.get('lead_quality') or 'UNASSIGNED'}, Score: {l.get('lead_score') or 0})"
        for l in leads
    ]
    selected_option = st.selectbox("Select Lead to Inspect:", options=lead_options, index=0)

    # Extract selected lead_id
    selected_lead_id = selected_option.split(" - ")[0].strip()
    lead_detail = get_lead(selected_lead_id, db_path=db_path)

    if not lead_detail:
        st.error(f"Could not load details for lead ID: {selected_lead_id}")
        return

    # ----------------- PROMINENT BROKER SUMMARY -----------------
    st.markdown("### Executive Briefing Summary")
    summary_text = lead_detail.get("broker_summary")
    if summary_text:
        st.info(summary_text)
    else:
        st.warning("No broker summary recorded for this lead.")

    # ----------------- TWO-COLUMN DETAIL VIEW -----------------
    col_left, col_right = st.columns([1, 1])

    with col_left:
        st.markdown("#### Lead Profile & Parameters")
        b_name = lead_detail.get("name") or "Not specified"
        b_contact = lead_detail.get("contact") or "Not specified"
        b_intent = f"{lead_detail.get('intent', 'Buy')} ({lead_detail.get('intent_level', 'Standard')})"
        b_type = lead_detail.get("property_type") or "Not specified"
        bhk = f"{int(lead_detail.get('bedrooms'))} BHK" if lead_detail.get("bedrooms") else "Not specified"
        baths = f"{int(lead_detail.get('bathrooms'))}" if lead_detail.get("bathrooms") else "Not specified"
        area = f"{lead_detail.get('min_area_sqft')} sq.ft." if lead_detail.get("min_area_sqft") else "Not specified"
        city = lead_detail.get("preferred_city") or "Not specified"
        locality = lead_detail.get("preferred_locality") or "Not specified"
        timeline = lead_detail.get("timeline") or "Not specified"
        possession = lead_detail.get("possession_preference") or "Not specified"
        financing = lead_detail.get("financing_type") or "Not specified"
        loan_req = "Yes" if lead_detail.get("loan_required") == 1 else ("No" if lead_detail.get("loan_required") == 0 else "Not specified")

        st.markdown(f"- **Lead ID:** `{lead_detail.get('lead_id')}`")
        st.markdown(f"- **Contact:** {b_name} | {b_contact}")
        st.markdown(f"- **Intent:** {b_intent}")
        st.markdown(f"- **Property Type:** {b_type} | **Configuration:** {bhk} (Baths: {baths})")
        st.markdown(f"- **Preferred Location:** {locality}, {city}")
        st.markdown(f"- **Target Area:** {area}")
        st.markdown(f"- **Timeline / Possession:** {timeline} | {possession}")
        st.markdown(f"- **Financing:** {financing} (Loan Required: {loan_req})")

        # Profile completeness bar
        completeness = float(lead_detail.get("profile_completeness") or 0.0)
        st.markdown(f"**Profile Completeness:** {completeness}%")
        st.progress(min(1.0, completeness / 100.0))

    with col_right:
        st.markdown("#### Qualification & Decision Trace")

        q_col1, q_col2 = st.columns(2)
        with q_col1:
            score_val = lead_detail.get("lead_score")
            st.metric("Qualification Score", f"{int(score_val)}/100" if score_val is not None else "Pending")
        with q_col2:
            quality_tier = lead_detail.get("lead_quality") or "UNASSIGNED"
            st.metric("Lead Tier", quality_tier)

        # Action Badge
        render_action_badge(lead_detail.get("next_action"))

        # AI Reasoning
        st.markdown("**Decision Reasoning:**")
        reasoning = lead_detail.get("decision_reason")
        if reasoning:
            st.markdown(reasoning)
        else:
            st.write("No reasoning notes provided.")

    st.markdown("---")

    # -------------------------------------------------------------
    # 5. MATCHED PROPERTIES SECTION
    # -------------------------------------------------------------
    st.markdown("### Matched Property Inventory")
    matches = get_lead_matches(selected_lead_id, db_path=db_path)

    if matches:
        match_table_data = []
        for m in matches:
            match_table_data.append({
                "Property ID": m.get("property_id"),
                "Title": m.get("title") or "Unnamed Property",
                "Match Score": f"{m.get('match_percentage')}%" if m.get("match_percentage") is not None else "-",
                "Price": format_currency_inr(m.get("price")),
                "Location": m.get("location") or "-",
                "Match Reason": m.get("match_reason") or "Criteria matched"
            })
        st.dataframe(pd.DataFrame(match_table_data), use_container_width=True, hide_index=True)
    else:
        st.info("No property matches currently linked to this lead.")

    # -------------------------------------------------------------
    # 6. BROKER STATUS WORKFLOW
    # -------------------------------------------------------------
    st.markdown("---")
    st.markdown("### Pipeline Status Workflow")
    current_status = lead_detail.get("status") or "NEW"
    status_options = ["NEW", "IN_REVIEW", "CONTACTED", "MEETING_SCHEDULED", "CLOSED", "ARCHIVED"]

    curr_idx = status_options.index(current_status) if current_status in status_options else 0

    s_col1, s_col2 = st.columns([2, 1])
    with s_col1:
        new_status = st.selectbox("Update Lead Workflow Status:", options=status_options, index=curr_idx)
    with s_col2:
        st.write("")  # alignment spacer
        st.write("")
        if st.button("Update Status", key=f"btn_update_{selected_lead_id}"):
            if new_status != current_status:
                success = update_lead(selected_lead_id, {"status": new_status}, db_path=db_path)
                if success:
                    st.success(f"Lead `{selected_lead_id}` status updated to **{new_status}**.")
                    st.rerun()
                else:
                    st.error("Failed to update status.")
            else:
                st.info("Status is already set to this value.")


if __name__ == "__main__":
    # Allows independent local testing of the dashboard
    st.set_page_config(page_title="Real Estate Broker Dashboard", layout="wide")
    render_dashboard()
