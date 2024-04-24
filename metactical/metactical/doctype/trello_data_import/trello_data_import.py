# Copyright (c) 2024, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
import csv


class TrelloDataImport(Document):
	pass

@frappe.whitelist()
def import_csv(doc_name):
	# get file from doc_name and read it
	# parse the file and create cards

	# get the file
	doc = frappe.get_doc("Trello Data Import", doc_name)

	# read the file
	_file = frappe.get_doc("File", {"file_url": doc.file})
	filename = _file.get_full_path()
	csv_json = csv_to_json(filename)

	log_message = ""
	members_list = []

	for row in csv_json:
		members = row.get("Members").split(",") if row.get("Members") else []
		members_list.extend(members)
	
	# unique members
	members_list = list(set(members_list))
	project = frappe.db.exists("Project", {"project_name": row.get("Board Name")})

	if not project:
		project = frappe.new_doc("Project")
		project.project_name = row.get("Board Name")
		project.save()
		frappe.db.commit()
	
		log_message += f"Project {row.get('Board Name')} created\n"

	tasks_list = []
	# create queue for 50 tasks at a time
	for row in csv_json:
		if row["Archived"] != "true":
			tasks_list.append(row)

		if len(tasks_list) == 50:
			frappe.enqueue("metactical.metactical.doctype.trello_data_import.trello_data_import.create_tasks", queue="short", tasks_list=tasks_list, project=project, doc=doc)
			tasks_list = []

	# create tasks for remaining tasks
	if tasks_list:
		frappe.enqueue("metactical.metactical.doctype.trello_data_import.trello_data_import.create_tasks", queue="short", tasks_list=tasks_list, project=project, doc=doc)

	frappe.response["message"] = "Data import started"

def create_tasks(tasks_list, project, doc):
	log_message = ""
	for row in tasks_list:
		project = project if type(project) == str else project.name
		if row.get("Card Name") and not frappe.db.exists("Task", {"subject": row.get("Card Name"), "project": project}):
			task = frappe.new_doc("Task")
			if len(row["Card Name"]) > 137:
				task.subject = row["Card Name"][:137]+"..."
			else:
				task.subject = row["Card Name"]
			
			task.project = project if type(project) == str else project.name

			# assign due date to start date if start date is greater than due date
			if row.get("Start Date") and row.get("Due Date"):
				if frappe.utils.getdate(row.get("Start Date")) > frappe.utils.getdate(row.get("Due Date")):
					row["Due Date"] = row["Start Date"]
			elif not row.get("start_date"):
				row["Start Date"] = row.get("Due Date")

			list_name = frappe.scrub(row.get("List Name").lower().replace(" ", "_"))
			status_mapping = get_status_mapping()
			if list_name not in status_mapping:
				if list_name.startswith("doing"):
					task.status == "Working"
				else:
					task.status = "Open"
			else:
				task.status = status_mapping[list_name]

			task.exp_start_date = frappe.utils.getdate(row.get("Start Date")) if row.get("Start Date") else None
			task.exp_end_date = frappe.utils.getdate(row.get("Due Date")) if row.get("Due Date") else None
			task.description = (row['Card Name'] if len(row["Card Name"]) > 0 else "") + row.get("Card Description")
			task.flags.ignore_validate = True
			task.save()
			frappe.db.commit()
			log_message += f"Task {row.get('Card Name')} created\n"
		
			if row.get("Attachment Links"):
				# create attachment for each attachment
				# get the last item from attachments list
				attachment_doc = frappe.new_doc("File")
				attachment_doc.file_url = row["Attachment Links"]
				attachment_doc.folder = "Home/Attachments"
				attachment_doc.is_private = 1
				attachment_doc.attached_to_doctype = "Task"
				attachment_doc.attached_to_name = task.name
				attachment_doc.save()
				frappe.db.commit()
			
			if row.get("Members"):
				# create todo for each member
				members = row.get("Members").split(",")
				umapping = get_user_mapping()
				for member in members:
					todo = frappe.new_doc("ToDo")
					todo.description = task.subject
					todo.due_date = task.exp_end_date
					todo.owner = umapping.get(member.strip())
					todo.reference_type = "Task"
					todo.reference_name = task.name
					todo.assigned_by = frappe.session.user
					todo.save()
					log_message += f"Task {task.subject} assigned to {todo.owner}\n"
					frappe.db.commit()

	frappe.db.set_value("Trello Data Import", doc.name, "log",  log_message, update_modified=False)
	frappe.db.commit()

	frappe.publish_realtime("trello_data_import", {}, user=frappe.session.user)
def get_user_mapping():
	return {
		'manuel17541880': 'manuel@metactical.com', 
		'gari001':'gari@metactical.com', 
		'abdooljaleelkhan':'abdooljaleel@camouflage.ca', 
		'basem146': 'basem@metactical.com', 
		'irinap32':'irina.p@camouflage.ca', 
		'baseerkhudayar1':'baseer@goldenplazadistributors.com', 
		'walid973':'walid@metactical.com', 
		'zeyad115':'zeyad@metactical.com', 
		'mariamraouf2': 'mariam@ravenx.com', 
		'abdul73':'abdul@goldenplazadistributors.com', 
		'diellza36':'diellza@metactical.com', 
		'ajmaal': 'ajmal@metactical.com', 
		'diellza36':'diellza@metactical.com', 
		'bujanabanasi': 'bujana@metactical.com', 
		'victorp41': 'victor.p@camouflage.ca', 
		'osama96063986':'osama@metactical.com',
		'khalidkhudayar': 'khalid@goldenplazadistributors.com',
		'nushrat24': 'nushratfarjan@metactical.com'
	}


def csv_to_json(csvFilePath):
		jsonArray = []
		#read csv file
		with open(csvFilePath) as csvf:
			#load csv file data using csv library's dictionary reader
			csvReader = csv.DictReader(csvf, delimiter=',')

			#convert each csv row into python dict
			for row in csvReader:
				jsonArray.append(row)

		return jsonArray

def get_status_mapping():
	# reverse key and values of ab
	return {
		"todo": "Open",
		"doing": "Working",
		"under_review": "Pending Review",
		"backlog": "Template",
		"completed": "Completed",
		"done": "Completed",
		"review": "Pending Review",
		"pending": "Pending Review",
	}
	