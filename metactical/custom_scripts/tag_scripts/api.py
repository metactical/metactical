import frappe
from frappe import _
from metactical.utils.tag_automation_engine import TagAutomationEngine

@frappe.whitelist()
def execute_tag_script(script_manager_name, filters=None):
    """
    API to execute a tag script
    
    Args:
        script_manager_name: Name of Tag Script Manager
        filters: Optional JSON filters for target doctype
    
    Returns:
        execution_id: ID to track execution progress
    """
    if filters and isinstance(filters, str):
        import json
        filters = json.loads(filters)
    
    execution_id = TagAutomationEngine._process_single_document(
        script_manager_name, filters
    )
    
    return {
        "success": True,
        "execution_id": execution_id,
        "message": _("Tag script execution started. Track progress using execution ID.")
    }

@frappe.whitelist()
def get_execution_status(execution_id):
    """
    Get status of a running execution
    """
    log = frappe.get_doc("Tag Execution Log", {"execution_id": execution_id})
    
    return {
        "execution_id": execution_id,
        "status": log.status,
        "progress_percent": log.progress_percent,
        "records_processed": log.records_processed,
        "total_records": log.total_records,
        "current_batch": log.current_batch,
        "batch_count": log.batch_count,
        "start_time": log.start_time,
        "end_time": log.end_time,
        "duration": log.duration,
        "records_failed": log.records_failed
    }

@frappe.whitelist()
def cancel_execution(execution_id):
    """
    Cancel a running execution
    """
    TagAutomationEngine.cancel_execution(execution_id)
    return {"success": True, "message": _("Execution cancelled")}

@frappe.whitelist(allow_guest=True)
def run_all_scripts(target_doctype=None):
    """
    Run all enabled scripts
    """
    filters = {"enabled": 1}
    if target_doctype:
        filters["target_doctype"] = target_doctype
    
    scripts = frappe.get_all("Tag Script Manager", filters=filters, pluck='name')
    
    execution_ids = []
    for script in scripts:
        tag_automation_engine = TagAutomationEngine()
        execution_id = tag_automation_engine.execute_script(script_manager_name=script)
        execution_ids.append({
            "script": script,
            "execution_id": execution_id
        })
    
    return {
        "success": True,
        "executions": execution_ids
    }

@frappe.whitelist(allow_guest=True)
def test_script(script_manager_name, sample_doc_name):
    """
    Test a script on a single document
    """
    script_config = frappe.get_doc("Tag Script Manager", script_manager_name)
    doc = frappe.get_doc(script_config.target_doctype, sample_doc_name)
    
    # Execute script
    script_outputs = TagAutomationEngine._process_single_document(
        script_config, doc
    )
    
    # Evaluate conditions
    tags_to_apply = TagAutomationEngine._evaluate_conditions(
        script_config, script_outputs
    )
    
    return {
        "success": True,
        "outputs": script_outputs,
        "tags_to_apply": tags_to_apply
    }