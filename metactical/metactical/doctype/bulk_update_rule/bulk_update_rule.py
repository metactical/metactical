"""
Bulk Update Rule controller.

KEY DESIGN:
  - price_list_rate and standard_rate live on Item Price, NOT Item.
  - They always filter/update via price_list = 'RET - Camo'.
  - Actions use a message-type pattern: action_type (e.g. UpdatePrice) + action_value.
  - ACTION_TYPE_MAP maps each type to (doc_source, fieldname).
"""

import json
import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime, cstr, flt, cint
from frappe.desk.doctype.tag.tag import DocTags

# ─── Constants ────────────────────────────────────────────────────────
PRICE_LIST = "RET - Camo"

# Fields that live on Item Price
ITEM_PRICE_FIELDS = {"price_list_rate", "standard_rate"}

# Item Default fields
ITEM_DEFAULT_FIELDS = {"default_supplier"}

#Item Supplier fields
ITEM_SUPPLIER_FIELDS = {"supplier"}

# action_type → (doc_source, fieldname)
#   doc_source: "item" = tabItem, "price" = tabItem Price
ACTION_TYPE_MAP = {
    "UpdateItemGroup":       ("item",  "item_group"),
    "AddTag":                ("item",  "_user_tags"),
    "RemoveTag":             ("item",  "_user_tags"),
    "UpdateUOM":             ("item",  "stock_uom"),
    "DisableItem":           ("item",  "disabled"),
    "EnableItem":            ("item",  "disabled"),
    "UpdateValuationRate":   ("item",  "valuation_rate"),
    "UpdateDescription":     ("item",  "description"),
    "UpdateBrand":           ("item",  "brand"),
    "UpdateLastPingedOn":    ("item",  "last_pinged_on"),
}

OPERATOR_MAP = {
    "Equals To":              "=",
    "Not Equal To":           "!=",
    "Begins With":            "like",
    "Ends With":              "like",
    "Contains":               "like",
    "Does Not Contain":       "not like",
    "Greater Than":           ">",
    "Less Than":              "<",
    "Greater Than Or Equal":  ">=",
    "Less Than Or Equal":     "<=",
    "In":                     "in",
    "Not In":                 "not in",
    "Is Set":                 "is",
    "Is Not Set":             "is",
}


def _resolve_field(field_name, custom_field_name=None):
    if field_name == "custom_field":
        return (custom_field_name or "").strip()
    return field_name


def _is_price_field(fieldname):
    return fieldname in ITEM_PRICE_FIELDS

def _is_item_default_field(fieldname):
    return fieldname in ITEM_DEFAULT_FIELDS

def _is_item_supplier_field(fieldname):
    return fieldname in ITEM_SUPPLIER_FIELDS

