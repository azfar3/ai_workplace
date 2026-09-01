"""
ai_workplace/api/whatsapp_setup.py
────────────────────────────────────────
Handles OAuth token exchange and auto-configuration for Meta WhatsApp Embedded Signup
and WhatsApp Business App Coexistence.
"""

import frappe
import requests


@frappe.whitelist(allow_guest=True)
def handle_embedded_signup_code(code: str):
    """
    Exchanges Meta Embedded Signup authorization code for a long-lived access token,
    fetches WABA ID and Phone Number ID, and updates AI Workplace Settings automatically.
    """
    if not code:
        frappe.throw("Authorization code is required.")

    settings = frappe.get_single("AI Workplace Settings")
    app_id = settings.meta_app_id or "886662467657151"
    app_secret = settings.get_password("meta_app_secret")

    if not app_secret:
        # Fallback or alert if secret is missing
        frappe.log_error("Meta App Secret is missing in AI Workplace Settings.", "WhatsApp Setup Error")

    # 1. Exchange authorization code for User Access Token
    token_url = "https://graph.facebook.com/v20.0/oauth/access_token"
    params = {
        "client_id": app_id,
        "code": code
    }
    if app_secret:
        params["client_secret"] = app_secret

    try:
        res = requests.get(token_url, params=params, timeout=15).json()
    except Exception as e:
        frappe.log_error(f"Meta OAuth request exception: {str(e)}", "WhatsApp Setup Error")
        frappe.throw(f"Connection to Meta API failed: {str(e)}")

    if "error" in res:
        err_msg = res["error"].get("message", "Unknown OAuth error")
        frappe.log_error(f"Meta OAuth Error: {res}", "WhatsApp Setup Error")
        frappe.throw(f"Meta OAuth Exchange failed: {err_msg}")

    access_token = res.get("access_token")
    if not access_token:
        frappe.throw("Failed to retrieve access token from Meta response.")

    # 2. Fetch WABA ID (WhatsApp Business Account ID)
    waba_id = ""
    try:
        waba_res = requests.get(
            f"https://graph.facebook.com/v20.0/me/whatsapp_business_accounts?access_token={access_token}",
            timeout=15
        ).json()
        if "data" in waba_res and len(waba_res["data"]) > 0:
            waba_id = waba_res["data"][0].get("id", "")
    except Exception as e:
        frappe.logger("ai_workplace").warning(f"Could not fetch WABA ID automatically: {e}")

    # 3. Fetch Phone Number ID
    phone_number_id = ""
    if waba_id:
        try:
            phone_res = requests.get(
                f"https://graph.facebook.com/v20.0/{waba_id}/phone_numbers?access_token={access_token}",
                timeout=15
            ).json()
            if "data" in phone_res and len(phone_res["data"]) > 0:
                phone_number_id = phone_res["data"][0].get("id", "")
        except Exception as e:
            frappe.logger("ai_workplace").warning(f"Could not fetch Phone Number ID automatically: {e}")

    # 4. Update AI Workplace Settings
    settings.whatsapp_system_user_access_token = access_token
    settings.meta_access_token = access_token
    if waba_id:
        settings.meta_waba_id = waba_id
    if phone_number_id:
        settings.whatsapp_phone_number_id = phone_number_id
        settings.meta_phone_number_id = phone_number_id

    settings.save(ignore_permissions=True)
    frappe.db.commit()

    return {
        "status": "success",
        "message": "WhatsApp Coexistence account successfully linked to ERPNext!",
        "waba_id": waba_id,
        "phone_number_id": phone_number_id
    }
