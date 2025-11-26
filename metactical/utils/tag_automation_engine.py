# tag_automation_engine.py

import frappe
import importlib
import uuid
from datetime import datetime
from frappe import _
from frappe.utils import now_datetime, get_datetime, time_diff_in_seconds
from typing import Dict, List, Any, Optional
import json

class TagAutomationEngine:
    """
    Main engine for tag automation with batch processing for millions of records
    """
    def __init__(self):
        pass
    
    def execute_script(self, script_manager_name: str, filters: Optional[Dict] = None, 
                      execution_id: Optional[str] = None) -> str:
        """
        Execute a tag script for all matching documents using batch processing
        
        Args:
            script_manager_name: Name of the Tag Script Manager
            filters: Optional filters to apply on target doctype
            execution_id: Optional execution ID to resume a previous run
            
        Returns:
            execution_id: Unique ID for tracking this execution
        """
        script_config = frappe.get_doc("Tag Script Manager", script_manager_name)
        
        if not script_config.enabled:
            frappe.throw(_("Script {0} is disabled").format(script_manager_name))
        
        # Create or get execution log
        if not execution_id:
            execution_id = str(uuid.uuid4())
            execution_log = self._create_execution_log(
                script_config, execution_id
            )
        else:
            execution_log = frappe.get_doc("Tag Execution Log", 
                                          {"execution_id": execution_id})
        
        # Enqueue the batch processor
        frappe.enqueue(
            self.process_in_batches,
            queue='long',
            timeout=36000,  # 10 hours
            script_manager_name=script_manager_name,
            execution_id=execution_id,
            filters=filters,
            is_async=True,
            now=False
        )
        
        self.process_in_batches(
            script_manager_name, execution_id, filters
        )
        
        return execution_id
    
    def process_in_batches(self, script_manager_name: str, execution_id: str, 
                       filters: Optional[Dict] = None):

        # helper: safe DB update without version checking
        def safe_update(doctype, name, values):
            frappe.db.set_value(doctype, name, values, update_modified=False)
            frappe.db.commit()

        # --- Load initial docs ---
        script_config = frappe.get_doc("Tag Script Manager", script_manager_name)
        execution_log = frappe.get_doc("Tag Execution Log", 
                                    {"execution_id": execution_id})

        try:
            # ---------------------------------------------------------
            # 1) Mark execution "Running"
            # ---------------------------------------------------------
            start_time = now_datetime()
            safe_update(
                "Tag Execution Log",
                execution_log.name,
                {
                    "status": "Running",
                    "start_time": start_time
                }
            )
            execution_log.reload()

            # ---------------------------------------------------------
            # 2) Count total records
            # ---------------------------------------------------------
            total_records = self._get_total_records(
                script_config.target_doctype,
                script_config.filter_json
            )

            safe_update(
                "Tag Execution Log",
                execution_log.name,
                {"total_records": total_records}
            )
            execution_log.reload()

            # ---------------------------------------------------------
            # 3) Zero records → mark completed and exit
            # ---------------------------------------------------------
            if total_records == 0:
                safe_update(
                    "Tag Execution Log",
                    execution_log.name,
                    {
                        "status": "Completed",
                        "end_time": now_datetime()
                    }
                )
                return

            # ---------------------------------------------------------
            # 4) Calculate batches
            # ---------------------------------------------------------
            batch_size = script_config.batch_size or 1000
            total_batches = (total_records + batch_size - 1) // batch_size

            safe_update(
                "Tag Execution Log",
                execution_log.name,
                {"batch_count": total_batches}
            )
            execution_log.reload()

            # ---------------------------------------------------------
            # 5) Process batches (parallel or sequential)
            # ---------------------------------------------------------
            parallel_workers = min(script_config.parallel_workers or 1, 10)

            if parallel_workers > 1:
                # IMPORTANT: workers must NEVER update execution_log directly
                self._process_parallel_batches(
                    script_config, execution_log, filters,
                    batch_size, total_batches, parallel_workers
                )
            else:
                self._process_sequential_batches(
                    script_config, execution_log, filters,
                    batch_size, total_batches
                )

            # ---------------------------------------------------------
            # 6) Mark execution completed
            # ---------------------------------------------------------
            end_time = now_datetime()
            duration = None

            if start_time:
                duration_seconds = time_diff_in_seconds(end_time, start_time)
                duration = f"{duration_seconds:.2f} seconds"

            safe_update(
                "Tag Execution Log",
                execution_log.name,
                {
                    "status": "Completed",
                    "end_time": end_time,
                    "duration": duration
                }
            )
            execution_log.reload()

            # ---------------------------------------------------------
            # 7) Update script manager safely (no save())
            # ---------------------------------------------------------
            safe_update(
                "Tag Script Manager",
                script_config.name,
                {
                    "last_execution": now_datetime(),
                    "last_execution_status": "Completed",
                    "records_processed": execution_log.records_processed
                }
            )

        # -------------------------------------------------------------
        # ERROR HANDLING
        # -------------------------------------------------------------
        except Exception as e:

            safe_update(
                "Tag Execution Log",
                execution_log.name,
                {
                    "status": "Failed",
                    "end_time": now_datetime(),
                    "error_log": str(e)
                }
            )

            frappe.log_error(
                message=frappe.get_traceback(),
                title=f"Tag Automation Failed: {script_manager_name}"
            )
            raise

    
    def _process_sequential_batches(self, script_config, execution_log, filters, 
                                batch_size, total_batches):

        def safe_update(values):
            frappe.db.set_value("Tag Execution Log", execution_log.name, values, update_modified=False)
            frappe.db.commit()

        records_processed = 0
        records_failed = 0
            
        for batch_num in range(total_batches):
            try:
                offset = batch_num * batch_size
                filters = script_config.filter_json

                doc_names = self._get_batch_records(
                    script_config.target_doctype,
                    filters,
                    batch_size,
                    offset
                )
                                    
                batch_results = self._process_batch(script_config, doc_names)
                
                records_processed += batch_results['processed']
                records_failed += batch_results['failed']
                
                safe_update({
                    "current_batch": batch_num + 1,
                    "records_processed": records_processed,
                    "records_failed": records_failed,
                    "progress_percent": ((batch_num + 1) / total_batches) * 100
                })
                
            except Exception as e:
                records_failed += len(doc_names)
                execution_log.reload()
                error_msg = f"Batch {batch_num + 1} failed: {str(e)}\n"
                safe_update({
                    "records_failed": records_failed,
                    "error_log": (execution_log.error_log or "") + error_msg
                })    
    
    def _process_parallel_batches(self, script_config, execution_log, filters, 
                                 batch_size, total_batches, parallel_workers):
        """
        Process batches in parallel using multiple background jobs
        """
        import math
        
        # Split batches among workers
        batches_per_worker = math.ceil(total_batches / parallel_workers)
        
        jobs = []
        for worker_num in range(parallel_workers):
            start_batch = worker_num * batches_per_worker
            end_batch = min(start_batch + batches_per_worker, total_batches)
            
            if start_batch >= total_batches:
                break
            
            job = frappe.enqueue(
                "metactical.utils.tag_automation_engine.self._process_batch_range",
                queue='long',
                job_name=script_config.name + f"_worker_{worker_num+1}",
                timeout=36000,
                script_manager_name=script_config.name,
                execution_id=execution_log.execution_id,
                filters=filters,
                batch_size=batch_size,
                start_batch=start_batch,
                end_batch=end_batch,
                is_async=True,
                now=False
            )
            jobs.append(job)
        
        # Wait for all jobs to complete (in a real scenario, you'd poll the status)
        # For now, the execution log will be updated by each worker
    
    
    def _process_batch_range(self, script_manager_name, execution_id, filters, 
                            batch_size, start_batch, end_batch):
        """
        Process a range of batches (used for parallel processing)
        """
        script_config = frappe.get_doc("Tag Script Manager", script_manager_name)
        execution_log = frappe.get_doc("Tag Execution Log", 
                                      {"execution_id": execution_id})
        
        records_processed = 0
        records_failed = 0
        
        for batch_num in range(start_batch, end_batch):
            try:
                offset = batch_num * batch_size
                
                doc_names = self._get_batch_records(
                    script_config.target_doctype, 
                    filters, 
                    batch_size, 
                    offset
                )
                
                batch_results = self._process_batch(
                    script_config, doc_names
                )
                
                records_processed += batch_results['processed']
                records_failed += batch_results['failed']
                
                # Update progress (with locking to prevent race conditions)
                frappe.db.sql("""
                    UPDATE `tabTag Execution Log`
                    SET 
                        records_processed = records_processed + %s,
                        records_failed = records_failed + %s,
                        current_batch = GREATEST(current_batch, %s)
                    WHERE execution_id = %s
                """, (batch_results['processed'], batch_results['failed'], 
                     batch_num + 1, execution_id))
                frappe.db.commit()
                
            except Exception as e:
                records_failed += len(doc_names) if doc_names else 0
                frappe.log_error(
                    message=str(e),
                    title=f"Batch {batch_num + 1} failed - {script_manager_name}"
                )
    
    
    def _process_batch(self, script_config, doc_names: List[str]) -> Dict[str, int]:
        """
        Process a single batch of documents
        Returns dict with 'processed' and 'failed' counts
        """
        processed = 0
        failed = 0
        
        for doc_name in doc_names:
            try:
                self._process_single_document(
                    script_config, doc_name
                )
                processed += 1
            except Exception as e:
                failed += 1
                frappe.log_error(
                    message=f"Document: {doc_name}\n{str(e)}",
                    title=f"Tag Assignment Failed - {script_config.script_name}"
                )
        
        return {'processed': processed, 'failed': failed}
    
    
    def _process_single_document(self, script_config, doc_name: str):
        """
        Process a single document and assign tags
        """
        # Get document (without loading the full doc object for performance)
        doc = frappe.get_doc(script_config.target_doctype, doc_name)
        
        # Execute custom script
        script_outputs = self._execute_custom_script(
            script_config.script_path, doc
        )
                
        # Validate outputs (optional, can be skipped for performance)
        # self._validate_outputs(script_config, script_outputs)
        
        
        # Evaluate conditions
        # print("script_outputs:", script_outputs)
        tags_to_apply = self._evaluate_conditions(
            script_config, script_outputs
        )
                
        # Apply tags using direct DB operations for performance
        self._apply_tags_bulk(
            script_config, doc.doctype, doc.name, tags_to_apply
        )
    
    
    def _execute_custom_script(self, script_path: str, doc) -> Dict[str, Any]:
        """
        Execute the custom script function
        """
        try:
            module_path, function_name = script_path.rsplit('.', 1)
            module = importlib.import_module(module_path)
            script_function = getattr(module, function_name)
            
            return script_function(doc)
            
        except Exception as e:
            frappe.throw(_("Error executing script {0}: {1}").format(
                script_path, str(e)
            ))
    
    def _evaluate_conditions(self, script_config, outputs):
        """
        Evaluate conditions and return tags to apply
        """
        tags_to_apply = []
        if outputs is None:
            return tags_to_apply
        
        # Sort conditions by priority
        conditions = sorted(
            script_config.tag_conditions, 
            key=lambda x: x.priority
        )
                
        for condition in conditions:
            if self._evaluate_single_condition(condition, outputs):
                tag_name = condition.tag_to_assign
                if script_config.tag_prefix:
                    tag_name = script_config.tag_prefix + tag_name
                
                tags_to_apply.append({
                    "tag": tag_name,
                    "remove_others": condition.remove_other_tags,
                    "color": condition.tag_color
                })
                break  # Only apply first matching condition
        
        # Apply default tag if no conditions matched
        if not tags_to_apply and script_config.default_tag:
            default_tag = script_config.default_tag
            if script_config.tag_prefix:
                default_tag = script_config.tag_prefix + default_tag
            
            tags_to_apply.append({
                "tag": default_tag,
                "remove_others": False,
                "color": None
            })
        
        return tags_to_apply
    
    
    def _evaluate_single_condition(self, condition, outputs: Dict[str, Any]) -> bool:
        """
        Evaluate a single condition
        """
        field_value = outputs.get(condition.condition_field)
        operator = condition.operator
        compare_value = condition.value
        
        try:
            if operator == "=":
                return str(field_value) == str(compare_value)
            elif operator == "!=":
                return str(field_value) != str(compare_value)
            elif operator == ">":
                return float(field_value) > float(compare_value)
            elif operator == "<":
                return float(field_value) < float(compare_value)
            elif operator == ">=":
                return float(field_value) >= float(compare_value)
            elif operator == "<=":
                return float(field_value) <= float(compare_value)
            elif operator == "between":
                return float(compare_value) <= float(field_value) <= float(condition.value_2)
            elif operator == "in":
                values = [v.strip() for v in str(compare_value).split(',')]
                return str(field_value) in values
            elif operator == "not in":
                values = [v.strip() for v in str(compare_value).split(',')]
                return str(field_value) not in values
            elif operator == "contains":
                return str(compare_value).lower() in str(field_value).lower()
            elif operator == "not contains":
                return str(compare_value).lower() not in str(field_value).lower()
            elif operator == "is null":
                return field_value is None or field_value == ""
            elif operator == "is not null":
                return field_value is not None and field_value != ""
        except Exception:
            return False
        
        return False
    
    
    def _apply_tags_bulk(self, script_config, doctype: str, docname: str, 
                        tags_to_apply: List[Dict]):
        """
        Apply tags using bulk operations for better performance
        """
        if not tags_to_apply:
            return
        
        # Get existing tags
        existing_tags_str = frappe.db.get_value(doctype, docname, "_user_tags") or ""
        existing_tags = [t.strip() for t in existing_tags_str.split(",") if t.strip()]
        
        # Remove tags with same prefix if needed
        for tag_info in tags_to_apply:
            if tag_info["remove_others"] and script_config.tag_prefix:
                existing_tags = [
                    t for t in existing_tags 
                    if not t.startswith(script_config.tag_prefix)
                ]
        
        # Add new tags
        new_tags = existing_tags.copy()
        for tag_info in tags_to_apply:
            tag = tag_info["tag"]
            if tag not in new_tags:
                new_tags.append(tag)
                
                # Ensure tag exists in Tag DocType
                if not frappe.db.exists("Tag", tag):
                    tag_doc = frappe.get_doc({
                        "doctype": "Tag",
                        "name": tag
                    })
                    tag_doc.insert(ignore_permissions=True)
        
        # Update document tags
        new_tags_str = ",".join(new_tags)
        frappe.db.set_value(
            doctype, docname, "_user_tags", new_tags_str, 
            update_modified=False
        )
        
        # Update Tag Link table for each new tag
        for tag_info in tags_to_apply:
            tag = tag_info["tag"]
            
            # Check if link already exists
            link_exists = frappe.db.exists("Tag Link", {
                "tag": tag,
                "document_type": doctype,
                "document_name": docname
            })
            
            if not link_exists:
                frappe.get_doc({
                    "doctype": "Tag Link",
                    "tag": tag,
                    "document_type": doctype,
                    "document_name": docname,
                    "title": docname
                }).insert(ignore_permissions=True)
                frappe.db.commit()
    
    
    def _get_total_records(self, doctype: str, filters: Optional[Dict] = None) -> int:
        """
        Get total number of records to process
        """
        return frappe.db.count(doctype, filters=json.loads(filters) or {})
    
    
    def _get_batch_records(self, doctype: str, filters: Optional[Dict], 
                          limit: int, offset: int) -> List[str]:
        """
        Get a batch of record names using memory-efficient query
        """
        return frappe.get_all(
            doctype,
            filters=filters or {},
            pluck='name',
            limit=limit,
            start=offset,
            order_by='creation asc'  # Consistent ordering
        )
    
    
    def _create_execution_log(self, script_config, execution_id: str):
        """
        Create execution log document
        """
        log = frappe.get_doc({
            "doctype": "Tag Execution Log",
            "script_manager": script_config.name,
            "execution_id": execution_id,
            "status": "Queued",
            "total_records": 0,
            "records_processed": 0,
            "records_failed": 0,
            "current_batch": 0,
            "progress_percent": 0
        })
        log.insert(ignore_permissions=True)
        frappe.db.commit()
        return log
    
    def cancel_execution(execution_id: str):
        """
        Cancel a running execution
        """
        execution_log = frappe.get_doc("Tag Execution Log", 
                                      {"execution_id": execution_id})
        execution_log.status = "Cancelled"
        execution_log.end_time = now_datetime()
        execution_log.save(ignore_permissions=True)
        frappe.db.commit()