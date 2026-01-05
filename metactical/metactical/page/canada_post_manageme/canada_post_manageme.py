import frappe
from frappe import _
from metactical.utils.shipping.canada_post import CanadaPost
from datetime import datetime


@frappe.whitelist()
def get_erpnext_untransmitted_shipments(warehouse=None):
	"""
	Get shipments from ERPNext database that haven't been transmitted
	and are NOT on Canada Post (i.e., exist in ERP but not in Canada Post groups).
	
	Args:
		warehouse: Optional warehouse filter
	
	Returns:
		dict: {
			'shipments': List of untransmitted shipment records from ERPNext that are not on Canada Post
		}
	"""
	try:
		# First, get all shipments from Canada Post
		canada_post_result = get_untransmitted_shipments(warehouse)
		canada_post_shipments = canada_post_result.get('shipments', [])
		
		# Build set of shipment names that exist in Canada Post
		canada_post_shipment_names = {s['name'] for s in canada_post_shipments}
		
		# Build SQL query with filters
		conditions = [
			"service_provider = 'Canada Post'",
			"docstatus = 1",
			"ais_shipment_status = 'Shipped'",
			"(po_number IS NULL OR po_number = '')"
		]
		
		# Add warehouse filter only if a specific warehouse is selected
		if warehouse and warehouse != "" and warehouse != "All Warehouses":
			conditions.append(f"warehouse = {frappe.db.escape(warehouse)}")
		
		where_clause = " AND ".join(conditions)
		
		# Query shipments using SQL
		shipments = frappe.db.sql(f"""
			SELECT 
				name,
				pickup_date,
				warehouse,
				service_provider,
				delivery_customer,
				po_number
			FROM `tabShipment`
			WHERE {where_clause}
			ORDER BY pickup_date DESC
		""", as_dict=1)
		
		# Process shipments and filter out those that exist in Canada Post
		result_shipments = []
		for shipment in shipments:
			# Skip if this shipment exists in Canada Post
			if shipment.name in canada_post_shipment_names:
				continue
			
			warehouse_name = shipment.get('warehouse')
			pickup_date = shipment.get("pickup_date")
			
			if not pickup_date or not warehouse_name:
				continue
			
			# Build group_id in the same format as CanadaPost class
			if isinstance(pickup_date, str):
				pickup_date_obj = datetime.strptime(pickup_date, "%Y-%m-%d")
			else:
				pickup_date_obj = pickup_date
			
			pickup_date_str = pickup_date_obj.strftime("%Y%m%d")
			warehouse_prefix = warehouse_name.split("-")[0].replace(" ", "")
			group_id = f"{warehouse_prefix}-{pickup_date_str}"
			
			# Get tracking number from first shipment child record
			tracking_number = None
			shipment_records = frappe.get_all(
				'Canada Post Shipment',
				filters={'parent': shipment.name},
				fields=['awb_number'],
				limit=1
			)
			if shipment_records:
				tracking_number = shipment_records[0].get('awb_number')
			
			result_shipments.append({
				'name': shipment.name,
				'pickup_date': shipment.pickup_date,
				'warehouse': shipment.warehouse,
				'service_provider': shipment.service_provider,
				'delivery_customer': shipment.delivery_customer,
				'group_id': group_id,
				'tracking_number': tracking_number,
			})
		
		return {
			'shipments': result_shipments,
		}
	
	except Exception as e:
		frappe.log_error(
			title="ERPNext - Get Untransmitted Shipments Error",
			message=frappe.get_traceback()
		)
		frappe.throw(_("Error fetching ERPNext untransmitted shipments: {0}").format(str(e)))


@frappe.whitelist()
def get_untransmitted_shipments(warehouse=None):
	"""
	Get shipments from Canada Post API that haven't been transmitted
	(no manifest has been created for them).
	
	Args:
		warehouse: Optional warehouse filter
	
	Returns:
		dict: {
			'shipments': List of untransmitted shipment records with ERP data,
			'available_groups': List of available group IDs from Canada Post
		}
	"""
	try:
		# Initialize Canada Post API
		cp = CanadaPost()
		
		# Get available groups from Canada Post API
		available_groups = cp.get_available_groups()
		
		# TESTING: Only use specific group - REMOVE AFTER TESTING
		available_groups = [g for g in available_groups if g == "Stores-20251128"]
		
		untransmitted = []
		
		# Process each group to get shipments
		for group_id in available_groups:
			# Skip if warehouse filter is set and doesn't match
			if warehouse and warehouse != "" and warehouse != "All Warehouses":
				# Extract warehouse prefix from group_id (format: "WarehousePrefix-YYYYMMDD")
				group_warehouse_prefix = group_id.split("-")[0]
				filter_warehouse_prefix = warehouse.split("-")[0].replace(" ", "")
				
				if group_warehouse_prefix != filter_warehouse_prefix:
					continue
			
			# Get all shipments in this group from Canada Post
			group_shipments = cp.get_group_shipments(group_id)
			
			for cp_shipment in group_shipments:
				# Get the ERP Shipment name from customer-ref-1
				erp_shipment_name = cp_shipment['references'].get('ref_1')
				
				if not erp_shipment_name:
					continue
				
				# Check if this shipment exists in ERP and get its details
				try:
					shipment_doc = frappe.get_doc('Shipment', erp_shipment_name)
					
					# Skip if shipment has been transmitted (has po_number/manifest)
					if shipment_doc.po_number:
						continue
					
					# Add to untransmitted list
					untransmitted.append({
						'name': shipment_doc.name,
						'pickup_date': shipment_doc.pickup_date,
						'warehouse': shipment_doc.warehouse,
						'service_provider': 'Canada Post',
						'delivery_customer': shipment_doc.delivery_customer,
						'group_id': group_id,
						'tracking_number': cp_shipment.get('tracking_pin'),
						'shipment_id': cp_shipment.get('shipment_id'),
						'shipment_status': cp_shipment.get('shipment_status'),
						'service_code': cp_shipment.get('service_code', ''),
					})
					
				except frappe.DoesNotExistError:
					# Shipment exists in Canada Post but not in ERP
					frappe.log_error(
						title="Canada Post Shipment Not Found in ERP",
						message=f"Shipment {erp_shipment_name} found in Canada Post group {group_id} but doesn't exist in ERP"
					)
					continue
		
		# Sort by pickup date (newest first)
		untransmitted.sort(key=lambda x: x['pickup_date'], reverse=True)
		
		return {
			'shipments': untransmitted,
			'available_groups': available_groups,
		}
	
	except Exception as e:
		frappe.log_error(
			title="Canada Post - Get Untransmitted Shipments Error",
			message=frappe.get_traceback()
		)
		frappe.throw(_("Error fetching untransmitted shipments: {0}").format(str(e)))
