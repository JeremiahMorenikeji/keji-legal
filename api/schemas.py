"""Request/response models. Pydantic validates and bounds every input."""
from typing import Literal, Optional

from pydantic import BaseModel, Field

Jurisdiction = Literal["US", "CA", "UK", "EU"]


class ClassifyRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class ComplianceRequest(BaseModel):
    query: str = Field(min_length=3, max_length=2000)
    jurisdiction: Jurisdiction = "US"
    matter_ref: str = Field(default="KEJI-DRAFT", max_length=64)
    document_text: Optional[str] = Field(default=None, max_length=40000)
    document_name: Optional[str] = Field(default=None, max_length=200)


class ReviewRequest(BaseModel):
    validated_output: Optional[str] = Field(default=None, max_length=20000)
    reviewer_note: Optional[str] = Field(default=None, max_length=2000)


class MatterCreate(BaseModel):
    user_id: str = Field(min_length=36, max_length=36)  # a real auth.users UUID
    jurisdiction: Jurisdiction
    matter_type: str = Field(min_length=1, max_length=100)
    party_a: str = Field(default="", max_length=200)
    party_b: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=5000)


class ContractRequest(BaseModel):
    clause: str = Field(min_length=10, max_length=40000)
    agreement_type: str = Field(default="Commercial agreement", max_length=100)
    document_name: Optional[str] = Field(default=None, max_length=200)
    jurisdiction: Jurisdiction = "US"
    risk_tolerance: Literal["Standard", "Conservative (Strict)", "Aggressive"] = "Standard"
    focus_areas: list[str] = Field(default_factory=lambda: ["Liability & Indemnity"], max_length=8)