class BulkUpdateRule(Document):

    def validate(self):
        if not self.conditions:
            frappe.throw("At least one search condition is required.")
        if not self.actions:
            frappe.throw("At least one action is required.")
            
    # ──────────────────────────────────────────────────────────────────
    #  Classify conditions / actions
    # ──────────────────────────────────────────────────────────────────

    def _classify_conditions(self):
        item_conds = []
        price_conds = []
        item_default_conds = []
        item_supplier_conds = []
        inventory_conds = []
        variant_inventory_conds = []       # ← ADD THIS

        for c in self.conditions:
            fn = _resolve_field(c.field_name, c.custom_field_name)
            if _is_price_field(fn):
                price_conds.append(c)
            elif _is_item_default_field(fn):
                item_default_conds.append(c)
            elif _is_item_supplier_field(fn):
                item_supplier_conds.append(c)
            elif fn == "has_inventory":
                inventory_conds.append(c)
            elif fn == "variants_have_no_inventory":    # ← ADD THIS
                variant_inventory_conds.append(c)       # ← ADD THIS
            else:
                item_conds.append(c)

        return item_conds, price_conds, item_default_conds, item_supplier_conds, inventory_conds, variant_inventory_conds

    def _classify_action_fields(self):
        item_fields = set()
        price_fields = set()
        for a in self.actions:
            mapping = ACTION_TYPE_MAP.get(a.action_type)
            if not mapping:
                continue
            doc_type, fieldname = mapping
            if doc_type == "price" and fieldname:
                price_fields.add(fieldname)
            elif fieldname:
                item_fields.add(fieldname)
        return item_fields, price_fields

    # ──────────────────────────────────────────────────────────────────
    #  SQL condition builder
    # ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _condition_to_sql(cond, table_alias):
        fn = _resolve_field(cond.field_name, cond.custom_field_name)
        op = cond.operator
        val = cond.value or ""

        col = f"`{table_alias}`.`{fn}`"

        if op == "Is Set":
            return f"({col} IS NOT NULL AND {col} != '')", []
        if op == "Is Not Set":
            return f"({col} IS NULL OR {col} = '')", []
        if op == "Begins With":
            return f"{col} LIKE %s", [f"{val}%"]
        if op == "Ends With":
            return f"{col} LIKE %s", [f"%{val}"]
        if op == "Contains":
            return f"{col} LIKE %s", [f"%{val}%"]
        if op == "Does Not Contain":
            return f"{col} NOT LIKE %s", [f"%{val}%"]
        if op in ("In", "Not In"):
            vals = [v.strip() for v in val.split(",") if v.strip()]
            if not vals:
                return ("1=0" if op == "In" else "1=1"), []
            placeholders = ", ".join(["%s"] * len(vals))
            kw = "IN" if op == "In" else "NOT IN"
            return f"{col} {kw} ({placeholders})", vals


        sql_op = OPERATOR_MAP.get(op, "=")
        if op in ("Greater Than", "Less Than",
                  "Greater Than Or Equal", "Less Than Or Equal"):
            try:
                val = flt(val)
            except Exception:
                pass

        return f"{col} {sql_op} %s", [val]

    # ──────────────────────────────────────────────────────────────────
    #  Main query: Item LEFT JOIN Item Price
    # ──────────────────────────────────────────────────────────────────

    def get_matched_items(self, limit_page_length=10, start=0, for_update=False):
        item_conds, price_conds, item_default_conds, item_supplier_conds, inventory_conds, variant_inventory_conds = self._classify_conditions()
        item_action_fields, price_action_fields = self._classify_action_fields()

        needs_price = bool(price_conds) or bool(price_action_fields)
        needs_item_default = bool(item_default_conds)
        needs_item_supplier = bool(item_supplier_conds)
        needs_inventory = bool(inventory_conds)

        # ── SELECT ──
        select_cols = [
            "`i`.`name` AS `name`",
            "`i`.`item_code` AS `item_code`",
            "`i`.`item_name` AS `item_name`",
            "`i`.`item_group` AS `item_group`",
        ]

        # Extra Item fields needed by actions
        extra_item = set()
        for a in self.actions:
            mapping = ACTION_TYPE_MAP.get(a.action_type)
            if not mapping:
                continue
            doc_type, fieldname = mapping
            if doc_type == "item" and fieldname and fieldname not in ("name", "item_code", "item_name", "item_group"):
                extra_item.add(fieldname)

        # Condition fields for display
        VIRTUAL_FIELDS = {"has_inventory", "supplier", "default_supplier", "variants_have_no_inventory"}
        for c in self.conditions:
            fn = _resolve_field(c.field_name, c.custom_field_name)
            if not _is_price_field(fn) and fn not in ("name", "item_code", "item_name", "item_group") and fn not in VIRTUAL_FIELDS:
                extra_item.add(fn)

        for f in extra_item:
            select_cols.append(f"`i`.`{f}` AS `{f}`")

        if needs_price:
            select_cols.append("`ip`.`price_list_rate` AS `price_list_rate`")
            select_cols.append("`ip`.`name` AS `item_price_name`")
            try:
                meta = frappe.get_meta("Item Price")
                if meta.has_field("standard_rate"):
                    select_cols.append("`ip`.`standard_rate` AS `standard_rate`")
            except Exception:
                pass
            
        if needs_item_default:
            select_cols.append("`id`.`default_supplier` AS `default_supplier`")
        
        if needs_item_supplier:
            select_cols.append("`isup`.`supplier` AS `supplier`")

        select_sql = ", ".join(select_cols)

        # ── FROM + JOIN ──
        from_sql = "`tabItem` AS `i`"
        params = []

        if needs_price:
            from_sql += """
                LEFT JOIN `tabItem Price` AS `ip`
                    ON `ip`.`item_code` = `i`.`item_code`
                    AND `ip`.`price_list` = %s
            """
            params.append(PRICE_LIST)

        if needs_item_default:
            from_sql += """
                LEFT JOIN `tabItem Default` AS `id`
                    ON `id`.`parent` = `i`.`name`
            """

        if needs_item_supplier:
            from_sql += """
                LEFT JOIN `tabItem Supplier` AS `isup`
                    ON `isup`.`parent` = `i`.`name`
            """

        # ── WHERE ──
        where_parts = []

        for c in item_conds:
            frag, p = self._condition_to_sql(c, "i")
            where_parts.append(frag)
            params.extend(p)

        for c in price_conds:
            frag, p = self._condition_to_sql(c, "ip")
            where_parts.append(frag)
            params.extend(p)

        for c in item_default_conds:
            frag, p = self._condition_to_sql(c, "id")
            where_parts.append(frag)
            params.extend(p)

        for c in item_supplier_conds:
            frag, p = self._condition_to_sql(c, "isup")
            where_parts.append(frag)
            params.extend(p)

        for c in inventory_conds:
            op = c.operator
            if op in ("Is Set", "Equals To") and (c.value or "").strip() in ("1", "yes", "true", "", "True"):
                where_parts.append(
                    "EXISTS (SELECT 1 FROM `tabBin` WHERE `tabBin`.`item_code` = `i`.`item_code` AND `tabBin`.`actual_qty` > 0)"
                )
            else:
                where_parts.append(
                    "NOT EXISTS (SELECT 1 FROM `tabBin` WHERE `tabBin`.`item_code` = `i`.`item_code` AND `tabBin`.`actual_qty` > 0)"
                )
                
        for c in variant_inventory_conds:
            where_parts.append("""
                (
                    `i`.`has_variants` = 1
                    AND NOT EXISTS (
                        SELECT 1
                        FROM `tabItem` AS `vi`
                        JOIN `tabBin` AS `vb` ON `vb`.`item_code` = `vi`.`item_code`
                        WHERE `vi`.`variant_of` = `i`.`name`
                        AND `vb`.`actual_qty` > 0
                    )
                )
            """)

        where_sql = " AND ".join(where_parts) if where_parts else "1=1"

        # ── COUNT ──
        count_query = f"SELECT COUNT(DISTINCT `i`.`name`) AS cnt FROM {from_sql} WHERE {where_sql}"
        total = frappe.db.sql(count_query, params, as_dict=True)[0].cnt
        if for_update:
            return total
        
        # ── DATA ──
        data_params = list(params)
        limit_clause = ""
        if limit_page_length:
            limit_clause = "LIMIT %s OFFSET %s"
            data_params.extend([cint(limit_page_length), cint(start)])

        data_query = f"""
            SELECT DISTINCT {select_sql}
            FROM {from_sql}
            WHERE {where_sql}
            ORDER BY `i`.`modified` DESC
            {limit_clause}
        """
        items = frappe.db.sql(data_query, data_params, as_dict=True)

        return {"items": items, "total": total}

    # ──────────────────────────────────────────────────────────────────
    #  Preview / action computation
    # ──────────────────────────────────────────────────────────────────

    def compute_preview(self, items):
        preview = []
        for item in items:
            row = {"name": item.get("name") or item.get("item_code")}
            for action in self.actions:
                mapping = ACTION_TYPE_MAP.get(action.action_type)
                if not mapping or not mapping[1]:
                    continue
                _, fieldname = mapping
                if fieldname == "_user_tags":
                    tag_val = (action.action_value or "").strip()
                    row[f"{action.action_type}_before"] = ""
                    row[f"{action.action_type}_after"] = tag_val
                    continue
                
                before_val = item.get(fieldname)
                after_val = self._compute_action_value(action, item)
                row[f"{fieldname}_before"] = before_val
                row[f"{fieldname}_after"] = after_val
            preview.append(row)
        return preview

    def _compute_action_value(self, action, item):
            atype = action.action_type
            aval = (action.action_value or "").strip()

            if atype == "DisableItem":
                return 1
            if atype == "EnableItem":
                return 0
            if atype == "UpdateLastPingedOn":
                return frappe.utils.today()

            if atype in ("AddTag", "RemoveTag"):
                return aval  # handled separately in run_bulk_update

            return self._cast_value(aval)

    @staticmethod
    def _cast_value(val):
        if val is None:
            return None
        val = val.strip()
        if not val:
            return val
        if val.lower() in ("true", "yes"):
            return 1
        if val.lower() in ("false", "no"):
            return 0
        # Only cast to number if it actually looks like a number
        try:
            float(val)
            return flt(val) if "." in val else cint(val)
        except ValueError:
            return val

    def _get_action_columns(self):
        columns = []
        for action in self.actions:
            mapping = ACTION_TYPE_MAP.get(action.action_type)
            if not mapping or not mapping[1]:
                continue
            if mapping[1] == "_user_tags":
                col = action.action_type  # "AddTag" or "RemoveTag"
                if col not in columns:
                    columns.append(col)
            elif mapping[1] not in columns:
                columns.append(mapping[1])
        return columns

