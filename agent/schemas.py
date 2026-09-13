from typing import Optional, List
from pydantic import BaseModel, Field


class ExtractedLeadInfo(BaseModel):
    """Fields extracted directly by the LLM from user conversation."""
    name: Optional[str] = Field(default=None, description="Name of the buyer/client if mentioned")
    budget_min: Optional[float] = Field(default=None, description="Minimum budget in INR (e.g., 5000000 for 50 Lakhs)")
    budget_max: Optional[float] = Field(default=None, description="Maximum budget in INR (e.g., 8000000 for 80 Lakhs)")
    preferred_locations: List[str] = Field(default_factory=list, description="List of preferred areas, localities, or cities")
    property_type: Optional[str] = Field(default=None, description="Type of property, e.g., Apartment, Villa, Independent House, Penthouse, Plot")
    bedrooms: Optional[int] = Field(default=None, description="Number of bedrooms / BHK (e.g., 2, 3, 4)")
    timeline: Optional[str] = Field(default=None, description="Purchase timeframe: immediate, within_1_month, within_3_months, within_6_months, exploring")
    purpose: Optional[str] = Field(default=None, description="Purchase intention: self_use, investment, or rental_income")


class LeadProfile(BaseModel):
    """Primary Lead Profile model shared across all team members and matching the SQLite schema."""
    lead_id: str = Field(description="Unique lead identifier, e.g. L001")
    name: Optional[str] = Field(default=None, description="Full name of the lead")

    budget_min: Optional[float] = Field(default=None, description="Minimum budget in INR")
    budget_max: Optional[float] = Field(default=None, description="Maximum budget in INR")

    preferred_locations: List[str] = Field(default_factory=list, description="Target localities")

    property_type: Optional[str] = Field(default=None, description="e.g. Apartment, Villa")
    bedrooms: Optional[int] = Field(default=None, description="BHK count")

    timeline: Optional[str] = Field(default=None, description="Urgency / purchase timeline")
    purpose: Optional[str] = Field(default=None, description="'self_use' or 'investment'")

    # Filled downstream by Member 3 (Decision Agent) & Member 4 (Dashboard)
    qualification_status: Optional[str] = Field(default="NEW", description="HOT, WARM, COLD, or NEW")
    score: Optional[int] = Field(default=None, description="Lead qualification score 0-100")
    next_action: Optional[str] = Field(default=None, description="e.g. ESCALATE_TO_BROKER, SCHEDULE_CALL, NURTURE")

    def get_missing_fields(self) -> List[str]:
        """Returns list of essential real estate requirement fields that are not yet filled."""
        missing = []
        if self.budget_max is None and self.budget_min is None:
            missing.append("Budget Range")
        if not self.preferred_locations:
            missing.append("Preferred Location(s)")
        if not self.property_type:
            missing.append("Property Type")
        if self.bedrooms is None and (self.property_type or "").lower() not in ["plot", "land", "commercial"]:
            missing.append("Bedrooms (BHK)")
        if not self.timeline:
            missing.append("Purchase Timeline")
        if not self.purpose:
            missing.append("Purpose (Self-use / Investment)")
        return missing

    def completeness_percentage(self) -> int:
        """Calculates percentage of core requirements provided."""
        total_fields = 6
        missing_count = len(self.get_missing_fields())
        filled = max(0, total_fields - missing_count)
        return int((filled / total_fields) * 100)

    def budget_display(self) -> str:
        """Human-readable budget display in Indian numbering format (Lakhs / Crores)."""
        def format_inr(val: Optional[float]) -> str:
            if val is None:
                return ""
            if val >= 10000000:
                cr = val / 10000000
                return f"₹{cr:.2f}".rstrip("0").rstrip(".") + " Cr"
            elif val >= 100000:
                lakh = val / 100000
                return f"₹{lakh:.2f}".rstrip("0").rstrip(".") + " L"
            else:
                return f"₹{val:,.0f}"

        if self.budget_min and self.budget_max:
            return f"{format_inr(self.budget_min)} - {format_inr(self.budget_max)}"
        elif self.budget_max:
            return f"Up to {format_inr(self.budget_max)}"
        elif self.budget_min:
            return f"Above {format_inr(self.budget_min)}"
        return "Not Specified"


class ExtractionResult(BaseModel):
    """Result returned by the intake extraction pipeline after each user message."""
    extracted_info: ExtractedLeadInfo
    updated_profile: LeadProfile
    missing_fields: List[str] = Field(default_factory=list)
    assistant_reply: str = Field(description="Conversational response asking for missing details or acknowledging info")
    is_complete: bool = Field(default=False, description="True if all critical fields are captured")
