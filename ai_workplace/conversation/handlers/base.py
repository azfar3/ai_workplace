from typing import Protocol, Dict, Any, Optional
from ai_workplace.whatsapp.outbound import OutboundMessage

class ServiceHandler(Protocol):
    """
    Protocol defining the contract for all service handlers in the AI Workplace.
    Handlers encapsulate specific domains like Leave, Attendance, Travel, etc.
    """
    
    def can_handle(self, intent: str, state: str) -> bool:
        """Return True if this handler can process the given intent in the current state."""
        ...
        
    def handle(self, conv: Any, intent: str, clean_text: str, context: Dict[str, Any], trace_id: str) -> OutboundMessage:
        """Process the message and return an OutboundMessage."""
        ...
