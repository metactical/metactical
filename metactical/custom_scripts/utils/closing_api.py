import frappe

@frappe.whitelist()
def create_closing_entry(*args, **kwargs):
    """
    Create closing entries for the specified company and fiscal year.
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
        closing_date = form_data.get("Date", frappe.utils.nowdate())
        
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
        
        # Get expected data from backend
        expected_data = get_data(user, pos_profile, closing_date, pos_profile_doc.ifw_default_lead_source)
        
        # Create new End of Day Closing document
        end_of_day_closing = frappe.new_doc("End of Day Closing")
        end_of_day_closing.user = user
        end_of_day_closing.pos_profile = pos_profile
        end_of_day_closing.closing_date = closing_date
        end_of_day_closing.closing_time = frappe.utils.nowtime()
        end_of_day_closing.company = pos_profile_doc.company
        end_of_day_closing.cash_float = form_data.get("CashFloat")
        end_of_day_closing.subtracted_float = -form_data.get("CashFloat", 0)
        end_of_day_closing.closing_notes = form_data.get("ClosingNotes")
        end_of_day_closing.expected_cash = expected_data.get("expected_cash", 0)
        end_of_day_closing.opening_entry = form_data.get("OpeningEntry")
        
        # Process EOD Cash with validations
        cash_denominations = [100, 50, 20, 10, 5, 2, 1, 0.25, 0.10, 0.05, 0.01]
        roll_values = {2: 50, 1: 25, 0.25: 10, 0.1: 5, 0.05: 2, 0.01: 0.5}
        
        cash_data = form_data.get("CashCoins", [])
        total_cash = 0
        
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
            else:
                amount = cash_value * qty
            
            total_cash += amount
            
            end_of_day_closing.append("eod_cash", {
                "cash": cash_value,
                "qty": qty,
                "rolls": rolls,
                "amount": amount
            })
        
        # Calculate rounding (round down to nearest $5)
        cash_after_round = (total_cash // 5) * 5
        rounding = cash_after_round - total_cash
        total_cash_drop = total_cash - end_of_day_closing.cash_float - (total_cash - cash_after_round)
        
        end_of_day_closing.total_cash = total_cash
        end_of_day_closing.rounding = rounding
        end_of_day_closing.total_cash_drop = total_cash_drop
        
        # Process EOD Payments with expected vs actual validation
        payments = form_data.get("Payment", [])
        expected_payments = expected_data.get("payments", {})
        
        mop_total_expected = 0
        mop_total_actual = 0
        
        # Process Cash first
        for payment in payments:
            mop = payment.get("ModeOfPayment")
            if mop == "Cash":
                actual = float(payment.get("Amount", 0))
                expected = expected_payments.get(mop, 0)
                difference = actual - expected
                
                mop_total_expected += expected
                mop_total_actual += actual
                
                end_of_day_closing.append("eod_payments", {
                    "mode_of_payment": mop,
                    "expected": expected,
                    "actual": actual,
                    "difference": difference
                })
                break
        
        # Process other modes of payment
        for payment in payments:
            mop = payment.get("ModeOfPayment")
            if mop != "Cash":
                actual = float(payment.get("Amount", 0))
                expected = expected_payments.get(mop, 0)
                difference = actual - expected
                
                mop_total_expected += expected
                mop_total_actual += actual
                
                end_of_day_closing.append("eod_payments", {
                    "mode_of_payment": mop,
                    "expected": expected,
                    "actual": actual,
                    "difference": difference
                })
        
        end_of_day_closing.mop_total_expected = mop_total_expected
        end_of_day_closing.mop_total_actual = mop_total_actual
        end_of_day_closing.mop_total_difference = mop_total_actual - mop_total_expected
        
        # Process invoices
        invoices_data = expected_data.get("invoices", [])
        for invoice in invoices_data:
            if invoice.get("is_return") != 1:
                end_of_day_closing.append("invoices", {
                    "type": invoice.get("reference_doctype"),
                    "invoice": invoice.get("reference_name"),
                    "mode_of_payment": invoice.get("mode_of_payment"),
                    "amount_paid": invoice.get("amount_paid"),
                    "owing": invoice.get("owing")
                })
            else:
                end_of_day_closing.append("return_invoices", {
                    "type": invoice.get("reference_doctype"),
                    "invoice": invoice.get("reference_name"),
                    "mode_of_payment": invoice.get("mode_of_payment"),
                    "amount_paid": abs(invoice.get("amount_paid", 0)),
                    "owing": invoice.get("owing")
                })
        
        # Save the document
        end_of_day_closing.insert()
        end_of_day_closing.submit()
        frappe.db.commit()
        
        mode_of_payments = [{"mode_of_payment": d.mode_of_payment,
                             "expected": d.expected,
                             "actual": d.actual,
                             "difference": d.difference} for d in end_of_day_closing.eod_payments]
        
        frappe.response["status"] = "success"
        frappe.response["message"] = ""
        frappe.response["float_amount"] = end_of_day_closing.cash_float
        frappe.response["total_cash"] = end_of_day_closing.total_cash
        frappe.response["rounding"] = end_of_day_closing.rounding
        frappe.response["total_cash_drop"] = end_of_day_closing.total_cash_drop
        frappe.response["expected_cash"] = end_of_day_closing.expected_cash
        frappe.response["docname"] = end_of_day_closing.name
        frappe.response["total_expected"] = end_of_day_closing.mop_total_expected
        frappe.response["total_actual"] = end_of_day_closing.mop_total_actual
        frappe.response["total_difference"] = end_of_day_closing.mop_total_difference
        frappe.response["mode_of_payments"] = mode_of_payments
    except Exception as e:
        frappe.log_error(message=frappe.get_traceback(), title="POS - Error creating closing entry")
        frappe.db.rollback()
        frappe.response["status"] = "error"
        frappe.response["message"] = str(e)
        
def get_data(user, pos_profile, closing_date, source=None):
    """
    Fetch expected data for the closing entry.
    This should match the backend method called in the JS.
    """
    # This function should exist in your backend
    # metactical.metactical.doctype.end_of_day_closing.end_of_day_closing.get_data
    from metactical.metactical.doctype.end_of_day_closing.end_of_day_closing import get_data as backend_get_data
    
    return backend_get_data(closing_date, user, pos_profile, source)

def create_pos_api_log(form_data):
    """
    Create a log entry for the POS API call.
    """
    try:
        log = frappe.new_doc("POS API Log")
        log.request_type = "End of Day Closing"
        log.payload = frappe.as_json(form_data)
        log.insert(ignore_permissions=True)
    except Exception as e:
        frappe.log_error(message=frappe.get_traceback(), title="POS - Error creating API log")

@frappe.whitelist()
def get_last_opening_or_closing(pos_profile):
    """
    Check if the last opening in the POS profile is closed using End of Day Closing.
    If closed, return the End of Day Closing document; otherwise, return the POS Opening document.
    """
    try:
        pos_profile = pos_profile + " Operators"
        
        # Get the last POS Opening document for the given profile
        last_opening = frappe.db.get_all(
            "POS Opening",
            filters={"pos_profile": pos_profile},
            fields=["name", "opening_date", "opening_time"],
            order_by="creation desc",
            limit=1
        )
        
        if not last_opening:
            return {"Status": "error", "Message": f"No POS Opening found for profile '{pos_profile}'"}
        
        last_opening_doc = last_opening[0]
        
        # Check if there is a corresponding End of Day Closing for the last opening
        closing_exists = frappe.db.exists(
            "End of Day Closing",
            {"pos_profile": pos_profile, "opening_entry": last_opening_doc["name"]}
        )
        
        if closing_exists:
            # Fetch the End of Day Closing document
            closing_doc = frappe.get_doc("End of Day Closing", closing_exists)
            full_name = frappe.db.get_value("User", closing_doc.user, "full_name")

            frappe.response["Status"] = "closed"
            frappe.response["Message"] = ""
            frappe.response["Docname"] = closing_doc.name
            frappe.response["CashFloat"] = closing_doc.cash_float
            frappe.response["Date"] = closing_doc.closing_date
            frappe.response["CreatedBy"] = full_name
        else:
            # Return the POS Opening document
            opening_doc = frappe.get_doc("POS Opening", last_opening_doc["name"])
            full_name = frappe.db.get_value("User", opening_doc.user, "full_name")

            frappe.response["Status"] = "open"
            frappe.response["Message"] = ""
            frappe.response["Docname"] = opening_doc.name
            frappe.response["CashFloat"] = opening_doc.total_cash
            frappe.response["Date"] = opening_doc.opening_date
            frappe.response["CreatedBy"] = full_name
    except Exception as e:
        frappe.log_error(message=frappe.get_traceback(), title="POS - Error fetching last opening or closing")
        return {"Status": "error", "Message": str(e)}