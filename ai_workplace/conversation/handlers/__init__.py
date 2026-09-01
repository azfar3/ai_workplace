from ai_workplace.conversation.handlers.travel import TravelHandler
from ai_workplace.conversation.handlers.leave import LeaveHandler
from ai_workplace.conversation.handlers.attendance import AttendanceHandler
from ai_workplace.conversation.handlers.payroll import PayrollHandler
from ai_workplace.conversation.handlers.profile import ProfileHandler
from ai_workplace.conversation.handlers.policy import PolicyHandler
from ai_workplace.conversation.handlers.general import GeneralHandler
from ai_workplace.conversation.handlers.deliverables import DeliverablesHandler

def register_all_handlers():
    from ai_workplace.conversation.router import ServiceRegistry
    ServiceRegistry.register(TravelHandler())
    ServiceRegistry.register(LeaveHandler())
    ServiceRegistry.register(AttendanceHandler())
    ServiceRegistry.register(PayrollHandler())
    ServiceRegistry.register(ProfileHandler())
    ServiceRegistry.register(PolicyHandler())
    ServiceRegistry.register(GeneralHandler())
    ServiceRegistry.register(DeliverablesHandler())

