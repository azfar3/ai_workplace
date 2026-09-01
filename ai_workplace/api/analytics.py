"""
Phase 4: Admin Analytics Service
Server-side aggregation for AI Workplace Control Center.
"""

import frappe
from frappe.utils import add_days, today, now_datetime

@frappe.whitelist()
def get_dashboard_summary() -> dict:
    frappe.only_for("System Manager")
    
    # Provider Health
    providers = frappe.get_all("AI Workplace Provider", filters={"is_active": 1}, fields=["name", "provider_name"])
    healthy_providers = 0
    for p in providers:
        state = frappe.cache().get_value(f"ai_workplace:circuit:{p.name}")
        if not state or '"state": "CLOSED"' in state or '"state": "HALF_OPEN"' in state:
            healthy_providers += 1
            
    sys_health = "CRITICAL"
    if healthy_providers == len(providers) and len(providers) > 0:
        sys_health = "HEALTHY"
    elif healthy_providers > 0:
        sys_health = "DEGRADED"

    # Last 30 Days Stats
    thirty_days_ago = add_days(today(), -30)
    usage = frappe.get_all(
        "AI Workplace Usage Log",
        filters={"creation": [">=", thirty_days_ago]},
        fields=["success", "tokens_total", "total_cost", "latency_ms", "fallback_used"]
    )
    
    total_reqs = len(usage)
    success_reqs = sum(1 for u in usage if u.success)
    fallback_reqs = sum(1 for u in usage if u.fallback_used)
    total_tokens = sum((u.tokens_total or 0) for u in usage)
    total_cost = sum((float(u.total_cost) or 0.0) for u in usage)
    
    avg_latency = 0
    if total_reqs > 0:
        avg_latency = sum((u.latency_ms or 0) for u in usage) / total_reqs

    # RAG / Indexing
    chunks = frappe.db.count("AI Workplace Knowledge Chunk")
    gaps = frappe.db.count("AI Knowledge Gap Log", {"status": "Open"})
    
    # Conversations
    active_conv = frappe.db.count("WhatsApp Conversation", {"conversation_status": "Active"})

    return {
        "health": sys_health,
        "providers_healthy": healthy_providers,
        "providers_total": len(providers),
        "requests_total": total_reqs,
        "success_rate": round((success_reqs / total_reqs * 100) if total_reqs else 0, 1),
        "fallback_rate": round((fallback_reqs / total_reqs * 100) if total_reqs else 0, 1),
        "avg_latency_ms": round(avg_latency, 1),
        "tokens_total": total_tokens,
        "total_cost": round(total_cost, 4),
        "knowledge_chunks": chunks,
        "open_knowledge_gaps": gaps,
        "active_conversations": active_conv
    }

@frappe.whitelist()
def get_usage_metrics(days: int = 30) -> dict:
    frappe.only_for("System Manager")
    start_date = add_days(today(), -int(days))
    
    # Aggregated query for requests over time
    chart_data = frappe.db.sql("""
        SELECT 
            DATE(creation) as date,
            COUNT(*) as total,
            SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as success,
            SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as failed,
            SUM(CASE WHEN fallback_used = 1 THEN 1 ELSE 0 END) as fallback,
            SUM(IFNULL(tokens_total, 0)) as tokens,
            SUM(IFNULL(total_cost, 0)) as cost
        FROM `tabAI Workplace Usage Log`
        WHERE creation >= %s
        GROUP BY DATE(creation)
        ORDER BY date ASC
    """, (start_date,), as_dict=True)

    # Provider breakdown
    provider_data = frappe.db.sql("""
        SELECT 
            IFNULL(provider, 'Unknown') as provider,
            COUNT(*) as total,
            SUM(IFNULL(tokens_total, 0)) as tokens,
            SUM(IFNULL(total_cost, 0)) as cost,
            AVG(IFNULL(latency_ms, 0)) as avg_latency
        FROM `tabAI Workplace Usage Log`
        WHERE creation >= %s
        GROUP BY provider
        ORDER BY total DESC
    """, (start_date,), as_dict=True)
    
    # Latency percentiles (approximate via SQL)
    latencies = frappe.db.sql("""
        SELECT latency_ms FROM `tabAI Workplace Usage Log` 
        WHERE creation >= %s AND latency_ms > 0
        ORDER BY latency_ms ASC
    """, (start_date,), as_dict=True)
    
    p50 = p95 = p99 = 0
    if latencies:
        p50 = latencies[int(len(latencies)*0.5)]["latency_ms"]
        p95 = latencies[int(len(latencies)*0.95)]["latency_ms"] if len(latencies) > 20 else latencies[-1]["latency_ms"]
        p99 = latencies[int(len(latencies)*0.99)]["latency_ms"] if len(latencies) > 100 else latencies[-1]["latency_ms"]

    return {
        "timeline": chart_data,
        "providers": provider_data,
        "latency": {
            "p50": round(p50, 1),
            "p95": round(p95, 1),
            "p99": round(p99, 1)
        }
    }

