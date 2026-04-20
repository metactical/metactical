"""
Bulk Update Rule controller.

Handles building dynamic filters from conditions, previewing matched items,
and executing bulk updates as a background job.

KEY DESIGN NOTE:
  - price_list_rate and standard_rate live on Item Price, NOT Item.
  - Whenever these fields appear in conditions or actions, we query/update
    Item Price filtered by  price_list = 'RET - Camo'.
  - All other fields are treated as Item fields.
"""

import json
import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime, cstr, flt, cint


# ─── Constants ────────────────────────────────────────────────────────
PRICE_LIST = "RET - Camo"

# Fields that actually live on Item Price, not Item
ITEM_PRICE_FIELDS = {"price_list_rate", "standard_rate"}

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
    """Return the actual fieldname, handling the custom_field case."""
    if field_name == "custom_field":
        return (custom_field_name or "").strip()
    return field_name


def _is_price_field(fieldname):
    """True if this field lives on Item Price."""
    return fieldname in ITEM_PRICE_FIELDS


class BulkUpdateRule(Document):
    """DocType controller for Bulk Update Rule."""

    def validate(self):
        if not self.conditions:
            frappe.throw("At least one search condition is required.")
        if not self.actions:
            frappe.throw("At least one action is required.")
        self._validate_actions()

    def _validate_actions(self):
        for action in self.actions:
            if action.action_type == "Set To Formula":
                allowed = set("abcdefghijklmnopqrstuvwxyz_0123456789.+-*/() ")
                if not set(action.action_value.lower()).issubset(allowed):
                    frappe.throw(
                        f"Action row {action.idx}: formula contains invalid characters."
                    )

    # ──────────────────────────────────────────────────────────────────
    #  Helpers: classify conditions / actions into Item vs Item Price
    # ──────────────────────────────────────────────────────────────────

    def _classify_conditions(self):
        """Split conditions into Item conditions and Item Price conditions."""
        item_conds = []
        price_conds = []
        for c in self.conditions:
            fn = _resolve_field(c.field_name, c.custom_field_name)
            if _is_price_field(fn):
                price_conds.append(c)
            else:
                item_conds.append(c)
        return item_conds, price_conds

    def _classify_action_fields(self):
        """Return sets of (item_fields, price_fields) targeted by actions."""
        item_fields = set()
        price_fields = set()
        for a in self.actions:
            fn = _resolve_field(a.target_field, a.custom_target_field)
            if _is_price_field(fn):
                price_fields.add(fn)
            else:
                item_fields.add(fn)
        return item_fields, price_fields

    # ──────────────────────────────────────────────────────────────────
    #  Build WHERE clause fragment from a condition row
    # ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _condition_to_sql(cond, table_alias):
        """
        Return (sql_fragment, params_list) for one condition row.
        table_alias is 'i' for Item or 'ip' for Item Price.
        """
        fn = _resolve_field(cond.field_name, cond.custom_field_name)
        op = cond.operator
        val = cond.value or ""
        sql_op = OPERATOR_MAP.get(op, "=")

        col = f"`{table_alias}`.`{fn}`"

        if op == "Is Set":
            return f"({col} IS NOT NULL AND {col} != '')", []
        if op == "Is Not Set":
            return f"({col} IS NULL OR {col} = '')", []

        if op == "Begins With":
            return f"{col} LIKE %s", [f"{val}%"]
        if op == "Ends With":
            return f"{col} LIKE %s", [f"%{val}"]
        if op in ("Contains",):
            return f"{col} LIKE %s", [f"%{val}%"]
        if op == "Does Not Contain":
            return f"{col} NOT LIKE %s", [f"%{val}%"]

        if op in ("In", "Not In"):
            vals = [v.strip() for v in val.split(",") if v.strip()]
            if not vals:
                # No values → match nothing / everything
                return ("1=0" if op == "In" else "1=1"), []
            placeholders = ", ".join(["%s"] * len(vals))
            kw = "IN" if op == "In" else "NOT IN"
            return f"{col} {kw} ({placeholders})", vals

        # Numeric comparisons – try to cast
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

    def get_matched_items(self, limit_page_length=10, start=0):
        """
        Return items matching conditions across Item and Item Price.

        Always LEFT JOINs Item Price (price_list = PRICE_LIST) so that
        price_list_rate / standard_rate are available for conditions,
        preview, and actions.
        """
        item_conds, price_conds = self._classify_conditions()
        _, price_action_fields = self._classify_action_fields()

        # Determine if we need Item Price at all
        needs_price = bool(price_conds) or bool(price_action_fields)

        # Also check if any formula references a price field
        for a in self.actions:
            if a.action_type in ("Set To Formula", "Multiply By",
                                  "Add Value", "Subtract Value",
                                  "Set To Field Value"):
                for token in self._tokenize_formula(a.action_value):
                    if _is_price_field(token):
                        needs_price = True

        # ── SELECT columns ──
        select_cols = [
            "`i`.`name` AS `name`",
            "`i`.`item_code` AS `item_code`",
            "`i`.`item_name` AS `item_name`",
            "`i`.`item_group` AS `item_group`",
        ]

        # Add Item-level action target fields
        extra_item_fields = set()
        for a in self.actions:
            fn = _resolve_field(a.target_field, a.custom_target_field)
            if not _is_price_field(fn) and fn not in ("name", "item_code", "item_name", "item_group"):
                extra_item_fields.add(fn)
            # Also add formula source fields
            if a.action_type in ("Set To Formula", "Multiply By",
                                  "Add Value", "Subtract Value",
                                  "Set To Field Value"):
                for token in self._tokenize_formula(a.action_value):
                    if not _is_price_field(token) and token not in ("name", "item_code", "item_name", "item_group"):
                        extra_item_fields.add(token)

        # Add condition fields that are Item-level (for display)
        for c in self.conditions:
            fn = _resolve_field(c.field_name, c.custom_field_name)
            if not _is_price_field(fn) and fn not in ("name", "item_code", "item_name", "item_group"):
                extra_item_fields.add(fn)

        for f in extra_item_fields:
            select_cols.append(f"`i`.`{f}` AS `{f}`")

        if needs_price:
            select_cols.append(f"`ip`.`price_list_rate` AS `price_list_rate`")
            select_cols.append(f"`ip`.`name` AS `item_price_name`")
            # standard_rate is not a standard Item Price field in ERPNext v15;
            # it may be price_list_rate or a custom field. Include if it exists:
            try:
                meta = frappe.get_meta("Item Price")
                if meta.has_field("standard_rate"):
                    select_cols.append(f"`ip`.`standard_rate` AS `standard_rate`")
            except Exception:
                pass
            
        print(f"SELECT columns: {select_cols}")
        print(f"Needs price join: {needs_price}")
        print(f"Item conditions: {len(item_conds)}, Price conditions: {len(price_conds)}")

        select_sql = ", ".join(select_cols)

        # ── FROM + JOIN ──
        from_sql = "`tabItem` AS `i`"
        if needs_price:
            from_sql += f"""
                LEFT JOIN `tabItem Price` AS `ip`
                    ON `ip`.`item_code` = `i`.`item_code`
                    AND `ip`.`price_list` = %s
            """

        # ── WHERE ──
        where_parts = []
        params = []

        if needs_price:
            params.append(PRICE_LIST)

        for c in item_conds:
            frag, p = self._condition_to_sql(c, "i")
            where_parts.append(frag)
            params.extend(p)

        for c in price_conds:
            frag, p = self._condition_to_sql(c, "ip")
            where_parts.append(frag)
            params.extend(p)

        where_sql = " AND ".join(where_parts) if where_parts else "1=1"

        # ── COUNT ──
        count_query = f"SELECT COUNT(*) AS cnt FROM {from_sql} WHERE {where_sql}"
        total = frappe.db.sql(count_query, params, as_dict=True)[0].cnt

        # ── DATA ──
        limit_clause = ""
        data_params = list(params)
        if limit_page_length:
            limit_clause = "LIMIT %s OFFSET %s"
            data_params.extend([cint(limit_page_length), cint(start)])

        data_query = f"""
            SELECT {select_sql}
            FROM {from_sql}
            WHERE {where_sql}
            ORDER BY `i`.`modified` DESC
            {limit_clause}
        """
        items = frappe.db.sql(data_query, data_params, as_dict=True)

        return {"items": items, "total": total}

    @staticmethod
    def _tokenize_formula(formula):
        """Extract alphanumeric tokens (potential field names) from a formula string."""
        tokens = []
        for token in formula.replace("*", " ").replace("+", " ").replace(
            "-", " ").replace("/", " ").replace("(", " ").replace(")", " ").split():
            cleaned = token.strip()
            if cleaned and cleaned.replace("_", "").replace(".", "").isalpha():
                tokens.append(cleaned)
        return tokens

    # ──────────────────────────────────────────────────────────────────
    #  Preview: compute before/after for each matched item
    # ──────────────────────────────────────────────────────────────────

    def compute_preview(self, items):
        preview = []
        for item in items:
            row = {"name": item.get("name") or item.get("item_code")}
            for action in self.actions:
                target = _resolve_field(action.target_field, action.custom_target_field)
                before_val = item.get(target)
                after_val = self._compute_action_value(action, item)
                row[f"{target}_before"] = before_val
                row[f"{target}_after"] = after_val
            preview.append(row)
        return preview

    def _compute_action_value(self, action, item):
        atype = action.action_type
        aval = action.action_value
        target = _resolve_field(action.target_field, action.custom_target_field)

        if atype == "Set To Value":
            return self._cast_value(aval)

        if atype == "Set To Field Value":
            return item.get(aval.strip())

        if atype == "Multiply By":
            return flt(item.get(target)) * flt(aval)

        if atype == "Add Value":
            return flt(item.get(target)) + flt(aval)

        if atype == "Subtract Value":
            return flt(item.get(target)) - flt(aval)

        if atype == "Set To Formula":
            return self._eval_formula(aval, item)

        return None

    @staticmethod
    def _eval_formula(formula, item):
        ns = {}
        for key, val in item.items():
            try:
                ns[key] = flt(val)
            except Exception:
                ns[key] = 0
        try:
            code = compile(formula, "<formula>", "eval")
            allowed = {
                "__builtins__": {},
                "abs": abs, "round": round, "min": min, "max": max,
                "int": int, "float": float,
            }
            allowed.update(ns)
            return eval(code, allowed)
        except Exception as e:
            frappe.log_error(f"Formula evaluation error: {e}", "Bulk Update Rule")
            return None

    @staticmethod
    def _cast_value(val):
        if val is None:
            return None
        val = val.strip()
        if val.lower() in ("true", "1", "yes"):
            return 1
        if val.lower() in ("false", "0", "no"):
            return 0
        try:
            return flt(val) if "." in val else cint(val)
        except Exception:
            return val


