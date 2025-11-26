# myapp/scripts/customer.py

import frappe
from frappe.utils import today, add_months, flt

def calculate_customer_segment(customer_name):
    """
    Segment customers based on RFM (Recency, Frequency, Monetary)
    
    Returns:
        dict: {
            'segment': Customer segment,
            'total_revenue': Total revenue,
            'transaction_count': Number of transactions,
            'days_since_last_order': Recency
        }
    """
    
    customer = frappe.get_doc("Customer", customer_name)
    
    # Get last 12 months data
    twelve_months_ago = add_months(today(), -12)
    
    # Calculate total revenue
    total_revenue = frappe.db.sql("""
        SELECT SUM(grand_total)
        FROM `tabSales Invoice`
        WHERE customer = %s
        AND posting_date >= %s
        AND docstatus = 1
    """, (customer, twelve_months_ago))[0][0] or 0.0
    
    # Calculate transaction count
    transaction_count = frappe.db.sql("""
        SELECT COUNT(*)
        FROM `tabSales Invoice`
        WHERE customer = %s
        AND posting_date >= %s
        AND docstatus = 1
    """, (customer, twelve_months_ago))[0][0] or 0
    
    # Calculate recency (days since last order)
    last_order = frappe.db.sql("""
        SELECT MAX(posting_date)
        FROM `tabSales Invoice`
        WHERE customer = %s
        AND docstatus = 1
    """, (customer,))[0][0]
    
    if last_order:
        from frappe.utils import getdate, date_diff
        days_since_last = date_diff(today(), last_order)
    else:
        days_since_last = 9999
    
    # Average order value
    avg_order_value = total_revenue / transaction_count if transaction_count > 0 else 0
    
    # Segment logic (RFM scoring)
    if days_since_last <= 30 and total_revenue >= 100000 and transaction_count >= 10:
        segment = 'VIP'
    elif days_since_last <= 60 and total_revenue >= 50000:
        segment = 'High Value'
    elif days_since_last <= 90 and transaction_count >= 5:
        segment = 'Regular'
    elif days_since_last <= 180:
        segment = 'Occasional'
    elif days_since_last > 180 and days_since_last < 9999:
        segment = 'At Risk'
    elif days_since_last >= 365:
        segment = 'Dormant'
    else:
        segment = 'New'
    
    return {
        'segment': segment,
        'total_revenue': float(total_revenue),
        'transaction_count': int(transaction_count),
        'days_since_last_order': int(days_since_last),
        'avg_order_value': float(avg_order_value)
    }