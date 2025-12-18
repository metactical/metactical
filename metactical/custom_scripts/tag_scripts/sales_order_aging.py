# myapp/scripts/sales.py

import frappe
from frappe.utils import today, date_diff, getdate

def calculate_order_aging(sales_order_doc):
    """
    Calculate aging metrics for sales orders
    
    Returns:
        dict: {
            'days_old': Days since order creation,
            'days_overdue': Days past delivery date,
            'fulfillment_status': Status code,
            'aging_bucket': Age category
        }
    """
    
    order_date = getdate(sales_order_doc.transaction_date)
    current_date = getdate(today())
    
    days_old = date_diff(current_date, order_date)
    
    # Calculate days overdue
    if sales_order_doc.delivery_date:
        delivery_date = getdate(sales_order_doc.delivery_date)
        days_overdue = date_diff(current_date, delivery_date)
        if days_overdue < 0:
            days_overdue = 0
    else:
        days_overdue = 0
    
    # Determine fulfillment status
    if sales_order_doc.status == 'Completed':
        fulfillment_status = 'Completed'
    elif sales_order_doc.per_delivered >= 100:
        fulfillment_status = 'Delivered'
    elif sales_order_doc.per_delivered > 0:
        fulfillment_status = 'Partial'
    elif days_overdue > 0:
        fulfillment_status = 'Overdue'
    else:
        fulfillment_status = 'Pending'
    
    # Age buckets
    if days_old <= 7:
        aging_bucket = '0-7 days'
    elif days_old <= 14:
        aging_bucket = '8-14 days'
    elif days_old <= 30:
        aging_bucket = '15-30 days'
    elif days_old <= 60:
        aging_bucket = '31-60 days'
    else:
        aging_bucket = '60+ days'
    
    return {
        'days_old': int(days_old),
        'days_overdue': int(days_overdue),
        'fulfillment_status': fulfillment_status,
        'aging_bucket': aging_bucket,
        'percent_delivered': float(sales_order_doc.per_delivered or 0)
    }