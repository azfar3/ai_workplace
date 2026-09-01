import frappe
from ai_workplace.ai.query_resolver import QueryResolver

frappe.init(site="erp.v15")
frappe.connect()

print(QueryResolver.resolve("what is my leave balance?"))
print(QueryResolver.resolve("show my salary slip"))
