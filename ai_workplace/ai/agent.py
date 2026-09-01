import json
import time
from typing import Any, Dict, Optional, Tuple
import frappe
import requests

from ai_workplace.context.schema import AIRequestContext
from ai_workplace.ai.schemas import IntentRouterResponse
from ai_workplace.ai.logger import log_llm_usage

class IntentAgent:
    """
    A core agent that takes a user query and an AIRequestContext, 
    and returns a structured IntentRouterResponse by calling the Groq LLM API.
    """
    def __init__(self):
        # In a real setup, we would read from "Groq AI Settings" or a generic "AI Provider" setup.
        self.settings = frappe.get_single("Groq AI Settings")
        self.api_key = self.settings.get_password("api_key") if self.settings else None
        self.model = self.settings.model if self.settings else "llama3-8b-8192"
        self.base_url = "https://api.groq.com/openai/v1/chat/completions"

    def execute(
        self, 
        user_query: str, 
        context: AIRequestContext, 
        trace_id: str = ""
    ) -> IntentRouterResponse:
        """
        Calls the LLM to determine intent and potential tool execution.
        """
        if not self.api_key:
            return self._fallback_response("AI provider not configured")

        system_prompt = self._build_system_prompt(context)
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # We enforce JSON output using Groq's JSON mode if available, 
        # or we just prompt it heavily to output JSON matching the schema.
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_query}
            ],
            "temperature": self.settings.temperature if self.settings else 0.1,
            "max_tokens": self.settings.max_tokens if self.settings else 512,
            "response_format": {"type": "json_object"}
        }

        start_time = time.time()
        try:
            response = requests.post(self.base_url, headers=headers, json=payload, timeout=10)
            response.raise_for_status()
            data = response.json()
            latency_ms = int((time.time() - start_time) * 1000)
            
            # Log usage
            usage = data.get("usage", {})
            log_llm_usage(
                provider="Groq",
                model=self.model,
                tokens_in=usage.get("prompt_tokens", 0),
                tokens_out=usage.get("completion_tokens", 0),
                latency_ms=latency_ms,
                employee=context.employee_name,
                trace_id=trace_id,
            )

            content = data["choices"][0]["message"]["content"]
            parsed_json = json.loads(content)
            
            # Validate using Pydantic
            return IntentRouterResponse(**parsed_json)
            
        except Exception as e:
            frappe.logger("ai_workplace").error(f"IntentAgent Error: {str(e)}")
            return self._fallback_response(str(e))

    def _build_system_prompt(self, context: AIRequestContext) -> str:
        schema = IntentRouterResponse.schema_json()
        return f"""You are a helpful HR Assistant. 
Your job is to determine the user's intent and whether a tool should be invoked to answer their question.
You MUST output ONLY valid JSON matching the following schema:
{schema}

USER CONTEXT:
Name: {context.employee_name or 'Guest'}
Role: {context.person_type}
Language: {context.language}
Allowed Services: {', '.join(context.allowed_intents) if context.allowed_intents else 'None'}

If the user asks a general question, return requires_tool=false and provide a direct_response.
If the user asks for their leave balance, return intent='leave_balance', requires_tool=true, and tool_name='get_leave_balance'.
If the user asks for a policy, return intent='search_knowledge', requires_tool=true, and tool_name='search_knowledge'.
"""

    def _fallback_response(self, error: str) -> IntentRouterResponse:
        return IntentRouterResponse(
            intent="unknown",
            confidence=0.0,
            requires_tool=False,
            direct_response=f"I'm sorry, my AI systems are currently unavailable. Error: {error}"
        )
