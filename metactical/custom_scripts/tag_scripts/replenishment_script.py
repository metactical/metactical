import frappe
from frappe.utils import today, add_days, getdate
from datetime import datetime, timedelta

def calculate_inventory_metrics(item_doc):
    """
    Calculate inventory health metrics for an item
    
    Returns:
        dict: {
            'date_of_supply': Date when stock expected to run out,
            'quantity_on_hand': Current stock,
            'days_of_supply': Days until stockout,
            'reorder_level': Calculated reorder level,
            'stock_status': Current status code
        }
    """
    
    item_code = item_doc.name
    
    # Get quantity on hand from all warehouses
    qty_on_hand = frappe.db.sql("""
        SELECT SUM(actual_qty)
        FROM `tabBin`
        WHERE item_code = %s
    """, (item_code,))[0][0] or 0.0
    
    # Get average daily consumption (last 90 days)
    ninety_days_ago = add_days(today(), -90)
    
    consumption = frappe.db.sql("""
        SELECT SUM(ABS(actual_qty))
        FROM `tabStock Ledger Entry`
        WHERE item_code = %s
        AND posting_date >= %s
        AND actual_qty < 0
        AND voucher_type NOT IN ('Stock Reconciliation')
    """, (item_code, ninety_days_ago))[0][0] or 0.0
    
    avg_daily_consumption = consumption / 90
    
    # Calculate days of supply
    if avg_daily_consumption > 0:
        days_of_supply = qty_on_hand / avg_daily_consumption
    else:
        days_of_supply = 999  # No consumption, consider as excess
    
    # Calculate date of supply
    if days_of_supply < 999:
        date_of_supply = add_days(today(), int(days_of_supply))
    else:
        date_of_supply = None
    
    # Calculate reorder level (e.g., 14 days of stock + safety stock)
    lead_time_days = item_doc.lead_time_days or 14
    safety_stock_days = 7
    reorder_level = avg_daily_consumption * (lead_time_days + safety_stock_days)
    
    # Determine stock status
    if qty_on_hand <= 0:
        stock_status = 0  # Out of Stock
    elif qty_on_hand < reorder_level * 0.5:
        stock_status = 1  # Critical
    elif qty_on_hand < reorder_level:
        stock_status = 2  # Low
    elif days_of_supply > 90:
        stock_status = 4  # Excess
    else:
        stock_status = 3  # Healthy
    
    return {
        'date_of_supply': date_of_supply.strftime('%Y-%m-%d') if date_of_supply else None,
        'quantity_on_hand': float(qty_on_hand),
        'days_of_supply': int(days_of_supply) if days_of_supply < 999 else 999,
        'reorder_level': float(reorder_level),
        'stock_status': stock_status,
        'avg_daily_consumption': float(avg_daily_consumption)
    }


def calculate_fast_slow_moving(item_doc):
    """
    Classify items as fast/slow/non-moving
    
    Returns:
        dict: {
            'movement_type': 'Fast'/'Medium'/'Slow'/'Non-Moving',
            'turnover_ratio': Annual turnover ratio,
            'days_since_last_transaction': Days since last movement
        }
    """
    
    item_code = item_doc.name
    
    # Get last transaction date
    last_transaction = frappe.db.sql("""
        SELECT MAX(posting_date)
        FROM `tabStock Ledger Entry`
        WHERE item_code = %s
    """, (item_code,))[0][0]
    
    if last_transaction:
        days_since_last = (getdate(today()) - getdate(last_transaction)).days
    else:
        days_since_last = 9999
    
    # Calculate annual turnover
    one_year_ago = add_days(today(), -365)
    
    total_issued = frappe.db.sql("""
        SELECT SUM(ABS(actual_qty))
        FROM `tabStock Ledger Entry`
        WHERE item_code = %s
        AND posting_date >= %s
        AND actual_qty < 0
    """, (item_code, one_year_ago))[0][0] or 0.0
    
    avg_inventory = frappe.db.sql("""
        SELECT AVG(actual_qty)
        FROM `tabBin`
        WHERE item_code = %s
    """, (item_code,))[0][0] or 0.0
    
    if avg_inventory > 0:
        turnover_ratio = total_issued / avg_inventory
    else:
        turnover_ratio = 0
    
    # Classify movement
    if days_since_last > 180:
        movement_type = 'Non-Moving'
    elif turnover_ratio >= 12:  # More than once per month
        movement_type = 'Fast'
    elif turnover_ratio >= 4:   # 4-12 times per year
        movement_type = 'Medium'
    else:
        movement_type = 'Slow'
    
    return {
        'movement_type': movement_type,
        'turnover_ratio': float(turnover_ratio),
        'days_since_last_transaction': int(days_since_last)
    }