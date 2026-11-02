"""Legacy endpoint aliases; all webhooks use the canonical guarded pipeline."""
from ai_workplace.api.whatsapp_webhook import (
    receive, verify, _process_receive, _process_verify,
)
