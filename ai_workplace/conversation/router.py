from typing import Dict, List, Any, Optional
from ai_workplace.conversation.handlers.base import ServiceHandler
from ai_workplace.whatsapp.outbound import OutboundMessage

class ServiceRegistry:
    _handlers: List[ServiceHandler] = []

    @classmethod
    def register(cls, handler: ServiceHandler):
        cls._handlers.append(handler)

    @classmethod
    def get_handler(cls, intent: str, state: str) -> Optional[ServiceHandler]:
        for handler in cls._handlers:
            if handler.can_handle(intent, state):
                return handler
        return None

    @classmethod
    def dispatch(cls, conv: Any, intent: str, clean_text: str, context: Dict[str, Any], trace_id: str) -> Optional[OutboundMessage]:
        handler = cls.get_handler(intent, conv.current_state)
        if handler:
            return handler.handle(conv, intent, clean_text, context, trace_id)
        return None
