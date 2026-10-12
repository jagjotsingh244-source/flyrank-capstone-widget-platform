from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class FormFieldSchema(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    label: str = Field(..., min_length=1, max_length=100)
    type: str = Field("text", pattern="^(text|email|textarea|tel|number)$")
    required: bool = True
    placeholder: Optional[str] = ""

class WidgetCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    type: str = Field("signup", pattern="^(signup|contact|cta_popover)$")
    title: str = Field(..., min_length=1, max_length=150)
    description: Optional[str] = Field(None, max_length=500)
    fields_schema: List[FormFieldSchema] = Field(default_factory=lambda: [
        FormFieldSchema(name="email", label="Email", type="email", required=True, placeholder="you@domain.com")
    ])
    button_text: str = Field("Submit", min_length=1, max_length=50)
    display_theme: Dict[str, Any] = Field(default_factory=lambda: {
        "primary_color": "#4F46E5",
        "position": "bottom-right",
        "theme": "light"
    })
    is_active: bool = True

class WidgetUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    type: Optional[str] = Field(None, pattern="^(signup|contact|cta_popover)$")
    title: Optional[str] = Field(None, min_length=1, max_length=150)
    description: Optional[str] = Field(None, max_length=500)
    fields_schema: Optional[List[FormFieldSchema]] = None
    button_text: Optional[str] = Field(None, min_length=1, max_length=50)
    display_theme: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None

class WidgetResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    type: str
    title: str
    description: Optional[str]
    fields_schema: List[FormFieldSchema]
    button_text: str
    display_theme: Dict[str, Any]
    is_active: bool
    created_at: str
    updated_at: str
    embed_snippet: str

class PublicWidgetConfig(BaseModel):
    id: str
    type: str
    title: str
    description: Optional[str]
    fields: List[FormFieldSchema]
    button_text: str
    display_theme: Dict[str, Any]
    submission_url: str

class SubmissionCreate(BaseModel):
    widget_id: str = Field(..., min_length=1)
    data: Dict[str, Any] = Field(...)
    hp: Optional[str] = Field(None, alias="_hp", description="Honeypot trap field - must remain empty")

    model_config = {
        "populate_by_name": True
    }

class SubmissionResponse(BaseModel):
    id: str
    widget_id: str
    status: str
    message: str
    geo: Optional[Dict[str, Any]] = None
    created_at: str

class DashboardStats(BaseModel):
    total_submissions: int
    total_widgets: int
    submissions_by_widget: List[Dict[str, Any]]
    geo_breakdown: List[Dict[str, Any]]
    recent_submissions: List[Dict[str, Any]]
