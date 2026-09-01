# Copyright (c) 2026, MicroMerger and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from ai_workplace.ai.evidence import classify_data_safety, CLASS_ORGANIZATIONAL

class AIKnowledgeEntry(Document):
    def validate(self):
        if getattr(self, "file_attachment", None):
            extracted = self.extract_attachment_text()
            if extracted and not self.answer:
                self.answer = extracted

        # Strict Data Classification Guardrail:
        # Never allow EMPLOYEE_SPECIFIC or SENSITIVE data into shared knowledge
        combined_text = f"{self.title} {self.question or ''} {self.answer}"
        classification = classify_data_safety(combined_text)
        if classification != CLASS_ORGANIZATIONAL:
            frappe.throw(
                f"Security Guardrail Violation: Knowledge Entry contains {classification} data. "
                "Only ORGANIZATIONAL data (general policies, SOPs, FAQs) can enter the shared AI Knowledge Base."
            )
        self.data_classification = CLASS_ORGANIZATIONAL

        if self.status == "PUBLISHED" and not self.approved_by:
            self.approved_by = frappe.session.user
            self.approved_on = frappe.utils.now_datetime()

    def extract_attachment_text(self) -> str:
        import os
        if not getattr(self, "file_attachment", None):
            return ""

        file_url = self.file_attachment
        file_path = frappe.get_site_path("public", file_url.lstrip("/"))
        if not os.path.exists(file_path):
            file_path = frappe.get_site_path(file_url.lstrip("/"))
            if not os.path.exists(file_path):
                return ""

        ext = os.path.splitext(file_path)[1].lower()

        if ext == ".pdf":
            try:
                import fitz
                pdf_doc = fitz.open(file_path)
                return "\n\n".join(page.get_text().strip() for page in pdf_doc if page.get_text().strip())
            except Exception:
                try:
                    import pypdf
                    reader = pypdf.PdfReader(file_path)
                    return "\n\n".join(p.extract_text() or "" for p in reader.pages)
                except Exception:
                    return ""

        elif ext == ".docx":
            try:
                import docx
                doc = docx.Document(file_path)
                return "\n".join(p.text.strip() for p in doc.paragraphs if p.text.strip())
            except Exception:
                return ""

        elif ext in (".txt", ".md"):
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    return f.read()
            except Exception:
                return ""

        return ""

    def on_update(self):
        """Auto-index into Knowledge Chunk vector/search index when saved/published."""
        if self.status in ("APPROVED", "PUBLISHED"):
            self.sync_to_knowledge_chunks()

    def sync_to_knowledge_chunks(self):
        """Chunk and save entry into AI Workplace Knowledge Chunk."""
        source_name = f"knowledge_entry_{self.name}"
        
        # Ensure Knowledge Source exists
        if not frappe.db.exists("AI Workplace Knowledge Source", "knowledge_entries"):
            src = frappe.new_doc("AI Workplace Knowledge Source")
            src.source_name = "knowledge_entries"
            src.source_type = "Policy"
            src.is_active = 1
            src.insert(ignore_permissions=True)

        # Delete existing chunks for this specific entry
        frappe.db.delete("AI Workplace Knowledge Chunk", {"knowledge_source": "knowledge_entries", "chunk_text": ["like", f"%[{self.title}]%"]})

        # Insert new chunk with Employment Type scoping
        emp_type = getattr(self, "applicable_employment_type", None) or "All"
        emp_type_str = f" [Target Employment Type: {emp_type}]" if emp_type != "All" else ""
        chunk_text = f"[Source: {self.title}]{emp_type_str} {self.question or self.title}: {self.answer}"
        doc = frappe.new_doc("AI Workplace Knowledge Chunk")
        doc.knowledge_source = "knowledge_entries"
        doc.chunk_index = 0
        doc.chunk_text = chunk_text
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
