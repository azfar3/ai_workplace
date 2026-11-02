"""Backfill guidance/validity metadata without external embedding calls."""
import frappe


def execute():
    if not frappe.db.exists('DocType', 'AI Workplace Knowledge Chunk'):
        return
    if frappe.db.exists('DocType', 'AI Workplace Knowledge Source'):
        for source in frappe.get_all('AI Workplace Knowledge Source', fields=['name','effective_to','guided_questions','related_intent']):
            frappe.db.set_value('AI Workplace Knowledge Chunk', {'knowledge_source': source.name},
                                {key: source.get(key) for key in ('effective_to','guided_questions','related_intent')}, update_modified=False)
    if not frappe.db.exists('DocType', 'AI Knowledge Entry'):
        return
    entries = frappe.get_all('AI Knowledge Entry', fields=['name','title','status','applicable_employment_type','target_department','target_location','effective_from','effective_to','version','approved_on','guided_questions','related_intent'])
    by_id = {entry.name:entry for entry in entries}
    by_title = {}
    for entry in entries:
        by_title.setdefault(entry.title,[]).append(entry)
    for chunk in frappe.get_all('AI Workplace Knowledge Chunk', filters={'knowledge_source':'knowledge_entries'}, fields=['name','source_id','chunk_text']):
        entry = by_id.get(chunk.source_id)
        if not entry:
            matches = [rows[0] for title,rows in by_title.items() if len(rows)==1 and (chunk.chunk_text or '').startswith(f'[Source: {title}]')]
            entry = matches[0] if len(matches)==1 else None
        if not entry or entry.status not in {'APPROVED','PUBLISHED'}:
            # Unmapped/unapproved chunks cannot remain in the approved index.
            frappe.db.delete('AI Workplace Knowledge Chunk', {'name':chunk.name})
            continue
        frappe.db.set_value('AI Workplace Knowledge Chunk',chunk.name,dict(
            source_type='AI Knowledge Entry',source_id=entry.name,document_name=entry.title,
            target_employment_type=entry.applicable_employment_type or 'All',target_department=entry.target_department,
            target_location=entry.target_location,effective_date=entry.effective_from,effective_to=entry.effective_to,
            policy_version=str(entry.version or '1'),source_date=entry.effective_from,
            guided_questions=entry.guided_questions,related_intent=entry.related_intent),update_modified=False)