# ═══════════════════════════════════════════════════════════════════════
#  Background execution
# ═══════════════════════════════════════════════════════════════════════

def run_bulk_update(rule_name):
    doc = frappe.get_doc("Bulk Update Rule", rule_name)
    doc.db_set("execution_status", "Running")
    frappe.db.commit()

    updated = 0
    errors = []
    updated_item_ids = []

    try:
        result = doc.get_matched_items(limit_page_length=0)
        total = result["total"]
        items = result["items"]

        _, price_action_fields = doc._classify_action_fields()

        for i, item in enumerate(items):
            try:
                item_updates = {}
                price_updates = {}
                tag_actions = []

                for action in doc.actions:
                    mapping = ACTION_TYPE_MAP.get(action.action_type)
                    if not mapping:
                        continue
                    doc_type, fieldname = mapping

                    if fieldname == "_user_tags":
                        tag_val = (action.action_value or "").strip()
                        if tag_val:
                            tag_actions.append((action.action_type, tag_val))
                        continue

                    if not fieldname:
                        continue
                    new_val = doc._compute_action_value(action, item)
                    if new_val is None:
                        continue

                    if doc_type == "price":
                        price_updates[fieldname] = new_val
                    else:
                        item_updates[fieldname] = new_val

                # Apply Item updates
                item_changed = False
                if item_updates:
                    dt = doc.target_doctype or "Item"
                    item_name = item["name"]
                    for field, val in item_updates.items():
                        current_val = frappe.db.get_value(dt, item_name, field)
                        if current_val != val:
                            frappe.db.set_value(dt, item_name, field, val)
                            item_changed = True

                # Apply Item Price updates
                price_changed = False
                if price_updates and item.get("item_price_name"):
                    price_doc = frappe.get_doc("Item Price", item["item_price_name"])
                    for field, val in price_updates.items():
                        if price_doc.get(field) != val:
                            price_doc.set(field, val)
                            price_changed = True
                    if price_changed:
                        price_doc.flags.ignore_validate_update_after_submit = True
                        price_doc.save(ignore_permissions=True)

                # Apply tag actions
                tag_changed = False
                item_name = item.get("name")
                dt = doc.target_doctype or "Item"
                
                # Replace the tag_actions block inside run_bulk_update:
                for tag_action, tag_val in tag_actions:
                    try:
                        existing_tags = frappe.db.get_list("Tag Link", filters={"document_name": item_name}, pluck="tag")
                        if tag_action == "AddTag":
                            if tag_val not in existing_tags:
                                existing_tags.append(tag_val)
                                frappe.get_doc({
                                    "doctype": "Tag Link",
                                    "document_type": dt,
                                    "document_name": item_name,
                                    "tag": tag_val,
                                }).insert(ignore_permissions=True)

                                frappe.db.set_value(dt, item_name, "_user_tags", ",".join(existing_tags))
                                tag_changed = True
                        elif tag_action == "RemoveTag":
                            if tag_val in existing_tags:
                                existing_tags.remove(tag_val)
                                frappe.db.set_value(dt, item_name, "_user_tags", ",".join(existing_tags))
                                frappe.db.delete("Tag Link", filters={"document_type": dt, "document_name": item_name, "tag": tag_val})
                            
                                tag_changed = True
                    except Exception:
                        frappe.throw(f"Error processing tag action '{tag_action}' for tag '{tag_val}' on item '{item_name}'")

                if item_changed or price_changed or tag_changed:
                    updated += 1
                updated_item_ids.append(item_name)

                if (i + 1) % 50 == 0:
                    frappe.db.commit()
                    frappe.publish_realtime(
                        "bulk_update_progress",
                        {"rule_name": rule_name, "total": total,
                         "current": i + 1, "status": "Running"},
                        user=frappe.session.user,
                    )

            except Exception as e:
                errors.append(f"{item.get('name', '?')}: {cstr(e)}")
                frappe.log_error(
                    f"Bulk Update error on {item.get('name', '?')}: {e}",
                    "Bulk Update Rule",
                )

        frappe.db.commit()

        log_lines = [f"Total matched: {total}", f"Updated: {updated}"]
        if errors:
            log_lines.append(f"Errors ({len(errors)}):")
            log_lines.extend(errors[:50])

        retail_skus = []
        if updated_item_ids:
            sku_map = {
                r.name: r.ifw_retailskusuffix
                for r in frappe.get_all(
                    "Item",
                    filters={"name": ["in", updated_item_ids]},
                    fields=["name", "ifw_retailskusuffix"],
                )
            }
            retail_skus = [sku_map.get(n) or "" for n in updated_item_ids]

        doc.reload()
        doc.execution_status = "Completed"
        doc.last_executed_on = now_datetime()
        doc.last_executed_by = frappe.session.user
        doc.last_match_count = total
        doc.execution_log = "\n".join(log_lines)
        doc.updated_items = ",".join(updated_item_ids)
        doc.updated_retail_skus = ",".join(retail_skus)
        doc.save(ignore_permissions=True)
        frappe.db.commit()

        # Single completion event — no progress event before this
        frappe.publish_realtime(
            "bulk_update_progress",
            {"rule_name": rule_name, "total": total, "current": total,
             "status": "Completed", "updated": updated, "errors": len(errors)},
            user=frappe.session.user,
        )

    except Exception as e:
        frappe.log_error(f"Bulk Update failed: {e}", "Bulk Update Rule")
        doc.reload()
        doc.db_set({
            "execution_status": "Failed",
            "execution_log": cstr(e),
        })
        frappe.db.commit()
        frappe.publish_realtime(
            "bulk_update_progress",
            {"rule_name": rule_name, "status": "Failed", "error": cstr(e)},
            user=frappe.session.user,
        )
        
