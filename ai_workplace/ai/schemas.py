from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

class IntentRouterResponse(BaseModel):
    """
    Schema for the LLM output when determining the user's intent.
    """
    intent: str = Field(
        ...,
        description="The resolved intent of the user. Should match one of the system's known capabilities (e.g., 'leave_balance', 'hr_contact', 'attendance_summary') or 'unknown'."
    )
    confidence: float = Field(
        ...,
        description="Confidence score of the intent detection, from 0.0 to 1.0.",
        ge=0.0,
        le=1.0
    )
    requires_tool: bool = Field(
        default=False,
        description="Whether a specific backend tool needs to be invoked to fulfill the intent."
    )
    tool_name: Optional[str] = Field(
        default=None,
        description="The name of the backend tool to invoke, if requires_tool is true."
    )
    tool_arguments: Dict[str, Any] = Field(
        default_factory=dict,
        description="A dictionary of arguments to pass to the tool. Only provide if requires_tool is true."
    )
    direct_response: Optional[str] = Field(
        default=None,
        description="If no tool is required, provide a direct text response to the user."
    )

    class Config:
        json_schema_extra = {
            "example": {
                "intent": "leave_balance",
                "confidence": 0.95,
                "requires_tool": True,
                "tool_name": "get_leave_balance",
                "tool_arguments": {"leave_type": "Annual Leave"},
                "direct_response": None
            }
        }
