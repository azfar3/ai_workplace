import os
import frappe
from frappe.model.document import Document

class AIWorkplaceKnowledgeSource(Document):
    def validate(self):
        if self.file_attachment:
            extracted = self.extract_attachment_text()
            if extracted:
                if self.content and self.content.strip() and self.content.strip() != extracted.strip():
                    if extracted not in self.content:
                        self.content = f"{self.content}\n\n{extracted}".strip()
                else:
                    self.content = extracted

    def extract_attachment_text(self) -> str:
        if not self.file_attachment:
            return ""

        file_url = self.file_attachment
        file_path = frappe.get_site_path("public", file_url.lstrip("/"))
        if not os.path.exists(file_path):
            # Check private files
            file_path = frappe.get_site_path(file_url.lstrip("/"))
            if not os.path.exists(file_path):
                return ""

        ext = os.path.splitext(file_path)[1].lower()

        if ext == ".pdf":
            try:
                import fitz
                pdf_doc = fitz.open(file_path)
                text_parts = [page.get_text() for page in pdf_doc]
                return "\n\n".join(t.strip() for t in text_parts if t.strip())
            except Exception as exc:
                try:
                    import pypdf
                    reader = pypdf.PdfReader(file_path)
                    return "\n\n".join(p.extract_text() or "" for p in reader.pages)
                except Exception as sub_exc:
                    frappe.msgprint(f"Failed to extract PDF text: {exc}")
                    return ""

        elif ext == ".docx":
            try:
                import docx
                doc = docx.Document(file_path)
                return "\n".join(p.text.strip() for p in doc.paragraphs if p.text.strip())
            except Exception as exc:
                frappe.msgprint(f"Failed to extract DOCX text: {exc}")
                return ""

        elif ext in (".txt", ".md", ".json", ".csv"):
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    return f.read()
            except Exception as exc:
                frappe.msgprint(f"Failed to read text file: {exc}")
                return ""

        return ""

    def on_update(self):
        """Auto-reindex source into Knowledge Chunks when saved."""
        if self.is_active:
            try:
                from ai_workplace.ai.indexer import reindex_source
                reindex_source(self.name)
            except Exception:
                pass