# ═══════════════════════════════════════════════════════════════════════
#  Whitelisted API endpoints
# ═══════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def preview_rule(rule_name, limit=10, start=0):
    doc = frappe.get_doc("Bulk Update Rule", rule_name)
    result = doc.get_matched_items(limit_page_length=cint(limit), start=cint(start))
    result["preview"] = doc.compute_preview(result["items"])
    result["action_columns"] = doc._get_action_columns()
    return result


@frappe.whitelist()
def execute_rule(rule_name):
    doc = frappe.get_doc("Bulk Update Rule", rule_name)
    doc.db_set("execution_status", "Queued")
    job = frappe.enqueue(
        "metactical.metactical.doctype.bulk_update_rule.bulk_update_rule.run_bulk_update",
        queue="long",
        timeout=3600,
        rule_name=rule_name,
        now=False,
    )
    
    return {"status": "queued", "job_id": job.id if job else None}


@frappe.whitelist()
def export_preview(rule_name):
    import csv
    import io

    doc = frappe.get_doc("Bulk Update Rule", rule_name)
    result = doc.get_matched_items(limit_page_length=0)
    preview = doc.compute_preview(result["items"])
    columns = doc._get_action_columns()

    output = io.StringIO()
    writer = csv.writer(output)

    header = ["Item"]
    for col in columns:
        header += [f"{col} (Before)", f"{col} (After)"]
    writer.writerow(header)

    for row in preview:
        r = [row["name"]]
        for col in columns:
            r += [row.get(f"{col}_before", ""), row.get(f"{col}_after", "")]
        writer.writerow(r)

    content = output.getvalue()
    file_doc = frappe.get_doc({
        "doctype": "File",
        "file_name": f"bulk_update_preview_{rule_name}.csv",
        "content": content,
        "is_private": 1,
    })
    file_doc.save(ignore_permissions=True)
    frappe.db.commit()
    return {"file_url": file_doc.file_url}


