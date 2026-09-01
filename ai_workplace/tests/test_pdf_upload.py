import os
import frappe

def test_pdf_docx_upload():
    # 1. Create a dummy test PDF file using fitz
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "MicroMerger Welfare Policy 2026: Employees are eligible for annual health insurance reimbursement up to PKR 100,000.")
    
    pdf_path = frappe.get_site_path("public", "files", "test_welfare_policy.pdf")
    doc.save(pdf_path)
    doc.close()

    file_url = "/files/test_welfare_policy.pdf"

    # 2. Create Knowledge Source with PDF attachment
    source_name = "Test_Welfare_Policy_PDF"
    if frappe.db.exists("AI Workplace Knowledge Source", source_name):
        frappe.delete_doc("AI Workplace Knowledge Source", source_name, ignore_permissions=True)

    src = frappe.new_doc("AI Workplace Knowledge Source")
    src.source_name = source_name
    src.source_type = "Policy"
    src.file_attachment = file_url
    src.is_active = 1
    src.insert(ignore_permissions=True)
    frappe.db.commit()

    print("=== Extracted PDF Content in Knowledge Source ===")
    print("Content:", src.content)

    # 3. Test RAG Search against PDF extracted text
    from ai_workplace.ai.indexer import search_knowledge
    res = search_knowledge("health insurance reimbursement welfare policy")
    print("\n=== RAG Search Result for PDF Content ===")
    for r in res:
        print(r)
