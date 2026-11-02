"""Admin-only, text-free conversation engagement aggregates."""
import frappe


@frappe.whitelist()
def get_engagement(range_type='30d', from_date=None, to_date=None):
    frappe.only_for('System Manager')
    from ai_workplace.api.analytics import get_date_range_bounds
    _, _, start, end = get_date_range_bounds(range_type, from_date, to_date)
    return engagement_metrics(start, end)


def engagement_metrics(start, end):
    if not frappe.db.exists('DocType', 'AI Conversation Event'):
        return dict(counts={}, topics=[], guided_conversations=0, engaged_conversations=0, response_rate=0, tokens=0, cost=0)
    rows = frappe.db.sql('''SELECT `event`, COUNT(*) AS total, SUM(token_count) AS tokens, SUM(cost) AS cost
        FROM `tabAI Conversation Event` WHERE creation BETWEEN %s AND %s GROUP BY `event`''', (start,end), as_dict=True)
    counts = {r.event: int(r.total) for r in rows}
    topics = frappe.db.sql('''SELECT topic, COUNT(*) AS questions FROM `tabAI Conversation Event`
        WHERE `event`='question' AND creation BETWEEN %s AND %s GROUP BY topic ORDER BY questions DESC LIMIT 20''', (start,end), as_dict=True)
    rates = frappe.db.sql('''SELECT COUNT(DISTINCT q.conversation) AS guided,
        COUNT(DISTINCT CASE WHEN EXISTS (SELECT 1 FROM `tabAI Conversation Event` r
            WHERE r.conversation=q.conversation AND r.topic=q.topic AND r.`event`='reply'
              AND r.creation>=q.creation AND r.creation<=%s) THEN q.conversation END) AS engaged
        FROM `tabAI Conversation Event` q WHERE q.`event`='question' AND q.creation BETWEEN %s AND %s''', (end,start,end), as_dict=True)[0]
    guided, engaged = int(rates.guided or 0), int(rates.engaged or 0)
    return dict(counts=counts, topics=topics, guided_conversations=guided, engaged_conversations=engaged,
                response_rate=round(100*engaged/guided,1) if guided else 0,
                tokens=sum(int(r.tokens or 0) for r in rows), cost=sum(float(r.cost or 0) for r in rows))
