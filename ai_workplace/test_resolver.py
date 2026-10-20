import frappe
from ai_workplace.ai.query_resolver import QueryResolver

def execute():
    result = QueryResolver.resolve("svc_pay_slip_latest")
    print(f"Resolve svc_pay_slip_latest: {result}")

    result2 = QueryResolver.resolve("Last Salary Slip")
    print(f"Resolve 'Last Salary Slip': {result2}")
