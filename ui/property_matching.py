"""
ui/property_matching.py

Streamlit UI component for displaying matching properties.
Displays property matches returned by services/property_matcher.py.
Follows Member 2 specifications:
- Pure UI component (no property filtering or matching logic).
- Displays property cards with:
  - Title, Property ID, Location, Property type, Match percentage
  - Four-column layout: Bedrooms | Bathrooms | Price | Possession
  - Amenities (displays 'Not specified' if missing)
  - Match Reasoning (only shown if explanation is present)
- Expandable section: '📋 View All Matching Properties as Table' using st.dataframe(..., hide_index=True)
- Handles missing fields gracefully.
- Displays 'No suitable properties found.' when matches is empty.
- Includes local format_inr() helper without altering underlying numeric prices.
"""

from typing import List, Dict, Any, Optional
import streamlit as st
import pandas as pd


def format_inr(amount: Any) -> str:
    """
    Formats numeric amount into Indian Rupee currency string.
    Example: 7500000 -> ₹75,00,000
    """
    if amount is None:
        return "N/A"
    try:
        val = int(round(float(amount)))
    except (ValueError, TypeError):
        return f"₹{amount}"

    s = str(abs(val))
    if len(s) <= 3:
        formatted = s
    else:
        last_three = s[-3:]
        other = s[:-3]
        groups = []
        while len(other) > 2:
            groups.insert(0, other[-2:])
            other = other[:-2]
        if other:
            groups.insert(0, other)
        formatted = f"{','.join(groups)},{last_three}"

    prefix = "-₹" if val < 0 else "₹"
    return f"{prefix}{formatted}"


def render_property_matches(
    matches: Optional[List[Dict[str, Any]]] = None,
    *args,
    **kwargs,
):
    """
    Renders matching properties in Streamlit.

    Args:
        matches: List of property dictionaries returned by services.property_matcher.find_matches.
    """
    st.subheader("Matching Property Recommendations")

    if not matches:
        st.info("No suitable properties found.")
        return

    for prop in matches:
        title = prop.get("title") or "Property"
        prop_id = prop.get("property_id") or "N/A"
        location = prop.get("location") or "Not specified"
        prop_type = prop.get("property_type") or "Not specified"
        bedrooms = prop.get("bedrooms")
        bathrooms = prop.get("bathrooms")
        price = prop.get("price", 0.0)
        possession = prop.get("possession_date") or "Not specified"
        amenities = prop.get("amenities") or "Not specified"
        explanation = prop.get("match_explanation") or prop.get("explanation")

        match_pct = prop.get("match_percentage")
        if not match_pct:
            score = prop.get("match_score")
            match_pct = f"{int(round(score))}%" if score is not None else "N/A"

        try:
            card = st.container(border=True)
        except TypeError:
            card = st.container()

        with card:
            # Header with Title, ID, Location, Type, and Match Score
            col_info, col_metric = st.columns([3, 1])
            with col_info:
                st.markdown(f"### {title} ({prop_id})")
                st.write(f"**Location:** {location} | **Type:** {prop_type}")
            with col_metric:
                st.metric("Match", match_pct)

            # Four-column property details: Bedrooms | Bathrooms | Price | Possession
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.markdown("**Bedrooms**")
                st.write(f"{bedrooms} BHK" if bedrooms else "Not specified")
            with col2:
                st.markdown("**Bathrooms**")
                st.write(f"{bathrooms} Bathrooms" if bathrooms else "Not specified")
            with col3:
                st.markdown("**Price**")
                st.write(f"{format_inr(price)}")
            with col4:
                st.markdown("**Possession**")
                st.write(f"{possession}")

            # Amenities
            st.write(f"**Amenities:** {amenities}")

            # Match explanation if available
            if explanation:
                st.write(f"**Match Evaluation:** {explanation}")

    # Expandable section for table view
    with st.expander("Tabular View of Matches"):
        table_rows = []
        for p in matches:
            pct = p.get("match_percentage")
            if not pct and p.get("match_score") is not None:
                pct = f"{int(round(p['match_score']))}%"
            elif not pct:
                pct = "N/A"

            table_rows.append({
                "ID": p.get("property_id", "N/A"),
                "Title": p.get("title", "N/A"),
                "Location": p.get("location", "Not specified"),
                "Type": p.get("property_type", "Not specified"),
                "BHK": p.get("bedrooms", "N/A"),
                "Baths": p.get("bathrooms", "N/A"),
                "Price": format_inr(p.get("price")),
                "Possession": p.get("possession_date") or "Not specified",
                "Match": pct,
                "Explanation": p.get("match_explanation") or p.get("explanation") or "",
            })
        df = pd.DataFrame(table_rows)
        st.dataframe(df, use_container_width=True, hide_index=True)
