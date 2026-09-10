import frappe
import json

@frappe.whitelist()
def subscribe(endpoint, p256dh, auth, user_agent=None):
    if not frappe.session.user or frappe.session.user == "Guest":
        frappe.throw("Unauthorized", frappe.PermissionError)
    
    existing = frappe.db.get_value("Web Push Subscription", 
        {"endpoint": endpoint, "user": frappe.session.user}, "name")
    
    if existing:
        doc = frappe.get_doc("Web Push Subscription", existing)
        doc.p256dh = p256dh
        doc.auth = auth
        doc.enabled = 1
        doc.save(ignore_permissions=True)
    else:
        doc = frappe.new_doc("Web Push Subscription")
        doc.user = frappe.session.user
        doc.endpoint = endpoint
        doc.p256dh = p256dh
        doc.auth = auth
        doc.user_agent = user_agent
        doc.enabled = 1
        doc.insert(ignore_permissions=True)
    
    frappe.db.commit()
    return {"status": "success"}

@frappe.whitelist()
def unsubscribe(endpoint):
    if not frappe.session.user or frappe.session.user == "Guest":
        frappe.throw("Unauthorized", frappe.PermissionError)
        
    existing = frappe.db.get_value("Web Push Subscription", 
        {"endpoint": endpoint, "user": frappe.session.user}, "name")
        
    if existing:
        doc = frappe.get_doc("Web Push Subscription", existing)
        doc.enabled = 0
        doc.save(ignore_permissions=True)
        frappe.db.commit()
        return {"status": "success"}
    return {"status": "not_found"}

@frappe.whitelist()
def get_vapid_public_key():
    if not frappe.session.user or frappe.session.user == "Guest":
        return None
    return frappe.conf.get("vapid_public_key")

def send_push_notification(user, payload):
    frappe.enqueue(
        "ai_workplace.api.notifications._send_push_notification_job",
        queue="short",
        timeout=120,
        user=user,
        payload=payload
    )

def _send_push_notification_job(user, payload):
    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        frappe.logger("ai_workplace").warning("pywebpush not installed. Cannot send push notification.")
        return

    vapid_private_key = frappe.conf.get("vapid_private_key")
    vapid_public_key = frappe.conf.get("vapid_public_key")
    vapid_subject = frappe.conf.get("vapid_subject", "mailto:admin@example.com")
    
    if not vapid_private_key or not vapid_public_key:
        return
        
    subscriptions = frappe.get_all("Web Push Subscription", 
        filters={"user": user, "enabled": 1},
        fields=["name", "endpoint", "p256dh", "auth"])
        
    for sub in subscriptions:
        try:
            webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {
                        "p256dh": sub.p256dh,
                        "auth": sub.auth
                    }
                },
                data=json.dumps(payload),
                vapid_private_key=vapid_private_key,
                vapid_claims={
                    "sub": vapid_subject
                }
            )
            frappe.logger("ai_workplace").info(f"Web Push sent to {user}")
        except WebPushException as ex:
            frappe.logger("ai_workplace").error(f"Web Push failed for {user}: {ex}")
            if ex.response is not None and ex.response.status_code in [410, 404]:
                frappe.db.set_value("Web Push Subscription", sub.name, "enabled", 0)
                frappe.db.commit()
        except Exception as e:
            frappe.logger("ai_workplace").error(f"Web Push failed for {user} unexpectedly: {e}")