# ═══════════════════════════════════════════════════════════════════════
#  Background execution
# ═══════════════════════════════════════════════════════════════════════

def run_bulk_update(rule_name):
    """
    Background job: fetch all matching items and apply actions.

    For Item fields  → update the Item doc.
    For price fields → update the Item Price doc (price_list = PRICE_LIST).
    """
    doc = frappe.get_doc("Bulk Update Rule", rule_name)
    doc.db_set("execution_status", "Running")
    frappe.db.commit()

    updated = 0
    errors = []

    try:
        result = doc.get_matched_items(limit_page_length=0)
        print(f"Total matched items: {result['total']}")
        total = result["total"]
        items = result["items"]

        frappe.publish_realtime(
            "bulk_update_progress",
            {"rule_name": rule_name, "total": total, "current": 0, "status": "Running"},
            user=frappe.session.user,
        )

        _, price_action_fields = doc._classify_action_fields()
        item_action_fields_set, _ = doc._classify_action_fields()

        for i, item in enumerate(items):
            try:
                item_changed = False
                price_changed = False

                # ── Collect new values ──
                item_updates = {}
                price_updates = {}

                for action in doc.actions:
                    target = _resolve_field(action.target_field, action.custom_target_field)
                    new_val = doc._compute_action_value(action, item)
                    if new_val is None:
                        continue

                    if _is_price_field(target):
                        price_updates[target] = new_val
                    else:
                        item_updates[target] = new_val

                # ── Apply Item updates ──
                if item_updates:
                    item_doc = frappe.get_doc("Item", item["name"])
                    for field, val in item_updates.items():
                        if item_doc.get(field) != val:
                            item_doc.set(field, val)
                            item_changed = True
                    if item_changed:
                        item_doc.flags.ignore_validate_update_after_submit = True
                        item_doc.save(ignore_permissions=True)

                # ── Apply Item Price updates ──
                if price_updates and item.get("item_price_name"):
                    price_doc = frappe.get_doc("Item Price", item["item_price_name"])
                    for field, val in price_updates.items():
                        if price_doc.get(field) != val:
                            price_doc.set(field, val)
                            price_changed = True
                    if price_changed:
                        price_doc.flags.ignore_validate_update_after_submit = True
                        price_doc.save(ignore_permissions=True)

                if item_changed or price_changed:
                    updated += 1

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

        doc.reload()
        doc.db_set({
            "execution_status": "Completed",
            "last_executed_on": now_datetime(),
            "last_executed_by": frappe.session.user,
            "last_match_count": total,
            "execution_log": "\n".join(log_lines),
        })
        frappe.db.commit()

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
    columns = []
    for action in doc.actions:
        columns.append(_resolve_field(action.target_field, action.custom_target_field))
    result["action_columns"] = columns
    return result


@frappe.whitelist()
def execute_rule(rule_name):
    doc = frappe.get_doc("Bulk Update Rule", rule_name)
    doc.db_set("execution_status", "Queued")

    # job = frappe.enqueue(
    #     "metactical.metactical.doctype.bulk_update_rule.bulk_update_rule.run_bulk_update",
    #     queue="long",
    #     timeout=3600,
    #     rule_name=rule_name,
    #     now=False,
    # )
    
    run_bulk_update(rule_name)
    # return {"status": "queued", "job_id": job.id if job else None}


@frappe.whitelist()
def export_preview(rule_name):
    import csv
    import io

    doc = frappe.get_doc("Bulk Update Rule", rule_name)
    result = doc.get_matched_items(limit_page_length=0)
    preview = doc.compute_preview(result["items"])
    columns = []
    for action in doc.actions:
        columns.append(_resolve_field(action.target_field, action.custom_target_field))

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

    columns = []
    for action in doc.actions:
        columns.append(_resolve_field(action.target_field, action.custom_target_field))
    result["action_columns"] = columns
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
                "target_field": a.target_field,
                "custom_target_field": a.custom_target_field or "",
                "action_type": a.action_type,
                "action_value": a.action_value,
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