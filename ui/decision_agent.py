# ui/decision_agent.py
import streamlit as st
import time

def render_decision_agent(decision_data: dict):
    """
    Renders the AI Agent Trace and Decision in Streamlit.
    Expected input is the dictionary returned by agent.graph.run_decision_agent().
    """
    st.subheader("AI Qualification & Decision Engine")
    
    if not decision_data:
        st.info("Waiting for lead profile and property matches to run evaluation...")
        return
        
    # Simulate thinking trace (Agent Trace)
    with st.status("Agent analyzing lead...", expanded=True) as status:
        st.write("Lead profile parsed.")
        time.sleep(0.3)
        st.write("Property dataset scanned.")
        time.sleep(0.3)
        st.write(f"Lead qualification evaluated: {decision_data.get('score', 0)}/100")
        time.sleep(0.3)
        status.update(label="Analysis Complete", state="complete", expanded=False)
        
    st.markdown("---")
    
    # Layout the decision
    col1, col2 = st.columns(2)
    
    with col1:
        score = decision_data.get('score', 0)
        status_tier = decision_data.get('qualification_status', 'UNKNOWN')
        st.metric("Qualification Score", f"{score}/100", status_tier)
        
        action = decision_data.get('next_action', 'UNKNOWN')
        
        # Display action with appropriate styling
        if action == "ESCALATE_TO_BROKER":
            st.success(f"**RECOMMENDED ACTION:**\n\n### {action}")
        elif action == "LOW_PRIORITY":
            st.error(f"**RECOMMENDED ACTION:**\n\n### {action}")
        elif action == "SEND_PROPERTY_SHORTLIST":
            st.info(f"**RECOMMENDED ACTION:**\n\n### {action}")
        else:
            st.warning(f"**RECOMMENDED ACTION:**\n\n### {action}")
            
    with col2:
        st.markdown("**Decision Reasoning:**")
        reasoning_list = decision_data.get('reasoning', [])
        if isinstance(reasoning_list, list):
            for reason in reasoning_list:
                st.markdown(f"- {reason}")
        else:
            st.markdown(f"- {reasoning_list}")
            
    st.markdown("---")
    st.markdown("**Executive Briefing Summary:**")
    st.info(decision_data.get('broker_summary', 'No summary provided.'))
