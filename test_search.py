import frappe
frappe.init(site="erp.v15")
frappe.connect()

from ai_workplace.ai.indexer import search_knowledge

query = "what is the notice period"
context = {"policy_scope": "HO"}
res = search_knowledge(query, context=context)

print(f"Results for HO context: {len(res)}")
for r in res:
    print(r["score"], r["keyword_score"], r["semantic_score"], r["document"], r["section"])
