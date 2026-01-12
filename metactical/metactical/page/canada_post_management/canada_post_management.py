import frappe
from frappe import _
from metactical.utils.shipping.canada_post import CanadaPost
from datetime import datetime, timedelta


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
		
		# Get unique group IDs to prevent processing the same group multiple times
		available_groups = list(set(available_groups))
		
		# For testing purposes, only use groups with "Stores" in it
		#available_groups = [g for g in available_groups if "Stores" in g]
		
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
			group_shipments = cp.get_group_shipments(group_id=group_id)
			
			for cp_shipment in group_shipments:
				# Get the ERP Shipment name from customer-ref-1
				erp_shipment_name = cp_shipment['references'].get('ref_1')
				
				# If no reference is provided, try to find the shipment by shipment_id
				if not erp_shipment_name:
					shipment_id = cp_shipment.get('shipment_id')
					if shipment_id:
						# Search for shipment in ERPNext by shipment_id in child table
						shipment_records = frappe.get_all(
							'Canada Post Shipment',
							filters={'shipment_id': shipment_id},
							fields=['parent'],
							limit=1
						)
						if shipment_records:
							erp_shipment_name = shipment_records[0].get('parent')
				
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


@frappe.whitelist()
def get_past_manifests(from_date=None, to_date=None):
	"""
	Get past manifests from Canada Post API within a date range.
	
	Args:
		from_date: Start date in YYYY-MM-DD format (optional, defaults to 30 days ago)
		to_date: End date in YYYY-MM-DD format (optional, defaults to today)
	
	Returns:
		dict: {
			'manifests': List of manifest records with links
		}
	"""
	try:
		# Set default dates if not provided
		if not to_date:
			to_date = datetime.now().strftime("%Y-%m-%d")
		
		if not from_date:
			from_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
		
		# Validate date range (max 90 days)
		from_date_obj = datetime.strptime(from_date, "%Y-%m-%d")
		to_date_obj = datetime.strptime(to_date, "%Y-%m-%d")
		date_diff = (to_date_obj - from_date_obj).days
		
		if date_diff > 90:
			frappe.throw(_("Date range cannot exceed 90 days"))
		
		if date_diff < 0:
			frappe.throw(_("'To Date' must be after 'From Date'"))
		
		# Initialize Canada Post API
		cp = CanadaPost()
		
		# Get manifests from Canada Post
		manifests = cp.get_manifests_by_date_range(from_date, to_date)
		
		return {
			'manifests': manifests
		}
	
	except Exception as e:
		frappe.log_error(
			title="Canada Post - Get Past Manifests Error",
			message=frappe.get_traceback()
		)
		frappe.throw(_("Error fetching past manifests: {0}").format(str(e)))


@frappe.whitelist()
def get_manifest_shipments(manifest_shipments_url, media_type):
	"""
	Get shipments for a specific manifest.
	
	Args:
		manifest_shipments_url: The URL to fetch manifest shipments
		media_type: The media type for the request
	
	Returns:
		dict: {
			'shipments': List of shipment records
		}
	"""
	try:
		# Initialize Canada Post API
		cp = CanadaPost()
		
		# Fetch manifest shipments
		response = cp.get_response(
			manifest_shipments_url, 
			None, 
			headers={'Accept': media_type}, 
			method='GET'
		)
		
		if not response or 'shipments' not in response:
			return {'shipments': []}
		
		# Get shipment links
		shipment_links = response['shipments'].get('link', [])
		if isinstance(shipment_links, dict):
			shipment_links = [shipment_links]
		
		shipments_data = []
		
		for link in shipment_links:
			try:
				# Get individual shipment details
				shipment_response = cp.get_response(
					link['@href'], 
					None, 
					headers={'Accept': link['@media-type']}, 
					method='GET'
				)
				
				if shipment_response and 'shipment-info' in shipment_response:
					shipment_info = shipment_response['shipment-info']
					
					# Get ERP Shipment name from references
					erp_shipment_name = None
					if 'customer-references' in shipment_info:
						refs = shipment_info['customer-references']
						erp_shipment_name = refs.get('customer-ref-1')
					
					# Try to get additional data from ERP if shipment exists
					warehouse = None
					pickup_date = None
					delivery_customer = None
					
					if erp_shipment_name:
						try:
							shipment_doc = frappe.get_doc('Shipment', erp_shipment_name)
							warehouse = shipment_doc.warehouse
							pickup_date = shipment_doc.pickup_date
							delivery_customer = shipment_doc.delivery_customer
						except frappe.DoesNotExistError:
							pass
					
					# Build shipment data
					shipment_data = {
						'name': erp_shipment_name,
						'shipment_id': shipment_info.get('shipment-id'),
						'tracking_number': shipment_info.get('tracking-pin'),
						'shipment_status': shipment_info.get('shipment-status'),
						'warehouse': warehouse,
						'pickup_date': pickup_date,
						'delivery_customer': delivery_customer,
						'service_provider': 'Canada Post',
					}
					
					# Get service code if available
					if 'delivery-spec' in shipment_info and 'service-code' in shipment_info['delivery-spec']:
						shipment_data['service_code'] = shipment_info['delivery-spec']['service-code']
					
					shipments_data.append(shipment_data)
					
			except Exception as e:
				frappe.log_error(
					title="Canada Post - Get Manifest Shipment Details Error",
					message=f"Error getting shipment from {link.get('@href', 'unknown')}: {str(e)}"
				)
				continue
		
		return {
			'shipments': shipments_data
		}
	
	except Exception as e:
		frappe.log_error(
			title="Canada Post - Get Manifest Shipments Error",
			message=frappe.get_traceback()
		)
		frappe.throw(_("Error fetching manifest shipments: {0}").format(str(e)))


@frappe.whitelist()
def get_manifest_pdf(artifact_url, media_type):
	"""
	Fetch manifest PDF from Canada Post API and return as base64.
	
	Args:
		artifact_url: The URL to fetch the manifest PDF
		media_type: The media type for the request
	
	Returns:
		dict: {
			'pdf_data': Base64 encoded PDF data,
			'filename': Suggested filename
		}
	"""
	try:
		import base64
		
		# Initialize Canada Post API
		cp = CanadaPost()
		
		# Fetch the PDF
		response = cp.get_response(
			artifact_url,
			None,
			headers={'Accept': media_type},
			return_request=True,
			method='GET'
		)
		
		if response.status_code != 200:
			frappe.throw(_("Failed to fetch manifest PDF"))
		
		# Convert to base64
		pdf_base64 = base64.b64encode(response.content).decode('utf-8')
		
		# Extract PO number from URL if possible for filename
		filename = "manifest.pdf"
		
		return {
			'pdf_data': pdf_base64,
			'filename': filename
		}
	
	except Exception as e:
		frappe.log_error(
			title="Canada Post - Get Manifest PDF Error",
			message=frappe.get_traceback()
		)
		frappe.throw(_("Error fetching manifest PDF: {0}").format(str(e)))

