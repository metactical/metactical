
import frappe
from frappe import _
from frappe.core.doctype.communication.email import make
from frappe.model.document import Document
from frappe.utils import add_days, getdate, today


# called through hooks to send campaign mails to leads
def send_email_to_leads_or_contacts():
	email_campaigns = frappe.get_all(
		"Email Campaign", filters={"status": ("not in", ["Unsubscribed", "Completed", "Scheduled"])}
	)

	for camp in email_campaigns:
		email_campaign = frappe.get_doc("Email Campaign", camp.name)
		campaign = frappe.get_cached_doc("Campaign", email_campaign.campaign_name)
		for entry in campaign.get("campaign_schedules"):
			scheduled_date = add_days(email_campaign.get("start_date"), entry.get("send_after_days"))
			if scheduled_date == getdate(today()):
				print(f"Sending email for campaign: {email_campaign.name} on {scheduled_date}")
				send_mail(entry, email_campaign)

def send_mail(entry, email_campaign):
	recipient_list = []
	if email_campaign.email_campaign_for == "Email Group":
		for member in frappe.db.get_list(
			"Email Group Member", filters={"email_group": email_campaign.get("recipient")}, fields=["email"]
		):
			recipient_list.append(member["email"])
	else:
		recipient_list.append(
			frappe.db.get_value(
				email_campaign.email_campaign_for, email_campaign.get("recipient"), "email_id"
			)
		)

	email_template = frappe.get_doc("Email Template", entry.get("email_template"))
	sender = frappe.db.get_value("User", email_campaign.get("sender"), "email")
	for receipient in recipient_list:
		context = {"doc": frappe.get_doc(email_campaign.email_campaign_for, email_campaign.recipient), "email": receipient}

		# send mail and link communication to document
		comm = make(
			doctype="Email Campaign",
			name=email_campaign.name,
			subject=frappe.render_template(email_template.get("subject"), context),
			content=frappe.render_template(email_template.get("response_html"), context),
			sender=sender,
			recipients=[receipient],
			communication_medium="Email",
			sent_or_received="Sent",
			send_email=True,
			email_template=email_template.name,
		)
	return comm

