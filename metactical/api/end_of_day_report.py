import frappe
from datetime import datetime
from dateutil.relativedelta import relativedelta

@frappe.whitelist(allow_guest=True)
def get_us_report_data(date):
	#date = "2023-02-16"
	data = []
	total_stores_with_tax = 0
	total_stores_without_tax = 0
	total_web_with_tax = 0
	total_web_without_tax = 0
	total_stores_mtd = 0
	total_stores_pmtd = 0
	total_web_mtd = 0
	total_web_pmtd = 0
	
	sources = frappe.db.get_all("Lead Source", ['name', 'ais_report_label'])
	
	#Get Stores data
	for source in sources:
		wtype = source.name.split("-")
		row = {"location": source.ais_report_label, "total_with_tax": 0, "total_without_tax": 0}
		sql = ""
		if not (len(wtype) > 0 and wtype[0].strip() == "Website") \
			and source.ais_report_label is not None and source.ais_report_label != "":
			sql = """SELECT 
						COALESCE(SUM(total), 0) AS total_without_tax
					FROM
						`tabSales Invoice`
					WHERE
						source = %(source)s AND posting_date = %(date)s
						AND docstatus = 1"""
			query = frappe.db.sql(sql, {"source": source.name, "date": date}, as_dict=1)
			if len(query) > 0:
				row.update({
					"total_without_tax": query[0].total_without_tax
				})
				total_web_without_tax += query[0].total_without_tax
			else:
				row.update({
					"total_with_tax": 0.0,
					"total_without_tax": 0.0
				})
				
			#Get month to date values
			selected_date = datetime.strptime(date, "%Y-%m-%d")
			start_date = datetime.strftime(selected_date, "%Y-%m-01")
			query = frappe.db.sql("""SELECT
										COALESCE(SUM(total), 0) AS total_mtd
									FROM
										`tabSales Invoice`
									WHERE
										source = %(source)s AND posting_date BETWEEN %(start_date)s
										AND %(end_date)s AND docstatus = 1""",
								{"source": source.name, "start_date": start_date, "end_date": date}, as_dict=1)
			if len(query) > 0:
				row.update({
					"total_mtd": query[0].total_mtd
				})
				total_stores_mtd += query[0].total_mtd
			else:
				row.update({
					"total_mtd": 0.0
				})
				
			# Get previous years month to date
			previous_month = selected_date + relativedelta(years=-1)
			start_date = datetime.strftime(previous_month, "%Y-%m-01")
			end_date = datetime.strftime(previous_month, "%Y-%m-%d")
			query = frappe.db.sql("""SELECT
										COALESCE(SUM(total), 0) AS total_pmtd
									FROM
										`tabSales Order`
									WHERE
										source = %(source)s AND transaction_date BETWEEN %(start_date)s
										AND %(end_date)s AND docstatus = 1""", 
								{"source": source.name, "start_date": start_date, "end_date": end_date}, as_dict=1)
			if len(query) > 0:
				row.update({
					"total_pmtd": query[0].total_pmtd
				})
				total_stores_pmtd += query[0].total_pmtd
			else:
				row.update({
					"total_pmtd": 0.0
				})
				
			data.append(row)
	
	for source in sources:
		wtype = source.name.split("-")
		row = {"location": source.ais_report_label, "total_with_tax": 0, "total_without_tax": 0}
		sql = ""
		if len(wtype) > 0 and wtype[0].strip() == "Website" \
			and source.ais_report_label is not None and source.ais_report_label != "":
			sql = """SELECT 
						COALESCE(SUM(total), 0) AS total_without_tax,
						COALESCE(SUM(grand_total), 0) AS total_with_tax
					FROM
						`tabSales Order`
					WHERE
						source = %(source)s AND transaction_date = %(date)s
						AND docstatus = 1"""
			query = frappe.db.sql(sql, {"source": source.name, "date": date}, as_dict=1)
			if len(query) > 0:
				row.update({
					"total_without_tax": query[0].total_without_tax
				})
				total_stores_without_tax += query[0].total_without_tax
			else:
				row.update({
					"total_without_tax": 0.0
				})
				
			#Get month to date values
			selected_date = datetime.strptime(date, "%Y-%m-%d")
			start_date = datetime.strftime(selected_date, "%Y-%m-01")
			query = frappe.db.sql("""SELECT
										COALESCE(SUM(total), 0) AS total_mtd
									FROM
										`tabSales Order`
									WHERE
										source = %(source)s AND transaction_date BETWEEN %(start_date)s
										AND %(end_date)s AND docstatus = 1""",
								{"source": source.name, "start_date": start_date, "end_date": date}, as_dict=1)
			if len(query) > 0:
				row.update({
					"total_mtd": query[0].total_mtd
				})
				total_web_mtd += query[0].total_mtd
			else:
				row.update({
					"total_mtd": 0.0
				})
				
			# Get previous year's month to date
			previous_month = selected_date + relativedelta(years=-1)
			start_date = datetime.strftime(previous_month, "%Y-%m-01")
			end_date = datetime.strftime(previous_month, "%Y-%m-%d")
			query = frappe.db.sql("""SELECT
										COALESCE(SUM(total), 0) AS total_pmtd
									FROM
										`tabSales Order`
									WHERE
										source = %(source)s AND transaction_date BETWEEN %(start_date)s
										AND %(end_date)s AND docstatus = 1""", 
								{"source": source.name, "start_date": start_date, "end_date": end_date}, as_dict=1)
			if len(query) > 0:
				row.update({
					"total_pmtd": query[0].total_pmtd
				})
				total_web_pmtd += query[0].total_pmtd
			else:
				row.update({
					"total_pmtd": 0.0
				})
			
			data.append(row)
			
	#Add an empty row followed with totals rows
	data.append({})
	data.append({
		"location": "Total Stores", 
		"total_with_tax": total_stores_with_tax, 
		"total_without_tax": total_stores_without_tax,
		"total_mtd": total_stores_mtd,
		"total_pmtd": total_stores_pmtd
	})
	data.append({
		"location": "Total Websites", 
		"total_with_tax": total_web_with_tax, 
		"total_without_tax": total_web_without_tax,
		"total_mtd": total_web_mtd,
		"total_pmtd": total_web_pmtd
	})
	data.append({
		"location": "USD Total",
		"total_with_tax": total_stores_with_tax + total_web_with_tax,
		"total_without_tax": total_stores_without_tax + total_web_without_tax,
		"total_mtd": total_stores_mtd + total_web_mtd,
		"total_pmtd": total_stores_pmtd + total_web_pmtd
	})
	return data