@frappe.whitelist()
def preview_from_data(conditions, actions, target_doctype="Item", limit=20, start=0):
    if isinstance(conditions, str):
        conditions = json.loads(conditions)
    if isinstance(actions, str):
        actions = json.loads(actions)

    doc = frappe.get_doc({
        "doctype": "Bulk Update Rule",
        "rule_name": "__preview_temp__",
        "target_doctype": target_doctype,
        "conditions": conditions,
        "actions": actions,
    })

    result = doc.get_matched_items(limit_page_length=cint(limit), start=cint(start))
    result["preview"] = doc.compute_preview(result["items"])
    result["action_columns"] = doc._get_action_columns()

    # ── Fetch max allowed and attach to result so JS can react ──
    max_allowed = frappe.db.get_single_value("Metactical Settings", "max_number_of_items_to_bulk_update")
    result["max_allowed"] = cint(max_allowed) if max_allowed else 0

    return result

@frappe.whitelist()
def save_rule_from_page(rule_name, conditions, actions, target_doctype="Item",
                        description="", existing_rule=None):
    if isinstance(conditions, str):
        conditions = json.loads(conditions)
    if isinstance(actions, str):
        actions = json.loads(actions)

    if existing_rule and frappe.db.exists("Bulk Update Rule", existing_rule):
        doc = frappe.get_doc("Bulk Update Rule", existing_rule)
        doc.rule_name = rule_name
        doc.description = description
        doc.target_doctype = target_doctype
        doc.conditions = []
        doc.actions = []
        for c in conditions:
            doc.append("conditions", c)
        for a in actions:
            doc.append("actions", a)
        doc.save()
    else:
        doc = frappe.get_doc({
            "doctype": "Bulk Update Rule",
            "rule_name": rule_name,
            "description": description,
            "target_doctype": target_doctype,
            "conditions": conditions,
            "actions": actions,
        })
        doc.insert()

    # ── Check max BEFORE committing ──
    max_allowed = frappe.db.get_single_value("Metactical Settings", "max_number_of_items_to_bulk_update")
    if max_allowed:
        total_matched = doc.get_matched_items(limit_page_length=0, for_update=True)
        if total_matched > cint(max_allowed):
            frappe.db.rollback()
            frappe.throw(
                f"This rule matches <b>{total_matched:,}</b> items, which exceeds the maximum "
                f"of <b>{cint(max_allowed):,}</b>. Please refine your search conditions.",
                title="Too Many Items"
            )

    frappe.db.commit()
    return {"name": doc.name, "rule_name": doc.rule_name}

