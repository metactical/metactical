import frappe

@frappe.whitelist()
def create_opening_entry(*args, **kwargs):
    """
    Create opening entries for the specified company and fiscal year.
    """
    try:
        form_data = dict(frappe.form_dict)
        create_pos_api_log(form_data)
        frappe.set_user(form_data.get("User"))

        # Validate required fields
        pos_profile = form_data.get("PosProfile")
        if not pos_profile:
            frappe.response["status"] = "error"
            frappe.response["message"] = "POS Profile is required"
            return
        
        pos_profile = pos_profile + " Operators"
            
        user = form_data.get("User")
        opening_date = form_data.get("Date", frappe.utils.nowdate())
        
        # Get POS Profile document
        pos_profile_name = pos_profile
        if not frappe.db.exists("POS Profile", pos_profile_name):
            frappe.response["status"] = "error"
            frappe.response["message"] = f"POS Profile '{pos_profile_name}' does not exist"
            return
            
        pos_profile_doc = frappe.get_doc("POS Profile", pos_profile_name)
        
        # check if the user is in the pos profile users
        pos_profile_users = [d.user for d in pos_profile_doc.get("applicable_for_users")]
        if user not in pos_profile_users:
            # return {"status": "error", "message": f"User '{user}' is not assigned to POS Profile '{pos_profile_name}'"}
            frappe.response["status"] = "error"
            frappe.response["message"] = f"User '{user}' is not assigned to POS Profile '{pos_profile_name}'"
            return
                
        # Create new End of Day Opening document
        opening = frappe.new_doc("POS Opening")
        opening.user = user
        opening.pos_profile = pos_profile
        opening.opening_date = opening_date
        opening.opening_time = frappe.utils.nowtime()
        opening.company = pos_profile_doc.company
        opening.cash_float = form_data.get("CashFloat")
        
        # Process EOD Cash with validations
        cash_denominations = [100, 50, 20, 10, 5, 2, 1, 0.25, 0.10, 0.05, 0.01]
        roll_values = {2: 50, 1: 25, 0.25: 10, 0.1: 5, 0.05: 2, 0.01: 0.5}
        
        cash_data = form_data.get("CashCoins", [])
        total_cash = 0
        bills_total = 0
        coins_total = 0
        
        for cash_item in cash_data:
            cash_value = float(cash_item.get("CashAndCoin", 0))
            qty = int(cash_item.get("Qty", 0))
            rolls = int(cash_item.get("Rolls", 0))
                        
            # Validation: Rolls can only be added for coins of $2 or less
            if rolls > 0 and cash_value > 2:
                frappe.throw(f"Error: Rolls can only be added for coins of $2 or less. Invalid for ${cash_value}")
            
            # Calculate amount based on denomination and rolls
            if cash_value <= 2 and cash_value in roll_values:
                amount = (cash_value * qty) + (roll_values[cash_value] * rolls)
                bills_total += cash_value * qty if cash_value >= 1 else 0
                coins_total += cash_value * qty if cash_value < 1 else 0
            else:
                amount = cash_value * qty
                bills_total += amount if cash_value >= 5 else 0
                coins_total += amount if cash_value < 5 else 0
            
            total_cash += amount
            
            opening.append("opening_cash", {
                "cash": cash_value,
                "qty": qty,
                "rolls": rolls,
                "amount": amount
            })
            
        print(total_cash, bills_total, coins_total)
        
        opening.total_cash = total_cash
        opening.bills_total = bills_total
        opening.coins_total = coins_total
        
        # Save the document
        opening.insert()
        opening.submit()
        frappe.db.commit()
        
        frappe.response["status"] = "success"
        frappe.response["message"] = ""
        frappe.response["docname"] = opening.name
        frappe.response["float_amount"] = opening.cash_float
        frappe.response["total_cash"] = opening.total_cash
        frappe.response["bills_total"] = opening.bills_total
        frappe.response["coins_total"] = opening.coins_total
    except Exception as e:
        frappe.log_error(message=frappe.get_traceback(), title="POS - Error creating opening entry")
        frappe.response["status"] = "error"
        frappe.response["message"] = f"User {user} has no permission to create opening entry" if not str(e) else str(e)
        frappe.db.rollback()

def create_pos_api_log(form_data):
    """
    Create a log entry for the POS API call.
    """
    try:
        log = frappe.new_doc("POS API Log")
        log.request_type = "POS Opening"
        log.payload = frappe.as_json(form_data)
        log.insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception as e:
        frappe.log_error(message=frappe.get_traceback(), title="POS - Error creating API log")