@frappe.whitelist()
def get_provider_health() -> list:
    frappe.only_for("System Manager")
    providers = frappe.get_all("AI Workplace Provider", fields=["name", "provider_name", "api_base_url"])
    result = []
    
    import json
    for p in providers:
        raw_state = frappe.cache().get_value(f"ai_workplace:circuit:{p.name}")
        cb_state = "CLOSED"
        failures = 0
        if raw_state:
            try:
                data = json.loads(raw_state)
                cb_state = data.get("state", "CLOSED")
                failures = data.get("failures", 0)
            except Exception:
                pass
                
        # Get stats from usage logs
        stats = frappe.db.sql("""
            SELECT 
                COUNT(*) as reqs,
                SUM(CASE WHEN success=1 THEN 1 ELSE 0 END) as ok,
                AVG(IFNULL(latency_ms, 0)) as avg_lat
            FROM `tabAI Workplace Usage Log`
            WHERE provider = %s
        """, (p.name,), as_dict=True)
        
        stat = stats[0] if stats else {"reqs": 0, "ok": 0, "avg_lat": 0}
        reqs = stat.get("reqs") or 0
        ok = stat.get("ok") or 0
        avg_lat = stat.get("avg_lat") or 0
        fail_rate = round(((reqs - ok) / reqs * 100) if reqs else 0, 1)
        
        result.append({
            "name": p.name,
            "provider_name": p.provider_name,
            "circuit_state": cb_state,
            "consecutive_failures": failures,
            "total_requests": reqs,
            "fail_rate": fail_rate,
            "avg_latency": round(avg_lat, 1)
        })
    return result

@frappe.whitelist()
def reset_circuit_breaker(provider_name: str):
    frappe.only_for("System Manager")
    from ai_workplace.ai.router import CircuitBreaker
    CircuitBreaker.record_success(provider_name)
    frappe.log_error(title="Circuit Breaker Reset", message=f"Admin reset circuit breaker for {provider_name}")
    return {"success": True}

@frappe.whitelist()
def get_rag_metrics() -> dict:
    frappe.only_for("System Manager")
    sources = frappe.db.count("AI Workplace Knowledge Source")
    chunks = frappe.db.count("AI Workplace Knowledge Chunk")
    embedded = frappe.db.count("AI Workplace Knowledge Chunk", {"embedding_json": ("is", "set")})
    
    gaps = frappe.get_all("AI Knowledge Gap Log", fields=["name", "query", "status", "frequency", "last_seen"], order_by="frequency desc", limit=10)
    
    return {
        "sources": sources,
        "chunks": chunks,
        "embedded": embedded,
        "failed_embeddings": chunks - embedded,
        "gaps": gaps
    }

@frappe.whitelist()
def get_conversation_metrics() -> dict:
    frappe.only_for("System Manager")
    active = frappe.db.count("WhatsApp Conversation", {"conversation_status": "Active"})
    completed = frappe.db.count("WhatsApp Conversation", {"conversation_status": "Completed"})
    abandoned = frappe.db.count("WhatsApp Conversation", {"conversation_status": "Abandoned"})
    
    return {
        "active": active,
        "completed": completed,
        "abandoned": abandoned,
        "channels": []
    }

@frappe.whitelist()
def get_security_metrics() -> dict:
    frappe.only_for("System Manager")
    # For security metrics we use AI Action Log where redactions or blocks happened
    blocks = frappe.db.count("AI Action Log", {"action": ("in", ["Tool Error", "Authorization Failure", "Security Escalation"])})
    
    return {
        "blocked_actions": blocks
    }

@frappe.whitelist()
def get_recent_activity() -> list:
    frappe.only_for("System Manager")
    return frappe.get_all(
        "AI Workplace Usage Log",
        fields=["name", "creation", "channel", "provider", "model", "latency_ms", "tokens_total", "success", "fallback_used"],
        order_by="creation desc",
        limit=50
    )
