import re
import string
from typing import Dict, Any, Tuple, Optional
from ai_workplace.ai.intent_catalog import INTENT_CATALOG

class QueryResolver:
    """
    Deterministic Query Resolver
    Attempts to classify messages WITHOUT calling the LLM.
    """
    
    @staticmethod
    def normalize_text(text: str) -> str:
        """
        1. Text normalization
        2. Lowercasing
        3. Whitespace normalization
        4. Common spelling correction
        """
        if not text:
            return ""
        
        # Lowercase
        text = text.lower()
        
        # Remove punctuation
        text = text.translate(str.maketrans('', '', string.punctuation))
        
        # Whitespace normalization
        text = re.sub(r'\s+', ' ', text).strip()
        
        # Common spelling/Roman Urdu correction mapping
        corrections = {
            "chuti": "leave",
            "chutti": "leave",
            "paisa": "salary",
            "tankhwa": "salary",
            "slip": "salary slip",
            "payslip": "salary slip",
            "polices": "policies",
            "baance": "balance",
            "bal": "balance",
            "timings": "office timings"
        }
        
        words = text.split()
        normalized_words = [corrections.get(w, w) for w in words]
        
        return " ".join(normalized_words)

    @staticmethod
    def score_intent(text: str, intent_data: Dict[str, Any]) -> float:
        """
        Calculates a confidence score for a given intent based on keyword/phrase overlap.
        """
        score = 0.0
        
        # Exact alias match gets highest score
        for alias in intent_data.get("aliases", []):
            if text == QueryResolver.normalize_text(alias):
                return 1.0
            
            # Substring match gets partial score
            if QueryResolver.normalize_text(alias) in text:
                score = max(score, 0.8)
                
        # Keyword matching from intents array
        words = set(text.split())
        for intent_kw in intent_data.get("intents", []):
            intent_kw_norm = QueryResolver.normalize_text(intent_kw.replace("_", " "))
            if intent_kw_norm in text:
                score = max(score, 0.7)
                
        return score

    @classmethod
    def resolve(cls, message: str) -> Tuple[Optional[str], Optional[Dict[str, Any]], float]:
        """
        Resolve a message to an intent and metadata if confidence is high enough.
        Returns: (intent_key, metadata, confidence_score)
        """
        normalized_msg = cls.normalize_text(message)
        
        best_intent = None
        best_meta = None
        highest_score = 0.0
        
        for intent_key, meta in INTENT_CATALOG.items():
            score = cls.score_intent(normalized_msg, meta)
            if score > highest_score:
                highest_score = score
                best_intent = intent_key
                best_meta = meta
                
        # Threshold for deterministic resolution
        if highest_score >= 0.7:
            return best_intent, best_meta, highest_score
            
        return "unknown", None, 0.0