@frappe.whitelist()
def load_rule_data(rule_name):
    doc = frappe.get_doc("Bulk Update Rule", rule_name)
    return {
        "name": doc.name,
        "rule_name": doc.rule_name,
        "description": doc.description or "",
        "target_doctype": doc.target_doctype,
        "conditions": [
            {
                "logic_operator": c.logic_operator,
                "field_name": c.field_name,
                "custom_field_name": c.custom_field_name or "",
                "operator": c.operator,
                "value": c.value or "",
            }
            for c in doc.conditions
        ],
        "actions": [
            {
                "action_type": a.action_type,
                "action_value": a.action_value or "",
            }
            for a in doc.actions
        ],
        "execution_status": doc.execution_status,
        "last_executed_on": doc.last_executed_on,
        "last_match_count": doc.last_match_count,
    }


@frappe.whitelist()
def get_recent_rules(limit=10):
    return frappe.get_all(
        "Bulk Update Rule",
        fields=["name", "rule_name", "description", "execution_status",
                "last_executed_on", "last_match_count", "modified"],
        order_by="modified desc",
        limit_page_length=cint(limit),
    )


@frappe.whitelist()
def get_doctype_fields(doctype="Item"):
    meta = frappe.get_meta(doctype)
    fields = []
    for df in meta.fields:
        if df.fieldtype in (
            "Data", "Int", "Float", "Currency", "Select", "Link",
            "Check", "Small Text", "Long Text", "Text", "Percent",
        ):
            fields.append({
                "fieldname": df.fieldname,
                "label": df.label,
                "fieldtype": df.fieldtype,
                "options": df.options,
            })
    return fields


@frappe.whitelist()
def get_action_link_map():
    """Return a map of action_type -> Link DocType for the JS to render Link fields."""
    return {
        "UpdateItemGroup": "Item Group",
        "UpdateBrand": "Brand",
        "UpdateUOM": "UOM",
        "UpdateDefaultWarehouse": "Warehouse",
        "AddTag": "Tag",
        "RemoveTag": "Tag",
    }