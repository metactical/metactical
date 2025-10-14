
import frappe
from frappe import _
from frappe.core.doctype.communication.email import make
from frappe.model.document import Document
from frappe.utils import add_days, getdate, today
import time, sys
from frappe.utils import now_datetime
import random

MAX_RETRIES = 3

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
    
# called through hooks to send campaign mails to leads
@frappe.whitelist()
def send_email_to_leads_or_contacts(docname):
	email_campaign = frappe.get_doc("Email Campaign", docname)
	campaign = frappe.get_cached_doc("Campaign", email_campaign.campaign_name)
	for entry in campaign.get("campaign_schedules"):
		scheduled_date = add_days(email_campaign.get("start_date"), entry.get("send_after_days"))
		if scheduled_date == getdate(today()):
			frappe.enqueue(
				send_mail,
				job_name=f"send_campaign_email_{email_campaign.name}",
				queue="long",
				timeout=2600,
				entry=entry,
				email_campaign=email_campaign,
			)
		else:
			frappe.msgprint(
				_("No emails to send today. Next scheduled date is {0}").format(scheduled_date)
			)

def send_mail(entry, email_campaign):
    email_template = frappe.get_doc("Email Template", entry.get("email_template"))
    sender = frappe.db.get_value("User", email_campaign.get("sender"), "email")

    batch_size = 100  # emails per batch
    fetch_limit = 500  # how many recipients to fetch from DB at once

    if email_campaign.email_campaign_for == "Email Group":
        start = 0
        while True:
            # Fetch recipients in chunks of fetch_limit
            members = frappe.db.get_list(
                "Email Group Member",
                filters={"email_group": email_campaign.get("recipient")},
                fields=["email"],
                start=start,
                page_length=fetch_limit,
                order_by="creation asc",
            )

            if not members:
                break  # no more recipients

            # Process this chunk into batches
            recipient_list = [m["email"] for m in members]

            for i in range(0, len(recipient_list), batch_size):
                batch_recipients = recipient_list[i:i + batch_size]
                frappe.enqueue(
                    send_email_batch,
                    job_name=f"send_email_batch_{email_campaign.name}_{start//batch_size + (i//batch_size)}",
                    timeout=1600,
                    recipient_list=batch_recipients,
                    email_campaign=email_campaign,
                    email_template=email_template,
                    sender=sender,
                )
            
            sys.stdout.flush()
            time.sleep(30)

            # Move to next chunk
            start += fetch_limit
    else:
        # Single recipient case
        recipient = frappe.db.get_value(
            email_campaign.email_campaign_for,
            email_campaign.get("recipient"),
            "email_id"
        )
        if recipient:
            frappe.enqueue(
                send_email_batch,
                job_name=f"send_email_batch_{email_campaign.name}_single",
                timeout=1600,
                recipient_list=[recipient],
                email_campaign=email_campaign,
                email_template=email_template,
                sender=sender,
            )

def send_email_batch(recipient_list, email_campaign, email_template, sender):
    """Send campaign emails to a batch of recipients safely with commit + retry."""
    comm = None

    # Pre-fetch the main doc once (avoids repeated SELECT locks)
    try:
        target_doc = frappe.get_doc(email_campaign.email_campaign_for, email_campaign.recipient)
    except Exception as e:
        frappe.log_error(f"Failed to load target doc for {email_campaign.name}: {e}", "Email Campaign Batch")
        return

    for recipient in recipient_list:
        context = {"doc": target_doc, "email": recipient}

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                comm = make(
                    subject=frappe.render_template(email_template.get("subject"), context),
                    content=frappe.render_template(email_template.get("response_html"), context),
                    sender=sender,
                    recipients=[recipient],
                    communication_medium="Email",
                    sent_or_received="Sent",
                    send_email=True,
                    email_template=email_template.name,
                )

                frappe.db.commit()
                break

            except frappe.QueryTimeoutError as e:
                # rollback and retry after delay
                frappe.db.rollback()
                delay = 5 * attempt + random.randint(1, 4)
                time.sleep(delay)

            except Exception as e:
                frappe.db.rollback()
                frappe.log_error(f"Error sending to {recipient}: {e}", "Email Campaign Batch")
                break  # don't retry for non-lock exceptions

        # short pause to reduce pressure on DB
        time.sleep(0.2)

    return comm