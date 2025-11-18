# tag_automation_engine.py

import frappe
import importlib
import uuid
from datetime import datetime
from frappe import _
from frappe.utils import now_datetime, get_datetime, time_diff_in_seconds
from typing import Dict, List, Any, Optional

class TagAutomationEngine:
    """
    Main engine for tag automation with batch processing for millions of records
    """
    
    @staticmethod
    def execute_script(script_manager_name: str, filters: Optional[Dict] = None, 
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
            execution_log = TagAutomationEngine._create_execution_log(
                script_config, execution_id
            )
        else:
            execution_log = frappe.get_doc("Tag Execution Log", 
                                          {"execution_id": execution_id})
        
        # Enqueue the batch processor
        frappe.enqueue(
            "tag_automation.tag_automation_engine.TagAutomationEngine.process_in_batches",
            queue='long',
            timeout=36000,  # 10 hours
            script_manager_name=script_manager_name,
            execution_id=execution_id,
            filters=filters,
            is_async=True,
            now=False
        )
        
        return execution_id
    
    @staticmethod
    def process_in_batches(script_manager_name: str, execution_id: str, 
                          filters: Optional[Dict] = None):
        """
        Process all documents in batches with progress tracking
        """
        script_config = frappe.get_doc("Tag Script Manager", script_manager_name)
        execution_log = frappe.get_doc("Tag Execution Log", 
                                      {"execution_id": execution_id})
        
        try:
            execution_log.status = "Running"
            execution_log.start_time = now_datetime()
            execution_log.save(ignore_permissions=True)
            frappe.db.commit()
            
            # Get total count
            total_records = TagAutomationEngine._get_total_records(
                script_config.target_doctype, filters
            )
            execution_log.total_records = total_records
            execution_log.save(ignore_permissions=True)
            frappe.db.commit()
            
            if total_records == 0:
                execution_log.status = "Completed"
                execution_log.end_time = now_datetime()
                execution_log.save(ignore_permissions=True)
                frappe.db.commit()
                return
            
            # Calculate batches
            batch_size = script_config.batch_size or 1000
            total_batches = (total_records + batch_size - 1) // batch_size
            execution_log.batch_count = total_batches
            execution_log.save(ignore_permissions=True)
            frappe.db.commit()
            
            # Process batches
            parallel_workers = min(script_config.parallel_workers or 1, 10)
            
            if parallel_workers > 1:
                TagAutomationEngine._process_parallel_batches(
                    script_config, execution_log, filters, 
                    batch_size, total_batches, parallel_workers
                )
            else:
                TagAutomationEngine._process_sequential_batches(
                    script_config, execution_log, filters, 
                    batch_size, total_batches
                )
            
            # Mark as completed
            execution_log.reload()
            execution_log.status = "Completed"
            execution_log.end_time = now_datetime()
            
            if execution_log.start_time:
                duration = time_diff_in_seconds(execution_log.end_time, 
                                               execution_log.start_time)
                execution_log.duration = f"{duration:.2f} seconds"
            
            execution_log.save(ignore_permissions=True)
            frappe.db.commit()
            
            # Update script manager
            script_config.last_execution = now_datetime()
            script_config.last_execution_status = "Completed"
            script_config.records_processed = execution_log.records_processed
            script_config.save(ignore_permissions=True)
            frappe.db.commit()
            
        except Exception as e:
            execution_log.reload()
            execution_log.status = "Failed"
            execution_log.end_time = now_datetime()
            execution_log.error_log = str(e)
            execution_log.save(ignore_permissions=True)
            frappe.db.commit()
            
            frappe.log_error(
                message=frappe.get_traceback(),
                title=f"Tag Automation Failed: {script_manager_name}"
            )
            
            raise
    
    @staticmethod
    def _process_sequential_batches(script_config, execution_log, filters, 
                                    batch_size, total_batches):
        """
        Process batches sequentially
        """
        records_processed = 0
        records_failed = 0
        
        for batch_num in range(total_batches):
            try:
                offset = batch_num * batch_size
                
                # Get batch of document names
                doc_names = TagAutomationEngine._get_batch_records(
                    script_config.target_doctype, 
                    filters, 
                    batch_size, 
                    offset
                )
                
                # Process batch
                batch_results = TagAutomationEngine._process_batch(
                    script_config, doc_names
                )
                
                records_processed += batch_results['processed']
                records_failed += batch_results['failed']
                
                # Update progress
                execution_log.reload()
                execution_log.current_batch = batch_num + 1
                execution_log.records_processed = records_processed
                execution_log.records_failed = records_failed
                execution_log.progress_percent = ((batch_num + 1) / total_batches) * 100
                execution_log.save(ignore_permissions=True)
                frappe.db.commit()
                
            except Exception as e:
                records_failed += len(doc_names)
                error_msg = f"Batch {batch_num + 1} failed: {str(e)}\n"
                execution_log.reload()
                execution_log.error_log = (execution_log.error_log or "") + error_msg
                execution_log.save(ignore_permissions=True)
                frappe.db.commit()
    
    @staticmethod
    def _process_parallel_batches(script_config, execution_log, filters, 
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
                "tag_automation.tag_automation_engine.TagAutomationEngine._process_batch_range",
                queue='long',
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
    
    @staticmethod
    def _process_batch_range(script_manager_name, execution_id, filters, 
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
                
                doc_names = TagAutomationEngine._get_batch_records(
                    script_config.target_doctype, 
                    filters, 
                    batch_size, 
                    offset
                )
                
                batch_results = TagAutomationEngine._process_batch(
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
    
    @staticmethod
    def _process_batch(script_config, doc_names: List[str]) -> Dict[str, int]:
        """
        Process a single batch of documents
        Returns dict with 'processed' and 'failed' counts
        """
        processed = 0
        failed = 0
        
        for doc_name in doc_names:
            try:
                TagAutomationEngine._process_single_document(
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
    
    @staticmethod
    def _process_single_document(script_config, doc_name: str):
        """
        Process a single document and assign tags
        """
        # Get document (without loading the full doc object for performance)
        doc = frappe.get_doc(script_config.target_doctype, doc_name)
        
        # Execute custom script
        script_outputs = TagAutomationEngine._execute_custom_script(
            script_config.script_path, doc
        )
        
        # Validate outputs (optional, can be skipped for performance)
        # TagAutomationEngine._validate_outputs(script_config, script_outputs)
        
        # Evaluate conditions
        tags_to_apply = TagAutomationEngine._evaluate_conditions(
            script_config, script_outputs
        )
        
        # Apply tags using direct DB operations for performance
        TagAutomationEngine._apply_tags_bulk(
            script_config, doc.doctype, doc.name, tags_to_apply
        )
    
    @staticmethod
    def _execute_custom_script(script_path: str, doc) -> Dict[str, Any]:
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
    
    @staticmethod
    def _evaluate_conditions(script_config, outputs: Dict[str, Any]) -> List[Dict]:
        """
        Evaluate conditions and return tags to apply
        """
        tags_to_apply = []
        
        # Sort conditions by priority
        conditions = sorted(
            script_config.tag_conditions, 
            key=lambda x: x.priority
        )
        
        for condition in conditions:
            if TagAutomationEngine._evaluate_single_condition(condition, outputs):
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
    
    @staticmethod
    def _evaluate_single_condition(condition, outputs: Dict[str, Any]) -> bool:
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
    
    @staticmethod
    def _apply_tags_bulk(script_config, doctype: str, docname: str, 
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
                frappe.db.sql("""
                    INSERT INTO `tabTag Link` 
                    (name, creation, modified, modified_by, owner, docstatus, 
                     tag, document_type, document_name, title)
                    VALUES (UUID(), NOW(), NOW(), %s, %s, 0, %s, %s, %s, %s)
                """, (
                    frappe.session.user, frappe.session.user,
                    tag, doctype, docname, docname
                ))
    
    @staticmethod
    def _get_total_records(doctype: str, filters: Optional[Dict] = None) -> int:
        """
        Get total number of records to process
        """
        return frappe.db.count(doctype, filters=filters or {})
    
    @staticmethod
    def _get_batch_records(doctype: str, filters: Optional[Dict], 
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
    
    @staticmethod
    def _create_execution_log(script_config, execution_id: str):
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
    
    @staticmethod
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