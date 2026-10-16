import frappe
import requests

def _get_pairing_link(pos_url, branch_name, branch_user):
    url = f"{pos_url}/api/Users/GetPairingLink"
    response = requests.get(url, params={"storeName": branch_name, "branchUser": branch_user})
    return response, response.text


@frappe.whitelist()
def send_welcome_email(user, profile):
    user_full_name = frappe.get_value("User", user, "full_name")
    pos_url = frappe.db.get_single_value("Metactical Settings", "pos_url")

    if not pos_url:
        frappe.throw("POS URL is not set in Metactical Settings")
    elif pos_url[-1] == "/": 
        pos_url = pos_url[:-1]

    # get the branch name from profile by removing 'Operators'
    branch_name = profile.replace(" Operators", "")

    response, branch_pairing = _get_pairing_link(pos_url, branch_name, user_full_name)
    
    if not ("branchID" in branch_pairing and "userId" in branch_pairing):
        # Fallback: some branch users are registered by email rather than full
        # name on the POS side, so retry with the email before giving up.
        response, branch_pairing = _get_pairing_link(pos_url, branch_name, user)


    if "branchID" in branch_pairing and "userId" in branch_pairing:
        email_template = frappe.db.exists("Email Template", "POS User Welcome Email")
        if not email_template:
            frappe.throw("<b>POS User Welcome Email</b> Email template not found")
        
        email_template = frappe.get_doc("Email Template", "POS User Welcome Email")
        message = frappe.render_template(email_template.response, 
                                            {
                                                "branch_pairing": branch_pairing, 
                                                "pos_url": pos_url,
                                                "full_name": user_full_name
                                            })
        try:
            frappe.sendmail(
                recipients=user,
                subject=email_template.subject,
                message=message
            )
            frappe.msgprint(f"Welcome email sent to <b>{user_full_name}</b> for branch <b>{branch_name}</b>")

        except Exception as ex:
            frappe.msgprint(f"Error sending email: {ex}")
            
        frappe.response["url"] = f"{pos_url}?{branch_pairing}"
    elif not branch_pairing:
        frappe.throw(f"Unable to get branch pairing link for user <b>{user_full_name}</b> ({user}) and branch <b>{branch_name}</b>")
    else:
        res = response.json()
        frappe.throw(f"Error: {res['errors']}")
        
        