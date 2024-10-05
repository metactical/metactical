(() => {
  // ../erpnext/erpnext/public/js/conf.js
  frappe.provide("erpnext");
  $.extend(frappe.breadcrumbs.preferred, {
    "Item Group": "Stock",
    "Customer Group": "Selling",
    "Supplier Group": "Buying",
    Territory: "Selling",
    "Sales Person": "Selling",
    "Sales Partner": "Selling",
    Brand: "Stock",
    "Maintenance Schedule": "Support",
    "Maintenance Visit": "Support"
  });
  $.extend(frappe.breadcrumbs.module_map, {
    "ERPNext Integrations": "Integrations",
    Geo: "Settings",
    Portal: "Website",
    Utilities: "Settings",
    "E-commerce": "Website",
    Contacts: "CRM"
  });

  // ../erpnext/erpnext/public/js/utils.js
  frappe.provide("erpnext");
  frappe.provide("erpnext.utils");
  frappe.provide("erpnext.stock.utils");
  $.extend(erpnext, {
    get_currency: function(company) {
      if (!company && cur_frm)
        company = cur_frm.doc.company;
      if (company)
        return frappe.get_doc(":Company", company).default_currency || frappe.boot.sysdefaults.currency;
      else
        return frappe.boot.sysdefaults.currency;
    },
    get_presentation_currency_list: () => {
      const docs = frappe.boot.docs;
      let currency_list = docs.filter((d) => d.doctype === ":Currency").map((d) => d.name);
      currency_list.unshift("");
      return currency_list;
    },
    toggle_naming_series: function() {
      if (cur_frm && cur_frm.fields_dict.naming_series) {
        cur_frm.toggle_display("naming_series", cur_frm.doc.__islocal ? true : false);
      }
    },
    hide_company: function() {
      if (cur_frm.fields_dict.company) {
        var companies = Object.keys(locals[":Company"] || {});
        if (companies.length === 1) {
          if (!cur_frm.doc.company)
            cur_frm.set_value("company", companies[0]);
          cur_frm.toggle_display("company", false);
        } else if (erpnext.last_selected_company) {
          if (!cur_frm.doc.company)
            cur_frm.set_value("company", erpnext.last_selected_company);
        }
      }
    },
    is_perpetual_inventory_enabled: function(company) {
      if (company) {
        let company_local = locals[":Company"] && locals[":Company"][company];
        if (company_local) {
          return cint(company_local.enable_perpetual_inventory);
        }
      }
    },
    stale_rate_allowed: () => {
      return cint(frappe.boot.sysdefaults.allow_stale);
    },
    setup_serial_or_batch_no: function() {
      let grid_row = cur_frm.open_grid_row();
      if (!grid_row || !grid_row.grid_form.fields_dict.serial_no || grid_row.grid_form.fields_dict.serial_no.get_status() !== "Write")
        return;
      frappe.model.get_value("Item", { name: grid_row.doc.item_code }, ["has_serial_no", "has_batch_no"], ({ has_serial_no, has_batch_no }) => {
        Object.assign(grid_row.doc, { has_serial_no, has_batch_no });
        if (has_serial_no) {
          attach_selector_button(__("Add Serial No"), grid_row.grid_form.fields_dict.serial_no.$wrapper, this, grid_row);
        } else if (has_batch_no) {
          attach_selector_button(__("Pick Batch No"), grid_row.grid_form.fields_dict.batch_no.$wrapper, this, grid_row);
        }
      });
    },
    route_to_adjustment_jv: (args) => {
      frappe.model.with_doctype("Journal Entry", () => {
        let journal_entry = frappe.model.get_new_doc("Journal Entry");
        args.accounts.forEach((je_account) => {
          let child_row = frappe.model.add_child(journal_entry, "accounts");
          child_row.account = je_account.account;
          child_row.debit_in_account_currency = je_account.debit_in_account_currency;
          child_row.credit_in_account_currency = je_account.credit_in_account_currency;
          child_row.party_type = "";
        });
        frappe.set_route("Form", "Journal Entry", journal_entry.name);
      });
    },
    route_to_pending_reposts: (args) => {
      frappe.set_route("List", "Repost Item Valuation", args);
    }
  });
  $.extend(erpnext.utils, {
    set_party_dashboard_indicators: function(frm) {
      if (frm.doc.__onload && frm.doc.__onload.dashboard_info) {
        var company_wise_info = frm.doc.__onload.dashboard_info;
        if (company_wise_info.length > 1) {
          company_wise_info.forEach(function(info) {
            erpnext.utils.add_indicator_for_multicompany(frm, info);
          });
        } else if (company_wise_info.length === 1) {
          frm.dashboard.add_indicator(__("Annual Billing: {0}", [
            format_currency(company_wise_info[0].billing_this_year, company_wise_info[0].currency)
          ]), "blue");
          frm.dashboard.add_indicator(__("Total Unpaid: {0}", [
            format_currency(company_wise_info[0].total_unpaid, company_wise_info[0].currency)
          ]), company_wise_info[0].total_unpaid ? "orange" : "green");
          if (company_wise_info[0].loyalty_points) {
            frm.dashboard.add_indicator(__("Loyalty Points: {0}", [company_wise_info[0].loyalty_points]), "blue");
          }
        }
      }
    },
    add_indicator_for_multicompany: function(frm, info) {
      frm.dashboard.stats_area.show();
      frm.dashboard.stats_area_row.addClass("flex");
      frm.dashboard.stats_area_row.css("flex-wrap", "wrap");
      var color = info.total_unpaid ? "orange" : "green";
      var indicator = $('<div class="flex-column col-xs-6"><div style="margin-top:10px"><h6>' + info.company + '</h6></div><div class="badge-link small" style="margin-bottom:10px"><span class="indicator blue">Annual Billing: ' + format_currency(info.billing_this_year, info.currency) + '</span></div><div class="badge-link small" style="margin-bottom:10px"><span class="indicator ' + color + '">Total Unpaid: ' + format_currency(info.total_unpaid, info.currency) + "</span></div></div>").appendTo(frm.dashboard.stats_area_row);
      if (info.loyalty_points) {
        $('<div class="badge-link small" style="margin-bottom:10px"><span class="indicator blue">Loyalty Points: ' + info.loyalty_points + "</span></div>").appendTo(indicator);
      }
      return indicator;
    },
    get_party_name: function(party_type) {
      var dict = {
        Customer: "customer_name",
        Supplier: "supplier_name",
        Employee: "employee_name",
        Member: "member_name"
      };
      return dict[party_type];
    },
    copy_value_in_all_rows: function(doc, dt, dn, table_fieldname, fieldname) {
      var d = locals[dt][dn];
      if (d[fieldname]) {
        var cl = doc[table_fieldname] || [];
        for (var i = 0; i < cl.length; i++) {
          if (!cl[i][fieldname])
            cl[i][fieldname] = d[fieldname];
        }
      }
      refresh_field(table_fieldname);
    },
    get_terms: function(tc_name, doc, callback) {
      if (tc_name) {
        return frappe.call({
          method: "erpnext.setup.doctype.terms_and_conditions.terms_and_conditions.get_terms_and_conditions",
          args: {
            template_name: tc_name,
            doc
          },
          callback: function(r) {
            callback(r);
          }
        });
      }
    },
    make_bank_account: function(doctype, docname) {
      frappe.call({
        method: "erpnext.accounts.doctype.bank_account.bank_account.make_bank_account",
        args: {
          doctype,
          docname
        },
        freeze: true,
        callback: function(r) {
          var doclist = frappe.model.sync(r.message);
          frappe.set_route("Form", doclist[0].doctype, doclist[0].name);
        }
      });
    },
    add_dimensions: function(report_name, index) {
      let filters = frappe.query_reports[report_name].filters;
      frappe.call({
        method: "erpnext.accounts.doctype.accounting_dimension.accounting_dimension.get_dimensions",
        callback: function(r) {
          let accounting_dimensions = r.message[0];
          accounting_dimensions.forEach((dimension) => {
            let found = filters.some((el) => el.fieldname === dimension["fieldname"]);
            if (!found) {
              filters.splice(index, 0, {
                fieldname: dimension["fieldname"],
                label: __(dimension["label"]),
                fieldtype: "MultiSelectList",
                get_data: function(txt) {
                  return frappe.db.get_link_options(dimension["document_type"], txt);
                }
              });
            }
          });
        }
      });
    },
    add_inventory_dimensions: function(report_name, index) {
      let filters = frappe.query_reports[report_name].filters;
      frappe.call({
        method: "erpnext.stock.doctype.inventory_dimension.inventory_dimension.get_inventory_dimensions",
        callback: function(r) {
          if (r.message && r.message.length) {
            r.message.forEach((dimension) => {
              let existing_filter = filters.filter((el) => el.fieldname === dimension["fieldname"]);
              if (!existing_filter.length) {
                filters.splice(index, 0, {
                  fieldname: dimension["fieldname"],
                  label: __(dimension["doctype"]),
                  fieldtype: "MultiSelectList",
                  get_data: function(txt) {
                    return frappe.db.get_link_options(dimension["doctype"], txt);
                  }
                });
              } else {
                existing_filter[0]["fieldtype"] = "MultiSelectList";
                existing_filter[0]["get_data"] = function(txt) {
                  return frappe.db.get_link_options(dimension["doctype"], txt);
                };
              }
            });
          }
        }
      });
    },
    make_subscription: function(doctype, docname) {
      frappe.call({
        method: "frappe.automation.doctype.auto_repeat.auto_repeat.make_auto_repeat",
        args: {
          doctype,
          docname
        },
        callback: function(r) {
          var doclist = frappe.model.sync(r.message);
          frappe.set_route("Form", doclist[0].doctype, doclist[0].name);
        }
      });
    },
    make_pricing_rule: function(doctype, docname) {
      frappe.call({
        method: "erpnext.accounts.doctype.pricing_rule.pricing_rule.make_pricing_rule",
        args: {
          doctype,
          docname
        },
        callback: function(r) {
          var doclist = frappe.model.sync(r.message);
          frappe.set_route("Form", doclist[0].doctype, doclist[0].name);
        }
      });
    },
    first_row_is_empty: function(child_table) {
      if ($.isArray(child_table) && child_table.length > 0) {
        return !child_table[0].item_code;
      }
      return false;
    },
    remove_empty_first_row: function(frm, child_table_name) {
      const rows = frm["doc"][child_table_name];
      if (this.first_row_is_empty(rows)) {
        frm["doc"][child_table_name] = rows.splice(1);
      }
      return rows;
    },
    get_tree_options: function(option) {
      let unscrub_option = frappe.model.unscrub(option);
      let user_permission = frappe.defaults.get_user_permissions();
      let options;
      if (user_permission && user_permission[unscrub_option]) {
        options = user_permission[unscrub_option].map((perm) => perm.doc);
      } else {
        options = $.map(locals[`:${unscrub_option}`], function(c) {
          return c.name;
        }).sort();
      }
      return options.filter((value, index, self) => self.indexOf(value) === index);
    },
    get_tree_default: function(option) {
      let options = this.get_tree_options(option);
      if (options.includes(frappe.defaults.get_default(option))) {
        return frappe.defaults.get_default(option);
      } else {
        return options[0];
      }
    },
    overrides_parent_value_in_all_rows: function(doc, dt, dn, table_fieldname, fieldname, parent_fieldname) {
      if (doc[parent_fieldname]) {
        let cl = doc[table_fieldname] || [];
        for (let i = 0; i < cl.length; i++) {
          cl[i][fieldname] = doc[parent_fieldname];
        }
        frappe.refresh_field(table_fieldname);
      }
    },
    create_new_doc: function(doctype, update_fields) {
      frappe.model.with_doctype(doctype, function() {
        var new_doc = frappe.model.get_new_doc(doctype);
        for (let [key, value] of Object.entries(update_fields)) {
          new_doc[key] = value;
        }
        frappe.ui.form.make_quick_entry(doctype, null, null, new_doc);
      });
    },
    check_payments_app: () => {
      if (frappe.boot.versions && !frappe.boot.versions.payments) {
        const marketplace_link = '<a href="https://frappecloud.com/marketplace/apps/payments">Marketplace</a>';
        const github_link = '<a href="https://github.com/frappe/payments/">GitHub</a>';
        const msg = __("payments app is not installed. Please install it from {0} or {1}", [
          marketplace_link,
          github_link
        ]);
        frappe.msgprint(msg);
      }
    },
    get_fiscal_year: function(date, with_dates = false, boolean = false) {
      if (!frappe.boot.setup_complete) {
        return;
      }
      if (!date) {
        date = frappe.datetime.get_today();
      }
      let fiscal_year = "";
      frappe.call({
        method: "erpnext.accounts.utils.get_fiscal_year",
        args: {
          date,
          boolean
        },
        async: false,
        callback: function(r) {
          if (r.message) {
            if (with_dates)
              fiscal_year = r.message;
            else
              fiscal_year = r.message[0];
          }
        }
      });
      return fiscal_year;
    }
  });
  erpnext.utils.select_alternate_items = function(opts) {
    const frm = opts.frm;
    const warehouse_field = opts.warehouse_field || "warehouse";
    const item_field = opts.item_field || "item_code";
    this.data = [];
    const dialog2 = new frappe.ui.Dialog({
      title: __("Select Alternate Item"),
      fields: [
        { fieldtype: "Section Break", label: __("Items") },
        {
          fieldname: "alternative_items",
          fieldtype: "Table",
          cannot_add_rows: true,
          in_place_edit: true,
          data: this.data,
          get_data: () => {
            return this.data;
          },
          fields: [
            {
              fieldtype: "Data",
              fieldname: "docname",
              hidden: 1
            },
            {
              fieldtype: "Link",
              fieldname: "item_code",
              options: "Item",
              in_list_view: 1,
              read_only: 1,
              label: __("Item Code")
            },
            {
              fieldtype: "Link",
              fieldname: "alternate_item",
              options: "Item",
              default: "",
              in_list_view: 1,
              label: __("Alternate Item"),
              onchange: function() {
                const item_code = this.get_value();
                const warehouse = this.grid_row.on_grid_fields_dict.warehouse.get_value();
                if (item_code && warehouse) {
                  frappe.call({
                    method: "erpnext.stock.utils.get_latest_stock_qty",
                    args: {
                      item_code,
                      warehouse
                    },
                    callback: (r) => {
                      this.grid_row.on_grid_fields_dict.actual_qty.set_value(r.message || 0);
                    }
                  });
                }
              },
              get_query: (e) => {
                return {
                  query: "erpnext.stock.doctype.item_alternative.item_alternative.get_alternative_items",
                  filters: {
                    item_code: e.item_code
                  }
                };
              }
            },
            {
              fieldtype: "Link",
              fieldname: "warehouse",
              options: "Warehouse",
              default: "",
              in_list_view: 1,
              label: __("Warehouse"),
              onchange: function() {
                const warehouse = this.get_value();
                const item_code = this.grid_row.on_grid_fields_dict.item_code.get_value();
                if (item_code && warehouse) {
                  frappe.call({
                    method: "erpnext.stock.utils.get_latest_stock_qty",
                    args: {
                      item_code,
                      warehouse
                    },
                    callback: (r) => {
                      this.grid_row.on_grid_fields_dict.actual_qty.set_value(r.message || 0);
                    }
                  });
                }
              }
            },
            {
              fieldtype: "Float",
              fieldname: "actual_qty",
              default: 0,
              read_only: 1,
              in_list_view: 1,
              label: __("Available Qty")
            }
          ]
        }
      ],
      primary_action: function() {
        const args = this.get_values()["alternative_items"];
        const alternative_items = args.filter((d) => {
          if (d.alternate_item && d.item_code != d.alternate_item) {
            return true;
          }
        });
        alternative_items.forEach((d) => {
          let row = frappe.get_doc(opts.child_doctype, d.docname);
          let qty = null;
          if (row.doctype === "Work Order Item") {
            qty = row.required_qty;
          } else {
            qty = row.qty;
          }
          row[item_field] = d.alternate_item;
          frappe.model.set_value(row.doctype, row.name, "qty", qty);
          frappe.model.set_value(row.doctype, row.name, opts.original_item_field, d.item_code);
          frm.trigger(item_field, row.doctype, row.name);
        });
        refresh_field(opts.child_docname);
        this.hide();
      },
      primary_action_label: __("Update")
    });
    frm.doc[opts.child_docname].forEach((d) => {
      if (!opts.condition || opts.condition(d)) {
        dialog2.fields_dict.alternative_items.df.data.push({
          docname: d.name,
          item_code: d[item_field],
          warehouse: d[warehouse_field],
          actual_qty: d.actual_qty
        });
      }
    });
    this.data = dialog2.fields_dict.alternative_items.df.data;
    dialog2.fields_dict.alternative_items.grid.refresh();
    dialog2.show();
  };
  erpnext.utils.update_child_items = function(opts) {
    const frm = opts.frm;
    const cannot_add_row = typeof opts.cannot_add_row === "undefined" ? true : opts.cannot_add_row;
    const child_docname = typeof opts.cannot_add_row === "undefined" ? "items" : opts.child_docname;
    const child_meta = frappe.get_meta(`${frm.doc.doctype} Item`);
    const get_precision = (fieldname) => child_meta.fields.find((f) => f.fieldname == fieldname).precision;
    this.data = frm.doc[opts.child_docname].map((d) => {
      return {
        docname: d.name,
        name: d.name,
        item_code: d.item_code,
        delivery_date: d.delivery_date,
        schedule_date: d.schedule_date,
        conversion_factor: d.conversion_factor,
        qty: d.qty,
        rate: d.rate,
        uom: d.uom
      };
    });
    const fields = [
      {
        fieldtype: "Data",
        fieldname: "docname",
        read_only: 1,
        hidden: 1
      },
      {
        fieldtype: "Link",
        fieldname: "item_code",
        options: "Item",
        in_list_view: 1,
        read_only: 0,
        disabled: 0,
        label: __("Item Code"),
        get_query: function() {
          let filters;
          if (frm.doc.doctype == "Sales Order") {
            filters = { is_sales_item: 1 };
          } else if (frm.doc.doctype == "Purchase Order") {
            if (frm.doc.is_subcontracted) {
              if (frm.doc.is_old_subcontracting_flow) {
                filters = { is_sub_contracted_item: 1 };
              } else {
                filters = { is_stock_item: 0 };
              }
            } else {
              filters = { is_purchase_item: 1 };
            }
          }
          return {
            query: "erpnext.controllers.queries.item_query",
            filters
          };
        }
      },
      {
        fieldtype: "Link",
        fieldname: "uom",
        options: "UOM",
        read_only: 0,
        label: __("UOM"),
        reqd: 1,
        onchange: function() {
          frappe.call({
            method: "erpnext.stock.get_item_details.get_conversion_factor",
            args: { item_code: this.doc.item_code, uom: this.value },
            callback: (r) => {
              if (!r.exc) {
                if (this.doc.conversion_factor == r.message.conversion_factor)
                  return;
                const docname = this.doc.docname;
                dialog.fields_dict.trans_items.df.data.some((doc) => {
                  if (doc.docname == docname) {
                    doc.conversion_factor = r.message.conversion_factor;
                    dialog.fields_dict.trans_items.grid.refresh();
                    return true;
                  }
                });
              }
            }
          });
        }
      },
      {
        fieldtype: "Float",
        fieldname: "qty",
        default: 0,
        read_only: 0,
        in_list_view: 1,
        label: __("Qty"),
        precision: get_precision("qty")
      },
      {
        fieldtype: "Currency",
        fieldname: "rate",
        options: "currency",
        default: 0,
        read_only: 0,
        in_list_view: 1,
        label: __("Rate"),
        precision: get_precision("rate")
      }
    ];
    if (frm.doc.doctype == "Sales Order" || frm.doc.doctype == "Purchase Order") {
      fields.splice(2, 0, {
        fieldtype: "Date",
        fieldname: frm.doc.doctype == "Sales Order" ? "delivery_date" : "schedule_date",
        in_list_view: 1,
        label: frm.doc.doctype == "Sales Order" ? __("Delivery Date") : __("Reqd by date"),
        reqd: 1
      });
      fields.splice(3, 0, {
        fieldtype: "Float",
        fieldname: "conversion_factor",
        label: __("Conversion Factor"),
        precision: get_precision("conversion_factor")
      });
    }
    new frappe.ui.Dialog({
      title: __("Update Items"),
      size: "extra-large",
      fields: [
        {
          fieldname: "trans_items",
          fieldtype: "Table",
          label: "Items",
          cannot_add_rows: cannot_add_row,
          in_place_edit: false,
          reqd: 1,
          data: this.data,
          get_data: () => {
            return this.data;
          },
          fields
        }
      ],
      primary_action: function() {
        const trans_items = this.get_values()["trans_items"].filter((item) => !!item.item_code);
        frappe.call({
          method: "erpnext.controllers.accounts_controller.update_child_qty_rate",
          freeze: true,
          args: {
            parent_doctype: frm.doc.doctype,
            trans_items,
            parent_doctype_name: frm.doc.name,
            child_docname
          },
          callback: function() {
            frm.reload_doc();
          }
        });
        this.hide();
        refresh_field("items");
      },
      primary_action_label: __("Update")
    }).show();
  };
  erpnext.utils.map_current_doc = function(opts) {
    function _map() {
      if ($.isArray(cur_frm.doc.items) && cur_frm.doc.items.length > 0) {
        if (!cur_frm.doc.items[0].item_code) {
          cur_frm.doc.items = cur_frm.doc.items.splice(1);
        }
        var items_doctype = frappe.meta.get_docfield(cur_frm.doctype, "items").options;
        var link_fieldname = null;
        frappe.get_meta(items_doctype).fields.forEach(function(d) {
          if (d.options === opts.source_doctype)
            link_fieldname = d.fieldname;
        });
        var already_set = false;
        var item_qty_map = {};
        $.each(cur_frm.doc.items, function(i, d) {
          opts.source_name.forEach(function(src) {
            if (d[link_fieldname] == src) {
              already_set = true;
              if (item_qty_map[d.item_code])
                item_qty_map[d.item_code] += flt(d.qty);
              else
                item_qty_map[d.item_code] = flt(d.qty);
            }
          });
        });
        if (already_set) {
          opts.source_name.forEach(function(src) {
            frappe.model.with_doc(opts.source_doctype, src, function(r) {
              var source_doc = frappe.model.get_doc(opts.source_doctype, src);
              $.each(source_doc.items || [], function(i, row) {
                if (row.qty > flt(item_qty_map[row.item_code])) {
                  already_set = false;
                  return false;
                }
              });
            });
            if (already_set) {
              frappe.msgprint(__("You have already selected items from {0} {1}", [opts.source_doctype, src]));
              return;
            }
          });
        }
      }
      return frappe.call({
        type: "POST",
        method: "frappe.model.mapper.map_docs",
        args: {
          method: opts.method,
          source_names: opts.source_name,
          target_doc: cur_frm.doc,
          args: opts.args
        },
        callback: function(r) {
          if (!r.exc) {
            frappe.model.sync(r.message);
            cur_frm.dirty();
            cur_frm.refresh();
          }
        }
      });
    }
    let query_args = {};
    if (opts.get_query_filters) {
      query_args.filters = opts.get_query_filters;
    }
    if (opts.get_query_method) {
      query_args.query = opts.get_query_method;
    }
    if (query_args.filters || query_args.query) {
      opts.get_query = () => query_args;
    }
    if (opts.source_doctype) {
      let data_fields = [];
      if (["Purchase Receipt", "Delivery Note"].includes(opts.source_doctype)) {
        let target_meta = frappe.get_meta(cur_frm.doc.doctype);
        if (target_meta.fields.find((f) => f.fieldname === "taxes")) {
          data_fields.push({
            fieldname: "merge_taxes",
            fieldtype: "Check",
            label: __("Merge taxes from multiple documents")
          });
        }
      }
      const d = new frappe.ui.form.MultiSelectDialog({
        doctype: opts.source_doctype,
        target: opts.target,
        date_field: opts.date_field || void 0,
        setters: opts.setters,
        data_fields,
        get_query: opts.get_query,
        add_filters_group: 1,
        allow_child_item_selection: opts.allow_child_item_selection,
        child_fieldname: opts.child_fieldname,
        child_columns: opts.child_columns,
        size: opts.size,
        action: function(selections, args) {
          let values = selections;
          if (values.length === 0) {
            frappe.msgprint(__("Please select {0}", [opts.source_doctype]));
            return;
          }
          opts.source_name = values;
          if (opts.allow_child_item_selection || ["Purchase Receipt", "Delivery Note"].includes(opts.source_doctype)) {
            opts.args = args;
          }
          d.dialog.hide();
          _map();
        }
      });
      return d;
    }
    if (opts.source_name) {
      opts.source_name = [opts.source_name];
      _map();
    }
  };
  frappe.form.link_formatters["Item"] = function(value, doc) {
    if (doc && value && doc.item_name && doc.item_name !== value && doc.item_code === value) {
      return value + ": " + doc.item_name;
    } else if (!value && doc.doctype && doc.item_name) {
      return doc.item_name;
    } else {
      return value;
    }
  };
  frappe.form.link_formatters["Employee"] = function(value, doc) {
    if (doc && value && doc.employee_name && doc.employee_name !== value && doc.employee === value) {
      return value + ": " + doc.employee_name;
    } else if (!value && doc.doctype && doc.employee_name) {
      return doc.employee;
    } else {
      return value;
    }
  };
  frappe.form.link_formatters["Project"] = function(value, doc) {
    if (doc && value && doc.project_name && doc.project_name !== value && doc.project === value) {
      return value + ": " + doc.project_name;
    } else if (!value && doc.doctype && doc.project_name) {
      return doc.project;
    } else {
      return value;
    }
  };
  $(document).on("app_ready", function() {
    if (!frappe.datetime.is_timezone_same()) {
      $.each([
        "Stock Reconciliation",
        "Stock Entry",
        "Stock Ledger Entry",
        "Delivery Note",
        "Purchase Receipt",
        "Sales Invoice"
      ], function(i, d) {
        frappe.ui.form.on(d, "onload", function(frm) {
          cur_frm.set_df_property("posting_time", "description", frappe.sys_defaults.time_zone);
        });
      });
    }
  });
  $(document).on("app_ready", function() {
    $.each(frappe.boot.service_level_agreement_doctypes, function(_i, d) {
      frappe.ui.form.on(d, {
        onload: function(frm) {
          if (!frm.doc.service_level_agreement)
            return;
          frappe.call({
            method: "erpnext.support.doctype.service_level_agreement.service_level_agreement.get_service_level_agreement_filters",
            args: {
              doctype: frm.doc.doctype,
              name: frm.doc.service_level_agreement,
              customer: frm.doc.customer
            },
            callback: function(r) {
              if (r && r.message) {
                frm.set_query("priority", function() {
                  return {
                    filters: {
                      name: ["in", r.message.priority]
                    }
                  };
                });
                frm.set_query("service_level_agreement", function() {
                  return {
                    filters: {
                      name: ["in", r.message.service_level_agreements]
                    }
                  };
                });
              }
            }
          });
        },
        refresh: function(frm) {
          if (frm.doc.status !== "Closed" && frm.doc.service_level_agreement && ["First Response Due", "Resolution Due"].includes(frm.doc.agreement_status)) {
            frappe.call({
              method: "frappe.client.get",
              args: {
                doctype: "Service Level Agreement",
                name: frm.doc.service_level_agreement
              },
              callback: function(data) {
                let statuses = data.message.pause_sla_on;
                const hold_statuses = [];
                $.each(statuses, (_i2, entry) => {
                  hold_statuses.push(entry.status);
                });
                if (hold_statuses.includes(frm.doc.status)) {
                  frm.dashboard.clear_headline();
                  let message = {
                    indicator: "orange",
                    msg: __("SLA is on hold since {0}", [
                      moment(frm.doc.on_hold_since).fromNow(true)
                    ])
                  };
                  frm.dashboard.set_headline_alert('<div class="row"><div class="col-xs-12"><span class="indicator whitespace-nowrap ' + message.indicator + '"><span>' + message.msg + "</span></span> </div></div>");
                } else {
                  set_time_to_resolve_and_response(frm, data.message.apply_sla_for_resolution);
                }
              }
            });
          } else if (frm.doc.service_level_agreement) {
            frm.dashboard.clear_headline();
            let agreement_status = frm.doc.agreement_status == "Fulfilled" ? { indicator: "green", msg: "Service Level Agreement has been fulfilled" } : { indicator: "red", msg: "Service Level Agreement Failed" };
            frm.dashboard.set_headline_alert('<div class="row"><div class="col-xs-12"><span class="indicator whitespace-nowrap ' + agreement_status.indicator + '"><span class="hidden-xs">' + agreement_status.msg + "</span></span> </div></div>");
          }
        }
      });
    });
  });
  function set_time_to_resolve_and_response(frm, apply_sla_for_resolution) {
    frm.dashboard.clear_headline();
    let time_to_respond;
    if (!frm.doc.first_responded_on) {
      time_to_respond = get_time_left(frm.doc.response_by, frm.doc.agreement_status);
    } else {
      time_to_respond = get_status(frm.doc.response_by, frm.doc.first_responded_on);
    }
    let alert = `
		<div class="row">
			<div class="col-xs-12 col-sm-6">
				<span class="indicator whitespace-nowrap ${time_to_respond.indicator}">
					<span>Time to Respond: ${time_to_respond.diff_display}</span>
				</span>
			</div>`;
    if (apply_sla_for_resolution) {
      let time_to_resolve;
      if (!frm.doc.resolution_date) {
        time_to_resolve = get_time_left(frm.doc.resolution_by, frm.doc.agreement_status);
      } else {
        time_to_resolve = get_status(frm.doc.resolution_by, frm.doc.resolution_date);
      }
      alert += `
			<div class="col-xs-12 col-sm-6">
				<span class="indicator whitespace-nowrap ${time_to_resolve.indicator}">
					<span>Time to Resolve: ${time_to_resolve.diff_display}</span>
				</span>
			</div>`;
    }
    alert += "</div>";
    frm.dashboard.set_headline_alert(alert);
  }
  function get_time_left(timestamp, agreement_status) {
    const diff = moment(timestamp).diff(frappe.datetime.system_datetime(true));
    const diff_display = diff >= 44500 ? moment.duration(diff).humanize() : "Failed";
    let indicator = diff_display == "Failed" && agreement_status != "Fulfilled" ? "red" : "green";
    return { diff_display, indicator };
  }
  function get_status(expected, actual) {
    const time_left = moment(expected).diff(moment(actual));
    if (time_left >= 0) {
      return { diff_display: "Fulfilled", indicator: "green" };
    } else {
      return { diff_display: "Failed", indicator: "red" };
    }
  }
  function attach_selector_button(inner_text, append_loction, context, grid_row) {
    let $btn_div = $("<div>").css({ "margin-bottom": "10px", "margin-top": "10px" }).appendTo(append_loction);
    let $btn = $(`<button class="btn btn-sm btn-default">${inner_text}</button>`).appendTo($btn_div);
    $btn.on("click", function() {
      context.show_serial_batch_selector(grid_row.frm, grid_row.doc, "", "", true);
    });
  }
  $.extend(erpnext.stock.utils, {
    set_item_details_using_barcode(frm, child_row, callback) {
      const barcode_scanner = new erpnext.utils.BarcodeScanner({ frm });
      barcode_scanner.scan_api_call(child_row.barcode, callback);
    }
  });

  // ../metactical/metactical/custom_scripts/public/erpnext/utils.js
  frappe.provide("erpnext");
  frappe.provide("erpnext.utils");
  erpnext.utils.update_child_items = function(opts) {
    const frm = opts.frm;
    const cannot_add_row = typeof opts.cannot_add_row === "undefined" ? true : opts.cannot_add_row;
    const child_docname = typeof opts.cannot_add_row === "undefined" ? "items" : opts.child_docname;
    const child_meta = frappe.get_meta(`${frm.doc.doctype} Item`);
    const get_precision = (fieldname) => child_meta.fields.find((f) => f.fieldname == fieldname).precision;
    this.data = [];
    const fields = [{
      fieldtype: "Data",
      fieldname: "docname",
      read_only: 1,
      hidden: 1
    }, {
      fieldtype: "Link",
      fieldname: "item_code",
      options: "Item",
      in_list_view: 1,
      read_only: 0,
      disabled: 0,
      label: __("Item Code"),
      get_query: function() {
        let filters;
        if (frm.doc.doctype == "Sales Order") {
          filters = { "is_sales_item": 1 };
        } else if (frm.doc.doctype == "Purchase Order") {
          if (frm.doc.is_subcontracted == "Yes") {
            filters = { "is_sub_contracted_item": 1 };
          } else {
            filters = { "is_purchase_item": 1 };
          }
        }
        return {
          query: "erpnext.controllers.queries.item_query",
          filters
        };
      }
    }, {
      fieldtype: "Link",
      fieldname: "uom",
      options: "UOM",
      read_only: 0,
      label: __("UOM"),
      reqd: 1,
      onchange: function() {
        frappe.call({
          method: "erpnext.stock.get_item_details.get_conversion_factor",
          args: { item_code: this.doc.item_code, uom: this.value },
          callback: (r) => {
            if (!r.exc) {
              if (this.doc.conversion_factor == r.message.conversion_factor)
                return;
              const docname = this.doc.docname;
              dialog2.fields_dict.trans_items.df.data.some((doc) => {
                if (doc.docname == docname) {
                  doc.conversion_factor = r.message.conversion_factor;
                  dialog2.fields_dict.trans_items.grid.refresh();
                  return true;
                }
              });
            }
          }
        });
      }
    }, {
      fieldtype: "Float",
      fieldname: "qty",
      default: 0,
      read_only: 0,
      in_list_view: 1,
      label: __("Qty"),
      precision: get_precision("qty")
    }, {
      fieldtype: "Currency",
      fieldname: "rate",
      options: "currency",
      default: 0,
      read_only: 0,
      in_list_view: 1,
      label: __("Rate"),
      precision: get_precision("rate")
    }];
    if (frm.doc.doctype == "Sales Order") {
      fields.push({
        fieldtype: "Float",
        fieldname: "picked_qty",
        default: 0,
        read_only: 1,
        in_list_view: 0,
        label: __("Picked Qty"),
        precision: get_precision("picked_qty")
      }, {
        fieldtype: "Link",
        fieldname: "warehouse",
        read_only: 0,
        in_list_view: 1,
        label: __("Warehouse"),
        options: "Warehouse",
        reqd: 1
      });
    }
    if (frm.doc.doctype == "Sales Order" || frm.doc.doctype == "Purchase Order") {
      fields.splice(2, 0, {
        fieldtype: "Date",
        fieldname: frm.doc.doctype == "Sales Order" ? "delivery_date" : "schedule_date",
        in_list_view: 1,
        label: frm.doc.doctype == "Sales Order" ? __("Delivery Date") : __("Reqd by date"),
        reqd: 1
      });
      fields.splice(3, 0, {
        fieldtype: "Float",
        fieldname: "conversion_factor",
        default: 1,
        in_list_view: 0,
        label: __("Conversion Factor"),
        precision: get_precision("conversion_factor")
      });
    }
    const dialog2 = new frappe.ui.Dialog({
      title: __("Update Items"),
      fields: [
        {
          fieldname: "trans_items",
          fieldtype: "Table",
          label: "Items",
          cannot_add_rows: cannot_add_row,
          in_place_edit: false,
          reqd: 1,
          data: this.data,
          get_data: () => {
            return this.data;
          },
          fields
        }
      ],
      primary_action: function() {
        if (frm.doc.doctype == "Sales Order") {
          frm.doc[opts.child_docname].forEach((d) => {
            if (d.picked_qty == d.qty) {
              this.fields_dict.trans_items.df.data.push({
                "docname": d.name,
                "name": d.name,
                "item_code": d.item_code,
                "delivery_date": d.delivery_date,
                "schedule_date": d.schedule_date,
                "conversion_factor": d.conversion_factor,
                "qty": d.qty,
                "rate": d.rate,
                "uom": d.uom,
                "picked_qty": d.picked_qty,
                "warehouse": d.warehouse
              });
              this.data = dialog2.fields_dict.trans_items.df.data;
            }
          });
        }
        const trans_items = this.get_values()["trans_items"].filter((item) => !!item.item_code);
        if (frm.doc.doctype == "Sales Order") {
          trans_items.forEach((row) => {
            if (row.picked_qty > row.qty) {
              frappe.throw("Quantity can not be greater than the already picked qty for item " + row.item_code);
            }
          });
        }
        frappe.call({
          method: "metactical.custom_scripts.controllers.accounts_controller.update_child_qty_rate",
          freeze: true,
          args: {
            "parent_doctype": frm.doc.doctype,
            "trans_items": trans_items,
            "parent_doctype_name": frm.doc.name,
            "child_docname": child_docname
          },
          callback: function() {
            frm.reload_doc();
          }
        });
        this.hide();
        refresh_field("items");
      },
      primary_action_label: __("Update")
    });
    frm.doc[opts.child_docname].forEach((d) => {
      if (frm.doc.doctype == "Sales Order" && d.picked_qty < d.qty) {
        dialog2.fields_dict.trans_items.df.data.push({
          "docname": d.name,
          "name": d.name,
          "item_code": d.item_code,
          "delivery_date": d.delivery_date,
          "schedule_date": d.schedule_date,
          "conversion_factor": d.conversion_factor,
          "qty": d.qty,
          "rate": d.rate,
          "uom": d.uom,
          "picked_qty": d.picked_qty,
          "warehouse": d.warehouse
        });
        this.data = dialog2.fields_dict.trans_items.df.data;
        dialog2.fields_dict.trans_items.grid.refresh();
      } else if (frm.doc.doctype != "Sales Order") {
        dialog2.fields_dict.trans_items.df.data.push({
          "docname": d.name,
          "name": d.name,
          "item_code": d.item_code,
          "delivery_date": d.delivery_date,
          "schedule_date": d.schedule_date,
          "conversion_factor": d.conversion_factor,
          "qty": d.qty,
          "rate": d.rate,
          "uom": d.uom
        });
        this.data = dialog2.fields_dict.trans_items.df.data;
        dialog2.fields_dict.trans_items.grid.refresh();
      }
    });
    dialog2.show();
  };

  // ../erpnext/erpnext/public/js/queries.js
  frappe.provide("erpnext.queries");
  $.extend(erpnext.queries, {
    user: function() {
      return { query: "frappe.core.doctype.user.user.user_query" };
    },
    lead: function() {
      return { query: "erpnext.controllers.queries.lead_query" };
    },
    customer: function() {
      return { query: "erpnext.controllers.queries.customer_query" };
    },
    supplier: function() {
      return { query: "erpnext.controllers.queries.supplier_query" };
    },
    item: function(filters) {
      var args = { query: "erpnext.controllers.queries.item_query" };
      if (filters)
        args["filters"] = filters;
      return args;
    },
    bom: function() {
      return { query: "erpnext.controllers.queries.bom" };
    },
    task: function() {
      return { query: "erpnext.projects.utils.query_task" };
    },
    customer_filter: function(doc) {
      if (!doc.customer) {
        frappe.throw(__("Please set {0}", [__(frappe.meta.get_label(doc.doctype, "customer", doc.name))]));
      }
      return { filters: { customer: doc.customer } };
    },
    contact_query: function(doc) {
      if (frappe.dynamic_link) {
        if (!doc[frappe.dynamic_link.fieldname]) {
          frappe.throw(__("Please set {0}", [
            __(frappe.meta.get_label(doc.doctype, frappe.dynamic_link.fieldname, doc.name))
          ]));
        }
        return {
          query: "frappe.contacts.doctype.contact.contact.contact_query",
          filters: {
            link_doctype: frappe.dynamic_link.doctype,
            link_name: doc[frappe.dynamic_link.fieldname]
          }
        };
      }
    },
    address_query: function(doc) {
      if (frappe.dynamic_link) {
        if (!doc[frappe.dynamic_link.fieldname]) {
          frappe.throw(__("Please set {0}", [
            __(frappe.meta.get_label(doc.doctype, frappe.dynamic_link.fieldname, doc.name))
          ]));
        }
        return {
          query: "frappe.contacts.doctype.address.address.address_query",
          filters: {
            link_doctype: frappe.dynamic_link.doctype,
            link_name: doc[frappe.dynamic_link.fieldname]
          }
        };
      }
    },
    company_address_query: function(doc) {
      return {
        query: "frappe.contacts.doctype.address.address.address_query",
        filters: { is_your_company_address: 1, link_doctype: "Company", link_name: doc.company || "" }
      };
    },
    dispatch_address_query: function(doc) {
      return {
        query: "frappe.contacts.doctype.address.address.address_query",
        filters: { link_doctype: "Company", link_name: doc.company || "" }
      };
    },
    supplier_filter: function(doc) {
      if (!doc.supplier) {
        frappe.throw(__("Please set {0}", [__(frappe.meta.get_label(doc.doctype, "supplier", doc.name))]));
      }
      return { filters: { supplier: doc.supplier } };
    },
    lead_filter: function(doc) {
      if (!doc.lead) {
        frappe.throw(__("Please specify a {0}", [__(frappe.meta.get_label(doc.doctype, "lead", doc.name))]));
      }
      return { filters: { lead: doc.lead } };
    },
    not_a_group_filter: function() {
      return { filters: { is_group: 0 } };
    },
    employee: function() {
      return { query: "erpnext.controllers.queries.employee_query" };
    },
    warehouse: function(doc) {
      return {
        filters: [
          ["Warehouse", "company", "in", ["", cstr(doc.company)]],
          ["Warehouse", "is_group", "=", 0]
        ]
      };
    },
    get_filtered_dimensions: function(doc, child_fields, dimension, company) {
      let account = "";
      child_fields.forEach((field) => {
        if (!account) {
          account = doc[field];
        }
      });
      return {
        query: "erpnext.controllers.queries.get_filtered_dimensions",
        filters: {
          dimension,
          account,
          company
        }
      };
    }
  });
  erpnext.queries.setup_queries = function(frm, options, query_fn) {
    var me = this;
    var set_query = function(doctype, parentfield) {
      var link_fields = frappe.meta.get_docfields(doctype, frm.doc.name, {
        fieldtype: "Link",
        options
      });
      $.each(link_fields, function(i, df) {
        if (parentfield) {
          frm.set_query(df.fieldname, parentfield, query_fn);
        } else {
          frm.set_query(df.fieldname, query_fn);
        }
      });
    };
    set_query(frm.doc.doctype);
    $.each(frappe.meta.get_docfields(frm.doc.doctype, frm.doc.name, { fieldtype: "Table" }), function(i, df) {
      set_query(df.options, df.fieldname);
    });
  };
  erpnext.queries.setup_warehouse_query = function(frm) {
    frm.set_query("warehouse", "items", function(doc, cdt, cdn) {
      var row = locals[cdt][cdn];
      var filters = erpnext.queries.warehouse(frm.doc);
      if (row.item_code) {
        $.extend(filters, { query: "erpnext.controllers.queries.warehouse_query" });
        filters["filters"].push(["Bin", "item_code", "=", row.item_code]);
      }
      return filters;
    });
  };

  // ../erpnext/erpnext/public/js/sms_manager.js
  erpnext.SMSManager = function SMSManager(doc) {
    var me = this;
    this.setup = function() {
      var default_msg = {
        Lead: "",
        Opportunity: "Your enquiry has been logged into the system. Ref No: " + doc.name,
        Quotation: "Quotation " + doc.name + " has been sent via email. Thanks!",
        "Sales Order": "Sales Order " + doc.name + " has been created against " + (doc.quotation_no ? "Quote No:" + doc.quotation_no : "") + (doc.po_no ? " for your PO: " + doc.po_no : ""),
        "Delivery Note": "Items has been delivered against delivery note: " + doc.name + (doc.po_no ? " for your PO: " + doc.po_no : ""),
        "Sales Invoice": "Invoice " + doc.name + " has been sent via email " + (doc.po_no ? " for your PO: " + doc.po_no : ""),
        "Material Request": "Material Request " + doc.name + " has been raised in the system",
        "Purchase Order": "Purchase Order " + doc.name + " has been sent via email",
        "Purchase Receipt": "Items has been received against purchase receipt: " + doc.name
      };
      if (["Sales Order", "Delivery Note", "Sales Invoice"].includes(doc.doctype))
        this.show(doc.contact_person, "Customer", doc.customer, "", default_msg[doc.doctype]);
      else if (doc.doctype === "Quotation")
        this.show(doc.contact_person, "Customer", doc.party_name, "", default_msg[doc.doctype]);
      else if (["Purchase Order", "Purchase Receipt"].includes(doc.doctype))
        this.show(doc.contact_person, "Supplier", doc.supplier, "", default_msg[doc.doctype]);
      else if (doc.doctype == "Lead")
        this.show("", "", "", doc.mobile_no, default_msg[doc.doctype]);
      else if (doc.doctype == "Opportunity")
        this.show("", "", "", doc.contact_no, default_msg[doc.doctype]);
      else if (doc.doctype == "Material Request")
        this.show("", "", "", "", default_msg[doc.doctype]);
    };
    this.get_contact_number = function(contact, ref_doctype, ref_name) {
      frappe.call({
        method: "frappe.core.doctype.sms_settings.sms_settings.get_contact_number",
        args: {
          contact_name: contact,
          ref_doctype,
          ref_name
        },
        callback: function(r) {
          if (r.exc) {
            frappe.msgprint(r.exc);
            return;
          }
          me.number = r.message;
          me.show_dialog();
        }
      });
    };
    this.show = function(contact, ref_doctype, ref_name, mobile_nos, message) {
      this.message = message;
      if (mobile_nos) {
        me.number = mobile_nos;
        me.show_dialog();
      } else if (contact) {
        this.get_contact_number(contact, ref_doctype, ref_name);
      } else {
        me.show_dialog();
      }
    };
    this.show_dialog = function() {
      if (!me.dialog)
        me.make_dialog();
      me.dialog.set_values({
        message: me.message,
        number: me.number
      });
      me.dialog.show();
    };
    this.make_dialog = function() {
      var d = new frappe.ui.Dialog({
        title: "Send SMS",
        width: 400,
        fields: [
          { fieldname: "number", fieldtype: "Data", label: "Mobile Number", reqd: 1 },
          { fieldname: "message", fieldtype: "Text", label: "Message", reqd: 1 },
          { fieldname: "send", fieldtype: "Button", label: "Send" }
        ]
      });
      d.fields_dict.send.input.onclick = function() {
        var btn = d.fields_dict.send.input;
        var v = me.dialog.get_values();
        if (v) {
          $(btn).set_working();
          frappe.call({
            method: "frappe.core.doctype.sms_settings.sms_settings.send_sms",
            args: {
              receiver_list: [v.number],
              msg: v.message
            },
            callback: function(r) {
              $(btn).done_working();
              if (r.exc) {
                frappe.msgprint(r.exc);
                return;
              }
              me.dialog.hide();
            }
          });
        }
      };
      this.dialog = d;
    };
    this.setup();
  };

  // ../erpnext/erpnext/public/js/utils/party.js
  frappe.provide("erpnext.utils");
  var SALES_DOCTYPES = ["Quotation", "Sales Order", "Delivery Note", "Sales Invoice"];
  var PURCHASE_DOCTYPES = ["Supplier Quotation", "Purchase Order", "Purchase Receipt", "Purchase Invoice"];
  erpnext.utils.get_party_details = function(frm, method, args, callback) {
    if (!method) {
      method = "erpnext.accounts.party.get_party_details";
    }
    if (!args) {
      if (frm.doctype != "Purchase Order" && frm.doc.customer || frm.doc.party_name && ["Quotation", "Opportunity"].includes(frm.doc.doctype)) {
        let party_type = "Customer";
        if (frm.doc.quotation_to && ["Lead", "Prospect"].includes(frm.doc.quotation_to)) {
          party_type = frm.doc.quotation_to;
        }
        args = {
          party: frm.doc.customer || frm.doc.party_name,
          party_type,
          price_list: frm.doc.selling_price_list
        };
      } else if (frm.doc.supplier) {
        args = {
          party: frm.doc.supplier,
          party_type: "Supplier",
          bill_date: frm.doc.bill_date,
          price_list: frm.doc.buying_price_list
        };
      }
      if (!args) {
        if (in_list(SALES_DOCTYPES, frm.doc.doctype)) {
          args = {
            party: frm.doc.customer || frm.doc.party_name,
            party_type: "Customer"
          };
        }
        if (in_list(PURCHASE_DOCTYPES, frm.doc.doctype)) {
          args = {
            party: frm.doc.supplier,
            party_type: "Supplier"
          };
        }
      }
      if (!args || !args.party)
        return;
      args.posting_date = frm.doc.posting_date || frm.doc.transaction_date;
      args.fetch_payment_terms_template = cint(!frm.doc.ignore_default_payment_terms_template);
    }
    if (in_list(SALES_DOCTYPES, frm.doc.doctype)) {
      if (!args.company_address && frm.doc.company_address) {
        args.company_address = frm.doc.company_address;
      }
    }
    if (in_list(PURCHASE_DOCTYPES, frm.doc.doctype)) {
      if (!args.company_address && frm.doc.billing_address) {
        args.company_address = frm.doc.billing_address;
      }
      if (!args.shipping_address && frm.doc.shipping_address) {
        args.shipping_address = frm.doc.shipping_address;
      }
    }
    if (frappe.meta.get_docfield(frm.doc.doctype, "taxes")) {
      if (!erpnext.utils.validate_mandatory(frm, "Posting / Transaction Date", args.posting_date, args.party_type == "Customer" ? "customer" : "supplier"))
        return;
    }
    if (!erpnext.utils.validate_mandatory(frm, "Company", frm.doc.company, args.party_type == "Customer" ? "customer" : "supplier")) {
      return;
    }
    args.currency = frm.doc.currency;
    args.company = frm.doc.company;
    args.doctype = frm.doc.doctype;
    frappe.call({
      method,
      args,
      callback: function(r) {
        if (r.message) {
          frm.supplier_tds = r.message.supplier_tds;
          frm.updating_party_details = true;
          frappe.run_serially([
            () => frm.set_value(r.message),
            () => {
              frm.updating_party_details = false;
              if (callback)
                callback();
              frm.refresh();
              erpnext.utils.add_item(frm);
            }
          ]);
        }
      }
    });
  };
  erpnext.utils.add_item = function(frm) {
    if (frm.is_new()) {
      var prev_route = frappe.get_prev_route();
      if (prev_route[1] === "Item" && !(frm.doc.items && frm.doc.items.length)) {
        var item = frm.add_child("items");
        frm.refresh_field("items");
        frappe.model.set_value(item.doctype, item.name, "item_code", prev_route[2]);
      }
    }
  };
  erpnext.utils.get_address_display = function(frm, address_field, display_field, is_your_company_address) {
    if (frm.updating_party_details)
      return;
    if (!address_field) {
      if (frm.doctype != "Purchase Order" && frm.doc.customer) {
        address_field = "customer_address";
      } else if (frm.doc.supplier) {
        address_field = "supplier_address";
      } else
        return;
    }
    if (!display_field)
      display_field = "address_display";
    if (frm.doc[address_field]) {
      frappe.call({
        method: "frappe.contacts.doctype.address.address.get_address_display",
        args: { address_dict: frm.doc[address_field] },
        callback: function(r) {
          if (r.message) {
            frm.set_value(display_field, r.message);
          }
        }
      });
    } else {
      frm.set_value(display_field, "");
    }
  };
  erpnext.utils.set_taxes_from_address = function(frm, triggered_from_field, billing_address_field, shipping_address_field) {
    if (frm.updating_party_details)
      return;
    if (frappe.meta.get_docfield(frm.doc.doctype, "taxes")) {
      if (!erpnext.utils.validate_mandatory(frm, "Lead / Customer / Supplier", frm.doc.customer || frm.doc.supplier || frm.doc.lead || frm.doc.party_name, triggered_from_field)) {
        return;
      }
      if (!erpnext.utils.validate_mandatory(frm, "Posting / Transaction Date", frm.doc.posting_date || frm.doc.transaction_date, triggered_from_field)) {
        return;
      }
    } else {
      return;
    }
    frappe.call({
      method: "erpnext.accounts.party.get_address_tax_category",
      args: {
        tax_category: frm.doc.tax_category,
        billing_address: frm.doc[billing_address_field],
        shipping_address: frm.doc[shipping_address_field]
      },
      callback: function(r) {
        if (!r.exc) {
          if (frm.doc.tax_category != r.message) {
            frm.set_value("tax_category", r.message);
          } else {
            erpnext.utils.set_taxes(frm, triggered_from_field);
          }
        }
      }
    });
  };
  erpnext.utils.set_taxes = function(frm, triggered_from_field) {
    if (frappe.meta.get_docfield(frm.doc.doctype, "taxes")) {
      if (!erpnext.utils.validate_mandatory(frm, "Company", frm.doc.company, triggered_from_field)) {
        return;
      }
      if (!erpnext.utils.validate_mandatory(frm, "Lead / Customer / Supplier", frm.doc.customer || frm.doc.supplier || frm.doc.lead || frm.doc.party_name, triggered_from_field)) {
        return;
      }
      if (!erpnext.utils.validate_mandatory(frm, "Posting / Transaction Date", frm.doc.posting_date || frm.doc.transaction_date, triggered_from_field)) {
        return;
      }
    } else {
      return;
    }
    var party_type, party;
    if (frm.doc.lead) {
      party_type = "Lead";
      party = frm.doc.lead;
    } else if (frm.doc.customer) {
      party_type = "Customer";
      party = frm.doc.customer;
    } else if (frm.doc.supplier) {
      party_type = "Supplier";
      party = frm.doc.supplier;
    } else if (frm.doc.quotation_to) {
      party_type = frm.doc.quotation_to;
      party = frm.doc.party_name;
    }
    if (!frm.doc.company) {
      frappe.throw(__("Kindly select the company first"));
    }
    frappe.call({
      method: "erpnext.accounts.party.set_taxes",
      args: {
        party,
        party_type,
        posting_date: frm.doc.posting_date || frm.doc.transaction_date,
        company: frm.doc.company,
        customer_group: frm.doc.customer_group,
        supplier_group: frm.doc.supplier_group,
        tax_category: frm.doc.tax_category,
        billing_address: frm.doc.customer || frm.doc.lead ? frm.doc.customer_address : frm.doc.supplier_address,
        shipping_address: frm.doc.shipping_address_name
      },
      callback: function(r) {
        if (r.message) {
          frm.set_value("taxes_and_charges", r.message);
        }
      }
    });
  };
  erpnext.utils.get_contact_details = function(frm) {
    if (frm.updating_party_details)
      return;
    if (frm.doc["contact_person"]) {
      frappe.call({
        method: "frappe.contacts.doctype.contact.contact.get_contact_details",
        args: { contact: frm.doc.contact_person },
        callback: function(r) {
          if (r.message)
            frm.set_value(r.message);
        }
      });
    } else {
      frm.set_value({
        contact_person: "",
        contact_display: "",
        contact_email: "",
        contact_mobile: "",
        contact_phone: "",
        contact_designation: "",
        contact_department: ""
      });
    }
  };
  erpnext.utils.validate_mandatory = function(frm, label, value, trigger_on) {
    if (!value) {
      frm.doc[trigger_on] = "";
      refresh_field(trigger_on);
      frappe.throw({ message: __("Please enter {0} first", [label]), title: __("Mandatory") });
      return false;
    }
    return true;
  };
  erpnext.utils.get_shipping_address = function(frm, callback) {
    if (frm.doc.company) {
      if (frm.doc.inter_company_order_reference || frm.doc.internal_invoice_reference || frm.doc.internal_order_reference) {
        if (callback) {
          return callback();
        }
      }
      frappe.call({
        method: "erpnext.accounts.custom.address.get_shipping_address",
        args: {
          company: frm.doc.company,
          address: frm.doc.shipping_address
        },
        callback: function(r) {
          if (r.message) {
            frm.set_value("shipping_address", r.message[0]);
            frm.set_value("shipping_address_display", r.message[1]);
          }
          if (callback) {
            return callback();
          }
        }
      });
    } else {
      frappe.msgprint(__("Select company first"));
    }
  };

  // ../erpnext/erpnext/public/js/controllers/stock_controller.js
  frappe.provide("erpnext.stock");
  erpnext.stock.StockController = class StockController extends frappe.ui.form.Controller {
    onload() {
      if (this.frm.fields_dict.company) {
        this.setup_warehouse_query();
      }
    }
    barcode(doc, cdt, cdn) {
      let row = locals[cdt][cdn];
      if (row.barcode) {
        erpnext.stock.utils.set_item_details_using_barcode(this.frm, row, (r) => {
          frappe.model.set_value(cdt, cdn, {
            "item_code": r.message.item_code,
            "qty": 1
          });
        });
      }
    }
    setup_warehouse_query() {
      var me = this;
      erpnext.queries.setup_queries(this.frm, "Warehouse", function() {
        return erpnext.queries.warehouse(me.frm.doc);
      });
    }
    setup_posting_date_time_check() {
      frappe.ui.form.on(this.frm.doctype, "set_posting_date_and_time_read_only", function(frm) {
        if (frm.doc.docstatus == 0 && frm.doc.set_posting_time) {
          frm.set_df_property("posting_date", "read_only", 0);
          frm.set_df_property("posting_time", "read_only", 0);
        } else {
          frm.set_df_property("posting_date", "read_only", 1);
          frm.set_df_property("posting_time", "read_only", 1);
        }
      });
      frappe.ui.form.on(this.frm.doctype, "set_posting_time", function(frm) {
        frm.trigger("set_posting_date_and_time_read_only");
      });
      frappe.ui.form.on(this.frm.doctype, "refresh", function(frm) {
        if (frm.doc.docstatus == 0) {
          if (!frm.doc.posting_date) {
            frm.set_value("posting_date", frappe.datetime.nowdate());
          }
          if (!frm.doc.posting_time) {
            frm.set_value("posting_time", frappe.datetime.now_time());
          }
          frm.trigger("set_posting_date_and_time_read_only");
        }
      });
    }
    show_stock_ledger() {
      var me = this;
      if (this.frm.doc.docstatus > 0) {
        cur_frm.add_custom_button(__("Stock Ledger"), function() {
          frappe.route_options = {
            voucher_no: me.frm.doc.name,
            from_date: me.frm.doc.posting_date,
            to_date: moment(me.frm.doc.modified).format("YYYY-MM-DD"),
            company: me.frm.doc.company,
            show_cancelled_entries: me.frm.doc.docstatus === 2,
            ignore_prepared_report: true
          };
          frappe.set_route("query-report", "Stock Ledger");
        }, __("View"));
      }
    }
    show_general_ledger() {
      var me = this;
      if (this.frm.doc.docstatus > 0) {
        cur_frm.add_custom_button(__("Accounting Ledger"), function() {
          frappe.route_options = {
            voucher_no: me.frm.doc.name,
            from_date: me.frm.doc.posting_date,
            to_date: moment(me.frm.doc.modified).format("YYYY-MM-DD"),
            company: me.frm.doc.company,
            group_by: "Group by Voucher (Consolidated)",
            show_cancelled_entries: me.frm.doc.docstatus === 2,
            ignore_prepared_report: true
          };
          frappe.set_route("query-report", "General Ledger");
        }, __("View"));
      }
    }
  };

  // ../erpnext/erpnext/public/js/payment/payments.js
  erpnext.payments = class payments extends erpnext.stock.StockController {
    make_payment() {
      var me = this;
      this.dialog = new frappe.ui.Dialog({
        title: "Payment"
      });
      this.dialog.show();
      this.$body = this.dialog.body;
      this.set_payment_primary_action();
      this.make_keyboard();
      this.select_text();
    }
    select_text() {
      $(this.$body).find(".form-control").click(function() {
        $(this).select();
      });
    }
    set_payment_primary_action() {
      var me = this;
      this.dialog.set_primary_action(__("Submit"), function() {
        $.each(me.frm.doc.payments, function(index, data) {
          if (data.amount != 0) {
            me.dialog.hide();
            me.submit_invoice();
            return;
          }
        });
      });
    }
    make_keyboard() {
      var me = this;
      $(this.$body).empty();
      $(this.$body).html(frappe.render_template("pos_payment", this.frm.doc));
      this.show_payment_details();
      this.bind_keyboard_event();
      this.clear_amount();
    }
    make_multimode_payment() {
      var me = this;
      if (this.frm.doc.change_amount > 0) {
        me.payment_val = me.doc.outstanding_amount;
      }
      this.payments = frappe.model.add_child(this.frm.doc, "Multi Mode Payment", "payments");
      this.payments.mode_of_payment = this.dialog.fields_dict.mode_of_payment.get_value();
      this.payments.amount = flt(this.payment_val);
    }
    show_payment_details() {
      var me = this;
      var multimode_payments = $(this.$body).find(".multimode-payments").empty();
      if (this.frm.doc.payments.length) {
        $.each(this.frm.doc.payments, function(index, data) {
          $(frappe.render_template("payment_details", {
            mode_of_payment: data.mode_of_payment,
            amount: data.amount,
            idx: data.idx,
            currency: me.frm.doc.currency,
            type: data.type
          })).appendTo(multimode_payments);
          if (data.type == "Cash" && data.amount == me.frm.doc.paid_amount) {
            me.idx = data.idx;
            me.selected_mode = $(me.$body).find(repl("input[idx='%(idx)s']", { idx: me.idx }));
            me.highlight_selected_row();
            me.bind_amount_change_event();
          }
        });
      } else {
        $("<p>No payment mode selected in pos profile</p>").appendTo(multimode_payments);
      }
    }
    set_outstanding_amount() {
      this.selected_mode = $(this.$body).find(repl("input[idx='%(idx)s']", { idx: this.idx }));
      this.highlight_selected_row();
      this.payment_val = 0;
      if (this.frm.doc.outstanding_amount > 0 && flt(this.selected_mode.val()) == 0) {
        this.payment_val = flt(this.frm.doc.outstanding_amount / this.frm.doc.conversion_rate, precision("outstanding_amount"));
        this.selected_mode.val(format_currency(this.payment_val, this.frm.doc.currency));
        this.update_payment_amount();
      } else if (flt(this.selected_mode.val()) > 0) {
        this.payment_val = flt(this.selected_mode.val());
      }
      this.selected_mode.select();
      this.bind_amount_change_event();
    }
    bind_keyboard_event() {
      var me = this;
      this.payment_val = "";
      this.bind_form_control_event();
      this.bind_numeric_keys_event();
    }
    bind_form_control_event() {
      var me = this;
      $(this.$body).find(".pos-payment-row").click(function() {
        me.idx = $(this).attr("idx");
        me.set_outstanding_amount();
      });
      $(this.$body).find(".form-control").click(function() {
        me.idx = $(this).attr("idx");
        me.set_outstanding_amount();
        me.update_paid_amount(true);
      });
      $(this.$body).find(".write_off_amount").change(function() {
        me.write_off_amount(flt($(this).val()), precision("write_off_amount"));
      });
      $(this.$body).find(".change_amount").change(function() {
        me.change_amount(flt($(this).val()), precision("change_amount"));
      });
    }
    highlight_selected_row() {
      var selected_row = $(this.$body).find(repl(".pos-payment-row[idx='%(idx)s']", { idx: this.idx }));
      $(this.$body).find(".pos-payment-row").removeClass("selected-payment-mode");
      selected_row.addClass("selected-payment-mode");
      $(this.$body).find(".amount").attr("disabled", true);
      this.selected_mode.attr("disabled", false);
    }
    bind_numeric_keys_event() {
      var me = this;
      $(this.$body).find(".pos-keyboard-key").click(function() {
        me.payment_val += $(this).text();
        me.selected_mode.val(format_currency(me.payment_val, me.frm.doc.currency));
        me.idx = me.selected_mode.attr("idx");
        me.update_paid_amount();
      });
      $(this.$body).find(".delete-btn").click(function() {
        me.payment_val = cstr(flt(me.selected_mode.val())).slice(0, -1);
        me.selected_mode.val(format_currency(me.payment_val, me.frm.doc.currency));
        me.idx = me.selected_mode.attr("idx");
        me.update_paid_amount();
      });
    }
    bind_amount_change_event() {
      var me = this;
      this.selected_mode.change(function() {
        me.payment_val = flt($(this).val()) || 0;
        me.selected_mode.val(format_currency(me.payment_val, me.frm.doc.currency));
        me.idx = me.selected_mode.attr("idx");
        me.update_payment_amount();
      });
    }
    clear_amount() {
      var me = this;
      $(this.$body).find(".clr").click(function(e) {
        e.stopPropagation();
        me.idx = $(this).attr("idx");
        me.selected_mode = $(me.$body).find(repl("input[idx='%(idx)s']", { idx: me.idx }));
        me.payment_val = 0;
        me.selected_mode.val(0);
        me.highlight_selected_row();
        me.update_payment_amount();
      });
    }
    write_off_amount(write_off_amount) {
      this.frm.doc.write_off_amount = flt(write_off_amount, precision("write_off_amount"));
      this.frm.doc.base_write_off_amount = flt(this.frm.doc.write_off_amount * this.frm.doc.conversion_rate, precision("base_write_off_amount"));
      this.calculate_outstanding_amount(false);
      this.show_amounts();
    }
    change_amount(change_amount) {
      var me = this;
      this.frm.doc.change_amount = flt(change_amount, precision("change_amount"));
      this.calculate_write_off_amount();
      this.show_amounts();
    }
    update_paid_amount(update_write_off) {
      var me = this;
      if (["change_amount", "write_off_amount"].includes(this.idx)) {
        var value = me.selected_mode.val();
        if (me.idx == "change_amount") {
          me.change_amount(value);
        } else {
          if (flt(value) == 0 && update_write_off && me.frm.doc.outstanding_amount > 0) {
            value = flt(me.frm.doc.outstanding_amount / me.frm.doc.conversion_rate, precision(me.idx));
          }
          me.write_off_amount(value);
        }
      } else {
        this.update_payment_amount();
      }
    }
    update_payment_amount() {
      var me = this;
      $.each(this.frm.doc.payments, function(index, data) {
        if (cint(me.idx) == cint(data.idx)) {
          data.amount = flt(me.selected_mode.val(), 2);
        }
      });
      this.calculate_outstanding_amount(false);
      this.show_amounts();
    }
    show_amounts() {
      var me = this;
      $(this.$body).find(".write_off_amount").val(format_currency(this.frm.doc.write_off_amount, this.frm.doc.currency));
      $(this.$body).find(".paid_amount").text(format_currency(this.frm.doc.paid_amount, this.frm.doc.currency));
      $(this.$body).find(".change_amount").val(format_currency(this.frm.doc.change_amount, this.frm.doc.currency));
      $(this.$body).find(".outstanding_amount").text(format_currency(this.frm.doc.outstanding_amount, frappe.get_doc(":Company", this.frm.doc.company).default_currency));
      this.update_invoice();
    }
  };

  // ../erpnext/erpnext/public/js/controllers/taxes_and_totals.js
  erpnext.taxes_and_totals = class TaxesAndTotals extends erpnext.payments {
    setup() {
      this.fetch_round_off_accounts();
    }
    apply_pricing_rule_on_item(item) {
      let effective_item_rate = item.price_list_rate;
      let item_rate = item.rate;
      if (["Sales Order", "Quotation"].includes(item.parenttype) && item.blanket_order_rate) {
        effective_item_rate = item.blanket_order_rate;
      }
      if (item.margin_type == "Percentage") {
        item.rate_with_margin = flt(effective_item_rate) + flt(effective_item_rate) * (flt(item.margin_rate_or_amount) / 100);
      } else {
        item.rate_with_margin = flt(effective_item_rate) + flt(item.margin_rate_or_amount);
      }
      item.base_rate_with_margin = flt(item.rate_with_margin) * flt(this.frm.doc.conversion_rate);
      item_rate = flt(item.rate_with_margin, precision("rate", item));
      if (item.discount_percentage && !item.discount_amount) {
        item.discount_amount = flt(item.rate_with_margin) * flt(item.discount_percentage) / 100;
      }
      if (item.discount_amount) {
        item_rate = flt(item.rate_with_margin - item.discount_amount, precision("rate", item));
        item.discount_percentage = 100 * flt(item.discount_amount) / flt(item.rate_with_margin);
      }
      frappe.model.set_value(item.doctype, item.name, "rate", item_rate);
    }
    async calculate_taxes_and_totals(update_paid_amount) {
      this.discount_amount_applied = false;
      this._calculate_taxes_and_totals();
      this.calculate_discount_amount();
      if (this.frm.doc.apply_discount_on == "Grand Total" && this.frm.doc.is_cash_or_non_trade_discount) {
        this.frm.doc.grand_total -= this.frm.doc.discount_amount;
        this.frm.doc.base_grand_total -= this.frm.doc.base_discount_amount;
        this.frm.doc.rounding_adjustment = 0;
        this.frm.doc.base_rounding_adjustment = 0;
        this.set_rounded_total();
      }
      await this.calculate_shipping_charges();
      if (["Sales Invoice", "POS Invoice", "Purchase Invoice"].includes(this.frm.doc.doctype) && this.frm.doc.docstatus < 2 && !this.frm.doc.is_return) {
        this.calculate_total_advance(update_paid_amount);
      }
      if (["Sales Invoice", "POS Invoice"].includes(this.frm.doc.doctype) && this.frm.doc.is_pos && this.frm.doc.is_return) {
        this.set_total_amount_to_default_mop();
        this.calculate_paid_amount();
      }
      if (["Quotation", "Sales Order", "Delivery Note", "Sales Invoice"].includes(this.frm.doc.doctype)) {
        this.calculate_commission();
        this.calculate_contribution();
      }
      if (this.frm.doc.doctype === "Purchase Invoice" && this.frm.doc.is_return && this.frm.doc.grand_total > this.frm.doc.paid_amount) {
        this.frm.doc.paid_amount = flt(this.frm.doc.grand_total, precision("grand_total"));
      }
      this.frm.refresh_fields();
    }
    calculate_discount_amount() {
      if (frappe.meta.get_docfield(this.frm.doc.doctype, "discount_amount")) {
        this.set_discount_amount();
        this.apply_discount_amount();
      }
    }
    _calculate_taxes_and_totals() {
      const is_quotation = this.frm.doc.doctype == "Quotation";
      this.frm._items = is_quotation ? this.filtered_items() : this.frm.doc.items;
      this.validate_conversion_rate();
      this.calculate_item_values();
      this.initialize_taxes();
      this.determine_exclusive_rate();
      this.calculate_net_total();
      this.calculate_taxes();
      this.manipulate_grand_total_for_inclusive_tax();
      this.calculate_totals();
      this._cleanup();
    }
    validate_conversion_rate() {
      this.frm.doc.conversion_rate = flt(this.frm.doc.conversion_rate, cur_frm ? precision("conversion_rate") : 9);
      var conversion_rate_label = frappe.meta.get_label(this.frm.doc.doctype, "conversion_rate", this.frm.doc.name);
      var company_currency = this.get_company_currency();
      if (!this.frm.doc.conversion_rate) {
        if (this.frm.doc.currency == company_currency) {
          this.frm.set_value("conversion_rate", 1);
        } else {
          const subs = [conversion_rate_label, this.frm.doc.currency, company_currency];
          const err_message = __("{0} is mandatory. Maybe Currency Exchange record is not created for {1} to {2}", subs);
          frappe.throw(err_message);
        }
      }
    }
    calculate_item_values() {
      var me = this;
      if (!this.discount_amount_applied) {
        for (const item of this.frm._items || []) {
          frappe.model.round_floats_in(item);
          item.net_rate = item.rate;
          item.qty = item.qty === void 0 ? me.frm.doc.is_return ? -1 : 1 : item.qty;
          if (!(me.frm.doc.is_return || me.frm.doc.is_debit_note)) {
            item.net_amount = item.amount = flt(item.rate * item.qty, precision("amount", item));
          } else {
            let qty = flt(item.qty);
            if (!qty) {
              qty = me.frm.doc.is_debit_note ? 1 : -1;
              if (me.frm.doc.doctype !== "Purchase Receipt" && me.frm.doc.is_return === 1) {
                qty = flt(item.qty);
              }
            }
            item.net_amount = item.amount = flt(item.rate * qty, precision("amount", item));
          }
          item.item_tax_amount = 0;
          item.total_weight = flt(item.weight_per_unit * item.stock_qty);
          me.set_in_company_currency(item, ["price_list_rate", "rate", "amount", "net_rate", "net_amount"]);
        }
      }
    }
    set_in_company_currency(doc, fields) {
      var me = this;
      $.each(fields, function(i, f) {
        doc["base_" + f] = flt(flt(doc[f], precision(f, doc)) * me.frm.doc.conversion_rate, precision("base_" + f, doc));
      });
    }
    initialize_taxes() {
      var me = this;
      $.each(this.frm.doc["taxes"] || [], function(i, tax) {
        if (!tax.dont_recompute_tax) {
          tax.item_wise_tax_detail = {};
        }
        var tax_fields = [
          "total",
          "tax_amount_after_discount_amount",
          "tax_amount_for_current_item",
          "grand_total_for_current_item",
          "tax_fraction_for_current_item",
          "grand_total_fraction_for_current_item"
        ];
        if (cstr(tax.charge_type) != "Actual" && !(me.discount_amount_applied && me.frm.doc.apply_discount_on == "Grand Total")) {
          tax_fields.push("tax_amount");
        }
        $.each(tax_fields, function(i2, fieldname) {
          tax[fieldname] = 0;
        });
        if (!this.discount_amount_applied && cur_frm) {
          cur_frm.cscript.validate_taxes_and_charges(tax.doctype, tax.name);
          me.validate_inclusive_tax(tax);
        }
        frappe.model.round_floats_in(tax);
      });
    }
    fetch_round_off_accounts() {
      let me = this;
      frappe.flags.round_off_applicable_accounts = [];
      if (me.frm.doc.company) {
        return frappe.call({
          "method": "erpnext.controllers.taxes_and_totals.get_round_off_applicable_accounts",
          "args": {
            "company": me.frm.doc.company,
            "account_list": frappe.flags.round_off_applicable_accounts
          },
          callback(r) {
            if (r.message) {
              frappe.flags.round_off_applicable_accounts.push(...r.message);
            }
          }
        });
      }
    }
    determine_exclusive_rate() {
      var me = this;
      var has_inclusive_tax = false;
      $.each(me.frm.doc["taxes"] || [], function(i, row) {
        if (cint(row.included_in_print_rate))
          has_inclusive_tax = true;
      });
      if (has_inclusive_tax == false)
        return;
      $.each(me.frm._items || [], function(n, item) {
        var item_tax_map = me._load_item_tax_rate(item.item_tax_rate);
        var cumulated_tax_fraction = 0;
        var total_inclusive_tax_amount_per_qty = 0;
        $.each(me.frm.doc["taxes"] || [], function(i, tax) {
          var current_tax_fraction = me.get_current_tax_fraction(tax, item_tax_map);
          tax.tax_fraction_for_current_item = current_tax_fraction[0];
          var inclusive_tax_amount_per_qty = current_tax_fraction[1];
          if (i == 0) {
            tax.grand_total_fraction_for_current_item = 1 + tax.tax_fraction_for_current_item;
          } else {
            tax.grand_total_fraction_for_current_item = me.frm.doc["taxes"][i - 1].grand_total_fraction_for_current_item + tax.tax_fraction_for_current_item;
          }
          cumulated_tax_fraction += tax.tax_fraction_for_current_item;
          total_inclusive_tax_amount_per_qty += inclusive_tax_amount_per_qty * flt(item.qty);
        });
        if (!me.discount_amount_applied && item.qty && (total_inclusive_tax_amount_per_qty || cumulated_tax_fraction)) {
          var amount = flt(item.amount) - total_inclusive_tax_amount_per_qty;
          item.net_amount = flt(amount / (1 + cumulated_tax_fraction));
          item.net_rate = item.qty ? flt(item.net_amount / item.qty, precision("net_rate", item)) : 0;
          me.set_in_company_currency(item, ["net_rate", "net_amount"]);
        }
      });
    }
    get_current_tax_fraction(tax, item_tax_map) {
      var current_tax_fraction = 0;
      var inclusive_tax_amount_per_qty = 0;
      if (cint(tax.included_in_print_rate)) {
        var tax_rate = this._get_tax_rate(tax, item_tax_map);
        if (tax.charge_type == "On Net Total") {
          current_tax_fraction = tax_rate / 100;
        } else if (tax.charge_type == "On Previous Row Amount") {
          current_tax_fraction = tax_rate / 100 * this.frm.doc["taxes"][cint(tax.row_id) - 1].tax_fraction_for_current_item;
        } else if (tax.charge_type == "On Previous Row Total") {
          current_tax_fraction = tax_rate / 100 * this.frm.doc["taxes"][cint(tax.row_id) - 1].grand_total_fraction_for_current_item;
        } else if (tax.charge_type == "On Item Quantity") {
          inclusive_tax_amount_per_qty = flt(tax_rate);
        }
      }
      if (tax.add_deduct_tax && tax.add_deduct_tax == "Deduct") {
        current_tax_fraction *= -1;
        inclusive_tax_amount_per_qty *= -1;
      }
      return [current_tax_fraction, inclusive_tax_amount_per_qty];
    }
    _get_tax_rate(tax, item_tax_map) {
      return Object.keys(item_tax_map).indexOf(tax.account_head) != -1 ? flt(item_tax_map[tax.account_head], precision("rate", tax)) : tax.rate;
    }
    calculate_net_total() {
      var me = this;
      this.frm.doc.total_qty = this.frm.doc.total = this.frm.doc.base_total = this.frm.doc.net_total = this.frm.doc.base_net_total = 0;
      $.each(this.frm._items || [], function(i, item) {
        me.frm.doc.total += item.amount;
        me.frm.doc.total_qty += item.qty;
        me.frm.doc.base_total += item.base_amount;
        me.frm.doc.net_total += item.net_amount;
        me.frm.doc.base_net_total += item.base_net_amount;
      });
    }
    calculate_shipping_charges() {
      if (this.frm.doc.is_pos) {
        return;
      }
      frappe.model.round_floats_in(this.frm.doc, ["total", "base_total", "net_total", "base_net_total"]);
      if (frappe.meta.get_docfield(this.frm.doc.doctype, "shipping_rule", this.frm.doc.name)) {
        return this.shipping_rule();
      }
    }
    add_taxes_from_item_tax_template(item_tax_map) {
      let me = this;
      if (item_tax_map && cint(frappe.defaults.get_default("add_taxes_from_item_tax_template"))) {
        if (typeof item_tax_map == "string") {
          item_tax_map = JSON.parse(item_tax_map);
        }
        $.each(item_tax_map, function(tax, rate) {
          let found = (me.frm.doc.taxes || []).find((d) => d.account_head === tax);
          if (!found) {
            let child = frappe.model.add_child(me.frm.doc, "taxes");
            child.charge_type = "On Net Total";
            child.account_head = tax;
            child.rate = 0;
          }
        });
      }
    }
    calculate_taxes() {
      var me = this;
      this.frm.doc.rounding_adjustment = 0;
      var actual_tax_dict = {};
      $.each(this.frm.doc["taxes"] || [], function(i, tax) {
        if (tax.charge_type == "Actual") {
          actual_tax_dict[tax.idx] = flt(tax.tax_amount, precision("tax_amount", tax));
        }
      });
      $.each(this.frm._items || [], function(n, item) {
        var item_tax_map = me._load_item_tax_rate(item.item_tax_rate);
        $.each(me.frm.doc["taxes"] || [], function(i, tax) {
          var current_tax_amount = me.get_current_tax_amount(item, tax, item_tax_map);
          if (tax.charge_type == "Actual") {
            actual_tax_dict[tax.idx] -= current_tax_amount;
            if (n == me.frm._items.length - 1) {
              current_tax_amount += actual_tax_dict[tax.idx];
            }
          }
          if (tax.charge_type != "Actual" && !(me.discount_amount_applied && me.frm.doc.apply_discount_on == "Grand Total")) {
            tax.tax_amount += current_tax_amount;
          }
          tax.tax_amount_for_current_item = current_tax_amount;
          tax.tax_amount_after_discount_amount += current_tax_amount;
          if (tax.category) {
            current_tax_amount = tax.category == "Valuation" ? 0 : current_tax_amount;
            current_tax_amount *= tax.add_deduct_tax == "Deduct" ? -1 : 1;
          }
          if (i == 0) {
            tax.grand_total_for_current_item = flt(item.net_amount + current_tax_amount);
          } else {
            tax.grand_total_for_current_item = flt(me.frm.doc["taxes"][i - 1].grand_total_for_current_item + current_tax_amount);
          }
          if (n == me.frm._items.length - 1) {
            me.round_off_totals(tax);
            me.set_in_company_currency(tax, ["tax_amount", "tax_amount_after_discount_amount"]);
            me.round_off_base_values(tax);
            me.set_cumulative_total(i, tax);
            me.set_in_company_currency(tax, ["total"]);
            if (i == me.frm.doc["taxes"].length - 1 && me.discount_amount_applied && me.frm.doc.apply_discount_on == "Grand Total" && me.frm.doc.discount_amount) {
              me.frm.doc.rounding_adjustment = flt(me.frm.doc.grand_total - flt(me.frm.doc.discount_amount) - tax.total, precision("rounding_adjustment"));
            }
          }
        });
      });
    }
    set_cumulative_total(row_idx, tax) {
      var tax_amount = tax.tax_amount_after_discount_amount;
      if (tax.category == "Valuation") {
        tax_amount = 0;
      }
      if (tax.add_deduct_tax == "Deduct") {
        tax_amount = -1 * tax_amount;
      }
      if (row_idx == 0) {
        tax.total = flt(this.frm.doc.net_total + tax_amount, precision("total", tax));
      } else {
        tax.total = flt(this.frm.doc["taxes"][row_idx - 1].total + tax_amount, precision("total", tax));
      }
    }
    _load_item_tax_rate(item_tax_rate) {
      return item_tax_rate ? JSON.parse(item_tax_rate) : {};
    }
    get_current_tax_amount(item, tax, item_tax_map) {
      var tax_rate = this._get_tax_rate(tax, item_tax_map);
      var current_tax_amount = 0;
      if (["On Previous Row Amount", "On Previous Row Total"].includes(tax.charge_type)) {
        if (tax.idx === 1) {
          frappe.throw(__("Cannot select charge type as 'On Previous Row Amount' or 'On Previous Row Total' for first row"));
        }
        if (!tax.row_id) {
          tax.row_id = tax.idx - 1;
        }
      }
      if (tax.charge_type == "Actual") {
        var actual = flt(tax.tax_amount, precision("tax_amount", tax));
        current_tax_amount = this.frm.doc.net_total ? item.net_amount / this.frm.doc.net_total * actual : 0;
      } else if (tax.charge_type == "On Net Total") {
        current_tax_amount = tax_rate / 100 * item.net_amount;
      } else if (tax.charge_type == "On Previous Row Amount") {
        current_tax_amount = tax_rate / 100 * this.frm.doc["taxes"][cint(tax.row_id) - 1].tax_amount_for_current_item;
      } else if (tax.charge_type == "On Previous Row Total") {
        current_tax_amount = tax_rate / 100 * this.frm.doc["taxes"][cint(tax.row_id) - 1].grand_total_for_current_item;
      } else if (tax.charge_type == "On Item Quantity") {
        current_tax_amount = tax_rate * item.qty;
      }
      if (!tax.dont_recompute_tax) {
        this.set_item_wise_tax(item, tax, tax_rate, current_tax_amount);
      }
      return current_tax_amount;
    }
    set_item_wise_tax(item, tax, tax_rate, current_tax_amount) {
      let tax_detail = tax.item_wise_tax_detail;
      let key = item.item_code || item.item_name;
      if (typeof tax_detail == "string") {
        tax.item_wise_tax_detail = JSON.parse(tax.item_wise_tax_detail);
        tax_detail = tax.item_wise_tax_detail;
      }
      let item_wise_tax_amount = current_tax_amount * this.frm.doc.conversion_rate;
      if (tax_detail && tax_detail[key])
        item_wise_tax_amount += tax_detail[key][1];
      tax_detail[key] = [tax_rate, flt(item_wise_tax_amount, precision("base_tax_amount", tax))];
    }
    round_off_totals(tax) {
      if (frappe.flags.round_off_applicable_accounts.includes(tax.account_head)) {
        tax.tax_amount = Math.round(tax.tax_amount);
        tax.tax_amount_after_discount_amount = Math.round(tax.tax_amount_after_discount_amount);
      }
      tax.tax_amount = flt(tax.tax_amount, precision("tax_amount", tax));
      tax.tax_amount_after_discount_amount = flt(tax.tax_amount_after_discount_amount, precision("tax_amount", tax));
    }
    round_off_base_values(tax) {
      if (frappe.flags.round_off_applicable_accounts.includes(tax.account_head)) {
        tax.base_tax_amount = Math.round(tax.base_tax_amount);
        tax.base_tax_amount_after_discount_amount = Math.round(tax.base_tax_amount_after_discount_amount);
      }
    }
    manipulate_grand_total_for_inclusive_tax() {
      var me = this;
      if (this.frm.doc["taxes"] && this.frm.doc["taxes"].length) {
        var any_inclusive_tax = false;
        $.each(this.frm.doc.taxes || [], function(i, d) {
          if (cint(d.included_in_print_rate))
            any_inclusive_tax = true;
        });
        if (any_inclusive_tax) {
          var last_tax = me.frm.doc["taxes"].slice(-1)[0];
          var non_inclusive_tax_amount = frappe.utils.sum($.map(this.frm.doc.taxes || [], function(d) {
            if (!d.included_in_print_rate) {
              return flt(d.tax_amount_after_discount_amount);
            }
          }));
          var diff = me.frm.doc.total + non_inclusive_tax_amount - flt(last_tax.total, precision("grand_total"));
          if (me.discount_amount_applied && me.frm.doc.discount_amount) {
            diff -= flt(me.frm.doc.discount_amount);
          }
          diff = flt(diff, precision("rounding_adjustment"));
          if (diff && Math.abs(diff) <= 5 / Math.pow(10, precision("tax_amount", last_tax))) {
            me.frm.doc.rounding_adjustment = diff;
          }
        }
      }
    }
    calculate_totals() {
      var me = this;
      var tax_count = this.frm.doc["taxes"] ? this.frm.doc["taxes"].length : 0;
      this.frm.doc.grand_total = flt(tax_count ? this.frm.doc["taxes"][tax_count - 1].total + flt(this.frm.doc.rounding_adjustment) : this.frm.doc.net_total);
      if (["Quotation", "Sales Order", "Delivery Note", "Sales Invoice", "POS Invoice"].includes(this.frm.doc.doctype)) {
        this.frm.doc.base_grand_total = this.frm.doc.total_taxes_and_charges ? flt(this.frm.doc.grand_total * this.frm.doc.conversion_rate) : this.frm.doc.base_net_total;
      } else {
        this.frm.doc.taxes_and_charges_added = this.frm.doc.taxes_and_charges_deducted = 0;
        if (tax_count) {
          $.each(this.frm.doc["taxes"] || [], function(i, tax) {
            if (["Valuation and Total", "Total"].includes(tax.category)) {
              if (tax.add_deduct_tax == "Add") {
                me.frm.doc.taxes_and_charges_added += flt(tax.tax_amount_after_discount_amount);
              } else {
                me.frm.doc.taxes_and_charges_deducted += flt(tax.tax_amount_after_discount_amount);
              }
            }
          });
          frappe.model.round_floats_in(this.frm.doc, ["taxes_and_charges_added", "taxes_and_charges_deducted"]);
        }
        this.frm.doc.base_grand_total = flt(this.frm.doc.taxes_and_charges_added || this.frm.doc.taxes_and_charges_deducted ? flt(this.frm.doc.grand_total * this.frm.doc.conversion_rate) : this.frm.doc.base_net_total);
        this.set_in_company_currency(this.frm.doc, ["taxes_and_charges_added", "taxes_and_charges_deducted"]);
      }
      this.frm.doc.total_taxes_and_charges = flt(this.frm.doc.grand_total - this.frm.doc.net_total - flt(this.frm.doc.rounding_adjustment), precision("total_taxes_and_charges"));
      this.set_in_company_currency(this.frm.doc, ["total_taxes_and_charges", "rounding_adjustment"]);
      frappe.model.round_floats_in(this.frm.doc, ["grand_total", "base_grand_total"]);
      this.set_rounded_total();
    }
    set_rounded_total() {
      var disable_rounded_total = 0;
      if (frappe.meta.get_docfield(this.frm.doc.doctype, "disable_rounded_total", this.frm.doc.name)) {
        disable_rounded_total = this.frm.doc.disable_rounded_total;
      } else if (frappe.sys_defaults.disable_rounded_total) {
        disable_rounded_total = frappe.sys_defaults.disable_rounded_total;
      }
      if (cint(disable_rounded_total)) {
        this.frm.doc.rounded_total = 0;
        this.frm.doc.base_rounded_total = 0;
        return;
      }
      if (frappe.meta.get_docfield(this.frm.doc.doctype, "rounded_total", this.frm.doc.name)) {
        this.frm.doc.rounded_total = round_based_on_smallest_currency_fraction(this.frm.doc.grand_total, this.frm.doc.currency, precision("rounded_total"));
        this.frm.doc.rounding_adjustment += flt(this.frm.doc.rounded_total - this.frm.doc.grand_total, precision("rounding_adjustment"));
        this.set_in_company_currency(this.frm.doc, ["rounding_adjustment", "rounded_total"]);
      }
    }
    _cleanup() {
      this.frm.doc.base_in_words = this.frm.doc.in_words = "";
      let items = this.frm._items;
      if (items && items.length) {
        if (!frappe.meta.get_docfield(items[0].doctype, "item_tax_amount", this.frm.doctype)) {
          $.each(items || [], function(i, item) {
            delete item["item_tax_amount"];
          });
        }
      }
      if (this.frm.doc["taxes"] && this.frm.doc["taxes"].length) {
        var temporary_fields = [
          "tax_amount_for_current_item",
          "grand_total_for_current_item",
          "tax_fraction_for_current_item",
          "grand_total_fraction_for_current_item"
        ];
        if (!frappe.meta.get_docfield(this.frm.doc["taxes"][0].doctype, "tax_amount_after_discount_amount", this.frm.doctype)) {
          temporary_fields.push("tax_amount_after_discount_amount");
        }
        $.each(this.frm.doc["taxes"] || [], function(i, tax) {
          $.each(temporary_fields, function(i2, fieldname) {
            delete tax[fieldname];
          });
          if (!tax.dont_recompute_tax) {
            tax.item_wise_tax_detail = JSON.stringify(tax.item_wise_tax_detail);
          }
        });
      }
    }
    set_discount_amount() {
      if (this.frm.doc.additional_discount_percentage) {
        this.frm.doc.discount_amount = flt(flt(this.frm.doc[frappe.scrub(this.frm.doc.apply_discount_on)]) * this.frm.doc.additional_discount_percentage / 100, precision("discount_amount"));
      }
    }
    apply_discount_amount() {
      var me = this;
      var distributed_amount = 0;
      this.frm.doc.base_discount_amount = 0;
      if (this.frm.doc.discount_amount) {
        if (!this.frm.doc.apply_discount_on)
          frappe.throw(__("Please select Apply Discount On"));
        this.frm.doc.base_discount_amount = flt(this.frm.doc.discount_amount * this.frm.doc.conversion_rate, precision("base_discount_amount"));
        if (this.frm.doc.apply_discount_on == "Grand Total" && this.frm.doc.is_cash_or_non_trade_discount) {
          return;
        }
        var total_for_discount_amount = this.get_total_for_discount_amount();
        var net_total = 0;
        if (total_for_discount_amount) {
          $.each(this.frm._items || [], function(i, item) {
            distributed_amount = flt(me.frm.doc.discount_amount) * item.net_amount / total_for_discount_amount;
            item.net_amount = flt(item.net_amount - distributed_amount, precision("base_amount", item));
            net_total += item.net_amount;
            if ((!(me.frm.doc.taxes || []).length || total_for_discount_amount == me.frm.doc.net_total || me.frm.doc.apply_discount_on == "Net Total") && i == (me.frm._items || []).length - 1) {
              var discount_amount_loss = flt(me.frm.doc.net_total - net_total - me.frm.doc.discount_amount, precision("net_total"));
              item.net_amount = flt(item.net_amount + discount_amount_loss, precision("net_amount", item));
            }
            item.net_rate = item.qty ? flt(item.net_amount / item.qty, precision("net_rate", item)) : 0;
            me.set_in_company_currency(item, ["net_rate", "net_amount"]);
          });
          this.discount_amount_applied = true;
          this._calculate_taxes_and_totals();
        }
      }
    }
    get_total_for_discount_amount() {
      if (this.frm.doc.apply_discount_on == "Net Total") {
        return this.frm.doc.net_total;
      } else {
        var total_actual_tax = 0;
        var actual_taxes_dict = {};
        $.each(this.frm.doc["taxes"] || [], function(i, tax) {
          if (["Actual", "On Item Quantity"].includes(tax.charge_type)) {
            var tax_amount = tax.category == "Valuation" ? 0 : tax.tax_amount;
            tax_amount *= tax.add_deduct_tax == "Deduct" ? -1 : 1;
            actual_taxes_dict[tax.idx] = tax_amount;
          } else if (actual_taxes_dict[tax.row_id] !== null) {
            var actual_tax_amount = flt(actual_taxes_dict[tax.row_id]) * flt(tax.rate) / 100;
            actual_taxes_dict[tax.idx] = actual_tax_amount;
          }
        });
        $.each(actual_taxes_dict, function(key, value) {
          if (value)
            total_actual_tax += value;
        });
        return flt(this.frm.doc.grand_total - total_actual_tax, precision("grand_total"));
      }
    }
    calculate_total_advance(update_paid_amount) {
      var total_allocated_amount = frappe.utils.sum($.map(this.frm.doc["advances"] || [], function(adv) {
        return flt(adv.allocated_amount, precision("allocated_amount", adv));
      }));
      this.frm.doc.total_advance = flt(total_allocated_amount, precision("total_advance"));
      if (this.frm.doc.write_off_outstanding_amount_automatically) {
        this.frm.doc.write_off_amount = 0;
      }
      this.calculate_outstanding_amount(update_paid_amount);
      this.calculate_write_off_amount();
    }
    is_internal_invoice() {
      if (["Sales Invoice", "Purchase Invoice"].includes(this.frm.doc.doctype)) {
        if (this.frm.doc.company === this.frm.doc.represents_company) {
          return true;
        }
      }
      return false;
    }
    calculate_outstanding_amount(update_paid_amount) {
      if (["Sales Invoice", "POS Invoice"].includes(this.frm.doc.doctype) && this.frm.doc.is_return) {
        this.calculate_paid_amount();
      }
      if (this.frm.doc.is_return || this.frm.doc.docstatus > 0 || this.is_internal_invoice())
        return;
      frappe.model.round_floats_in(this.frm.doc, ["grand_total", "total_advance", "write_off_amount"]);
      if (["Sales Invoice", "POS Invoice", "Purchase Invoice"].includes(this.frm.doc.doctype)) {
        let grand_total = this.frm.doc.rounded_total || this.frm.doc.grand_total;
        let base_grand_total = this.frm.doc.base_rounded_total || this.frm.doc.base_grand_total;
        if (this.frm.doc.party_account_currency == this.frm.doc.currency) {
          var total_amount_to_pay = flt(grand_total - this.frm.doc.total_advance - this.frm.doc.write_off_amount, precision("grand_total"));
        } else {
          var total_amount_to_pay = flt(flt(base_grand_total, precision("base_grand_total")) - this.frm.doc.total_advance - this.frm.doc.base_write_off_amount, precision("base_grand_total"));
        }
        frappe.model.round_floats_in(this.frm.doc, ["paid_amount"]);
        this.set_in_company_currency(this.frm.doc, ["paid_amount"]);
        if (this.frm.refresh_field) {
          this.frm.refresh_field("paid_amount");
          this.frm.refresh_field("base_paid_amount");
        }
        if (["Sales Invoice", "POS Invoice"].includes(this.frm.doc.doctype)) {
          let total_amount_for_payment = this.frm.doc.redeem_loyalty_points && this.frm.doc.loyalty_amount ? flt(total_amount_to_pay - this.frm.doc.loyalty_amount, precision("base_grand_total")) : total_amount_to_pay;
          this.set_default_payment(total_amount_for_payment, update_paid_amount);
          this.calculate_paid_amount();
        }
        this.calculate_change_amount();
        var paid_amount = this.frm.doc.party_account_currency == this.frm.doc.currency ? this.frm.doc.paid_amount : this.frm.doc.base_paid_amount;
        this.frm.doc.outstanding_amount = flt(total_amount_to_pay - flt(paid_amount) + flt(this.frm.doc.change_amount * this.frm.doc.conversion_rate), precision("outstanding_amount"));
      }
    }
    set_total_amount_to_default_mop() {
      let grand_total = this.frm.doc.rounded_total || this.frm.doc.grand_total;
      let base_grand_total = this.frm.doc.base_rounded_total || this.frm.doc.base_grand_total;
      if (this.frm.doc.party_account_currency == this.frm.doc.currency) {
        var total_amount_to_pay = flt(grand_total - this.frm.doc.total_advance - this.frm.doc.write_off_amount, precision("grand_total"));
      } else {
        var total_amount_to_pay = flt(flt(base_grand_total, precision("base_grand_total")) - this.frm.doc.total_advance - this.frm.doc.base_write_off_amount, precision("base_grand_total"));
      }
      if (!this.frm.doc.is_return) {
        this.frm.doc.payments.find((payment) => {
          if (payment.default) {
            payment.amount = total_amount_to_pay;
          }
        });
      }
      this.frm.refresh_fields();
    }
    set_default_payment(total_amount_to_pay, update_paid_amount) {
      var me = this;
      var payment_status = true;
      if (this.frm.doc.is_pos && (update_paid_amount === void 0 || update_paid_amount)) {
        $.each(this.frm.doc["payments"] || [], function(index, data) {
          if (data.default && payment_status && total_amount_to_pay > 0) {
            let base_amount, amount;
            if (me.frm.doc.party_account_currency == me.frm.doc.currency) {
              base_amount = flt(total_amount_to_pay * me.frm.doc.conversion_rate, precision("base_amount", data));
              amount = flt(total_amount_to_pay, precision("amount", data));
            } else {
              base_amount = flt(total_amount_to_pay, precision("base_amount", data));
              amount = flt(total_amount_to_pay / me.frm.doc.conversion_rate, precision("amount", data));
            }
            frappe.model.set_value(data.doctype, data.name, "base_amount", base_amount);
            frappe.model.set_value(data.doctype, data.name, "amount", amount);
            payment_status = false;
          } else if (me.frm.doc.paid_amount) {
            frappe.model.set_value(data.doctype, data.name, "amount", 0);
          }
        });
      }
    }
    calculate_paid_amount() {
      var me = this;
      var paid_amount = 0;
      var base_paid_amount = 0;
      if (this.frm.doc.is_pos) {
        $.each(this.frm.doc["payments"] || [], function(index, data) {
          data.base_amount = flt(data.amount * me.frm.doc.conversion_rate, precision("base_amount", data));
          paid_amount += data.amount;
          base_paid_amount += data.base_amount;
        });
      } else if (!this.frm.doc.is_return) {
        this.frm.doc.payments = [];
      }
      if (this.frm.doc.redeem_loyalty_points && this.frm.doc.loyalty_amount) {
        base_paid_amount += this.frm.doc.loyalty_amount;
        paid_amount += flt(this.frm.doc.loyalty_amount / me.frm.doc.conversion_rate, precision("paid_amount"));
      }
      this.frm.set_value("paid_amount", flt(paid_amount, precision("paid_amount")));
      this.frm.set_value("base_paid_amount", flt(base_paid_amount, precision("base_paid_amount")));
    }
    calculate_change_amount() {
      this.frm.doc.change_amount = 0;
      this.frm.doc.base_change_amount = 0;
      if (["Sales Invoice", "POS Invoice"].includes(this.frm.doc.doctype) && this.frm.doc.paid_amount > this.frm.doc.grand_total && !this.frm.doc.is_return) {
        var payment_types = $.map(this.frm.doc.payments, function(d) {
          return d.type;
        });
        if (in_list(payment_types, "Cash")) {
          var grand_total = this.frm.doc.rounded_total || this.frm.doc.grand_total;
          var base_grand_total = this.frm.doc.base_rounded_total || this.frm.doc.base_grand_total;
          this.frm.doc.change_amount = flt(this.frm.doc.paid_amount - grand_total, precision("change_amount"));
          this.frm.doc.base_change_amount = flt(this.frm.doc.base_paid_amount - base_grand_total, precision("base_change_amount"));
        }
      }
    }
    calculate_write_off_amount() {
      if (this.frm.doc.write_off_outstanding_amount_automatically) {
        this.frm.doc.write_off_amount = flt(this.frm.doc.outstanding_amount, precision("write_off_amount"));
        this.frm.doc.base_write_off_amount = flt(this.frm.doc.write_off_amount * this.frm.doc.conversion_rate, precision("base_write_off_amount"));
        this.calculate_outstanding_amount(false);
      }
    }
    filtered_items() {
      return this.frm.doc.items.filter((item) => !item["is_alternative"]);
    }
  };

  // ../erpnext/erpnext/public/js/controllers/transaction.js
  erpnext.TransactionController = class TransactionController extends erpnext.taxes_and_totals {
    setup() {
      super.setup();
      let me = this;
      frappe.flags.hide_serial_batch_dialog = true;
      frappe.ui.form.on(this.frm.doctype + " Item", "rate", function(frm, cdt, cdn) {
        var item = frappe.get_doc(cdt, cdn);
        var has_margin_field = frappe.meta.has_field(cdt, "margin_type");
        frappe.model.round_floats_in(item, ["rate", "price_list_rate"]);
        if (item.price_list_rate) {
          if (item.rate > item.price_list_rate && has_margin_field) {
            item.discount_percentage = 0;
            item.margin_type = "Amount";
            item.margin_rate_or_amount = flt(item.rate - item.price_list_rate, precision("margin_rate_or_amount", item));
            item.rate_with_margin = item.rate;
          } else {
            item.discount_percentage = flt((1 - item.rate / item.price_list_rate) * 100, precision("discount_percentage", item));
            item.discount_amount = flt(item.price_list_rate) - flt(item.rate);
            item.margin_type = "";
            item.margin_rate_or_amount = 0;
            item.rate_with_margin = 0;
          }
        } else {
          item.discount_percentage = 0;
          item.margin_type = "";
          item.margin_rate_or_amount = 0;
          item.rate_with_margin = 0;
        }
        item.base_rate_with_margin = item.rate_with_margin * flt(frm.doc.conversion_rate);
        cur_frm.cscript.set_gross_profit(item);
        cur_frm.cscript.calculate_taxes_and_totals();
        cur_frm.cscript.calculate_stock_uom_rate(frm, cdt, cdn);
      });
      frappe.ui.form.on(this.frm.cscript.tax_table, "rate", function(frm, cdt, cdn) {
        cur_frm.cscript.calculate_taxes_and_totals();
      });
      frappe.ui.form.on(this.frm.cscript.tax_table, "tax_amount", function(frm, cdt, cdn) {
        cur_frm.cscript.calculate_taxes_and_totals();
      });
      frappe.ui.form.on(this.frm.cscript.tax_table, "row_id", function(frm, cdt, cdn) {
        cur_frm.cscript.calculate_taxes_and_totals();
      });
      frappe.ui.form.on(this.frm.cscript.tax_table, "included_in_print_rate", function(frm, cdt, cdn) {
        cur_frm.cscript.set_dynamic_labels();
        cur_frm.cscript.calculate_taxes_and_totals();
      });
      frappe.ui.form.on(this.frm.doctype, "apply_discount_on", function(frm) {
        if (frm.doc.additional_discount_percentage) {
          frm.trigger("additional_discount_percentage");
        } else {
          cur_frm.cscript.calculate_taxes_and_totals();
        }
      });
      frappe.ui.form.on(this.frm.doctype, "additional_discount_percentage", function(frm) {
        if (!frm.doc.apply_discount_on) {
          frappe.msgprint(__("Please set 'Apply Additional Discount On'"));
          return;
        }
        frm.via_discount_percentage = true;
        if (frm.doc.additional_discount_percentage && frm.doc.discount_amount) {
          frm.doc.discount_amount = 0;
          frm.cscript.calculate_taxes_and_totals();
        }
        var total = flt(frm.doc[frappe.model.scrub(frm.doc.apply_discount_on)]);
        var discount_amount = flt(total * flt(frm.doc.additional_discount_percentage) / 100, precision("discount_amount"));
        frm.set_value("discount_amount", discount_amount).then(() => delete frm.via_discount_percentage);
      });
      frappe.ui.form.on(this.frm.doctype, "discount_amount", function(frm) {
        frm.cscript.set_dynamic_labels();
        if (!frm.via_discount_percentage) {
          frm.doc.additional_discount_percentage = 0;
        }
        frm.cscript.calculate_taxes_and_totals();
      });
      frappe.ui.form.on(this.frm.doctype + " Item", {
        items_add: function(frm, cdt, cdn) {
          var item = frappe.get_doc(cdt, cdn);
          if (!item.warehouse && frm.doc.set_warehouse) {
            item.warehouse = frm.doc.set_warehouse;
          }
          if (!item.target_warehouse && frm.doc.set_target_warehouse) {
            item.target_warehouse = frm.doc.set_target_warehouse;
          }
          if (!item.from_warehouse && frm.doc.set_from_warehouse) {
            item.from_warehouse = frm.doc.set_from_warehouse;
          }
          erpnext.accounts.dimensions.copy_dimension_from_first_row(frm, cdt, cdn, "items");
        }
      });
      if (this.frm.fields_dict["items"].grid.get_field("batch_no")) {
        this.frm.set_query("batch_no", "items", function(doc, cdt, cdn) {
          return me.set_query_for_batch(doc, cdt, cdn);
        });
      }
      if (this.frm.docstatus < 2 && this.frm.fields_dict["payment_terms_template"] && this.frm.fields_dict["payment_schedule"] && this.frm.doc.payment_terms_template && !this.frm.doc.payment_schedule.length) {
        this.frm.trigger("payment_terms_template");
      }
      if (this.frm.fields_dict["taxes"]) {
        this["taxes_remove"] = this.calculate_taxes_and_totals;
      }
      if (this.frm.fields_dict["items"]) {
        this["items_remove"] = this.process_item_removal;
      }
      if (this.frm.fields_dict["recurring_print_format"]) {
        this.frm.set_query("recurring_print_format", function(doc) {
          return {
            filters: [
              ["Print Format", "doc_type", "=", cur_frm.doctype]
            ]
          };
        });
      }
      if (this.frm.fields_dict["return_against"]) {
        this.frm.set_query("return_against", function(doc) {
          var filters = {
            "docstatus": 1,
            "is_return": 0,
            "company": doc.company
          };
          if (me.frm.fields_dict["customer"] && doc.customer)
            filters["customer"] = doc.customer;
          if (me.frm.fields_dict["supplier"] && doc.supplier)
            filters["supplier"] = doc.supplier;
          return {
            filters
          };
        });
      }
      if (this.frm.fields_dict["items"].grid.get_field("expense_account")) {
        this.frm.set_query("expense_account", "items", function(doc) {
          return {
            filters: {
              "company": doc.company,
              "report_type": "Profit and Loss",
              "is_group": 0
            }
          };
        });
      }
      if (frappe.meta.get_docfield(this.frm.doc.doctype, "pricing_rules")) {
        this.frm.set_indicator_formatter("pricing_rule", function(doc) {
          return doc.rule_applied ? "green" : "red";
        });
      }
      if (this.frm.fields_dict["items"].grid.get_field("blanket_order")) {
        this.frm.set_query("blanket_order", "items", function(doc, cdt, cdn) {
          var item = locals[cdt][cdn];
          return {
            query: "erpnext.controllers.queries.get_blanket_orders",
            filters: {
              "company": doc.company,
              "blanket_order_type": doc.doctype === "Sales Order" ? "Selling" : "Purchasing",
              "item": item.item_code
            }
          };
        });
      }
      if (this.frm.fields_dict.taxes_and_charges) {
        this.frm.set_query("taxes_and_charges", function() {
          return {
            filters: [
              ["company", "=", me.frm.doc.company],
              ["docstatus", "!=", 2]
            ]
          };
        });
      }
    }
    onload() {
      var me = this;
      if (this.frm.doc.__islocal) {
        var currency = frappe.defaults.get_user_default("currency");
        let set_value = (fieldname, value) => {
          if (me.frm.fields_dict[fieldname] && !me.frm.doc[fieldname]) {
            return me.frm.set_value(fieldname, value);
          }
        };
        this.frm.trigger("set_default_internal_warehouse");
        return frappe.run_serially([
          () => set_value("currency", currency),
          () => set_value("price_list_currency", currency),
          () => set_value("status", "Draft"),
          () => set_value("is_subcontracted", 0),
          () => {
            if (this.frm.doc.company && !this.frm.doc.amended_from) {
              this.frm.trigger("company");
            }
          }
        ]);
      }
      if (this.frm.fields_dict["items"].grid.get_field("batch_no")) {
        let batch_field = this.frm.get_docfield("items", "batch_no");
        if (batch_field) {
          batch_field.get_route_options_for_new_doc = (row) => {
            return {
              "item": row.doc.item_code
            };
          };
        }
      }
    }
    is_return() {
      if (!this.frm.doc.is_return && this.frm.doc.return_against) {
        this.frm.set_value("return_against", "");
      }
    }
    setup_quality_inspection() {
      if (!["Delivery Note", "Sales Invoice", "Purchase Receipt", "Purchase Invoice"].includes(this.frm.doc.doctype)) {
        return;
      }
      const me = this;
      if (!this.frm.is_new() && this.frm.doc.docstatus === 0 && frappe.model.can_create("Quality Inspection")) {
        this.frm.add_custom_button(__("Quality Inspection(s)"), () => {
          me.make_quality_inspection();
        }, __("Create"));
        this.frm.page.set_inner_btn_group_as_primary(__("Create"));
      }
      const inspection_type = ["Purchase Receipt", "Purchase Invoice"].includes(this.frm.doc.doctype) ? "Incoming" : "Outgoing";
      let quality_inspection_field = this.frm.get_docfield("items", "quality_inspection");
      quality_inspection_field.get_route_options_for_new_doc = function(row) {
        if (me.frm.is_new())
          return;
        return {
          "inspection_type": inspection_type,
          "reference_type": me.frm.doc.doctype,
          "reference_name": me.frm.doc.name,
          "item_code": row.doc.item_code,
          "description": row.doc.description,
          "item_serial_no": row.doc.serial_no ? row.doc.serial_no.split("\n")[0] : null,
          "batch_no": row.doc.batch_no
        };
      };
      this.frm.set_query("quality_inspection", "items", function(doc, cdt, cdn) {
        let d = locals[cdt][cdn];
        return {
          filters: {
            docstatus: 1,
            inspection_type,
            reference_name: doc.name,
            item_code: d.item_code
          }
        };
      });
    }
    make_payment_request() {
      let me = this;
      const payment_request_type = ["Sales Order", "Sales Invoice"].includes(this.frm.doc.doctype) ? "Inward" : "Outward";
      frappe.call({
        method: "erpnext.accounts.doctype.payment_request.payment_request.make_payment_request",
        args: {
          dt: me.frm.doc.doctype,
          dn: me.frm.doc.name,
          recipient_id: me.frm.doc.contact_email,
          payment_request_type,
          party_type: payment_request_type == "Outward" ? "Supplier" : "Customer",
          party: payment_request_type == "Outward" ? me.frm.doc.supplier : me.frm.doc.customer
        },
        callback: function(r) {
          if (!r.exc) {
            frappe.model.sync(r.message);
            frappe.set_route("Form", r.message.doctype, r.message.name);
          }
        }
      });
    }
    onload_post_render() {
      var _a;
      if (this.frm.doc.__islocal && !(this.frm.doc.taxes || []).length && !((_a = this.frm.doc.__onload) == null ? void 0 : _a.load_after_mapping)) {
        frappe.after_ajax(() => this.apply_default_taxes());
      } else if (this.frm.doc.__islocal && this.frm.doc.company && this.frm.doc["items"] && !this.frm.doc.is_pos) {
        frappe.after_ajax(() => this.calculate_taxes_and_totals());
      }
      if (frappe.meta.get_docfield(this.frm.doc.doctype + " Item", "item_code")) {
        this.setup_item_selector();
        this.frm.get_field("items").grid.set_multiple_add("item_code", "qty");
      }
    }
    refresh() {
      erpnext.toggle_naming_series();
      erpnext.hide_company();
      this.set_dynamic_labels();
      this.setup_sms();
      this.setup_quality_inspection();
      this.validate_has_items();
    }
    scan_barcode() {
      const barcode_scanner = new erpnext.utils.BarcodeScanner({ frm: this.frm });
      barcode_scanner.process_scan();
    }
    barcode(doc, cdt, cdn) {
      let row = locals[cdt][cdn];
      if (row.barcode) {
        erpnext.stock.utils.set_item_details_using_barcode(this.frm, row, (r) => {
          debugger;
          frappe.model.set_value(cdt, cdn, {
            "item_code": r.message.item_code,
            "qty": 1
          });
        });
      }
    }
    validate_has_items() {
      let table = this.frm.doc.items;
      this.frm.has_items = table && table.length && table[0].qty && table[0].item_code;
    }
    apply_default_taxes() {
      var me = this;
      var taxes_and_charges_field = frappe.meta.get_docfield(me.frm.doc.doctype, "taxes_and_charges", me.frm.doc.name);
      if (!this.frm.doc.taxes_and_charges && this.frm.doc.taxes && this.frm.doc.taxes.length > 0) {
        return;
      }
      if (taxes_and_charges_field) {
        return frappe.call({
          method: "erpnext.controllers.accounts_controller.get_default_taxes_and_charges",
          args: {
            "master_doctype": taxes_and_charges_field.options,
            "tax_template": me.frm.doc.taxes_and_charges || "",
            "company": me.frm.doc.company
          },
          debounce: 2e3,
          callback: function(r) {
            if (!r.exc && r.message) {
              frappe.run_serially([
                () => {
                  if (r.message.taxes_and_charges) {
                    me.frm.doc.taxes_and_charges = r.message.taxes_and_charges;
                  }
                  if (r.message.taxes) {
                    me.frm.set_value("taxes", r.message.taxes);
                  }
                },
                () => me.set_dynamic_labels(),
                () => me.calculate_taxes_and_totals()
              ]);
            }
          }
        });
      }
    }
    setup_sms() {
      var me = this;
      let blacklist = ["Purchase Invoice", "BOM"];
      if (this.frm.doc.docstatus === 1 && !["Lost", "Stopped", "Closed"].includes(this.frm.doc.status) && !blacklist.includes(this.frm.doctype)) {
        this.frm.page.add_menu_item(__("Send SMS"), function() {
          me.send_sms();
        });
      }
    }
    send_sms() {
      var sms_man = new erpnext.SMSManager(this.frm.doc);
    }
    item_code(doc, cdt, cdn) {
      var me = this;
      var item = frappe.get_doc(cdt, cdn);
      var update_stock = 0, show_batch_dialog = 0;
      item.weight_per_unit = 0;
      item.weight_uom = "";
      item.conversion_factor = 0;
      if (["Sales Invoice"].includes(this.frm.doc.doctype)) {
        update_stock = cint(me.frm.doc.update_stock);
        show_batch_dialog = update_stock;
      } else if (this.frm.doc.doctype === "Purchase Receipt" && me.frm.doc.is_return || this.frm.doc.doctype === "Delivery Note") {
        show_batch_dialog = 1;
      }
      item.barcode = null;
      if (item.item_code || item.serial_no) {
        if (!this.validate_company_and_party()) {
          this.frm.fields_dict["items"].grid.grid_rows[item.idx - 1].remove();
        } else {
          item.pricing_rules = "";
          return this.frm.call({
            method: "erpnext.stock.get_item_details.get_item_details",
            child: item,
            args: {
              doc: me.frm.doc,
              args: {
                item_code: item.item_code,
                barcode: item.barcode,
                serial_no: item.serial_no,
                batch_no: item.batch_no,
                set_warehouse: me.frm.doc.set_warehouse,
                warehouse: item.warehouse,
                customer: me.frm.doc.customer || me.frm.doc.party_name,
                quotation_to: me.frm.doc.quotation_to,
                supplier: me.frm.doc.supplier,
                currency: me.frm.doc.currency,
                update_stock,
                conversion_rate: me.frm.doc.conversion_rate,
                price_list: me.frm.doc.selling_price_list || me.frm.doc.buying_price_list,
                price_list_currency: me.frm.doc.price_list_currency,
                plc_conversion_rate: me.frm.doc.plc_conversion_rate,
                company: me.frm.doc.company,
                order_type: me.frm.doc.order_type,
                is_pos: cint(me.frm.doc.is_pos),
                is_return: cint(me.frm.doc.is_return),
                is_subcontracted: me.frm.doc.is_subcontracted,
                ignore_pricing_rule: me.frm.doc.ignore_pricing_rule,
                doctype: me.frm.doc.doctype,
                name: me.frm.doc.name,
                project: item.project || me.frm.doc.project,
                qty: item.qty || 1,
                net_rate: item.rate,
                stock_qty: item.stock_qty,
                conversion_factor: item.conversion_factor,
                weight_per_unit: item.weight_per_unit,
                uom: item.uom,
                weight_uom: item.weight_uom,
                manufacturer: item.manufacturer,
                stock_uom: item.stock_uom,
                pos_profile: cint(me.frm.doc.is_pos) ? me.frm.doc.pos_profile : "",
                cost_center: item.cost_center,
                tax_category: me.frm.doc.tax_category,
                item_tax_template: item.item_tax_template,
                child_doctype: item.doctype,
                child_docname: item.name,
                is_old_subcontracting_flow: me.frm.doc.is_old_subcontracting_flow
              }
            },
            callback: function(r) {
              if (!r.exc) {
                frappe.run_serially([
                  () => {
                    var d = locals[cdt][cdn];
                    me.add_taxes_from_item_tax_template(d.item_tax_rate);
                    if (d.free_item_data && d.free_item_data.length > 0) {
                      me.apply_product_discount(d);
                    }
                  },
                  () => {
                    if ((me.frm.doc.is_internal_customer || me.frm.doc.is_internal_supplier) && me.frm.doc.represents_company === me.frm.doc.company) {
                      me.get_incoming_rate(item, me.frm.posting_date, me.frm.posting_time, me.frm.doc.doctype, me.frm.doc.company);
                    } else {
                      me.frm.script_manager.trigger("price_list_rate", cdt, cdn);
                    }
                  },
                  () => {
                    if (me.frm.doc.is_internal_customer || me.frm.doc.is_internal_supplier) {
                      me.calculate_taxes_and_totals();
                    }
                  },
                  () => me.toggle_conversion_factor(item),
                  () => {
                    if (show_batch_dialog)
                      return frappe.db.get_value("Item", item.item_code, ["has_batch_no", "has_serial_no"]).then((r2) => {
                        if (r2.message && (r2.message.has_batch_no || r2.message.has_serial_no)) {
                          frappe.flags.hide_serial_batch_dialog = false;
                        }
                      });
                  },
                  () => {
                    if (show_batch_dialog && !frappe.flags.hide_serial_batch_dialog)
                      return frappe.db.get_single_value("Stock Settings", "disable_serial_no_and_batch_selector").then((value) => {
                        if (value) {
                          frappe.flags.hide_serial_batch_dialog = true;
                        }
                      });
                  },
                  () => {
                    if (show_batch_dialog && !frappe.flags.hide_serial_batch_dialog) {
                      var d = locals[cdt][cdn];
                      $.each(r.message, function(k, v) {
                        if (!d[k])
                          d[k] = v;
                      });
                      if (d.has_batch_no && d.has_serial_no) {
                        d.batch_no = void 0;
                      }
                      erpnext.show_serial_batch_selector(me.frm, d, (item2) => {
                        me.frm.script_manager.trigger("qty", item2.doctype, item2.name);
                        if (!me.frm.doc.set_warehouse)
                          me.frm.script_manager.trigger("warehouse", item2.doctype, item2.name);
                        me.apply_price_list(item2, true);
                      }, void 0, !frappe.flags.hide_serial_batch_dialog);
                    }
                  },
                  () => me.conversion_factor(doc, cdt, cdn, true),
                  () => me.remove_pricing_rule(item),
                  () => {
                    if (item.apply_rule_on_other_items) {
                      let key = item.name;
                      me.apply_rule_on_other_items({ key: item });
                    }
                  },
                  () => {
                    var company_currency = me.get_company_currency();
                    me.update_item_grid_labels(company_currency);
                  }
                ]);
              }
            }
          });
        }
      }
    }
    price_list_rate(doc, cdt, cdn) {
      var item = frappe.get_doc(cdt, cdn);
      frappe.model.round_floats_in(item, ["price_list_rate", "discount_percentage"]);
      if (in_list(["Quotation Item", "Sales Order Item", "Delivery Note Item", "Sales Invoice Item", "POS Invoice Item", "Purchase Invoice Item", "Purchase Order Item", "Purchase Receipt Item"]), cdt)
        this.apply_pricing_rule_on_item(item);
      else
        item.rate = flt(item.price_list_rate * (1 - item.discount_percentage / 100), precision("rate", item));
      this.calculate_taxes_and_totals();
    }
    margin_rate_or_amount(doc, cdt, cdn) {
      let item = frappe.get_doc(cdt, cdn);
      this.apply_pricing_rule_on_item(item);
      this.calculate_taxes_and_totals();
      cur_frm.refresh_fields();
    }
    margin_type(doc, cdt, cdn) {
      let item = frappe.get_doc(cdt, cdn);
      if (!item.margin_type) {
        frappe.model.set_value(cdt, cdn, "margin_rate_or_amount", 0);
      } else {
        this.apply_pricing_rule_on_item(item, doc, cdt, cdn);
        this.calculate_taxes_and_totals();
        cur_frm.refresh_fields();
      }
    }
    get_incoming_rate(item, posting_date, posting_time, voucher_type, company) {
      let item_args = {
        "item_code": item.item_code,
        "warehouse": in_list("Purchase Receipt", "Purchase Invoice") ? item.from_warehouse : item.warehouse,
        "posting_date": posting_date,
        "posting_time": posting_time,
        "qty": item.qty * item.conversion_factor,
        "serial_no": item.serial_no,
        "batch_no": item.batch_no,
        "voucher_type": voucher_type,
        "company": company,
        "allow_zero_valuation_rate": item.allow_zero_valuation_rate
      };
      frappe.call({
        method: "erpnext.stock.utils.get_incoming_rate",
        args: {
          args: item_args
        },
        callback: function(r) {
          frappe.model.set_value(item.doctype, item.name, "rate", r.message * item.conversion_factor);
        }
      });
    }
    add_taxes_from_item_tax_template(item_tax_map) {
      let me = this;
      if (item_tax_map && cint(frappe.defaults.get_default("add_taxes_from_item_tax_template"))) {
        if (typeof item_tax_map == "string") {
          item_tax_map = JSON.parse(item_tax_map);
        }
        $.each(item_tax_map, function(tax, rate) {
          let found = (me.frm.doc.taxes || []).find((d) => d.account_head === tax);
          if (!found) {
            let child = frappe.model.add_child(me.frm.doc, "taxes");
            child.charge_type = "On Net Total";
            child.account_head = tax;
            child.rate = 0;
          }
        });
      }
    }
    serial_no(doc, cdt, cdn) {
      var me = this;
      var item = frappe.get_doc(cdt, cdn);
      if (item && item.doctype === "Purchase Receipt Item Supplied") {
        return;
      }
      if (item && item.serial_no) {
        if (!item.item_code) {
          this.frm.trigger("item_code", cdt, cdn);
        } else {
          item.serial_no = item.serial_no.replace(/,/g, "\n");
          item.conversion_factor = item.conversion_factor || 1;
          refresh_field("serial_no", item.name, item.parentfield);
          if (!doc.is_return && cint(frappe.user_defaults.set_qty_in_transactions_based_on_serial_no_input)) {
            setTimeout(() => {
              me.update_qty(cdt, cdn);
            }, 1e4);
          }
        }
      }
    }
    update_qty(cdt, cdn) {
      var valid_serial_nos = [];
      var serialnos = [];
      var item = frappe.get_doc(cdt, cdn);
      serialnos = item.serial_no.split("\n");
      for (var i = 0; i < serialnos.length; i++) {
        if (serialnos[i] != "") {
          valid_serial_nos.push(serialnos[i]);
        }
      }
      frappe.model.set_value(item.doctype, item.name, "qty", valid_serial_nos.length / item.conversion_factor);
      frappe.model.set_value(item.doctype, item.name, "stock_qty", valid_serial_nos.length);
    }
    validate() {
      this.calculate_taxes_and_totals(false);
    }
    update_stock() {
      this.frm.trigger("set_default_internal_warehouse");
    }
    set_default_internal_warehouse() {
      let me = this;
      if (this.frm.doc.doctype === "Sales Invoice" && me.frm.doc.update_stock || this.frm.doc.doctype == "Delivery Note") {
        if (this.frm.doc.is_internal_customer && this.frm.doc.company === this.frm.doc.represents_company) {
          frappe.db.get_value("Company", this.frm.doc.company, "default_in_transit_warehouse", function(value) {
            me.frm.set_value("set_target_warehouse", value.default_in_transit_warehouse);
          });
        }
      }
      if (this.frm.doc.doctype === "Purchase Invoice" && me.frm.doc.update_stock || this.frm.doc.doctype == "Purchase Receipt") {
        if (this.frm.doc.is_internal_supplier && this.frm.doc.company === this.frm.doc.represents_company) {
          frappe.db.get_value("Company", this.frm.doc.company, "default_in_transit_warehouse", function(value) {
            me.frm.set_value("set_from_warehouse", value.default_in_transit_warehouse);
          });
        }
      }
    }
    company() {
      var me = this;
      var set_pricing = function() {
        if (me.frm.doc.company && me.frm.fields_dict.currency) {
          var company_currency = me.get_company_currency();
          var company_doc = frappe.get_doc(":Company", me.frm.doc.company);
          if (!me.frm.doc.currency) {
            me.frm.set_value("currency", company_currency);
          }
          if (me.frm.doc.currency == company_currency) {
            me.frm.set_value("conversion_rate", 1);
          }
          if (me.frm.doc.price_list_currency == company_currency) {
            me.frm.set_value("plc_conversion_rate", 1);
          }
          if (company_doc && company_doc.default_letter_head) {
            if (me.frm.fields_dict.letter_head) {
              me.frm.set_value("letter_head", company_doc.default_letter_head);
            }
          }
          let selling_doctypes_for_tc = ["Sales Invoice", "Quotation", "Sales Order", "Delivery Note"];
          if (company_doc.default_selling_terms && frappe.meta.has_field(me.frm.doc.doctype, "tc_name") && selling_doctypes_for_tc.includes(me.frm.doc.doctype) && !me.frm.doc.tc_name) {
            me.frm.set_value("tc_name", company_doc.default_selling_terms);
          }
          let buying_doctypes_for_tc = [
            "Request for Quotation",
            "Supplier Quotation",
            "Purchase Order",
            "Material Request",
            "Purchase Receipt"
          ];
          if (company_doc.default_buying_terms && frappe.meta.has_field(me.frm.doc.doctype, "tc_name") && buying_doctypes_for_tc.includes(me.frm.doc.doctype) && !me.frm.doc.tc_name) {
            me.frm.set_value("tc_name", company_doc.default_buying_terms);
          }
          frappe.run_serially([
            () => me.frm.script_manager.trigger("currency"),
            () => me.update_item_tax_map(),
            () => me.apply_default_taxes(),
            () => me.apply_pricing_rule()
          ]);
        }
      };
      var set_party_account = function(set_pricing2) {
        if (["Sales Invoice", "Purchase Invoice"].includes(me.frm.doc.doctype)) {
          if (me.frm.doc.doctype == "Sales Invoice") {
            var party_type = "Customer";
            var party_account_field = "debit_to";
          } else {
            var party_type = "Supplier";
            var party_account_field = "credit_to";
          }
          var party = me.frm.doc[frappe.model.scrub(party_type)];
          if (party && me.frm.doc.company) {
            return frappe.call({
              method: "erpnext.accounts.party.get_party_account",
              args: {
                company: me.frm.doc.company,
                party_type,
                party
              },
              callback: function(r) {
                if (!r.exc && r.message) {
                  me.frm.set_value(party_account_field, r.message);
                  set_pricing2();
                }
              }
            });
          } else {
            set_pricing2();
          }
        } else {
          set_pricing2();
        }
      };
      if (frappe.meta.get_docfield(this.frm.doctype, "shipping_address") && ["Purchase Order", "Purchase Receipt", "Purchase Invoice"].includes(this.frm.doctype)) {
        erpnext.utils.get_shipping_address(this.frm, function() {
          set_party_account(set_pricing);
        });
      } else {
        set_party_account(set_pricing);
      }
      if (this.frm.doc.company) {
        erpnext.last_selected_company = this.frm.doc.company;
      }
    }
    transaction_date() {
      if (this.frm.doc.transaction_date) {
        this.frm.transaction_date = this.frm.doc.transaction_date;
        frappe.ui.form.trigger(this.frm.doc.doctype, "currency");
      }
    }
    posting_date() {
      var me = this;
      if (this.frm.doc.posting_date) {
        this.frm.posting_date = this.frm.doc.posting_date;
        if (this.frm.doc.doctype == "Sales Invoice" && this.frm.doc.customer || this.frm.doc.doctype == "Purchase Invoice" && this.frm.doc.supplier) {
          return frappe.call({
            method: "erpnext.accounts.party.get_due_date",
            args: {
              "posting_date": me.frm.doc.posting_date,
              "party_type": me.frm.doc.doctype == "Sales Invoice" ? "Customer" : "Supplier",
              "bill_date": me.frm.doc.bill_date,
              "party": me.frm.doc.doctype == "Sales Invoice" ? me.frm.doc.customer : me.frm.doc.supplier,
              "company": me.frm.doc.company
            },
            callback: function(r, rt) {
              if (r.message) {
                me.frm.doc.due_date = r.message;
                refresh_field("due_date");
                frappe.ui.form.trigger(me.frm.doc.doctype, "currency");
                me.recalculate_terms();
              }
            }
          });
        } else {
          frappe.ui.form.trigger(me.frm.doc.doctype, "currency");
        }
      }
    }
    due_date() {
      if (this.frm.doc.due_date && !this.frm.updating_party_details && !this.frm.doc.is_pos) {
        if (this.frm.doc.payment_terms_template || this.frm.doc.payment_schedule && this.frm.doc.payment_schedule.length) {
          var message1 = "";
          var message2 = "";
          var final_message = __("Please clear the") + " ";
          if (this.frm.doc.payment_terms_template) {
            message1 = __("selected Payment Terms Template");
            final_message = final_message + message1;
          }
          if ((this.frm.doc.payment_schedule || []).length) {
            message2 = __("Payment Schedule Table");
            if (message1.length !== 0)
              message2 = " and " + message2;
            final_message = final_message + message2;
          }
          frappe.msgprint(final_message);
        }
      }
    }
    bill_date() {
      this.posting_date();
    }
    recalculate_terms() {
      const doc = this.frm.doc;
      if (doc.payment_terms_template) {
        this.payment_terms_template();
      } else if (doc.payment_schedule) {
        const me = this;
        doc.payment_schedule.forEach(function(term) {
          if (term.payment_term) {
            me.payment_term(doc, term.doctype, term.name);
          } else {
            frappe.model.set_value(term.doctype, term.name, "due_date", doc.posting_date || doc.transaction_date);
          }
        });
      }
    }
    get_company_currency() {
      return erpnext.get_currency(this.frm.doc.company);
    }
    contact_person() {
      erpnext.utils.get_contact_details(this.frm);
    }
    currency() {
      var _a;
      let transaction_date = this.frm.doc.transaction_date || this.frm.doc.posting_date;
      let me = this;
      this.set_dynamic_labels();
      let company_currency = this.get_company_currency();
      if (this.frm.doc.currency && this.frm.doc.currency !== company_currency && !((_a = this.frm.doc.__onload) == null ? void 0 : _a.load_after_mapping)) {
        this.get_exchange_rate(transaction_date, this.frm.doc.currency, company_currency, function(exchange_rate) {
          if (exchange_rate != me.frm.doc.conversion_rate) {
            me.set_margin_amount_based_on_currency(exchange_rate);
            me.set_actual_charges_based_on_currency(exchange_rate);
            me.frm.set_value("conversion_rate", exchange_rate);
          }
        });
      } else {
        if (this.frm.doc.currency === this.get_company_currency()) {
          this.frm.set_value("conversion_rate", 1);
        } else {
          this.conversion_rate();
        }
      }
    }
    conversion_rate() {
      var _a;
      const me = this.frm;
      if (this.frm.doc.currency === this.get_company_currency()) {
        this.frm.set_value("conversion_rate", 1);
      }
      if (this.frm.doc.currency === this.frm.doc.price_list_currency && this.frm.doc.plc_conversion_rate !== this.frm.doc.conversion_rate) {
        this.frm.set_value("plc_conversion_rate", this.frm.doc.conversion_rate);
      }
      if (flt(this.frm.doc.conversion_rate) > 0) {
        if ((_a = this.frm.doc.__onload) == null ? void 0 : _a.load_after_mapping) {
          this.calculate_taxes_and_totals();
        } else if (!this.in_apply_price_list) {
          this.apply_price_list();
        }
      }
      this.frm.set_df_property("conversion_rate", "read_only", erpnext.stale_rate_allowed() ? 0 : 1);
    }
    apply_discount_on_item(doc, cdt, cdn, field) {
      var item = frappe.get_doc(cdt, cdn);
      if (!item.price_list_rate) {
        item[field] = 0;
      } else {
        this.price_list_rate(doc, cdt, cdn);
      }
      this.set_gross_profit(item);
    }
    shipping_rule() {
      var me = this;
      if (this.frm.doc.shipping_rule) {
        return this.frm.call({
          doc: this.frm.doc,
          method: "apply_shipping_rule",
          callback: function(r) {
            me._calculate_taxes_and_totals();
          }
        }).fail(() => this.frm.set_value("shipping_rule", ""));
      }
    }
    set_margin_amount_based_on_currency(exchange_rate) {
      if (in_list(["Quotation", "Sales Order", "Delivery Note", "Sales Invoice", "Purchase Invoice", "Purchase Order", "Purchase Receipt"]), this.frm.doc.doctype) {
        var me = this;
        $.each(this.frm.doc.items || [], function(i, d) {
          if (d.margin_type == "Amount") {
            frappe.model.set_value(d.doctype, d.name, "margin_rate_or_amount", flt(d.margin_rate_or_amount) / flt(exchange_rate));
          }
        });
      }
    }
    set_actual_charges_based_on_currency(exchange_rate) {
      var me = this;
      $.each(this.frm.doc.taxes || [], function(i, d) {
        if (d.charge_type == "Actual") {
          frappe.model.set_value(d.doctype, d.name, "tax_amount", flt(d.base_tax_amount) / flt(exchange_rate));
        }
      });
    }
    get_exchange_rate(transaction_date, from_currency, to_currency, callback) {
      var args;
      if (["Quotation", "Sales Order", "Delivery Note", "Sales Invoice"].includes(this.frm.doctype)) {
        args = "for_selling";
      } else if (["Purchase Order", "Purchase Receipt", "Purchase Invoice"].includes(this.frm.doctype)) {
        args = "for_buying";
      }
      if (!transaction_date || !from_currency || !to_currency)
        return;
      return frappe.call({
        method: "erpnext.setup.utils.get_exchange_rate",
        args: {
          transaction_date,
          from_currency,
          to_currency,
          args
        },
        freeze: true,
        freeze_message: __("Fetching exchange rates ..."),
        callback: function(r) {
          callback(flt(r.message));
        }
      });
    }
    price_list_currency() {
      var _a;
      var me = this;
      this.set_dynamic_labels();
      var company_currency = this.get_company_currency();
      if (this.frm.doc.price_list_currency !== company_currency && !((_a = this.frm.doc.__onload) == null ? void 0 : _a.load_after_mapping)) {
        this.get_exchange_rate(this.frm.doc.posting_date, this.frm.doc.price_list_currency, company_currency, function(exchange_rate) {
          me.frm.set_value("plc_conversion_rate", exchange_rate);
        });
      } else {
        this.plc_conversion_rate();
      }
    }
    plc_conversion_rate() {
      if (this.frm.doc.price_list_currency === this.get_company_currency()) {
        this.frm.set_value("plc_conversion_rate", 1);
      } else if (this.frm.doc.price_list_currency === this.frm.doc.currency && this.frm.doc.plc_conversion_rate && cint(this.frm.doc.plc_conversion_rate) != 1 && cint(this.frm.doc.plc_conversion_rate) != cint(this.frm.doc.conversion_rate)) {
        this.frm.set_value("conversion_rate", this.frm.doc.plc_conversion_rate);
      }
      if (!this.in_apply_price_list) {
        this.apply_price_list(null, true);
      }
    }
    uom(doc, cdt, cdn) {
      var me = this;
      var item = frappe.get_doc(cdt, cdn);
      item.pricing_rules = "";
      if (item.item_code && item.uom) {
        return this.frm.call({
          method: "erpnext.stock.get_item_details.get_conversion_factor",
          args: {
            item_code: item.item_code,
            uom: item.uom
          },
          callback: function(r) {
            if (!r.exc) {
              frappe.model.set_value(cdt, cdn, "conversion_factor", r.message.conversion_factor);
            }
          }
        });
      }
      me.calculate_stock_uom_rate(doc, cdt, cdn);
    }
    conversion_factor(doc, cdt, cdn, dont_fetch_price_list_rate) {
      if (frappe.meta.get_docfield(cdt, "stock_qty", cdn)) {
        var item = frappe.get_doc(cdt, cdn);
        frappe.model.round_floats_in(item, ["qty", "conversion_factor"]);
        item.stock_qty = flt(item.qty * item.conversion_factor, precision("stock_qty", item));
        refresh_field("stock_qty", item.name, item.parentfield);
        this.toggle_conversion_factor(item);
        if (doc.doctype != "Material Request") {
          item.total_weight = flt(item.stock_qty * item.weight_per_unit);
          refresh_field("total_weight", item.name, item.parentfield);
          this.calculate_net_weight();
        }
        if (frappe.flags.dont_fetch_price_list_rate) {
          return;
        }
        if (!dont_fetch_price_list_rate && frappe.meta.has_field(doc.doctype, "price_list_currency")) {
          this.apply_price_list(item, true);
        }
        this.calculate_stock_uom_rate(doc, cdt, cdn);
      }
    }
    is_a_mapped_document(item) {
      const mapped_item_field_map = {
        "Delivery Note Item": ["si_detail", "so_detail", "dn_detail"],
        "Sales Invoice Item": ["dn_detail", "so_detail", "sales_invoice_item"],
        "Purchase Receipt Item": ["purchase_order_item", "purchase_invoice_item", "purchase_receipt_item"],
        "Purchase Invoice Item": ["purchase_order_item", "pr_detail", "po_detail"]
      };
      const mappped_fields = mapped_item_field_map[item.doctype] || [];
      return mappped_fields.map((field) => item[field]).filter(Boolean).length > 0;
    }
    batch_no(doc, cdt, cdn) {
      let item = frappe.get_doc(cdt, cdn);
      if (!this.is_a_mapped_document(item)) {
        this.apply_price_list(item, true);
      }
    }
    toggle_conversion_factor(item) {
      if (this.frm.get_field("items").grid.fields_map.conversion_factor) {
        this.frm.fields_dict.items.grid.toggle_enable("conversion_factor", item.uom != item.stock_uom && !frappe.meta.get_docfield(cur_frm.fields_dict.items.grid.doctype, "conversion_factor").read_only ? true : false);
      }
    }
    qty(doc, cdt, cdn) {
      let item = frappe.get_doc(cdt, cdn);
      frappe.run_serially([
        () => this.remove_pricing_rule(item),
        () => this.conversion_factor(doc, cdt, cdn, true),
        () => this.calculate_stock_uom_rate(doc, cdt, cdn),
        () => this.apply_pricing_rule(item, true)
      ]);
    }
    calculate_stock_uom_rate(doc, cdt, cdn) {
      let item = frappe.get_doc(cdt, cdn);
      item.stock_uom_rate = flt(item.rate) / flt(item.conversion_factor);
      refresh_field("stock_uom_rate", item.name, item.parentfield);
    }
    service_stop_date(frm, cdt, cdn) {
      var child = locals[cdt][cdn];
      if (child.service_stop_date) {
        let start_date = Date.parse(child.service_start_date);
        let end_date = Date.parse(child.service_end_date);
        let stop_date = Date.parse(child.service_stop_date);
        if (stop_date < start_date) {
          frappe.model.set_value(cdt, cdn, "service_stop_date", "");
          frappe.throw(__("Service Stop Date cannot be before Service Start Date"));
        } else if (stop_date > end_date) {
          frappe.model.set_value(cdt, cdn, "service_stop_date", "");
          frappe.throw(__("Service Stop Date cannot be after Service End Date"));
        }
      }
    }
    service_start_date(frm, cdt, cdn) {
      var child = locals[cdt][cdn];
      if (child.service_start_date) {
        frappe.call({
          "method": "erpnext.stock.get_item_details.calculate_service_end_date",
          args: { "args": child },
          callback: function(r) {
            frappe.model.set_value(cdt, cdn, "service_end_date", r.message.service_end_date);
          }
        });
      }
    }
    process_item_removal() {
      this.frm.trigger("calculate_taxes_and_totals");
      this.frm.trigger("calculate_net_weight");
    }
    calculate_net_weight() {
      var me = this;
      this.frm.doc.total_net_weight = 0;
      $.each(this.frm.doc["items"] || [], function(i, item) {
        me.frm.doc.total_net_weight += flt(item.total_weight);
      });
      refresh_field("total_net_weight");
      this.shipping_rule();
    }
    set_dynamic_labels() {
      this.frm.toggle_reqd("plc_conversion_rate", !!(this.frm.doc.price_list_name && this.frm.doc.price_list_currency));
      var company_currency = this.get_company_currency();
      this.change_form_labels(company_currency);
      this.change_grid_labels(company_currency);
      this.frm.refresh_fields();
    }
    change_form_labels(company_currency) {
      var me = this;
      this.frm.set_currency_labels([
        "base_total",
        "base_net_total",
        "base_total_taxes_and_charges",
        "base_discount_amount",
        "base_grand_total",
        "base_rounded_total",
        "base_in_words",
        "base_taxes_and_charges_added",
        "base_taxes_and_charges_deducted",
        "total_amount_to_pay",
        "base_paid_amount",
        "base_write_off_amount",
        "base_change_amount",
        "base_operating_cost",
        "base_raw_material_cost",
        "base_total_cost",
        "base_scrap_material_cost",
        "base_rounding_adjustment"
      ], company_currency);
      this.frm.set_currency_labels([
        "total",
        "net_total",
        "total_taxes_and_charges",
        "discount_amount",
        "grand_total",
        "taxes_and_charges_added",
        "taxes_and_charges_deducted",
        "tax_withholding_net_total",
        "rounded_total",
        "in_words",
        "paid_amount",
        "write_off_amount",
        "operating_cost",
        "scrap_material_cost",
        "rounding_adjustment",
        "raw_material_cost",
        "total_cost"
      ], this.frm.doc.currency);
      this.frm.set_currency_labels(["outstanding_amount", "total_advance"], this.frm.doc.party_account_currency);
      cur_frm.set_df_property("conversion_rate", "description", "1 " + this.frm.doc.currency + " = [?] " + company_currency);
      if (this.frm.doc.price_list_currency && this.frm.doc.price_list_currency != company_currency) {
        cur_frm.set_df_property("plc_conversion_rate", "description", "1 " + this.frm.doc.price_list_currency + " = [?] " + company_currency);
      }
      this.frm.toggle_display([
        "conversion_rate",
        "base_total",
        "base_net_total",
        "base_tax_withholding_net_total",
        "base_total_taxes_and_charges",
        "base_taxes_and_charges_added",
        "base_taxes_and_charges_deducted",
        "base_grand_total",
        "base_rounded_total",
        "base_in_words",
        "base_discount_amount",
        "base_paid_amount",
        "base_write_off_amount",
        "base_operating_cost",
        "base_raw_material_cost",
        "base_total_cost",
        "base_scrap_material_cost",
        "base_rounding_adjustment"
      ], this.frm.doc.currency != company_currency);
      this.frm.toggle_display(["plc_conversion_rate", "price_list_currency"], this.frm.doc.price_list_currency != company_currency);
      var show = cint(cur_frm.doc.discount_amount) || (cur_frm.doc.taxes || []).filter(function(d) {
        return d.included_in_print_rate === 1;
      }).length;
      if (frappe.meta.get_docfield(cur_frm.doctype, "net_total"))
        cur_frm.toggle_display("net_total", show);
      if (frappe.meta.get_docfield(cur_frm.doctype, "base_net_total"))
        cur_frm.toggle_display("base_net_total", show && me.frm.doc.currency != company_currency);
    }
    change_grid_labels(company_currency) {
      var me = this;
      this.update_item_grid_labels(company_currency);
      this.toggle_item_grid_columns(company_currency);
      if (this.frm.doc.operations && this.frm.doc.operations.length > 0) {
        this.frm.set_currency_labels(["operating_cost", "hour_rate"], this.frm.doc.currency, "operations");
        this.frm.set_currency_labels(["base_operating_cost", "base_hour_rate"], company_currency, "operations");
        var item_grid = this.frm.fields_dict["operations"].grid;
        $.each(["base_operating_cost", "base_hour_rate"], function(i, fname) {
          if (frappe.meta.get_docfield(item_grid.doctype, fname))
            item_grid.set_column_disp(fname, me.frm.doc.currency != company_currency);
        });
      }
      if (this.frm.doc.scrap_items && this.frm.doc.scrap_items.length > 0) {
        this.frm.set_currency_labels(["rate", "amount"], this.frm.doc.currency, "scrap_items");
        this.frm.set_currency_labels(["base_rate", "base_amount"], company_currency, "scrap_items");
        var item_grid = this.frm.fields_dict["scrap_items"].grid;
        $.each(["base_rate", "base_amount"], function(i, fname) {
          if (frappe.meta.get_docfield(item_grid.doctype, fname))
            item_grid.set_column_disp(fname, me.frm.doc.currency != company_currency);
        });
      }
      if (this.frm.doc.taxes && this.frm.doc.taxes.length > 0) {
        this.frm.set_currency_labels(["tax_amount", "total", "tax_amount_after_discount"], this.frm.doc.currency, "taxes");
        this.frm.set_currency_labels(["base_tax_amount", "base_total", "base_tax_amount_after_discount"], company_currency, "taxes");
      }
      if (this.frm.doc.advances && this.frm.doc.advances.length > 0) {
        this.frm.set_currency_labels(["advance_amount", "allocated_amount"], this.frm.doc.party_account_currency, "advances");
      }
      this.update_payment_schedule_grid_labels(company_currency);
    }
    update_item_grid_labels(company_currency) {
      this.frm.set_currency_labels([
        "base_rate",
        "base_net_rate",
        "base_price_list_rate",
        "base_amount",
        "base_net_amount",
        "base_rate_with_margin"
      ], company_currency, "items");
      this.frm.set_currency_labels([
        "rate",
        "net_rate",
        "price_list_rate",
        "amount",
        "net_amount",
        "stock_uom_rate",
        "rate_with_margin"
      ], this.frm.doc.currency, "items");
    }
    update_payment_schedule_grid_labels(company_currency) {
      const me = this;
      if (this.frm.doc.payment_schedule && this.frm.doc.payment_schedule.length > 0) {
        this.frm.set_currency_labels(["base_payment_amount", "base_outstanding", "base_paid_amount"], company_currency, "payment_schedule");
        this.frm.set_currency_labels(["payment_amount", "outstanding", "paid_amount"], this.frm.doc.currency, "payment_schedule");
        var schedule_grid = this.frm.fields_dict["payment_schedule"].grid;
        $.each(["base_payment_amount", "base_outstanding", "base_paid_amount"], function(i, fname) {
          if (frappe.meta.get_docfield(schedule_grid.doctype, fname))
            schedule_grid.set_column_disp(fname, me.frm.doc.currency != company_currency);
        });
      }
    }
    toggle_item_grid_columns(company_currency) {
      const me = this;
      var item_grid = this.frm.fields_dict["items"].grid;
      $.each(["base_rate", "base_price_list_rate", "base_amount", "base_rate_with_margin"], function(i, fname) {
        if (frappe.meta.get_docfield(item_grid.doctype, fname))
          item_grid.set_column_disp(fname, me.frm.doc.currency != company_currency);
      });
      var show = cint(cur_frm.doc.discount_amount) || (cur_frm.doc.taxes || []).filter(function(d) {
        return d.included_in_print_rate === 1;
      }).length;
      $.each(["net_rate", "net_amount"], function(i, fname) {
        if (frappe.meta.get_docfield(item_grid.doctype, fname))
          item_grid.set_column_disp(fname, show);
      });
      $.each(["base_net_rate", "base_net_amount"], function(i, fname) {
        if (frappe.meta.get_docfield(item_grid.doctype, fname))
          item_grid.set_column_disp(fname, show && me.frm.doc.currency != company_currency);
      });
    }
    recalculate() {
      this.calculate_taxes_and_totals();
    }
    recalculate_values() {
      this.calculate_taxes_and_totals();
    }
    calculate_charges() {
      this.calculate_taxes_and_totals();
    }
    ignore_pricing_rule() {
      if (this.frm.doc.ignore_pricing_rule) {
        var me = this;
        var item_list = [];
        $.each(this.frm.doc["items"] || [], function(i, d) {
          if (d.item_code) {
            if (d.is_free_item) {
              me.frm.get_field("items").grid.grid_rows[i].remove();
            } else {
              item_list.push({
                "doctype": d.doctype,
                "name": d.name,
                "item_code": d.item_code,
                "pricing_rules": d.pricing_rules,
                "parenttype": d.parenttype,
                "parent": d.parent,
                "price_list_rate": d.price_list_rate
              });
            }
          }
        });
        return this.frm.call({
          method: "erpnext.accounts.doctype.pricing_rule.pricing_rule.remove_pricing_rules",
          args: { item_list },
          callback: function(r) {
            if (!r.exc && r.message) {
              r.message.forEach((row_item) => {
                me.remove_pricing_rule(row_item);
              });
              me._set_values_for_item_list(r.message);
              me.calculate_taxes_and_totals();
              if (me.frm.doc.apply_discount_on)
                me.frm.trigger("apply_discount_on");
            }
          }
        });
      } else {
        this.apply_pricing_rule();
      }
    }
    apply_pricing_rule(item, calculate_taxes_and_totals) {
      var _a;
      var me = this;
      var args = this._get_args(item);
      if (!(args.items && args.items.length)) {
        if (calculate_taxes_and_totals)
          me.calculate_taxes_and_totals();
        return;
      }
      if ((_a = this.frm.doc.__onload) == null ? void 0 : _a.load_after_mapping) {
        if (calculate_taxes_and_totals)
          me.calculate_taxes_and_totals();
        return;
      }
      return this.frm.call({
        method: "erpnext.accounts.doctype.pricing_rule.pricing_rule.apply_pricing_rule",
        args: { args, doc: me.frm.doc },
        callback: function(r) {
          if (!r.exc && r.message) {
            me._set_values_for_item_list(r.message);
            if (item)
              me.set_gross_profit(item);
            if (me.frm.doc.apply_discount_on)
              me.frm.trigger("apply_discount_on");
          }
        }
      });
    }
    _get_args(item) {
      var me = this;
      return {
        "items": this._get_item_list(item),
        "customer": me.frm.doc.customer || me.frm.doc.party_name,
        "quotation_to": me.frm.doc.quotation_to,
        "customer_group": me.frm.doc.customer_group,
        "territory": me.frm.doc.territory,
        "supplier": me.frm.doc.supplier,
        "supplier_group": me.frm.doc.supplier_group,
        "currency": me.frm.doc.currency,
        "conversion_rate": me.frm.doc.conversion_rate,
        "price_list": me.frm.doc.selling_price_list || me.frm.doc.buying_price_list,
        "price_list_currency": me.frm.doc.price_list_currency,
        "plc_conversion_rate": me.frm.doc.plc_conversion_rate,
        "company": me.frm.doc.company,
        "transaction_date": me.frm.doc.transaction_date || me.frm.doc.posting_date,
        "campaign": me.frm.doc.campaign,
        "sales_partner": me.frm.doc.sales_partner,
        "ignore_pricing_rule": me.frm.doc.ignore_pricing_rule,
        "doctype": me.frm.doc.doctype,
        "name": me.frm.doc.name,
        "is_return": cint(me.frm.doc.is_return),
        "update_stock": ["Sales Invoice", "Purchase Invoice"].includes(me.frm.doc.doctype) ? cint(me.frm.doc.update_stock) : 0,
        "conversion_factor": me.frm.doc.conversion_factor,
        "pos_profile": me.frm.doc.doctype == "Sales Invoice" ? me.frm.doc.pos_profile : "",
        "coupon_code": me.frm.doc.coupon_code
      };
    }
    _get_item_list(item) {
      var item_list = [];
      var append_item = function(d) {
        if (d.item_code) {
          item_list.push({
            "doctype": d.doctype,
            "name": d.name,
            "child_docname": d.name,
            "item_code": d.item_code,
            "item_group": d.item_group,
            "brand": d.brand,
            "qty": d.qty,
            "stock_qty": d.stock_qty,
            "uom": d.uom,
            "stock_uom": d.stock_uom,
            "parenttype": d.parenttype,
            "parent": d.parent,
            "pricing_rules": d.pricing_rules,
            "is_free_item": d.is_free_item,
            "warehouse": d.warehouse,
            "serial_no": d.serial_no,
            "batch_no": d.batch_no,
            "price_list_rate": d.price_list_rate,
            "conversion_factor": d.conversion_factor || 1
          });
          if (in_list(["Quotation Item", "Sales Order Item", "Delivery Note Item", "Sales Invoice Item", "Purchase Invoice Item", "Purchase Order Item", "Purchase Receipt Item"]), d.doctype) {
            item_list[0]["margin_type"] = d.margin_type;
            item_list[0]["margin_rate_or_amount"] = d.margin_rate_or_amount;
          }
        }
      };
      if (item) {
        append_item(item);
      } else {
        $.each(this.frm.doc["items"] || [], function(i, d) {
          append_item(d);
        });
      }
      return item_list;
    }
    _set_values_for_item_list(children) {
      const items_rule_dict = {};
      for (const child of children) {
        const existing_pricing_rule = frappe.model.get_value(child.doctype, child.name, "pricing_rules");
        for (const [key, value] of Object.entries(child)) {
          if (!["doctype", "name"].includes(key)) {
            if (key === "price_list_rate") {
              frappe.model.set_value(child.doctype, child.name, "rate", value);
            }
            if (key === "pricing_rules") {
              frappe.model.set_value(child.doctype, child.name, key, value);
            }
            if (key !== "free_item_data") {
              if (child.apply_rule_on_other_items && JSON.parse(child.apply_rule_on_other_items).length) {
                if (!in_list(JSON.parse(child.apply_rule_on_other_items), child.item_code)) {
                  continue;
                }
              }
              frappe.model.set_value(child.doctype, child.name, key, value);
            }
          }
        }
        frappe.model.round_floats_in(frappe.get_doc(child.doctype, child.name), ["price_list_rate", "discount_percentage"]);
        if (!this.frm.doc.ignore_pricing_rule && existing_pricing_rule && !child.pricing_rules) {
          this.apply_price_list(frappe.get_doc(child.doctype, child.name));
        } else if (!child.pricing_rules) {
          this.remove_pricing_rule(frappe.get_doc(child.doctype, child.name));
        }
        if (child.free_item_data && child.free_item_data.length > 0) {
          this.apply_product_discount(child);
        }
        if (child.apply_rule_on_other_items && JSON.parse(child.apply_rule_on_other_items).length) {
          items_rule_dict[child.name] = child;
        }
      }
      this.apply_rule_on_other_items(items_rule_dict);
      this.calculate_taxes_and_totals();
    }
    apply_rule_on_other_items(args) {
      const me = this;
      const fields = ["discount_percentage", "pricing_rules", "discount_amount", "rate"];
      for (var k in args) {
        let data = args[k];
        if (data && data.apply_rule_on_other_items && JSON.parse(data.apply_rule_on_other_items)) {
          me.frm.doc.items.forEach((d) => {
            if (in_list(JSON.parse(data.apply_rule_on_other_items), d[data.apply_rule_on])) {
              for (var k2 in data) {
                if (in_list(fields, k2) && data[k2] && (data.price_or_product_discount === "Price" || k2 === "pricing_rules")) {
                  frappe.model.set_value(d.doctype, d.name, k2, data[k2]);
                }
              }
            }
          });
        }
      }
    }
    apply_product_discount(args) {
      const items = this.frm.doc.items.filter((d) => d.is_free_item) || [];
      const exist_items = items.map((row) => {
        return { item_code: row.item_code, pricing_rules: row.pricing_rules };
      });
      args.free_item_data.forEach((pr_row) => {
        let row_to_modify = {};
        if (!items || !exist_items.filter((e_row) => {
          return e_row.item_code == pr_row.item_code && e_row.pricing_rules == pr_row.pricing_rules;
        }).length) {
          row_to_modify = frappe.model.add_child(this.frm.doc, this.frm.doc.doctype + " Item", "items");
        } else if (items) {
          row_to_modify = items.filter((d) => d.item_code === pr_row.item_code && d.pricing_rules === pr_row.pricing_rules)[0];
        }
        for (let key in pr_row) {
          row_to_modify[key] = pr_row[key];
        }
        this.frm.script_manager.copy_from_first_row("items", row_to_modify, ["expense_account", "income_account"]);
      });
      args.free_item_data = "";
      refresh_field("items");
    }
    apply_price_list(item, reset_plc_conversion) {
      if (this.frm.doc.doctype === "Material Request") {
        return;
      }
      if (!reset_plc_conversion) {
        this.frm.set_value("plc_conversion_rate", "");
      }
      var me = this;
      var args = this._get_args(item);
      if (!(args.items && args.items.length || args.price_list)) {
        return;
      }
      if (me.in_apply_price_list == true)
        return;
      me.in_apply_price_list = true;
      return this.frm.call({
        method: "erpnext.stock.get_item_details.apply_price_list",
        args: { args, doc: me.frm.doc },
        callback: function(r) {
          if (!r.exc) {
            frappe.run_serially([
              () => me.frm.set_value("price_list_currency", r.message.parent.price_list_currency),
              () => me.frm.set_value("plc_conversion_rate", r.message.parent.plc_conversion_rate),
              () => {
                if (args.items.length) {
                  me._set_values_for_item_list(r.message.children);
                  $.each(r.message.children || [], function(i, d) {
                    me.apply_discount_on_item(d, d.doctype, d.name, "discount_percentage");
                  });
                }
              },
              () => {
                me.in_apply_price_list = false;
              }
            ]);
          } else {
            me.in_apply_price_list = false;
          }
        }
      }).always(() => {
        me.in_apply_price_list = false;
      });
    }
    remove_pricing_rule(item) {
      let me = this;
      const fields = [
        "discount_percentage",
        "discount_amount",
        "margin_rate_or_amount",
        "rate_with_margin"
      ];
      if (item.remove_free_item) {
        var items = [];
        me.frm.doc.items.forEach((d) => {
          if (d.item_code != item.remove_free_item || !d.is_free_item) {
            items.push(d);
          }
        });
        me.frm.doc.items = items;
        refresh_field("items");
      } else if (item.applied_on_items && item.apply_on) {
        const applied_on_items = item.applied_on_items.split(",");
        me.frm.doc.items.forEach((row) => {
          if (applied_on_items.includes(row[item.apply_on])) {
            fields.forEach((f) => {
              row[f] = 0;
            });
            ["pricing_rules", "margin_type"].forEach((field) => {
              if (row[field]) {
                row[field] = "";
              }
            });
          }
        });
        me.trigger_price_list_rate();
      }
    }
    trigger_price_list_rate() {
      var me = this;
      this.frm.doc.items.forEach((child_row) => {
        me.frm.script_manager.trigger("price_list_rate", child_row.doctype, child_row.name);
      });
    }
    validate_company_and_party() {
      var me = this;
      var valid = true;
      if (frappe.flags.ignore_company_party_validation) {
        return valid;
      }
      $.each(["company", "customer"], function(i, fieldname) {
        if (frappe.meta.has_field(me.frm.doc.doctype, fieldname) && !["Purchase Order", "Purchase Invoice"].includes(me.frm.doc.doctype)) {
          if (!me.frm.doc[fieldname]) {
            frappe.msgprint(__("Please specify") + ": " + frappe.meta.get_label(me.frm.doc.doctype, fieldname, me.frm.doc.name) + ". " + __("It is needed to fetch Item Details."));
            valid = false;
          }
        }
      });
      return valid;
    }
    get_terms() {
      var me = this;
      erpnext.utils.get_terms(this.frm.doc.tc_name, this.frm.doc, function(r) {
        if (!r.exc) {
          me.frm.set_value("terms", r.message);
        }
      });
    }
    taxes_and_charges() {
      var me = this;
      if (this.frm.doc.taxes_and_charges) {
        return this.frm.call({
          method: "erpnext.controllers.accounts_controller.get_taxes_and_charges",
          args: {
            "master_doctype": frappe.meta.get_docfield(this.frm.doc.doctype, "taxes_and_charges", this.frm.doc.name).options,
            "master_name": this.frm.doc.taxes_and_charges
          },
          callback: function(r) {
            if (!r.exc) {
              if (me.frm.doc.shipping_rule && me.frm.doc.taxes) {
                for (let tax of r.message) {
                  me.frm.add_child("taxes", tax);
                }
                refresh_field("taxes");
              } else {
                me.frm.set_value("taxes", r.message);
                me.calculate_taxes_and_totals();
              }
            }
          }
        });
      }
    }
    tax_category() {
      var me = this;
      if (me.frm.updating_party_details)
        return;
      frappe.run_serially([
        () => this.update_item_tax_map(),
        () => erpnext.utils.set_taxes(this.frm, "tax_category")
      ]);
    }
    update_item_tax_map() {
      let me = this;
      let item_codes = [];
      let item_rates = {};
      let item_tax_templates = {};
      $.each(this.frm.doc.items || [], function(i, item) {
        if (item.item_code) {
          item_codes.push([item.item_code, item.name]);
          item_rates[item.name] = item.net_rate;
          item_tax_templates[item.name] = item.item_tax_template;
        }
      });
      if (item_codes.length) {
        return this.frm.call({
          method: "erpnext.stock.get_item_details.get_item_tax_info",
          args: {
            company: me.frm.doc.company,
            tax_category: cstr(me.frm.doc.tax_category),
            item_codes,
            item_rates,
            item_tax_templates
          },
          callback: function(r) {
            if (!r.exc) {
              $.each(me.frm.doc.items || [], function(i, item) {
                if (item.name && r.message.hasOwnProperty(item.name) && r.message[item.name].item_tax_template) {
                  item.item_tax_template = r.message[item.name].item_tax_template;
                  item.item_tax_rate = r.message[item.name].item_tax_rate;
                  me.add_taxes_from_item_tax_template(item.item_tax_rate);
                }
              });
            }
          }
        });
      }
    }
    item_tax_template(doc, cdt, cdn) {
      var me = this;
      if (me.frm.updating_party_details)
        return;
      var item = frappe.get_doc(cdt, cdn);
      if (item.item_tax_template) {
        return this.frm.call({
          method: "erpnext.stock.get_item_details.get_item_tax_map",
          args: {
            company: me.frm.doc.company,
            item_tax_template: item.item_tax_template,
            as_json: true
          },
          callback: function(r) {
            if (!r.exc) {
              item.item_tax_rate = r.message;
              me.add_taxes_from_item_tax_template(item.item_tax_rate);
              me.calculate_taxes_and_totals();
            }
          }
        });
      } else {
        item.item_tax_rate = "{}";
        me.calculate_taxes_and_totals();
      }
    }
    is_recurring() {
      if (this.frm.doc.is_recurring && this.frm.doc.__islocal) {
        frappe.msgprint(__("Please set recurring after saving"));
        this.frm.set_value("is_recurring", 0);
        return;
      }
      if (this.frm.doc.is_recurring) {
        if (!this.frm.doc.recurring_id) {
          this.frm.set_value("recurring_id", this.frm.doc.name);
        }
        var owner_email = this.frm.doc.owner == "Administrator" ? frappe.user_info("Administrator").email : this.frm.doc.owner;
        this.frm.doc.notification_email_address = $.map([
          cstr(owner_email),
          cstr(this.frm.doc.contact_email)
        ], function(v) {
          return v || null;
        }).join(", ");
        this.frm.doc.repeat_on_day_of_month = frappe.datetime.str_to_obj(this.frm.doc.posting_date).getDate();
      }
      refresh_many(["notification_email_address", "repeat_on_day_of_month"]);
    }
    from_date() {
      if (this.frm.doc.from_date) {
        var recurring_type_map = {
          "Monthly": 1,
          "Quarterly": 3,
          "Half-yearly": 6,
          "Yearly": 12
        };
        var months = recurring_type_map[this.frm.doc.recurring_type];
        if (months) {
          var to_date = frappe.datetime.add_months(this.frm.doc.from_date, months);
          this.frm.doc.to_date = frappe.datetime.add_days(to_date, -1);
          refresh_field("to_date");
        }
      }
    }
    set_gross_profit(item) {
      if (["Sales Order", "Quotation"].includes(this.frm.doc.doctype) && item.valuation_rate) {
        var rate = flt(item.rate) * flt(this.frm.doc.conversion_rate || 1);
        item.gross_profit = flt((rate - item.valuation_rate) * item.stock_qty, precision("amount", item));
      }
    }
    setup_item_selector() {
      return;
    }
    get_advances() {
      if (!this.frm.is_return) {
        var me = this;
        return this.frm.call({
          method: "set_advances",
          doc: this.frm.doc,
          callback: function(r, rt) {
            refresh_field("advances");
            me.frm.dirty();
          }
        });
      }
    }
    make_payment_entry() {
      let via_journal_entry = this.frm.doc.__onload && this.frm.doc.__onload.make_payment_via_journal_entry;
      if (this.has_discount_in_schedule() && !via_journal_entry) {
        this.prompt_user_for_reference_date();
      } else {
        this.make_mapped_payment_entry();
      }
    }
    make_mapped_payment_entry(args) {
      var me = this;
      args = args || { "dt": this.frm.doc.doctype, "dn": this.frm.doc.name };
      return frappe.call({
        method: me.get_method_for_payment(),
        args,
        callback: function(r) {
          var doclist = frappe.model.sync(r.message);
          frappe.set_route("Form", doclist[0].doctype, doclist[0].name);
        }
      });
    }
    prompt_user_for_reference_date() {
      let me = this;
      frappe.prompt({
        label: __("Cheque/Reference Date"),
        fieldname: "reference_date",
        fieldtype: "Date",
        reqd: 1
      }, (values) => {
        let args = {
          "dt": me.frm.doc.doctype,
          "dn": me.frm.doc.name,
          "reference_date": values.reference_date
        };
        me.make_mapped_payment_entry(args);
      }, __("Reference Date for Early Payment Discount"), __("Continue"));
    }
    has_discount_in_schedule() {
      let is_eligible = in_list(["Sales Order", "Sales Invoice", "Purchase Order", "Purchase Invoice"], this.frm.doctype);
      let has_payment_schedule = this.frm.doc.payment_schedule && this.frm.doc.payment_schedule.length;
      if (!is_eligible || !has_payment_schedule)
        return false;
      let has_discount = this.frm.doc.payment_schedule.some((row) => row.discount);
      return has_discount;
    }
    make_quality_inspection() {
      let data = [];
      const fields = [
        {
          label: "Items",
          fieldtype: "Table",
          fieldname: "items",
          cannot_add_rows: true,
          in_place_edit: true,
          data,
          get_data: () => {
            return data;
          },
          fields: [
            {
              fieldtype: "Data",
              fieldname: "docname",
              hidden: true
            },
            {
              fieldtype: "Read Only",
              fieldname: "item_code",
              label: __("Item Code"),
              in_list_view: true
            },
            {
              fieldtype: "Read Only",
              fieldname: "item_name",
              label: __("Item Name"),
              in_list_view: true
            },
            {
              fieldtype: "Float",
              fieldname: "qty",
              label: __("Accepted Quantity"),
              in_list_view: true,
              read_only: true
            },
            {
              fieldtype: "Float",
              fieldname: "sample_size",
              label: __("Sample Size"),
              reqd: true,
              in_list_view: true
            },
            {
              fieldtype: "Data",
              fieldname: "description",
              label: __("Description"),
              hidden: true
            },
            {
              fieldtype: "Data",
              fieldname: "serial_no",
              label: __("Serial No"),
              hidden: true
            },
            {
              fieldtype: "Data",
              fieldname: "batch_no",
              label: __("Batch No"),
              hidden: true
            }
          ]
        }
      ];
      const me = this;
      const dialog2 = new frappe.ui.Dialog({
        title: __("Select Items for Quality Inspection"),
        fields,
        primary_action: function() {
          const data2 = dialog2.get_values();
          frappe.call({
            method: "erpnext.controllers.stock_controller.make_quality_inspections",
            args: {
              doctype: me.frm.doc.doctype,
              docname: me.frm.doc.name,
              items: data2.items
            },
            freeze: true,
            callback: function(r) {
              if (r.message.length > 0) {
                if (r.message.length === 1) {
                  frappe.set_route("Form", "Quality Inspection", r.message[0]);
                } else {
                  frappe.route_options = {
                    "reference_type": me.frm.doc.doctype,
                    "reference_name": me.frm.doc.name
                  };
                  frappe.set_route("List", "Quality Inspection");
                }
              }
              dialog2.hide();
            }
          });
        },
        primary_action_label: __("Create")
      });
      this.frm.doc.items.forEach((item) => {
        if (this.has_inspection_required(item)) {
          let dialog_items = dialog2.fields_dict.items;
          dialog_items.df.data.push({
            "docname": item.name,
            "item_code": item.item_code,
            "item_name": item.item_name,
            "qty": item.qty,
            "description": item.description,
            "serial_no": item.serial_no,
            "batch_no": item.batch_no,
            "sample_size": item.sample_quantity
          });
          dialog_items.grid.refresh();
        }
      });
      data = dialog2.fields_dict.items.df.data;
      if (!data.length) {
        frappe.msgprint(__("All items in this document already have a linked Quality Inspection."));
      } else {
        dialog2.show();
      }
    }
    has_inspection_required(item) {
      if (this.frm.doc.doctype === "Stock Entry" && this.frm.doc.purpose == "Manufacture") {
        if (item.is_finished_item && !item.quality_inspection) {
          return true;
        }
      } else if (!item.quality_inspection) {
        return true;
      }
    }
    get_method_for_payment() {
      var method = "erpnext.accounts.doctype.payment_entry.payment_entry.get_payment_entry";
      if (cur_frm.doc.__onload && cur_frm.doc.__onload.make_payment_via_journal_entry) {
        if (["Sales Invoice", "Purchase Invoice"].includes(cur_frm.doc.doctype)) {
          method = "erpnext.accounts.doctype.journal_entry.journal_entry.get_payment_entry_against_invoice";
        } else {
          method = "erpnext.accounts.doctype.journal_entry.journal_entry.get_payment_entry_against_order";
        }
      }
      return method;
    }
    set_query_for_batch(doc, cdt, cdn) {
      var me = this;
      var item = frappe.get_doc(cdt, cdn);
      if (!item.item_code) {
        frappe.throw(__("Please enter Item Code to get batch no"));
      } else if (doc.doctype == "Purchase Receipt" || doc.doctype == "Purchase Invoice" && doc.update_stock) {
        return {
          filters: { "item": item.item_code }
        };
      } else {
        let filters = {
          "item_code": item.item_code,
          "posting_date": me.frm.doc.posting_date || frappe.datetime.nowdate()
        };
        if (doc.is_return) {
          filters["is_return"] = 1;
        }
        if (item.warehouse)
          filters["warehouse"] = item.warehouse;
        return {
          query: "erpnext.controllers.queries.get_batch_no",
          filters
        };
      }
    }
    set_query_for_item_tax_template(doc, cdt, cdn) {
      var item = frappe.get_doc(cdt, cdn);
      if (!item.item_code) {
        return doc.company ? { filters: { company: doc.company } } : {};
      } else {
        let filters = {
          "item_code": item.item_code,
          "valid_from": ["<=", doc.transaction_date || doc.bill_date || doc.posting_date],
          "item_group": item.item_group
        };
        if (doc.tax_category)
          filters["tax_category"] = doc.tax_category;
        if (doc.company)
          filters["company"] = doc.company;
        return {
          query: "erpnext.controllers.queries.get_tax_template",
          filters
        };
      }
    }
    payment_terms_template() {
      var me = this;
      const doc = this.frm.doc;
      if (doc.payment_terms_template && doc.doctype !== "Delivery Note") {
        var posting_date = doc.posting_date || doc.transaction_date;
        frappe.call({
          method: "erpnext.controllers.accounts_controller.get_payment_terms",
          args: {
            terms_template: doc.payment_terms_template,
            posting_date,
            grand_total: doc.rounded_total || doc.grand_total,
            base_grand_total: doc.base_rounded_total || doc.base_grand_total,
            bill_date: doc.bill_date
          },
          callback: function(r) {
            if (r.message && !r.exc) {
              me.frm.set_value("payment_schedule", r.message);
              const company_currency = me.get_company_currency();
              me.update_payment_schedule_grid_labels(company_currency);
            }
          }
        });
      }
    }
    payment_term(doc, cdt, cdn) {
      const me = this;
      var row = locals[cdt][cdn];
      if (row.payment_term) {
        frappe.call({
          method: "erpnext.controllers.accounts_controller.get_payment_term_details",
          args: {
            term: row.payment_term,
            bill_date: this.frm.doc.bill_date,
            posting_date: this.frm.doc.posting_date || this.frm.doc.transaction_date,
            grand_total: this.frm.doc.rounded_total || this.frm.doc.grand_total,
            base_grand_total: this.frm.doc.base_rounded_total || this.frm.doc.base_grand_total
          },
          callback: function(r) {
            if (r.message && !r.exc) {
              for (var d in r.message) {
                frappe.model.set_value(cdt, cdn, d, r.message[d]);
                const company_currency = me.get_company_currency();
                me.update_payment_schedule_grid_labels(company_currency);
              }
            }
          }
        });
      }
    }
    against_blanket_order(doc, cdt, cdn) {
      var item = locals[cdt][cdn];
      if (!item.against_blanket_order) {
        frappe.model.set_value(this.frm.doctype + " Item", item.name, "blanket_order", null);
        frappe.model.set_value(this.frm.doctype + " Item", item.name, "blanket_order_rate", 0);
      }
    }
    blanket_order(doc, cdt, cdn) {
      var me = this;
      var item = locals[cdt][cdn];
      if (item.blanket_order && (item.parenttype == "Sales Order" || item.parenttype == "Purchase Order")) {
        frappe.call({
          method: "erpnext.stock.get_item_details.get_blanket_order_details",
          args: {
            args: {
              item_code: item.item_code,
              customer: doc.customer,
              supplier: doc.supplier,
              company: doc.company,
              transaction_date: doc.transaction_date,
              blanket_order: item.blanket_order
            }
          },
          callback: function(r) {
            if (!r.message) {
              frappe.throw(__("Invalid Blanket Order for the selected Customer and Item"));
            } else {
              frappe.run_serially([
                () => frappe.model.set_value(cdt, cdn, "blanket_order_rate", r.message.blanket_order_rate),
                () => me.frm.script_manager.trigger("price_list_rate", cdt, cdn)
              ]);
            }
          }
        });
      }
    }
    set_reserve_warehouse() {
      this.autofill_warehouse(this.frm.doc.supplied_items, "reserve_warehouse", this.frm.doc.set_reserve_warehouse);
    }
    set_warehouse() {
      this.autofill_warehouse(this.frm.doc.items, "warehouse", this.frm.doc.set_warehouse);
    }
    set_target_warehouse() {
      this.autofill_warehouse(this.frm.doc.items, "target_warehouse", this.frm.doc.set_target_warehouse);
    }
    set_from_warehouse() {
      this.autofill_warehouse(this.frm.doc.items, "from_warehouse", this.frm.doc.set_from_warehouse);
    }
    autofill_warehouse(child_table, warehouse_field, warehouse) {
      if (warehouse && child_table && child_table.length) {
        let doctype = child_table[0].doctype;
        $.each(child_table || [], function(i, item) {
          frappe.model.set_value(doctype, item.name, warehouse_field, warehouse);
        });
      }
    }
    coupon_code() {
      if (this.frm.doc.coupon_code || this.frm._last_coupon_code) {
        const _ignore_pricing_rule = this.frm.doc.ignore_pricing_rule;
        return frappe.run_serially([
          () => this.frm.doc.ignore_pricing_rule = 1,
          () => this.frm.trigger("ignore_pricing_rule"),
          () => this.frm.doc.ignore_pricing_rule = _ignore_pricing_rule,
          () => this.frm.trigger("apply_pricing_rule"),
          () => this.frm._last_coupon_code = this.frm.doc.coupon_code
        ]);
      }
    }
  };
  erpnext.show_serial_batch_selector = function(frm, d, callback, on_close, show_dialog) {
    let warehouse, receiving_stock, existing_stock;
    if (frm.doc.is_return) {
      if (["Purchase Receipt", "Purchase Invoice"].includes(frm.doc.doctype)) {
        existing_stock = true;
        warehouse = d.warehouse;
      } else if (["Delivery Note", "Sales Invoice"].includes(frm.doc.doctype)) {
        receiving_stock = true;
      }
    } else {
      if (frm.doc.doctype == "Stock Entry") {
        if (frm.doc.purpose == "Material Receipt") {
          receiving_stock = true;
        } else {
          existing_stock = true;
          warehouse = d.s_warehouse;
        }
      } else {
        existing_stock = true;
        warehouse = d.warehouse;
      }
    }
    if (!warehouse) {
      if (receiving_stock) {
        warehouse = ["like", ""];
      } else if (existing_stock) {
        warehouse = ["!=", ""];
      }
    }
    frappe.require("assets/erpnext/js/utils/serial_no_batch_selector.js", function() {
      new erpnext.SerialNoBatchSelector({
        frm,
        item: d,
        warehouse_details: {
          type: "Warehouse",
          name: warehouse
        },
        callback,
        on_close
      }, show_dialog);
    });
  };
  erpnext.apply_putaway_rule = (frm, purpose = null) => {
    if (!frm.doc.company) {
      frappe.throw({ message: __("Please select a Company first."), title: __("Mandatory") });
    }
    if (!frm.doc.items.length)
      return;
    frappe.call({
      method: "erpnext.stock.doctype.putaway_rule.putaway_rule.apply_putaway_rule",
      args: {
        doctype: frm.doctype,
        items: frm.doc.items,
        company: frm.doc.company,
        sync: true,
        purpose
      },
      callback: (result) => {
        if (!result.exc && result.message) {
          frm.clear_table("items");
          let items = result.message;
          items.forEach((row) => {
            delete row["name"];
            let child = frm.add_child("items");
            Object.assign(child, row);
            frm.script_manager.trigger("qty", child.doctype, child.name);
          });
          frm.get_field("items").grid.refresh();
        }
      }
    });
  };

  // ../metactical/metactical/custom_scripts/public/erpnext/transaction.js
  erpnext.TransactionController = class TransactionController2 extends erpnext.TransactionController {
    ais_scan_to_confirm() {
      var me = this;
      var items = this.frm.doc.items;
      if (this.frm.doc.items && this.frm.doc.items.length > 0) {
        var fields = [
          { "fieldtype": "Link", "label": "Item", "options": "Item", "fieldname": "item_code", "in_list_view": 1 },
          { "fieldtype": "Float", "label": "Qty", "fieldname": "qty", "in_list_view": 1 }
        ];
        var scanned_dialog = new frappe.ui.Dialog({
          "fields": [
            { "fieldtype": "Data", "fieldname": "barcode", "label": "Scan Barcode" },
            { "fieldtype": "Table", "fieldname": "items", "fields": fields, "data": [] }
          ],
          "primary_action": function() {
            var values = scanned_dialog.get_values("items");
            for (let i in values.items) {
              var row = values.items[i];
              let exists = items.filter((itm) => itm.item_code == row.item_code);
              if (exists.length > 0) {
                exists[0].qty = row.qty;
              }
            }
            scanned_dialog.hide();
            me.frm.refresh_field("items");
          },
          "secondary_action": function() {
            scanned_dialog.hide();
          },
          "secondary_action_label": "Cancel",
          "no_submit_on_enter": true
        });
        scanned_dialog.barcode_scanned = function() {
          if (scanned_dialog.get_values()["barcode"] == "" || scanned_dialog.get_values()["barcode"] == null) {
            return;
          }
          frappe.call({
            method: "erpnext.selling.page.point_of_sale.point_of_sale.search_for_serial_or_batch_or_barcode_number",
            args: {
              search_value: scanned_dialog.get_values()["barcode"]
            }
          }).then((r) => {
            const data = r && r.message;
            if (!data || Object.keys(data).length === 0) {
              frappe.utils.play_sound("error");
              frappe.show_alert({
                message: __("Wrong barcode"),
                indicator: "orange"
              });
            } else {
              let existing_item = items.filter((itm) => itm.item_code == data.item_code);
              if (existing_item.length > 0) {
                var dialog_data = scanned_dialog.fields_dict.items.grid.data;
                let existing_row = dialog_data.filter((row) => row.item_code == data.item_code);
                if (existing_row.length > 0) {
                  existing_row[0].qty = existing_row[0].qty + 1;
                } else {
                  dialog_data.push({ "item_code": data.item_code, "qty": 1 });
                }
                scanned_dialog.fields_dict.items.grid.refresh();
                scanned_dialog.fields_dict.barcode.set_value("");
                frappe.utils.play_sound("alert");
              } else {
                frappe.utils.play_sound("error");
                frappe.show_alert({
                  message: __("Item not in list"),
                  indicator: "orange"
                });
              }
            }
          });
        };
        scanned_dialog.fields_dict.barcode.input.onkeypress = function(event) {
          if (event.keyCode == 13) {
            scanned_dialog.barcode_scanned();
          }
        };
        scanned_dialog.show();
      }
    }
  };

  // frappe-html:/media/n/Files/projects/metactical_v14/apps/metactical/metactical/erpnext_public/js/templates/item_selector.html
  frappe.templates["item_selector"] = `<div class="app-listing item-list image-view-container item-selector">
{% for (var i=0; i < data.length; i++) { var item = data[i]; %}
	{% if (i % 4 === 0) { %}<div class="image-view-row">{% } %}
	<div class="image-view-item" data-name="{{ item.name }}">
		<div class="image-view-header doclist-row">
			<div class="list-value">
				<a class="grey list-id" data-name="{{item.name}}"
					title="{{ item.item_name || item.name}}">
					{{item.item_name || item.name}}</a>
			</div>
		</div>
		<div class="image-view-body">
			<a  data-item-code="{{ item.name }}"
				title="{{ item.item_name || item.name }}"
			>
				<div class="image-field"
					style="
					{% if (!item.image) { %}
						background-color: #fafbfc;
					{% } %}
					border: 0px;"
				>
					{% if (!item.image) { %}
					<span class="placeholder-text">
						{%= frappe.get_abbr(item.item_name || item.name) %}
					</span>
					{% } %}
					{% if (item.image) { %}
					<img src="{{ item.image }}" alt="{{item.item_name || item.name}}">
					{% } %}
				</div>
			</a>
		</div>
	</div>
	{% if ((i % 4 === 3) || (i===data.length - 1)) { %}</div>{% } %}
{% endfor %}
</div>
`;

  // ../erpnext/erpnext/public/js/utils/item_selector.js
  erpnext.ItemSelector = class ItemSelector {
    constructor(opts) {
      $.extend(this, opts);
      if (!this.item_field) {
        this.item_field = "item_code";
      }
      if (!this.item_query) {
        this.item_query = erpnext.queries.item().query;
      }
      this.grid = this.frm.get_field("items").grid;
      this.setup();
    }
    setup() {
      var me = this;
      if (!this.grid.add_items_button) {
        this.grid.add_items_button = this.grid.add_custom_button(__("Add Items"), function() {
          if (!me.dialog) {
            me.make_dialog();
          }
          me.dialog.show();
          me.render_items();
          setTimeout(function() {
            me.dialog.input.focus();
          }, 1e3);
        });
      }
    }
    make_dialog() {
      this.dialog = new frappe.ui.Dialog({
        title: __("Add Items")
      });
      var body = $(this.dialog.body);
      body.html('<div><p><input type="text" class="form-control"></p>			<br><div class="results"></div></div>');
      this.dialog.input = body.find(".form-control");
      this.dialog.results = body.find(".results");
      var me = this;
      this.dialog.results.on("click", ".image-view-item", function() {
        me.add_item($(this).attr("data-name"));
      });
      this.dialog.input.on("keyup", function() {
        if (me.timeout_id) {
          clearTimeout(me.timeout_id);
        }
        me.timeout_id = setTimeout(function() {
          me.render_items();
          me.timeout_id = void 0;
        }, 500);
      });
    }
    add_item(item_code) {
      var added = false;
      $.each(this.frm.doc.items || [], (i, d2) => {
        if (d2[this.item_field] === item_code) {
          frappe.model.set_value(d2.doctype, d2.name, "qty", d2.qty + 1);
          frappe.show_alert({ message: __("Added {0} ({1})", [item_code, d2.qty]), indicator: "green" });
          added = true;
          return false;
        }
      });
      if (!added) {
        var d = null;
        frappe.run_serially([
          () => {
            d = this.grid.add_new_row();
          },
          () => frappe.model.set_value(d.doctype, d.name, this.item_field, item_code),
          () => frappe.timeout(0.1),
          () => {
            frappe.model.set_value(d.doctype, d.name, "qty", 1);
            frappe.show_alert({ message: __("Added {0} ({1})", [item_code, 1]), indicator: "green" });
          }
        ]);
      }
    }
    render_items() {
      let args = {
        query: this.item_query,
        filters: {}
      };
      args.txt = this.dialog.input.val();
      args.as_dict = 1;
      if (this.get_filters) {
        $.extend(args.filters, this.get_filters() || {});
      }
      var me = this;
      frappe.link_search("Item", args, function(r) {
        $.each(r.values, function(i, d) {
          if (!d.image) {
            d.abbr = frappe.get_abbr(d.item_name);
            d.color = frappe.get_palette(d.item_name);
          }
        });
        me.dialog.results.html(frappe.render_template("item_selector", { data: r.values }));
      });
    }
  };

  // ../erpnext/erpnext/public/js/help_links.js
  frappe.provide("frappe.help.help_links");
  var docsUrl = "https://erpnext.com/docs/";
  frappe.help.help_links["Form/Rename Tool"] = [
    {
      label: "Bulk Rename",
      url: docsUrl + "user/manual/en/using-erpnext/articles/bulk-rename"
    }
  ];
  frappe.help.help_links["List/User"] = [
    {
      label: "New User",
      url: docsUrl + "user/manual/en/setting-up/users-and-permissions/adding-users"
    },
    {
      label: "Rename User",
      url: docsUrl + "user/manual/en/setting-up/articles/rename-user"
    }
  ];
  frappe.help.help_links["permission-manager"] = [
    {
      label: "Role Permissions Manager",
      url: docsUrl + "user/manual/en/setting-up/users-and-permissions/role-based-permissions"
    },
    {
      label: "Managing Perm Level in Permissions Manager",
      url: docsUrl + "user/manual/en/setting-up/articles/managing-perm-level"
    },
    {
      label: "User Permissions",
      url: docsUrl + "user/manual/en/setting-up/users-and-permissions/user-permissions"
    },
    {
      label: "Sharing",
      url: docsUrl + "user/manual/en/setting-up/users-and-permissions/sharing"
    },
    {
      label: "Password",
      url: docsUrl + "user/manual/en/setting-up/articles/change-password"
    }
  ];
  frappe.help.help_links["Form/System Settings"] = [
    {
      label: "System Settings",
      url: docsUrl + "user/manual/en/setting-up/settings/system-settings"
    }
  ];
  frappe.help.help_links["Form/Data Import"] = [
    {
      label: "Importing and Exporting Data",
      url: docsUrl + "user/manual/en/setting-up/data/data-import"
    },
    {
      label: "Overwriting Data from Data Import Tool",
      url: docsUrl + "user/manual/en/setting-up/articles/overwriting-data-from-data-import-tool"
    }
  ];
  frappe.help.help_links["List/Data Import"] = [
    {
      label: "Importing and Exporting Data",
      url: docsUrl + "user/manual/en/setting-up/data/data-import"
    },
    {
      label: "Overwriting Data from Data Import Tool",
      url: docsUrl + "user/manual/en/setting-up/articles/overwriting-data-from-data-import-tool"
    }
  ];
  frappe.help.help_links["module_setup"] = [
    {
      label: "Role Permissions Manager",
      url: docsUrl + "user/manual/en/setting-up/users-and-permissions/role-based-permissions"
    }
  ];
  frappe.help.help_links["Form/Naming Series"] = [
    {
      label: "Naming Series",
      url: docsUrl + "user/manual/en/setting-up/settings/naming-series"
    },
    {
      label: "Setting the Current Value for Naming Series",
      url: docsUrl + "user/manual/en/setting-up/articles/naming-series-current-value"
    }
  ];
  frappe.help.help_links["Form/Global Defaults"] = [
    {
      label: "Global Settings",
      url: docsUrl + "user/manual/en/setting-up/settings/global-defaults"
    }
  ];
  frappe.help.help_links["List/Print Heading"] = [
    {
      label: "Print Heading",
      url: docsUrl + "user/manual/en/setting-up/print/print-headings"
    }
  ];
  frappe.help.help_links["Form/Print Heading"] = [
    {
      label: "Print Heading",
      url: docsUrl + "user/manual/en/setting-up/print/print-headings"
    }
  ];
  frappe.help.help_links["List/Letter Head"] = [
    {
      label: "Letter Head",
      url: docsUrl + "user/manual/en/setting-up/print/letter-head"
    }
  ];
  frappe.help.help_links["List/Address Template"] = [
    {
      label: "Address Template",
      url: docsUrl + "user/manual/en/setting-up/print/address-template"
    }
  ];
  frappe.help.help_links["List/Terms and Conditions"] = [
    {
      label: "Terms and Conditions",
      url: docsUrl + "user/manual/en/setting-up/print/terms-and-conditions"
    }
  ];
  frappe.help.help_links["List/Cheque Print Template"] = [
    {
      label: "Cheque Print Template",
      url: docsUrl + "user/manual/en/setting-up/print/cheque-print-template"
    }
  ];
  frappe.help.help_links["List/Email Account"] = [
    {
      label: "Email Account",
      url: docsUrl + "user/manual/en/setting-up/email/email-account"
    }
  ];
  frappe.help.help_links["List/Notification"] = [
    {
      label: "Notification",
      url: docsUrl + "user/manual/en/setting-up/notifications"
    }
  ];
  frappe.help.help_links["Form/Notification"] = [
    {
      label: "Notification",
      url: docsUrl + "user/manual/en/setting-up/notifications"
    }
  ];
  frappe.help.help_links["Form/Email Digest"] = [
    {
      label: "Email Digest",
      url: docsUrl + "user/manual/en/setting-up/email/email-digest"
    }
  ];
  frappe.help.help_links["Form/Email Digest"] = [
    {
      label: "Email Digest",
      url: docsUrl + "user/manual/en/setting-up/email/email-digest"
    }
  ];
  frappe.help.help_links["List/Auto Email Report"] = [
    {
      label: "Auto Email Reports",
      url: docsUrl + "user/manual/en/setting-up/email/auto-email-reports"
    }
  ];
  frappe.help.help_links["Form/Print Settings"] = [
    {
      label: "Print Settings",
      url: docsUrl + "user/manual/en/setting-up/print/print-settings"
    }
  ];
  frappe.help.help_links["print-format-builder"] = [
    {
      label: "Print Format Builder",
      url: docsUrl + "user/manual/en/setting-up/print/print-format-builder"
    }
  ];
  frappe.help.help_links["Form/PayPal Settings"] = [
    {
      label: "PayPal Settings",
      url: docsUrl + "user/manual/en/erpnext_integration/paypal-integration"
    }
  ];
  frappe.help.help_links["Form/Razorpay Settings"] = [
    {
      label: "Razorpay Settings",
      url: docsUrl + "user/manual/en/erpnext_integration/razorpay-integration"
    }
  ];
  frappe.help.help_links["Form/Dropbox Settings"] = [
    {
      label: "Dropbox Settings",
      url: docsUrl + "user/manual/en/erpnext_integration/dropbox-backup"
    }
  ];
  frappe.help.help_links["Form/LDAP Settings"] = [
    {
      label: "LDAP Settings",
      url: docsUrl + "user/manual/en/erpnext_integration/ldap-integration"
    }
  ];
  frappe.help.help_links["Form/Stripe Settings"] = [
    {
      label: "Stripe Settings",
      url: docsUrl + "user/manual/en/erpnext_integration/stripe-integration"
    }
  ];
  frappe.help.help_links["Form/Quotation"] = [
    { label: "Quotation", url: docsUrl + "user/manual/en/selling/quotation" },
    {
      label: "Applying Discount",
      url: docsUrl + "user/manual/en/selling/articles/applying-discount"
    },
    {
      label: "Sales Person",
      url: docsUrl + "user/manual/en/selling/articles/sales-persons-in-the-sales-transactions"
    },
    {
      label: "Applying Margin",
      url: docsUrl + "user/manual/en/selling/articles/adding-margin"
    }
  ];
  frappe.help.help_links["List/Customer"] = [
    { label: "Customer", url: docsUrl + "user/manual/en/CRM/customer" },
    {
      label: "Credit Limit",
      url: docsUrl + "user/manual/en/accounts/credit-limit"
    }
  ];
  frappe.help.help_links["Form/Customer"] = [
    { label: "Customer", url: docsUrl + "user/manual/en/CRM/customer" },
    {
      label: "Credit Limit",
      url: docsUrl + "user/manual/en/accounts/credit-limit"
    }
  ];
  frappe.help.help_links["List/Sales Taxes and Charges Template"] = [
    {
      label: "Setting Up Taxes",
      url: docsUrl + "user/manual/en/setting-up/setting-up-taxes"
    }
  ];
  frappe.help.help_links["Form/Sales Taxes and Charges Template"] = [
    {
      label: "Setting Up Taxes",
      url: docsUrl + "user/manual/en/setting-up/setting-up-taxes"
    }
  ];
  frappe.help.help_links["List/Sales Order"] = [
    {
      label: "Sales Order",
      url: docsUrl + "user/manual/en/selling/sales-order"
    },
    {
      label: "Recurring Sales Order",
      url: docsUrl + "user/manual/en/accounts/articles/recurring-orders-and-invoices"
    },
    {
      label: "Applying Discount",
      url: docsUrl + "user/manual/en/selling/articles/applying-discount"
    }
  ];
  frappe.help.help_links["Form/Sales Order"] = [
    {
      label: "Sales Order",
      url: docsUrl + "user/manual/en/selling/sales-order"
    },
    {
      label: "Recurring Sales Order",
      url: docsUrl + "user/manual/en/accounts/articles/recurring-orders-and-invoices"
    },
    {
      label: "Applying Discount",
      url: docsUrl + "user/manual/en/selling/articles/applying-discount"
    },
    {
      label: "Drop Shipping",
      url: docsUrl + "user/manual/en/selling/articles/drop-shipping"
    },
    {
      label: "Sales Person",
      url: docsUrl + "user/manual/en/selling/articles/sales-persons-in-the-sales-transactions"
    },
    {
      label: "Close Sales Order",
      url: docsUrl + "user/manual/en/selling/articles/close-sales-order"
    },
    {
      label: "Applying Margin",
      url: docsUrl + "user/manual/en/selling/articles/adding-margin"
    }
  ];
  frappe.help.help_links["Form/Product Bundle"] = [
    {
      label: "Product Bundle",
      url: docsUrl + "user/manual/en/selling/product-bundle"
    }
  ];
  frappe.help.help_links["Form/Selling Settings"] = [
    {
      label: "Selling Settings",
      url: docsUrl + "user/manual/en/selling/selling-settings"
    }
  ];
  frappe.help.help_links["List/Supplier"] = [
    { label: "Supplier", url: docsUrl + "user/manual/en/buying/supplier" }
  ];
  frappe.help.help_links["Form/Supplier"] = [
    { label: "Supplier", url: docsUrl + "user/manual/en/buying/supplier" }
  ];
  frappe.help.help_links["Form/Request for Quotation"] = [
    {
      label: "Request for Quotation",
      url: docsUrl + "user/manual/en/buying/request-for-quotation"
    },
    {
      label: "RFQ Video",
      url: docsUrl + "user/videos/learn/request-for-quotation.html"
    }
  ];
  frappe.help.help_links["Form/Supplier Quotation"] = [
    {
      label: "Supplier Quotation",
      url: docsUrl + "user/manual/en/buying/supplier-quotation"
    }
  ];
  frappe.help.help_links["Form/Buying Settings"] = [
    {
      label: "Buying Settings",
      url: docsUrl + "user/manual/en/buying/setup/buying-settings"
    }
  ];
  frappe.help.help_links["List/Purchase Order"] = [
    {
      label: "Purchase Order",
      url: docsUrl + "user/manual/en/buying/purchase-order"
    },
    {
      label: "Recurring Purchase Order",
      url: docsUrl + "user/manual/en/accounts/articles/recurring-orders-and-invoices"
    }
  ];
  frappe.help.help_links["Form/Purchase Order"] = [
    {
      label: "Purchase Order",
      url: docsUrl + "user/manual/en/buying/purchase-order"
    },
    {
      label: "Item UoM",
      url: docsUrl + "user/manual/en/buying/articles/purchasing-in-different-unit"
    },
    {
      label: "Supplier Item Code",
      url: docsUrl + "user/manual/en/buying/articles/maintaining-suppliers-part-no-in-item"
    },
    {
      label: "Recurring Purchase Order",
      url: docsUrl + "user/manual/en/accounts/articles/recurring-orders-and-invoices"
    },
    {
      label: "Subcontracting",
      url: docsUrl + "user/manual/en/manufacturing/subcontracting"
    }
  ];
  frappe.help.help_links["List/Purchase Taxes and Charges Template"] = [
    {
      label: "Setting Up Taxes",
      url: docsUrl + "user/manual/en/setting-up/setting-up-taxes"
    }
  ];
  frappe.help.help_links["List/Price List"] = [
    {
      label: "Price List",
      url: docsUrl + "user/manual/en/stock/price-lists"
    }
  ];
  frappe.help.help_links["List/Authorization Rule"] = [
    {
      label: "Authorization Rule",
      url: docsUrl + "user/manual/en/customize-erpnext/authorization-rule"
    }
  ];
  frappe.help.help_links["Form/SMS Settings"] = [
    {
      label: "SMS Settings",
      url: docsUrl + "user/manual/en/setting-up/sms-setting"
    }
  ];
  frappe.help.help_links["List/Stock Reconciliation"] = [
    {
      label: "Stock Reconciliation",
      url: docsUrl + "user/manual/en/stock/stock-reconciliation"
    }
  ];
  frappe.help.help_links["Tree/Territory"] = [
    {
      label: "Territory",
      url: docsUrl + "user/manual/en/selling/territory"
    }
  ];
  frappe.help.help_links["List/Workflow"] = [
    { label: "Workflow", url: docsUrl + "user/manual/en/setting-up/workflows" }
  ];
  frappe.help.help_links["List/Company"] = [
    {
      label: "Company",
      url: docsUrl + "user/manual/en/setting-up/company-setup"
    },
    {
      label: "Delete All Related Transactions for a Company",
      url: docsUrl + "user/manual/en/setting-up/articles/delete-a-company-and-all-related-transactions"
    }
  ];
  frappe.help.help_links["Tree/Account"] = [
    {
      label: "Chart of Accounts",
      url: docsUrl + "user/manual/en/accounts/chart-of-accounts"
    },
    {
      label: "Managing Tree Mastes",
      url: docsUrl + "user/manual/en/setting-up/articles/managing-tree-structure-masters"
    }
  ];
  frappe.help.help_links["Form/Sales Invoice"] = [
    {
      label: "Sales Invoice",
      url: docsUrl + "user/manual/en/accounts/sales-invoice"
    },
    {
      label: "Accounts Opening Balance",
      url: docsUrl + "user/manual/en/accounts/opening-balance"
    },
    {
      label: "Sales Return",
      url: docsUrl + "user/manual/en/stock/sales-return"
    },
    {
      label: "Recurring Sales Invoice",
      url: docsUrl + "user/manual/en/accounts/articles/recurring-orders-and-invoices"
    }
  ];
  frappe.help.help_links["List/Sales Invoice"] = [
    {
      label: "Sales Invoice",
      url: docsUrl + "user/manual/en/accounts/sales-invoice"
    },
    {
      label: "Accounts Opening Balance",
      url: docsUrl + "user/manual/en/accounts/opening-balances"
    },
    {
      label: "Sales Return",
      url: docsUrl + "user/manual/en/stock/sales-return"
    },
    {
      label: "Recurring Sales Invoice",
      url: docsUrl + "user/manual/en/accounts/articles/recurring-orders-and-invoices"
    }
  ];
  frappe.help.help_links["point-of-sale"] = [
    {
      label: "Point of Sale Invoice",
      url: docsUrl + "user/manual/en/accounts/point-of-sales"
    }
  ];
  frappe.help.help_links["List/POS Profile"] = [
    {
      label: "Point of Sale Profile",
      url: docsUrl + "user/manual/en/accounts/pos-profile"
    }
  ];
  frappe.help.help_links["Form/POS Profile"] = [
    {
      label: "POS Profile",
      url: docsUrl + "user/manual/en/accounts/pos-profile"
    }
  ];
  frappe.help.help_links["List/Purchase Invoice"] = [
    {
      label: "Purchase Invoice",
      url: docsUrl + "user/manual/en/accounts/purchase-invoice"
    },
    {
      label: "Accounts Opening Balance",
      url: docsUrl + "user/manual/en/accounts/opening-balance"
    },
    {
      label: "Recurring Purchase Invoice",
      url: docsUrl + "user/manual/en/accounts/articles/recurring-orders-and-invoices"
    }
  ];
  frappe.help.help_links["List/Journal Entry"] = [
    {
      label: "Journal Entry",
      url: docsUrl + "user/manual/en/accounts/journal-entry"
    },
    {
      label: "Advance Payment Entry",
      url: docsUrl + "user/manual/en/accounts/advance-payment-entry"
    },
    {
      label: "Accounts Opening Balance",
      url: docsUrl + "user/manual/en/accounts/opening-balance"
    }
  ];
  frappe.help.help_links["List/Payment Entry"] = [
    {
      label: "Payment Entry",
      url: docsUrl + "user/manual/en/accounts/payment-entry"
    }
  ];
  frappe.help.help_links["List/Payment Request"] = [
    {
      label: "Payment Request",
      url: docsUrl + "user/manual/en/accounts/payment-request"
    }
  ];
  frappe.help.help_links["List/Asset"] = [
    {
      label: "Managing Fixed Assets",
      url: docsUrl + "user/manual/en/asset"
    }
  ];
  frappe.help.help_links["List/Asset Category"] = [
    {
      label: "Asset Category",
      url: docsUrl + "user/manual/en/asset/asset-category"
    }
  ];
  frappe.help.help_links["Tree/Cost Center"] = [
    { label: "Budgeting", url: docsUrl + "user/manual/en/accounts/budgeting" }
  ];
  frappe.help.help_links["List/Item"] = [
    { label: "Item", url: docsUrl + "user/manual/en/stock/item" },
    {
      label: "Item Price",
      url: docsUrl + "user/manual/en/stock/item-price"
    },
    {
      label: "Barcode",
      url: docsUrl + "user/manual/en/stock/articles/track-items-using-barcode"
    },
    {
      label: "Item Wise Taxation",
      url: docsUrl + "user/manual/en/accounts/item-tax-template"
    },
    {
      label: "Managing Fixed Assets",
      url: docsUrl + "user/manual/en/asset"
    },
    {
      label: "Item Codification",
      url: docsUrl + "user/manual/en/stock/articles/item-codification"
    },
    {
      label: "Item Variants",
      url: docsUrl + "user/manual/en/stock/item-variants"
    },
    {
      label: "Item Valuation",
      url: docsUrl + "user/manual/en/stock/articles/item-valuation-fifo-and-moving-average"
    }
  ];
  frappe.help.help_links["Form/Item"] = [
    { label: "Item", url: docsUrl + "user/manual/en/stock/item" },
    {
      label: "Item Price",
      url: docsUrl + "user/manual/en/stock/item-price"
    },
    {
      label: "Barcode",
      url: docsUrl + "user/manual/en/stock/articles/track-items-using-barcode"
    },
    {
      label: "Item Wise Taxation",
      url: docsUrl + "user/manual/en/accounts/item-tax-template"
    },
    {
      label: "Managing Fixed Assets",
      url: docsUrl + "user/manual/en/asset"
    },
    {
      label: "Item Codification",
      url: docsUrl + "user/manual/en/stock/articles/item-codification"
    },
    {
      label: "Item Variants",
      url: docsUrl + "user/manual/en/stock/item-variants"
    },
    {
      label: "Item Valuation",
      url: docsUrl + "user/manual/en/stock/item/item-valuation-fifo-and-moving-average"
    }
  ];
  frappe.help.help_links["List/Purchase Receipt"] = [
    {
      label: "Purchase Receipt",
      url: docsUrl + "user/manual/en/stock/purchase-receipt"
    },
    {
      label: "Barcode",
      url: docsUrl + "user/manual/en/stock/articles/track-items-using-barcode"
    }
  ];
  frappe.help.help_links["List/Delivery Note"] = [
    {
      label: "Delivery Note",
      url: docsUrl + "user/manual/en/stock/delivery-note"
    },
    {
      label: "Barcode",
      url: docsUrl + "user/manual/en/stock/articles/track-items-using-barcode"
    },
    {
      label: "Sales Return",
      url: docsUrl + "user/manual/en/stock/sales-return"
    }
  ];
  frappe.help.help_links["Form/Delivery Note"] = [
    {
      label: "Delivery Note",
      url: docsUrl + "user/manual/en/stock/delivery-note"
    },
    {
      label: "Sales Return",
      url: docsUrl + "user/manual/en/stock/sales-return"
    },
    {
      label: "Barcode",
      url: docsUrl + "user/manual/en/stock/articles/track-items-using-barcode"
    }
  ];
  frappe.help.help_links["List/Installation Note"] = [
    {
      label: "Installation Note",
      url: docsUrl + "user/manual/en/stock/installation-note"
    }
  ];
  frappe.help.help_links["List/Budget"] = [
    { label: "Budgeting", url: docsUrl + "user/manual/en/accounts/budgeting" }
  ];
  frappe.help.help_links["List/Material Request"] = [
    {
      label: "Material Request",
      url: docsUrl + "user/manual/en/stock/material-request"
    },
    {
      label: "Auto-creation of Material Request",
      url: docsUrl + "user/manual/en/stock/articles/auto-creation-of-material-request"
    }
  ];
  frappe.help.help_links["Form/Material Request"] = [
    {
      label: "Material Request",
      url: docsUrl + "user/manual/en/stock/material-request"
    },
    {
      label: "Auto-creation of Material Request",
      url: docsUrl + "user/manual/en/stock/articles/auto-creation-of-material-request"
    }
  ];
  frappe.help.help_links["Form/Stock Entry"] = [
    { label: "Stock Entry", url: docsUrl + "user/manual/en/stock/stock-entry" },
    {
      label: "Stock Entry Types",
      url: docsUrl + "user/manual/en/stock/articles/stock-entry-purpose"
    },
    {
      label: "Repack Entry",
      url: docsUrl + "user/manual/en/stock/articles/repack-entry"
    },
    {
      label: "Opening Stock",
      url: docsUrl + "user/manual/en/stock/opening-stock"
    },
    {
      label: "Subcontracting",
      url: docsUrl + "user/manual/en/manufacturing/subcontracting"
    }
  ];
  frappe.help.help_links["List/Stock Entry"] = [
    { label: "Stock Entry", url: docsUrl + "user/manual/en/stock/stock-entry" }
  ];
  frappe.help.help_links["Tree/Warehouse"] = [
    { label: "Warehouse", url: docsUrl + "user/manual/en/stock/warehouse" }
  ];
  frappe.help.help_links["List/Serial No"] = [
    { label: "Serial No", url: docsUrl + "user/manual/en/stock/serial-no" }
  ];
  frappe.help.help_links["Form/Serial No"] = [
    { label: "Serial No", url: docsUrl + "user/manual/en/stock/serial-no" }
  ];
  frappe.help.help_links["List/Batch"] = [{ label: "Batch", url: docsUrl + "user/manual/en/stock/batch" }];
  frappe.help.help_links["Form/Batch"] = [{ label: "Batch", url: docsUrl + "user/manual/en/stock/batch" }];
  frappe.help.help_links["Form/Packing Slip"] = [
    {
      label: "Packing Slip",
      url: docsUrl + "user/manual/en/stock/packing-slip"
    }
  ];
  frappe.help.help_links["Form/Quality Inspection"] = [
    {
      label: "Quality Inspection",
      url: docsUrl + "user/manual/en/stock/quality-inspection"
    }
  ];
  frappe.help.help_links["Form/Landed Cost Voucher"] = [
    {
      label: "Landed Cost Voucher",
      url: docsUrl + "user/manual/en/stock/landed-cost-voucher"
    }
  ];
  frappe.help.help_links["Tree/Item Group"] = [
    {
      label: "Item Group",
      url: docsUrl + "user/manual/en/stock/item-group"
    }
  ];
  frappe.help.help_links["Form/Item Attribute"] = [
    {
      label: "Item Attribute",
      url: docsUrl + "user/manual/en/stock/item-attribute"
    }
  ];
  frappe.help.help_links["Form/UOM"] = [
    {
      label: "Fractions in UOM",
      url: docsUrl + "user/manual/en/stock/articles/managing-fractions-in-uom"
    }
  ];
  frappe.help.help_links["Form/Stock Reconciliation"] = [
    {
      label: "Opening Stock Entry",
      url: docsUrl + "user/manual/en/stock/stock-reconciliation"
    }
  ];
  frappe.help.help_links["Form/Lead"] = [{ label: "Lead", url: docsUrl + "user/manual/en/CRM/lead" }];
  frappe.help.help_links["Form/Opportunity"] = [
    { label: "Opportunity", url: docsUrl + "user/manual/en/CRM/opportunity" }
  ];
  frappe.help.help_links["Form/Address"] = [{ label: "Address", url: docsUrl + "user/manual/en/CRM/address" }];
  frappe.help.help_links["Form/Contact"] = [{ label: "Contact", url: docsUrl + "user/manual/en/CRM/contact" }];
  frappe.help.help_links["Form/Newsletter"] = [
    { label: "Newsletter", url: docsUrl + "user/manual/en/CRM/newsletter" }
  ];
  frappe.help.help_links["Form/Campaign"] = [
    { label: "Campaign", url: docsUrl + "user/manual/en/CRM/campaign" }
  ];
  frappe.help.help_links["Tree/Sales Person"] = [
    {
      label: "Sales Person",
      url: docsUrl + "user/manual/en/CRM/sales-person"
    }
  ];
  frappe.help.help_links["Form/Sales Person"] = [
    {
      label: "Sales Person Target",
      url: docsUrl + "user/manual/en/selling/sales-person-target-allocation"
    },
    {
      label: "Sales Person in Transactions",
      url: docsUrl + "user/manual/en/selling/articles/sales-persons-in-the-sales-transactions"
    }
  ];
  frappe.help.help_links["Form/BOM"] = [
    {
      label: "Bill of Material",
      url: docsUrl + "user/manual/en/manufacturing/bill-of-materials"
    },
    {
      label: "Nested BOM Structure",
      url: docsUrl + "user/manual/en/manufacturing/articles/managing-multi-level-bom"
    }
  ];
  frappe.help.help_links["Form/Work Order"] = [
    {
      label: "Work Order",
      url: docsUrl + "user/manual/en/manufacturing/work-order"
    }
  ];
  frappe.help.help_links["Form/Workstation"] = [
    {
      label: "Workstation",
      url: docsUrl + "user/manual/en/manufacturing/workstation"
    }
  ];
  frappe.help.help_links["Form/Operation"] = [
    {
      label: "Operation",
      url: docsUrl + "user/manual/en/manufacturing/operation"
    }
  ];
  frappe.help.help_links["Form/BOM Update Tool"] = [
    {
      label: "BOM Update Tool",
      url: docsUrl + "user/manual/en/manufacturing/bom-update-tool"
    }
  ];
  frappe.help.help_links["Form/Customize Form"] = [
    {
      label: "Custom Field",
      url: docsUrl + "user/manual/en/customize-erpnext/custom-field"
    },
    {
      label: "Customize Field",
      url: docsUrl + "user/manual/en/customize-erpnext/customize-form"
    }
  ];
  frappe.help.help_links["List/Custom Field"] = [
    {
      label: "Custom Field",
      url: docsUrl + "user/manual/en/customize-erpnext/custom-field"
    }
  ];
  frappe.help.help_links["Form/Custom Field"] = [
    {
      label: "Custom Field",
      url: docsUrl + "user/manual/en/customize-erpnext/custom-field"
    }
  ];

  // ../erpnext/erpnext/public/js/agriculture/ternary_plot.js
  frappe.provide("agriculture");
  agriculture.TernaryPlot = class TernaryPlot {
    constructor(opts) {
      Object.assign(this, opts);
      frappe.require("assets/frappe/js/lib/snap.svg-min.js", () => {
        this.make_svg();
        this.init_snap();
        this.init_config();
        this.make_plot();
        this.make_plot_marking();
        this.make_legend();
        this.mark_blip();
      });
    }
    make_svg() {
      this.$svg = $('<svg height="350" width="400">');
      $(this.parent).append(this.$svg);
    }
    init_snap() {
      this.paper = new Snap(this.$svg.get(0));
    }
    init_config() {
      this.config = {
        triangle_side: 300,
        spacing: 50,
        strokeWidth: 1,
        stroke: frappe.ui.color.get("black")
      };
      this.config.scaling_factor = this.config.triangle_side / 100;
      let { triangle_side: t, spacing: s, scaling_factor: p } = this.config;
      this.coords = {
        sand: {
          points: [s + t * Snap.cos(60), s, s, s + t * Snap.cos(30), s + t, s + t * Snap.cos(30)],
          color: frappe.ui.color.get("peach")
        },
        loamy_sand: {
          points: [
            s + 15 * p * Snap.cos(60),
            s + (100 - 15) * p * Snap.cos(30),
            s + 10 * p * Snap.cos(60),
            s + (100 - 10) * p * Snap.cos(30),
            s + (100 - 85) * p,
            s + t * Snap.cos(30),
            s + (100 - 70) * p,
            s + t * Snap.cos(30)
          ],
          color: frappe.ui.color.get("pink")
        },
        sandy_loam: {
          points: [
            s + 20 * p * Snap.cos(60) + 27.5 * p,
            s + (100 - 20) * p * Snap.cos(30),
            s + 20 * p * Snap.cos(60),
            s + (100 - 20) * p * Snap.cos(30),
            s + 15 * p * Snap.cos(60),
            s + (100 - 15) * p * Snap.cos(30),
            s + (100 - 75) * p,
            s + t * Snap.cos(30),
            s + (100 - 50) * p,
            s + t * Snap.cos(30),
            s + (100 - 50) * p + 7.5 * p * Snap.cos(60),
            s + t * Snap.cos(30) - 7.5 * p * Snap.cos(30),
            s + (100 - 50) * p + 7.5 * p * Snap.cos(60) - 10 * p,
            s + t * Snap.cos(30) - 7.5 * p * Snap.cos(30)
          ],
          color: frappe.ui.color.get("pink", "light")
        },
        loam: {
          points: [
            s + (100 - 50) * p + 27.5 * p * Snap.cos(60),
            s + t * Snap.cos(30) - 27.5 * p * Snap.cos(30),
            s + (100 - 50) * p + 27.5 * p * Snap.cos(60) - 22.5 * p,
            s + t * Snap.cos(30) - 27.5 * p * Snap.cos(30),
            s + 20 * p * Snap.cos(60) + 27.5 * p,
            s + (100 - 20) * p * Snap.cos(30),
            s + (100 - 50) * p + 7.5 * p * Snap.cos(60) - 10 * p,
            s + t * Snap.cos(30) - 7.5 * p * Snap.cos(30),
            s + (100 - 50) * p + 7.5 * p * Snap.cos(60),
            s + t * Snap.cos(30) - 7.5 * p * Snap.cos(30)
          ],
          color: frappe.ui.color.get("brown")
        },
        silt_loam: {
          points: [
            s + t - 27.5 * p * Snap.cos(60),
            s + 72.5 * p * Snap.cos(30),
            s + (100 - 50) * p + 27.5 * p * Snap.cos(60),
            s + t * Snap.cos(30) - 27.5 * p * Snap.cos(30),
            s + (100 - 50) * p,
            s + t * Snap.cos(30),
            s + (100 - 20) * p,
            s + t * Snap.cos(30),
            s + (100 - 20) * p + 12.5 * p * Snap.cos(60),
            s + 90 * p * Snap.cos(30),
            s + t - 12.5 * p * Snap.cos(60),
            s + (100 - 12.5) * p * Snap.cos(30)
          ],
          color: frappe.ui.color.get("green", "dark")
        },
        silt: {
          points: [
            s + t - 12.5 * p * Snap.cos(60),
            s + (100 - 12.5) * p * Snap.cos(30),
            s + (100 - 20) * p + 12.5 * p * Snap.cos(60),
            s + 90 * p * Snap.cos(30),
            s + (100 - 20) * p,
            s + t * Snap.cos(30),
            s + t,
            s + t * Snap.cos(30)
          ],
          color: frappe.ui.color.get("green")
        },
        silty_clay_loam: {
          points: [
            s + t - 40 * p * Snap.cos(60),
            s + 60 * p * Snap.cos(30),
            s + t - 40 * p * Snap.cos(60) - 20 * p,
            s + 60 * p * Snap.cos(30),
            s + t - 27.5 * p * Snap.cos(60) - 20 * p,
            s + 72.5 * p * Snap.cos(30),
            s + t - 27.5 * p * Snap.cos(60),
            s + 72.5 * p * Snap.cos(30)
          ],
          color: frappe.ui.color.get("cyan", "dark")
        },
        silty_clay: {
          points: [
            s + t - 60 * p * Snap.cos(60),
            s + 40 * p * Snap.cos(30),
            s + t - 40 * p * Snap.cos(60) - 20 * p,
            s + 60 * p * Snap.cos(30),
            s + t - 40 * p * Snap.cos(60),
            s + 60 * p * Snap.cos(30)
          ],
          color: frappe.ui.color.get("cyan")
        },
        clay_loam: {
          points: [
            s + t - 40 * p * Snap.cos(60) - 20 * p,
            s + 60 * p * Snap.cos(30),
            s + t - 40 * p * Snap.cos(60) - 45 * p,
            s + 60 * p * Snap.cos(30),
            s + t - 27.5 * p * Snap.cos(60) - 45 * p,
            s + 72.5 * p * Snap.cos(30),
            s + t - 27.5 * p * Snap.cos(60) - 20 * p,
            s + 72.5 * p * Snap.cos(30)
          ],
          color: frappe.ui.color.get("green", "light")
        },
        sandy_clay_loam: {
          points: [
            s + 35 * p * Snap.cos(60) + 20 * p,
            s + (100 - 35) * p * Snap.cos(30),
            s + 35 * p * Snap.cos(60),
            s + (100 - 35) * p * Snap.cos(30),
            s + 20 * p * Snap.cos(60),
            s + (100 - 20) * p * Snap.cos(30),
            s + 20 * p * Snap.cos(60) + 27.5 * p,
            s + (100 - 20) * p * Snap.cos(30),
            s + t - 27.5 * p * Snap.cos(60) - 45 * p,
            s + 72.5 * p * Snap.cos(30)
          ],
          color: frappe.ui.color.get("pink", "dark")
        },
        sandy_clay: {
          points: [
            s + 55 * p * Snap.cos(60),
            s + (100 - 55) * p * Snap.cos(30),
            s + 35 * p * Snap.cos(60),
            s + (100 - 35) * p * Snap.cos(30),
            s + 35 * p * Snap.cos(60) + 20 * p,
            s + (100 - 35) * p * Snap.cos(30)
          ],
          color: frappe.ui.color.get("red")
        },
        clay: {
          points: [
            s + t * Snap.cos(60),
            s,
            s + 55 * p * Snap.cos(60),
            s + (100 - 55) * p * Snap.cos(30),
            s + t - 40 * p * Snap.cos(60) - 45 * p,
            s + 60 * p * Snap.cos(30),
            s + t - 40 * p * Snap.cos(60) - 20 * p,
            s + 60 * p * Snap.cos(30),
            s + t - 60 * p * Snap.cos(60),
            s + 40 * p * Snap.cos(30)
          ],
          color: frappe.ui.color.get("yellow")
        }
      };
    }
    get_coords(soil_type) {
      return this.coords[soil_type].points;
    }
    get_color(soil_type) {
      return this.coords[soil_type].color;
    }
    make_plot() {
      for (let soil_type in this.coords) {
        this.paper.polygon(this.get_coords(soil_type)).attr({
          fill: this.get_color(soil_type),
          stroke: this.config.stroke,
          strokeWidth: this.config.strokeWidth
        });
      }
    }
    make_plot_marking() {
      let { triangle_side: t, spacing: s, scaling_factor: p } = this.config;
      let clay = this.paper.text(t * Snap.cos(60) / 2, s + t * Snap.cos(30) / 2, __("Clay")).attr({
        fill: frappe.ui.color.get("black")
      });
      clay.transform("r300");
      let silt = this.paper.text(t, s + t * Snap.cos(30) / 2, __("Silt")).attr({
        fill: frappe.ui.color.get("black")
      });
      silt.transform("r60");
      let sand = this.paper.text(35 + t * Snap.cos(60), 90 + t * Snap.cos(30), __("Sand")).attr({
        fill: frappe.ui.color.get("black")
      });
      sand.transform("r0");
    }
    make_legend() {
      let index = 1;
      let offset = 0;
      let exec_once = true;
      for (let soil_type in this.coords) {
        if (index > 6 && exec_once) {
          offset = 300;
          index = 1;
          exec_once = false;
        }
        let rect = this.paper.rect(0 + offset, 0 + index * 20, 100, 19, 5, 5).attr({
          fill: this.get_color(soil_type),
          stroke: frappe.ui.color.get("black")
        });
        let text = this.paper.text(5 + offset, 16 + index * 20, soil_type).attr({
          fill: frappe.ui.color.get("black"),
          "font-size": 12
        });
        index++;
      }
    }
    mark_blip({ clay, sand, silt } = this) {
      if (clay + sand + silt != 0) {
        let { triangle_side: t, spacing: s, scaling_factor: p } = this.config;
        let x_blip = s + clay * p * Snap.cos(60) + silt * p;
        let y_blip = s + silt * p * Snap.cos(30) + sand * p * Snap.sin(60);
        this.blip = this.paper.circle(x_blip, y_blip, 4).attr({
          fill: frappe.ui.color.get("orange"),
          stroke: frappe.ui.color.get("orange"),
          strokeWidth: 2
        });
      }
    }
    remove_blip() {
      if (typeof this.blip !== "undefined")
        this.blip.remove();
    }
  };

  // frappe-html:/media/n/Files/projects/metactical_v14/apps/metactical/metactical/erpnext_public/js/templates/item_quick_entry.html
  frappe.templates["item_quick_entry"] = `<div class="h6 uppercase" style="margin-top: 30px;">{{ __("Variant Attributes") }}</div>
<div class="attributes hide-control">
</div>
`;

  // ../erpnext/erpnext/public/js/utils/item_quick_entry.js
  frappe.provide("frappe.ui.form");
  frappe.ui.form.ItemQuickEntryForm = class ItemQuickEntryForm extends frappe.ui.form.QuickEntryForm {
    constructor(doctype, after_insert) {
      super(doctype, after_insert);
    }
    render_dialog() {
      this.mandatory = this.get_variant_fields().concat(this.mandatory);
      this.mandatory = this.mandatory.concat(this.get_attributes_fields());
      this.check_naming_series_based_on();
      super.render_dialog();
      this.init_post_render_dialog_operations();
      this.preset_fields_for_template();
      this.dialog.$wrapper.find(".edit-full").text(__("Edit in full page for more options like assets, serial nos, batches etc."));
    }
    check_naming_series_based_on() {
      if (frappe.defaults.get_default("item_naming_by") === "Naming Series") {
        this.mandatory = this.mandatory.filter((d) => d.fieldname !== "item_code");
      }
    }
    init_post_render_dialog_operations() {
      this.dialog.fields_dict.attribute_html.$wrapper.append(frappe.render_template("item_quick_entry"));
      this.init_for_create_variant_trigger();
      this.init_for_item_template_trigger();
      this.toggle_manufacturer_fields();
      this.dialog.get_field("item_template").df.hidden = 1;
      this.dialog.get_field("item_template").refresh();
    }
    register_primary_action() {
      var me = this;
      this.dialog.set_primary_action(__("Save"), function() {
        if (me.dialog.working)
          return;
        var data = me.dialog.get_values();
        var variant_values = {};
        if (me.dialog.fields_dict.create_variant.$input.prop("checked")) {
          variant_values = me.get_variant_doc();
          if (!Object.keys(variant_values).length) {
            data = null;
          }
          variant_values.stock_uom = me.template_doc.stock_uom;
          variant_values.item_group = me.template_doc.item_group;
        }
        if (data) {
          me.dialog.working = true;
          var values = me.update_doc();
          if (variant_values["variant_based_on"] == "Manufacturer") {
            values["variant_based_on"] = "Manufacturer";
          }
          $.extend(variant_values, values);
          me.insert(variant_values);
        }
      });
    }
    insert(variant_values) {
      let me = this;
      return new Promise((resolve) => {
        frappe.call({
          method: "frappe.client.insert",
          args: {
            doc: variant_values
          },
          callback: function(r) {
            me.dialog.hide();
            frappe.model.clear_doc(me.dialog.doc.doctype, me.dialog.doc.name);
            me.dialog.doc = r.message;
            if (frappe._from_link) {
              frappe.ui.form.update_calling_link(me.dialog.doc);
            } else {
              if (me.after_insert) {
                me.after_insert(me.dialog.doc);
              } else {
                me.open_form_if_not_list();
              }
            }
          },
          error: function() {
            me.open_doc();
          },
          always: function() {
            me.dialog.working = false;
            resolve(me.dialog.doc);
          },
          freeze: true
        });
      });
    }
    open_doc() {
      this.dialog.hide();
      this.update_doc();
      if (this.dialog.fields_dict.create_variant.$input.prop("checked")) {
        var template = this.dialog.fields_dict.item_template.input.value;
        if (template)
          frappe.set_route("Form", this.doctype, template);
      } else {
        frappe.set_route("Form", this.doctype, this.doc.name);
      }
    }
    get_variant_fields() {
      var variant_fields = [
        {
          fieldname: "create_variant",
          fieldtype: "Check",
          label: __("Create Variant")
        },
        {
          fieldname: "item_template",
          label: __("Item Template"),
          reqd: 0,
          fieldtype: "Link",
          options: "Item",
          get_query: function() {
            return {
              filters: {
                has_variants: 1
              }
            };
          }
        }
      ];
      return variant_fields;
    }
    get_manufacturing_fields() {
      this.manufacturer_fields = [
        {
          fieldtype: "Link",
          options: "Manufacturer",
          label: "Manufacturer",
          fieldname: "manufacturer",
          hidden: 1,
          reqd: 0
        },
        {
          fieldtype: "Data",
          label: "Manufacturer Part Number",
          fieldname: "manufacturer_part_no",
          hidden: 1,
          reqd: 0
        }
      ];
      return this.manufacturer_fields;
    }
    get_attributes_fields() {
      var attribute_fields = [
        {
          fieldname: "attribute_html",
          fieldtype: "HTML"
        }
      ];
      attribute_fields = attribute_fields.concat(this.get_manufacturing_fields());
      return attribute_fields;
    }
    init_for_create_variant_trigger() {
      var me = this;
      this.dialog.fields_dict.create_variant.$input.on("click", function() {
        me.preset_fields_for_template();
        me.init_post_template_trigger_operations(false, [], true);
      });
    }
    preset_fields_for_template() {
      var for_variant = this.dialog.get_value("create_variant");
      let template_field = this.dialog.get_field("item_template");
      template_field.df.reqd = for_variant;
      template_field.set_value("");
      template_field.df.hidden = !for_variant;
      template_field.refresh();
      ["item_code", "item_name", "item_group", "stock_uom"].forEach((d) => {
        let f = this.dialog.get_field(d);
        f.df.hidden = for_variant;
        f.refresh();
      });
      this.dialog.get_field("attribute_html").toggle(false);
      ["item_code", "stock_uom", "item_group"].forEach((d) => {
        let f = this.dialog.get_field(d);
        f.df.reqd = !for_variant;
        f.refresh();
      });
    }
    init_for_item_template_trigger() {
      var me = this;
      me.dialog.fields_dict["item_template"].df.onchange = () => {
        var template = me.dialog.fields_dict.item_template.input.value;
        me.template_doc = null;
        if (template) {
          frappe.call({
            method: "frappe.client.get",
            args: {
              doctype: "Item",
              name: template
            },
            callback: function(r) {
              me.template_doc = r.message;
              me.is_manufacturer = false;
              if (me.template_doc.variant_based_on === "Manufacturer") {
                me.init_post_template_trigger_operations(true, [], true);
              } else {
                me.init_post_template_trigger_operations(false, me.template_doc.attributes, false);
                me.render_attributes(me.template_doc.attributes);
              }
            }
          });
        } else {
          me.dialog.get_field("attribute_html").toggle(false);
          me.init_post_template_trigger_operations(false, [], true);
        }
      };
    }
    init_post_template_trigger_operations(is_manufacturer, attributes, attributes_flag) {
      this.attributes = attributes;
      this.attribute_values = {};
      this.attributes_count = attributes.length;
      this.dialog.fields_dict.attribute_html.$wrapper.find(".attributes").empty();
      this.is_manufacturer = is_manufacturer;
      this.toggle_manufacturer_fields();
      this.dialog.fields_dict.attribute_html.$wrapper.find(".attributes").toggleClass("hide-control", attributes_flag);
      this.dialog.fields_dict.attribute_html.$wrapper.find(".attributes-header").toggleClass("hide-control", attributes_flag);
    }
    toggle_manufacturer_fields() {
      var me = this;
      $.each(this.manufacturer_fields, function(i, dialog_field) {
        me.dialog.get_field(dialog_field.fieldname).df.hidden = !me.is_manufacturer;
        me.dialog.get_field(dialog_field.fieldname).df.reqd = dialog_field.fieldname == "manufacturer" ? me.is_manufacturer : false;
        me.dialog.get_field(dialog_field.fieldname).refresh();
      });
    }
    initiate_render_attributes() {
      this.dialog.fields_dict.attribute_html.$wrapper.find(".attributes").empty();
      this.render_attributes(this.attributes);
    }
    render_attributes(attributes) {
      var me = this;
      this.dialog.get_field("attribute_html").toggle(true);
      $.each(attributes, function(index, row) {
        var desc = "";
        var fieldtype = "Data";
        if (row.numeric_values) {
          fieldtype = "Float";
          desc = "Min Value: " + row.from_range + " , Max Value: " + row.to_range + ", in Increments of: " + row.increment;
        }
        me.init_make_control(fieldtype, row);
        me[row.attribute].set_value(me.attribute_values[row.attribute] || "");
        me[row.attribute].$wrapper.toggleClass("has-error", me.attribute_values[row.attribute] ? false : true);
        $(me[row.attribute].label_area).text(__(row.attribute));
        if (desc) {
          $(repl(`<p class="help-box small text-muted hidden-xs">%(desc)s</p>`, {
            desc
          })).insertAfter(me[row.attribute].input_area);
        }
        if (!row.numeric_values) {
          me.init_awesomplete_for_attribute(row);
        } else {
          me[row.attribute].$input.on("change", function() {
            me.attribute_values[row.attribute] = $(this).val();
            $(this).closest(".frappe-control").toggleClass("has-error", $(this).val() ? false : true);
          });
        }
      });
    }
    init_make_control(fieldtype, row) {
      this[row.attribute] = frappe.ui.form.make_control({
        df: {
          fieldtype,
          label: row.attribute,
          fieldname: row.attribute,
          options: row.options || ""
        },
        parent: $(this.dialog.fields_dict.attribute_html.wrapper).find(".attributes"),
        only_input: false
      });
      this[row.attribute].make_input();
    }
    init_awesomplete_for_attribute(row) {
      var me = this;
      this[row.attribute].input.awesomplete = new Awesomplete(this[row.attribute].input, {
        minChars: 0,
        maxItems: 99,
        autoFirst: true,
        list: []
      });
      this[row.attribute].$input.on("input", function(e) {
        frappe.call({
          method: "frappe.client.get_list",
          args: {
            doctype: "Item Attribute Value",
            filters: [
              ["parent", "=", $(e.target).attr("data-fieldname")],
              ["attribute_value", "like", e.target.value + "%"]
            ],
            fields: ["attribute_value"],
            parent: "Item Attribute"
          },
          callback: function(r) {
            if (r.message) {
              e.target.awesomplete.list = r.message.map(function(d) {
                return d.attribute_value;
              });
            }
          }
        });
      }).on("focus", function(e) {
        $(e.target).val("").trigger("input");
      }).on("awesomplete-close", function(e) {
        me.attribute_values[$(e.target).attr("data-fieldname")] = e.target.value;
        $(e.target).closest(".frappe-control").toggleClass("has-error", e.target.value ? false : true);
      });
    }
    get_variant_doc() {
      var me = this;
      var variant_doc = {};
      var attribute = this.validate_mandatory_attributes();
      if (Object.keys(attribute).length) {
        frappe.call({
          method: "erpnext.controllers.item_variant.create_variant_doc_for_quick_entry",
          args: {
            template: me.dialog.fields_dict.item_template.$input.val(),
            args: attribute
          },
          async: false,
          callback: function(r) {
            if (Object.prototype.toString.call(r.message) == "[object Object]") {
              variant_doc = r.message;
            } else {
              var msgprint_dialog = frappe.msgprint(__("Item Variant {0} already exists with same attributes", [
                repl('<a class="strong variant-click" data-item-code="%(item)s" 								>%(item)s</a>', {
                  item: r.message
                })
              ]));
              msgprint_dialog.$wrapper.find(".variant-click").on("click", function() {
                msgprint_dialog.hide();
                me.dialog.hide();
                if (frappe._from_link) {
                  frappe._from_link.set_value($(this).attr("data-item-code"));
                } else {
                  frappe.set_route("Form", "Item", $(this).attr("data-item-code"));
                }
              });
            }
          }
        });
      }
      return variant_doc;
    }
    validate_mandatory_attributes() {
      var me = this;
      var attribute = {};
      var mandatory = [];
      $.each(this.attributes, function(index, attr) {
        var value = me.attribute_values[attr.attribute] || "";
        if (value) {
          attribute[attr.attribute] = attr.numeric_values ? flt(value) : value;
        } else {
          mandatory.push(attr.attribute);
        }
      });
      if (this.is_manufacturer) {
        $.each(this.manufacturer_fields, function(index, field) {
          attribute[field.fieldname] = me.dialog.fields_dict[field.fieldname].input.value;
        });
      }
      return attribute;
    }
  };

  // ../erpnext/erpnext/public/js/utils/contact_address_quick_entry.js
  frappe.provide("frappe.ui.form");
  frappe.ui.form.ContactAddressQuickEntryForm = class ContactAddressQuickEntryForm extends frappe.ui.form.QuickEntryForm {
    constructor(doctype, after_insert, init_callback, doc, force) {
      super(doctype, after_insert, init_callback, doc, force);
      this.skip_redirect_on_error = true;
    }
    render_dialog() {
      this.mandatory = this.mandatory.concat(this.get_variant_fields());
      super.render_dialog();
    }
    insert() {
      const map_field_names = {
        email_address: "email_id",
        mobile_number: "mobile_no"
      };
      Object.entries(map_field_names).forEach(([fieldname, new_fieldname]) => {
        this.dialog.doc[new_fieldname] = this.dialog.doc[fieldname];
        delete this.dialog.doc[fieldname];
      });
      return super.insert();
    }
    get_variant_fields() {
      var variant_fields = [
        {
          fieldtype: "Section Break",
          label: __("Primary Contact Details"),
          collapsible: 1
        },
        {
          label: __("Email Id"),
          fieldname: "email_address",
          fieldtype: "Data",
          options: "Email"
        },
        {
          fieldtype: "Column Break"
        },
        {
          label: __("Mobile Number"),
          fieldname: "mobile_number",
          fieldtype: "Data"
        },
        {
          fieldtype: "Section Break",
          label: __("Primary Address Details"),
          collapsible: 1
        },
        {
          label: __("Address Line 1"),
          fieldname: "address_line1",
          fieldtype: "Data"
        },
        {
          label: __("Address Line 2"),
          fieldname: "address_line2",
          fieldtype: "Data"
        },
        {
          label: __("ZIP Code"),
          fieldname: "pincode",
          fieldtype: "Data"
        },
        {
          fieldtype: "Column Break"
        },
        {
          label: __("City"),
          fieldname: "city",
          fieldtype: "Data"
        },
        {
          label: __("State"),
          fieldname: "state",
          fieldtype: "Data"
        },
        {
          label: __("Country"),
          fieldname: "country",
          fieldtype: "Link",
          options: "Country"
        },
        {
          label: __("Customer POS Id"),
          fieldname: "customer_pos_id",
          fieldtype: "Data",
          hidden: 1
        }
      ];
      return variant_fields;
    }
  };

  // ../erpnext/erpnext/public/js/utils/customer_quick_entry.js
  frappe.provide("frappe.ui.form");
  frappe.ui.form.CustomerQuickEntryForm = frappe.ui.form.ContactAddressQuickEntryForm;

  // ../erpnext/erpnext/public/js/utils/supplier_quick_entry.js
  frappe.provide("frappe.ui.form");
  frappe.ui.form.SupplierQuickEntryForm = frappe.ui.form.ContactAddressQuickEntryForm;

  // ../erpnext/erpnext/public/js/call_popup/call_popup.js
  var CallPopup = class {
    constructor(call_log) {
      this.caller_number = call_log.from;
      this.call_log = call_log;
      this.setup_listener();
      this.make();
    }
    make() {
      frappe.utils.play_sound("incoming-call");
      this.dialog = new frappe.ui.Dialog({
        static: true,
        minimizable: true
      });
      this.dialog.get_close_btn().show();
      this.setup_dialog();
      this.set_call_status();
      frappe.utils.bind_actions_with_object(this.dialog.$body, this);
      this.dialog.$wrapper.addClass("call-popup");
      this.dialog.get_close_btn().unbind("click").click(this.close_modal.bind(this));
      this.dialog.show();
    }
    setup_dialog() {
      this.setup_call_details();
      this.dialog.$body.empty().append(this.caller_info);
    }
    set_indicator(color, blink = false) {
      let classes = `indicator ${color} ${blink ? "blink" : ""}`;
      this.dialog.header.find(".indicator").attr("class", classes);
    }
    set_call_status(call_status) {
      let title = "";
      call_status = call_status || this.call_log.status;
      if (["Ringing"].includes(call_status) || !call_status) {
        title = __("Incoming call from {0}", [this.get_caller_name() || this.caller_number]);
        this.set_indicator("blue", true);
      } else if (call_status === "In Progress") {
        title = __("Call Connected");
        this.set_indicator("green");
      } else if (["No Answer", "Missed"].includes(call_status)) {
        this.set_indicator("yellow");
        title = __("Call Missed");
      } else if (["Completed", "Busy", "Failed"].includes(call_status)) {
        this.set_indicator("red");
        title = __("Call Ended");
      } else {
        this.set_indicator("blue");
        title = call_status;
      }
      this.dialog.set_title(title);
    }
    update_call_log(call_log, missed) {
      this.call_log = call_log;
      this.set_call_status(missed ? "Missed" : null);
    }
    close_modal() {
      this.dialog.hide();
      delete erpnext.call_popup;
    }
    call_ended(call_log, missed) {
      frappe.utils.play_sound("call-disconnect");
      this.update_call_log(call_log, missed);
      setTimeout(() => {
        if (!this.dialog.get_value("call_summary")) {
          this.close_modal();
        }
      }, 6e4);
      this.clear_listeners();
    }
    get_caller_name() {
      const contact_link = this.get_contact_link();
      return contact_link.link_title || contact_link.link_name;
    }
    get_contact_link() {
      let log = this.call_log;
      let contact_link = log.links.find((d) => d.link_doctype === "Contact");
      return contact_link || {};
    }
    setup_listener() {
      frappe.realtime.on(`call_${this.call_log.id}_ended`, (call_log) => {
        this.call_ended(call_log);
      });
      frappe.realtime.on(`call_${this.call_log.id}_missed`, (call_log) => {
        this.call_ended(call_log, true);
      });
    }
    clear_listeners() {
      frappe.realtime.off(`call_${this.call_log.id}_ended`);
      frappe.realtime.off(`call_${this.call_log.id}_missed`);
    }
    setup_call_details() {
      this.caller_info = $(`<div></div>`);
      this.call_details = new frappe.ui.FieldGroup({
        fields: [
          {
            fieldname: "name",
            label: "Name",
            default: this.get_caller_name() || __("Unknown Caller"),
            fieldtype: "Data",
            read_only: 1
          },
          {
            fieldtype: "Button",
            label: __("Open Contact"),
            click: () => frappe.set_route("Form", "Contact", this.get_contact_link().link_name),
            depends_on: () => this.get_caller_name()
          },
          {
            fieldtype: "Button",
            label: __("Create New Contact"),
            click: this.create_new_contact.bind(this),
            depends_on: () => !this.get_caller_name()
          },
          {
            fieldtype: "Button",
            label: __("Create New Customer"),
            click: this.create_new_customer.bind(this),
            depends_on: () => !this.get_caller_name()
          },
          {
            fieldtype: "Button",
            label: __("Create New Lead"),
            click: () => frappe.new_doc("Lead", { mobile_no: this.caller_number }),
            depends_on: () => !this.get_caller_name()
          },
          {
            fieldtype: "Column Break"
          },
          {
            fieldname: "number",
            label: "Phone Number",
            fieldtype: "Data",
            default: this.caller_number,
            read_only: 1
          },
          {
            fieldtype: "Section Break",
            hide_border: 1
          },
          {
            fieldname: "call_type",
            label: "Call Type",
            fieldtype: "Link",
            options: "Telephony Call Type"
          },
          {
            fieldtype: "Section Break",
            hide_border: 1
          },
          {
            fieldtype: "Small Text",
            label: __("Call Summary"),
            fieldname: "call_summary"
          },
          {
            fieldtype: "Button",
            label: __("Save"),
            click: () => {
              const call_summary = this.call_details.get_value("call_summary");
              const call_type = this.call_details.get_value("call_type");
              if (!call_summary)
                return;
              frappe.xcall("erpnext.telephony.doctype.call_log.call_log.add_call_summary_and_call_type", {
                call_log: this.call_log.name,
                summary: call_summary,
                call_type
              }).then(() => {
                this.close_modal();
                frappe.show_alert({
                  message: `
								${__("Call Summary Saved")}
								<br>
								<a
									class="text-small text-muted"
									href="/app/call-log/${this.call_log.name}">
									${__("View call log")}
								</a>
							`,
                  indicator: "green"
                });
              });
            }
          }
        ],
        body: this.caller_info
      });
      this.call_details.make();
    }
    is_known_caller() {
      return Boolean(this.get_caller_name());
    }
    create_new_customer() {
      const new_customer = frappe.model.get_new_doc("Customer");
      new_customer.mobile_no = this.caller_number;
      frappe.set_route("Form", new_customer.doctype, new_customer.name);
    }
    create_new_contact() {
      const new_contact = frappe.model.get_new_doc("Contact");
      const phone_no = frappe.model.add_child(new_contact, "Contact Phone", "phone_nos");
      phone_no.phone = this.caller_number;
      phone_no.is_primary_mobile_no = 1;
      frappe.set_route("Form", new_contact.doctype, new_contact.name);
    }
  };
  $(document).on("app_ready", function() {
    frappe.realtime.on("show_call_popup", (call_log) => {
      let call_popup = erpnext.call_popup;
      if (call_popup && call_log.name === call_popup.call_log.name) {
        call_popup.update_call_log(call_log);
        call_popup.dialog.show();
      } else {
        erpnext.call_popup = new CallPopup(call_log);
      }
    });
  });
  window.CallPopup = CallPopup;

  // ../erpnext/erpnext/public/js/utils/dimension_tree_filter.js
  frappe.provide("erpnext.accounts");
  erpnext.accounts.dimensions = {
    setup_dimension_filters(frm, doctype) {
      this.accounting_dimensions = [];
      this.default_dimensions = {};
      this.fetch_custom_dimensions(frm, doctype);
    },
    fetch_custom_dimensions(frm, doctype) {
      let me = this;
      frappe.call({
        method: "erpnext.accounts.doctype.accounting_dimension.accounting_dimension.get_dimensions",
        args: {
          with_cost_center_and_project: true
        },
        callback: function(r) {
          me.accounting_dimensions = r.message[0];
          me.accounting_dimensions = me.accounting_dimensions.filter((x) => {
            return x.document_type != "Project";
          });
          me.default_dimensions = r.message[1];
          me.setup_filters(frm, doctype);
        }
      });
    },
    setup_filters(frm, doctype) {
      if (doctype == "Payment Entry" && this.accounting_dimensions) {
        frm.dimension_filters = this.accounting_dimensions;
      }
      if (this.accounting_dimensions) {
        this.accounting_dimensions.forEach((dimension) => {
          frappe.model.with_doctype(dimension["document_type"], () => {
            let parent_fields = [];
            frappe.meta.get_docfields(doctype).forEach((df) => {
              if (df.fieldtype === "Link" && df.options === "Account") {
                parent_fields.push(df.fieldname);
              } else if (df.fieldtype === "Table") {
                this.setup_child_filters(frm, df.options, df.fieldname, dimension["fieldname"]);
              }
              if (frappe.meta.has_field(doctype, dimension["fieldname"])) {
                this.setup_account_filters(frm, dimension["fieldname"], parent_fields);
              }
            });
          });
        });
      }
    },
    setup_child_filters(frm, doctype, parentfield, dimension) {
      let fields = [];
      if (frappe.meta.has_field(doctype, dimension)) {
        frappe.model.with_doctype(doctype, () => {
          frappe.meta.get_docfields(doctype).forEach((df) => {
            if (df.fieldtype === "Link" && df.options === "Account") {
              fields.push(df.fieldname);
            }
          });
          frm.set_query(dimension, parentfield, function(doc, cdt, cdn) {
            let row = locals[cdt][cdn];
            return erpnext.queries.get_filtered_dimensions(row, fields, dimension, doc.company);
          });
        });
      }
    },
    setup_account_filters(frm, dimension, fields) {
      frm.set_query(dimension, function(doc) {
        return erpnext.queries.get_filtered_dimensions(doc, fields, dimension, doc.company);
      });
    },
    update_dimension(frm, doctype) {
      if (this.accounting_dimensions) {
        this.accounting_dimensions.forEach((dimension) => {
          if (frm.is_new()) {
            if (frm.doc.company && Object.keys(this.default_dimensions || {}).length > 0 && this.default_dimensions[frm.doc.company]) {
              let default_dimension = this.default_dimensions[frm.doc.company][dimension["fieldname"]];
              if (default_dimension) {
                if (frappe.meta.has_field(doctype, dimension["fieldname"])) {
                  frm.set_value(dimension["fieldname"], default_dimension);
                }
                $.each(frm.doc.items || frm.doc.accounts || [], function(i, row) {
                  frappe.model.set_value(row.doctype, row.name, dimension["fieldname"], default_dimension);
                });
              }
            }
          }
        });
      }
    },
    copy_dimension_from_first_row(frm, cdt, cdn, fieldname) {
      if (frappe.meta.has_field(frm.doctype, fieldname) && this.accounting_dimensions) {
        this.accounting_dimensions.forEach((dimension) => {
          let row = frappe.get_doc(cdt, cdn);
          frm.script_manager.copy_from_first_row(fieldname, row, [dimension["fieldname"]]);
        });
      }
    }
  };

  // ../erpnext/erpnext/public/js/utils/unreconcile.js
  frappe.provide("erpnext.accounts");
  erpnext.accounts.unreconcile_payment = {
    add_unreconcile_btn(frm) {
      if (frm.doc.docstatus == 1) {
        if (frm.doc.doctype == "Journal Entry" && frm.doc.voucher_type != "Journal Entry" || !["Purchase Invoice", "Sales Invoice", "Journal Entry", "Payment Entry"].includes(frm.doc.doctype)) {
          return;
        }
        frappe.call({
          method: "erpnext.accounts.doctype.unreconcile_payment.unreconcile_payment.doc_has_references",
          args: {
            doctype: frm.doc.doctype,
            docname: frm.doc.name
          },
          callback: function(r) {
            if (r.message) {
              frm.add_custom_button(__("UnReconcile"), function() {
                erpnext.accounts.unreconcile_payment.build_unreconcile_dialog(frm);
              }, __("Actions"));
            }
          }
        });
      }
    },
    build_selection_map(frm, selections) {
      let selection_map = [];
      if (["Sales Invoice", "Purchase Invoice"].includes(frm.doc.doctype)) {
        selection_map = selections.map(function(elem) {
          return {
            company: elem.company,
            voucher_type: elem.voucher_type,
            voucher_no: elem.voucher_no,
            against_voucher_type: frm.doc.doctype,
            against_voucher_no: frm.doc.name
          };
        });
      } else if (["Payment Entry", "Journal Entry"].includes(frm.doc.doctype)) {
        selection_map = selections.map(function(elem) {
          return {
            company: elem.company,
            voucher_type: frm.doc.doctype,
            voucher_no: frm.doc.name,
            against_voucher_type: elem.voucher_type,
            against_voucher_no: elem.voucher_no
          };
        });
      }
      return selection_map;
    },
    build_unreconcile_dialog(frm) {
      if (["Sales Invoice", "Purchase Invoice", "Payment Entry", "Journal Entry"].includes(frm.doc.doctype)) {
        let child_table_fields = [
          {
            label: __("Voucher Type"),
            fieldname: "voucher_type",
            fieldtype: "Dynamic Link",
            options: "DocType",
            in_list_view: 1,
            read_only: 1
          },
          {
            label: __("Voucher No"),
            fieldname: "voucher_no",
            fieldtype: "Link",
            options: "voucher_type",
            in_list_view: 1,
            read_only: 1
          },
          {
            label: __("Allocated Amount"),
            fieldname: "allocated_amount",
            fieldtype: "Currency",
            in_list_view: 1,
            read_only: 1,
            options: "account_currency"
          },
          { label: __("Currency"), fieldname: "account_currency", fieldtype: "Currency", read_only: 1 }
        ];
        let unreconcile_dialog_fields = [
          {
            label: __("Allocations"),
            fieldname: "allocations",
            fieldtype: "Table",
            read_only: 1,
            fields: child_table_fields
          }
        ];
        frappe.call({
          method: "erpnext.accounts.doctype.unreconcile_payment.unreconcile_payment.get_linked_payments_for_doc",
          args: {
            company: frm.doc.company,
            doctype: frm.doc.doctype,
            docname: frm.doc.name
          },
          callback: function(r) {
            if (r.message) {
              unreconcile_dialog_fields[0].data = r.message;
              unreconcile_dialog_fields[0].get_data = function() {
                return r.message;
              };
              let d = new frappe.ui.Dialog({
                title: "UnReconcile Allocations",
                fields: unreconcile_dialog_fields,
                size: "large",
                cannot_add_rows: true,
                primary_action_label: "UnReconcile",
                primary_action(values) {
                  let selected_allocations = values.allocations.filter((x) => x.__checked);
                  if (selected_allocations.length > 0) {
                    let selection_map = erpnext.accounts.unreconcile_payment.build_selection_map(frm, selected_allocations);
                    erpnext.accounts.unreconcile_payment.create_unreconcile_docs(selection_map);
                    d.hide();
                  } else {
                    frappe.msgprint("No Selection");
                  }
                }
              });
              d.show();
            }
          }
        });
      }
    },
    create_unreconcile_docs(selection_map) {
      frappe.call({
        method: "erpnext.accounts.doctype.unreconcile_payment.unreconcile_payment.create_unreconcile_doc_for_selection",
        args: {
          selections: selection_map
        }
      });
    }
  };

  // ../erpnext/erpnext/public/js/utils/barcode_scanner.js
  erpnext.utils.BarcodeScanner = class BarcodeScanner {
    constructor(opts) {
      this.frm = opts.frm;
      this.scan_field_name = opts.scan_field_name || "scan_barcode";
      this.scan_barcode_field = this.frm.fields_dict[this.scan_field_name];
      this.barcode_field = opts.barcode_field || "barcode";
      this.serial_no_field = opts.serial_no_field || "serial_no";
      this.batch_no_field = opts.batch_no_field || "batch_no";
      this.uom_field = opts.uom_field || "uom";
      this.qty_field = opts.qty_field || "qty";
      this.max_qty_field = opts.max_qty_field;
      this.dont_allow_new_row = opts.dont_allow_new_row;
      this.prompt_qty = opts.prompt_qty;
      this.items_table_name = opts.items_table_name || "items";
      this.items_table = this.frm.doc[this.items_table_name];
      this.success_sound = opts.play_success_sound;
      this.fail_sound = opts.play_fail_sound;
      this.scan_api = opts.scan_api || "erpnext.stock.utils.scan_barcode";
    }
    process_scan() {
      return new Promise((resolve, reject2) => {
        let me = this;
        const input = this.scan_barcode_field.value;
        this.scan_barcode_field.set_value("");
        if (!input) {
          return;
        }
        this.scan_api_call(input, (r) => {
          const data = r && r.message;
          if (!data || Object.keys(data).length === 0) {
            this.show_alert(__("Cannot find Item with this Barcode"), "red");
            this.clean_up();
            this.play_fail_sound();
            reject2();
            return;
          }
          me.update_table(data).then((row) => {
            this.play_success_sound();
            resolve(row);
          }).catch(() => {
            this.play_fail_sound();
            reject2();
          });
        });
      });
    }
    scan_api_call(input, callback) {
      frappe.call({
        method: this.scan_api,
        args: {
          search_value: input
        }
      }).then((r) => {
        callback(r);
      });
    }
    update_table(data) {
      return new Promise((resolve) => {
        let cur_grid = this.frm.fields_dict[this.items_table_name].grid;
        frappe.flags.trigger_from_barcode_scanner = true;
        const { item_code, barcode, batch_no, serial_no, uom } = data;
        let row = this.get_row_to_modify_on_scan(item_code, batch_no, uom, barcode);
        this.is_new_row = false;
        if (!row) {
          if (this.dont_allow_new_row) {
            this.show_alert(__("Maximum quantity scanned for item {0}.", [item_code]), "red");
            this.clean_up();
            reject();
            return;
          }
          this.is_new_row = true;
          row = frappe.model.add_child(this.frm.doc, cur_grid.doctype, this.items_table_name);
          this.frm.script_manager.trigger(`${this.items_table_name}_add`, row.doctype, row.name);
          this.frm.has_items = false;
        }
        if (this.is_duplicate_serial_no(row, serial_no)) {
          this.clean_up();
          reject();
          return;
        }
        frappe.run_serially([
          () => this.set_selector_trigger_flag(data),
          () => this.set_item(row, item_code, barcode, batch_no, serial_no).then((qty) => {
            this.show_scan_message(row.idx, row.item_code, qty);
          }),
          () => this.set_barcode_uom(row, uom),
          () => this.set_serial_no(row, serial_no),
          () => this.set_batch_no(row, batch_no),
          () => this.set_barcode(row, barcode),
          () => this.clean_up(),
          () => this.revert_selector_flag(),
          () => resolve(row)
        ]);
      });
    }
    set_selector_trigger_flag(data) {
      const { batch_no, serial_no, has_batch_no, has_serial_no } = data;
      const require_selecting_batch = has_batch_no && !batch_no;
      const require_selecting_serial = has_serial_no && !serial_no;
      if (!(require_selecting_batch || require_selecting_serial)) {
        frappe.flags.hide_serial_batch_dialog = true;
      }
    }
    revert_selector_flag() {
      frappe.flags.hide_serial_batch_dialog = false;
      frappe.flags.trigger_from_barcode_scanner = false;
    }
    set_item(row, item_code, barcode, batch_no, serial_no) {
      return new Promise((resolve) => {
        const increment = async (value = 1) => {
          const item_data = { item_code };
          frappe.flags.trigger_from_barcode_scanner = true;
          item_data[this.qty_field] = Number(row[this.qty_field] || 0) + Number(value);
          await frappe.model.set_value(row.doctype, row.name, item_data);
          return value;
        };
        if (this.prompt_qty) {
          frappe.prompt(__("Please enter quantity for item {0}", [item_code]), ({ value }) => {
            increment(value).then((value2) => resolve(value2));
          });
        } else if (this.frm.has_items) {
          this.prepare_item_for_scan(row, item_code, barcode, batch_no, serial_no);
        } else {
          increment().then((value) => resolve(value));
        }
      });
    }
    prepare_item_for_scan(row, item_code, barcode, batch_no, serial_no) {
      var me = this;
      this.dialog = new frappe.ui.Dialog({
        title: __("Scan barcode for item {0}", [item_code]),
        fields: me.get_fields_for_dialog(row, item_code, barcode, batch_no, serial_no)
      });
      this.dialog.set_primary_action(__("Update"), () => {
        const item_data = { item_code };
        item_data[this.qty_field] = this.dialog.get_value("scanned_qty");
        item_data["has_item_scanned"] = 1;
        this.remaining_qty = flt(this.dialog.get_value("qty")) - flt(this.dialog.get_value("scanned_qty"));
        frappe.model.set_value(row.doctype, row.name, item_data);
        frappe.run_serially([
          () => this.set_batch_no(row, this.dialog.get_value("batch_no")),
          () => this.set_barcode(row, this.dialog.get_value("barcode")),
          () => this.set_serial_no(row, this.dialog.get_value("serial_no")),
          () => this.add_child_for_remaining_qty(row),
          () => this.clean_up()
        ]);
        this.dialog.hide();
      });
      this.dialog.show();
      this.$scan_btn = this.dialog.$wrapper.find(".link-btn");
      this.$scan_btn.css("display", "inline");
    }
    get_fields_for_dialog(row, item_code, barcode, batch_no, serial_no) {
      let fields = [
        {
          fieldtype: "Data",
          fieldname: "barcode_scanner",
          options: "Barcode",
          label: __("Scan Barcode"),
          onchange: (e) => {
            if (!e) {
              return;
            }
            if (e.target.value) {
              this.scan_api_call(e.target.value, (r) => {
                if (r.message) {
                  this.update_dialog_values(item_code, r);
                }
              });
            }
          }
        },
        {
          fieldtype: "Section Break"
        },
        {
          fieldtype: "Float",
          fieldname: "qty",
          label: __("Quantity to Scan"),
          default: row[this.qty_field] || 1
        },
        {
          fieldtype: "Column Break",
          fieldname: "column_break_1"
        },
        {
          fieldtype: "Float",
          read_only: 1,
          fieldname: "scanned_qty",
          label: __("Scanned Quantity"),
          default: 1
        },
        {
          fieldtype: "Section Break"
        }
      ];
      if (batch_no) {
        fields.push({
          fieldtype: "Link",
          fieldname: "batch_no",
          options: "Batch No",
          label: __("Batch No"),
          default: batch_no,
          read_only: 1,
          hidden: 1
        });
      }
      if (serial_no) {
        fields.push({
          fieldtype: "Small Text",
          fieldname: "serial_no",
          label: __("Serial Nos"),
          default: serial_no,
          read_only: 1
        });
      }
      if (barcode) {
        fields.push({
          fieldtype: "Data",
          fieldname: "barcode",
          options: "Barcode",
          label: __("Barcode"),
          default: barcode,
          read_only: 1,
          hidden: 1
        });
      }
      return fields;
    }
    update_dialog_values(scanned_item, r) {
      const { item_code, barcode, batch_no, serial_no } = r.message;
      this.dialog.set_value("barcode_scanner", "");
      if (item_code === scanned_item && (this.dialog.get_value("barcode") === barcode || batch_no || serial_no)) {
        if (batch_no) {
          this.dialog.set_value("batch_no", batch_no);
        }
        if (serial_no) {
          this.validate_duplicate_serial_no(serial_no);
          let serial_nos = this.dialog.get_value("serial_no") + "\n" + serial_no;
          this.dialog.set_value("serial_no", serial_nos);
        }
        let qty = flt(this.dialog.get_value("scanned_qty")) + 1;
        this.dialog.set_value("scanned_qty", qty);
      }
    }
    validate_duplicate_serial_no(serial_no) {
      let serial_nos = this.dialog.get_value("serial_no") ? this.dialog.get_value("serial_no").split("\n") : [];
      if (in_list(serial_nos, serial_no)) {
        frappe.throw(__("Serial No {0} already scanned", [serial_no]));
      }
    }
    add_child_for_remaining_qty(prev_row) {
      if (this.remaining_qty && this.remaining_qty > 0) {
        let cur_grid = this.frm.fields_dict[this.items_table_name].grid;
        let row = frappe.model.add_child(this.frm.doc, cur_grid.doctype, this.items_table_name);
        let ignore_fields = [
          "name",
          "idx",
          "batch_no",
          "barcode",
          "received_qty",
          "serial_no",
          "has_item_scanned"
        ];
        for (let key in prev_row) {
          if (in_list(ignore_fields, key)) {
            continue;
          }
          row[key] = prev_row[key];
        }
        row[this.qty_field] = this.remaining_qty;
        if (this.qty_field == "qty" && frappe.meta.has_field(row.doctype, "stock_qty")) {
          row["stock_qty"] = this.remaining_qty * row.conversion_factor;
        }
        this.frm.script_manager.trigger("item_code", row.doctype, row.name);
      }
    }
    async set_serial_no(row, serial_no) {
      if (serial_no && frappe.meta.has_field(row.doctype, this.serial_no_field)) {
        const existing_serial_nos = row[this.serial_no_field];
        let new_serial_nos = "";
        if (!!existing_serial_nos) {
          new_serial_nos = existing_serial_nos + "\n" + serial_no;
        } else {
          new_serial_nos = serial_no;
        }
        await frappe.model.set_value(row.doctype, row.name, this.serial_no_field, new_serial_nos);
      }
    }
    async set_barcode_uom(row, uom) {
      if (uom && frappe.meta.has_field(row.doctype, this.uom_field)) {
        await frappe.model.set_value(row.doctype, row.name, this.uom_field, uom);
      }
    }
    async set_batch_no(row, batch_no) {
      if (batch_no && frappe.meta.has_field(row.doctype, this.batch_no_field)) {
        await frappe.model.set_value(row.doctype, row.name, this.batch_no_field, batch_no);
      }
    }
    async set_barcode(row, barcode) {
      if (barcode && frappe.meta.has_field(row.doctype, this.barcode_field)) {
        await frappe.model.set_value(row.doctype, row.name, this.barcode_field, barcode);
      }
    }
    show_scan_message(idx, exist = null, qty = 1) {
      if (exist) {
        this.show_alert(__("Row #{0}: Qty increased by {1}", [idx, qty]), "green");
      } else {
        this.show_alert(__("Row #{0}: Item added", [idx]), "green");
      }
    }
    is_duplicate_serial_no(row, serial_no) {
      var _a;
      const is_duplicate = (_a = row[this.serial_no_field]) == null ? void 0 : _a.includes(serial_no);
      if (is_duplicate) {
        this.show_alert(__("Serial No {0} is already added", [serial_no]), "orange");
      }
      return is_duplicate;
    }
    get_row_to_modify_on_scan(item_code, batch_no, uom, barcode) {
      let cur_grid = this.frm.fields_dict[this.items_table_name].grid;
      let is_batch_no_scan = batch_no && frappe.meta.has_field(cur_grid.doctype, this.batch_no_field);
      let check_max_qty = this.max_qty_field && frappe.meta.has_field(cur_grid.doctype, this.max_qty_field);
      const matching_row = (row) => {
        const item_match = row.item_code == item_code;
        const batch_match = !row[this.batch_no_field] || row[this.batch_no_field] == batch_no;
        const uom_match = !uom || row[this.uom_field] == uom;
        const qty_in_limit = flt(row[this.qty_field]) < flt(row[this.max_qty_field]);
        const item_scanned = row.has_item_scanned;
        return item_match && uom_match && !item_scanned && (!is_batch_no_scan || batch_match) && (!check_max_qty || qty_in_limit);
      };
      return this.items_table.find(matching_row) || this.get_existing_blank_row();
    }
    get_existing_blank_row() {
      return this.items_table.find((d) => !d.item_code);
    }
    play_success_sound() {
      this.success_sound && frappe.utils.play_sound(this.success_sound);
    }
    play_fail_sound() {
      this.fail_sound && frappe.utils.play_sound(this.fail_sound);
    }
    clean_up() {
      this.scan_barcode_field.set_value("");
      refresh_field(this.items_table_name);
    }
    show_alert(msg, indicator, duration = 3) {
      frappe.show_alert({ message: msg, indicator }, duration);
    }
  };

  // ../erpnext/erpnext/public/js/telephony.js
  frappe.ui.form.ControlData = class ControlData extends frappe.ui.form.ControlData {
    make_input() {
      super.make_input();
      if (this.df.options == "Phone") {
        this.setup_phone();
      }
      if (this.frm && this.frm.fields_dict) {
        Object.values(this.frm.fields_dict).forEach(function(field) {
          if (field.df.read_only === 1 && field.df.options === "Phone" && field.disp_area.style[0] != "display" && !field.has_icon) {
            field.setup_phone();
            field.has_icon = true;
          }
        });
      }
    }
    setup_phone() {
      if (frappe.phone_call.handler) {
        let control = this.df.read_only ? ".control-value" : ".control-input";
        this.$wrapper.find(control).append(`
					<span class="phone-btn">
						<a class="btn-open no-decoration" title="${__("Make a call")}">
							${frappe.utils.icon("call")}
					</span>
				`).find(".phone-btn").click(() => {
          frappe.phone_call.handler(this.get_value(), this.frm);
        });
      }
    }
  };

  // frappe-html:/media/n/Files/projects/metactical_v14/apps/metactical/metactical/erpnext_public/js/templates/call_link.html
  frappe.templates["call_link"] = `<div class="call-detail-wrapper">
	<div class="head flex justify-between">
		<div>
			<span class="bold"> {{ type }} Call</span>
			{% if (duration) %}
			<span class="text-muted"> \u2022 {{ frappe.format(duration, { fieldtype: "Duration" }) }}</span>
			{% endif %}
			<span class="text-muted"> \u2022 {{ comment_when(creation) }}</span>
		</div>
		<span>
			<a class="action-btn" href="/app/call-log/{{ name }}" title="{{ __("Open Call Log") }}">
				<svg class="icon icon-sm">
					<use href="#icon-link-url" class="like-icon"></use>
				</svg>
			</a>
		</span>
	</div>


	<div class="body pt-3">
		{% if (type === "Incoming") { %}
			<span> Incoming call from {{ from }}, received by {{ to }}</span>
		{% } else { %}
			<span> Outgoing Call made by {{ from }} to {{ to }}</span>
		{% } %}
		<div class="summary pt-3">
		{% if (summary) { %}
			<i>{{ summary }}</i>
		{% } else { %}
			<i class="text-muted">{{ __("No Summary") }}</i>
		{% } %}
		</div>
		{% if (recording_url) { %}
		<div class="margin-top">
				<audio
					controls
					src="{{ recording_url }}">
				</audio>
		</div>
		{% } %}
	</div>
</div>
`;

  // ../erpnext/erpnext/public/js/bulk_transaction_processing.js
  frappe.provide("erpnext.bulk_transaction_processing");
  $.extend(erpnext.bulk_transaction_processing, {
    create: function(listview, from_doctype, to_doctype) {
      let checked_items = listview.get_checked_items();
      const doc_name = [];
      checked_items.forEach((Item) => {
        if (Item.docstatus == 0) {
          doc_name.push(Item.name);
        }
      });
      let count_of_rows = checked_items.length;
      frappe.confirm(__("Create {0} {1} ?", [count_of_rows, to_doctype]), () => {
        if (doc_name.length == 0) {
          frappe.call({
            method: "erpnext.utilities.bulk_transaction.transaction_processing",
            args: { data: checked_items, from_doctype, to_doctype }
          }).then(() => {
          });
          if (count_of_rows > 10) {
            frappe.show_alert("Starting a background job to create {0} {1}", [
              count_of_rows,
              to_doctype
            ]);
          }
        } else {
          frappe.msgprint(__("Selected document must be in submitted state"));
        }
      });
    }
  });

  // ../erpnext/erpnext/public/js/utils/crm_activities.js
  erpnext.utils.CRMActivities = class CRMActivities {
    constructor(opts) {
      $.extend(this, opts);
    }
    refresh() {
      var me = this;
      $(this.open_activities_wrapper).empty();
      let cur_form_footer = this.form_wrapper.find(".form-footer");
      if (!$(this.all_activities_wrapper).find(".form-footer").length) {
        this.all_activities_wrapper.empty();
        $(cur_form_footer).appendTo(this.all_activities_wrapper);
        $(this.all_activities_wrapper).removeClass("frappe-control");
        $(".timeline-actions").find(".btn-default").hide();
        $(".comment-box").hide();
        $($(".timeline-content").find(".nav-link")[0]).tab("show");
      }
      frappe.call({
        method: "erpnext.crm.utils.get_open_activities",
        args: {
          ref_doctype: this.frm.doc.doctype,
          ref_docname: this.frm.doc.name
        },
        callback: (r) => {
          if (!r.exc) {
            var activities_html = frappe.render_template("crm_activities", {
              tasks: r.message.tasks,
              events: r.message.events
            });
            $(activities_html).appendTo(me.open_activities_wrapper);
            $(".open-tasks").find(".completion-checkbox").on("click", function() {
              me.update_status(this, "ToDo");
            });
            $(".open-events").find(".completion-checkbox").on("click", function() {
              me.update_status(this, "Event");
            });
            me.create_task();
            me.create_event();
          }
        }
      });
    }
    create_task() {
      let me = this;
      let _create_task = () => {
        const args = {
          doc: me.frm.doc,
          frm: me.frm,
          title: __("New Task")
        };
        let composer = new frappe.views.InteractionComposer(args);
        composer.dialog.get_field("interaction_type").set_value("ToDo");
        $(composer.dialog.get_field("interaction_type").wrapper).closest(".form-column").hide();
        $(composer.dialog.get_field("summary").wrapper).closest(".form-section").hide();
      };
      $(".new-task-btn").click(_create_task);
    }
    create_event() {
      let me = this;
      let _create_event = () => {
        const args = {
          doc: me.frm.doc,
          frm: me.frm,
          title: __("New Event")
        };
        let composer = new frappe.views.InteractionComposer(args);
        composer.dialog.get_field("interaction_type").set_value("Event");
        $(composer.dialog.get_field("interaction_type").wrapper).hide();
      };
      $(".new-event-btn").click(_create_event);
    }
    async update_status(input_field, doctype) {
      let completed = $(input_field).prop("checked") ? 1 : 0;
      let docname = $(input_field).attr("name");
      if (completed) {
        await frappe.db.set_value(doctype, docname, "status", "Closed");
        this.refresh();
      }
    }
  };
  erpnext.utils.CRMNotes = class CRMNotes {
    constructor(opts) {
      $.extend(this, opts);
    }
    refresh() {
      var me = this;
      this.notes_wrapper.find(".notes-section").remove();
      let notes = this.frm.doc.notes || [];
      notes.sort(function(a, b) {
        return new Date(b.added_on) - new Date(a.added_on);
      });
      let notes_html = frappe.render_template("crm_notes", {
        notes
      });
      $(notes_html).appendTo(this.notes_wrapper);
      this.add_note();
      $(".notes-section").find(".edit-note-btn").on("click", function() {
        me.edit_note(this);
      });
      $(".notes-section").find(".delete-note-btn").on("click", function() {
        me.delete_note(this);
      });
    }
    add_note() {
      let me = this;
      let _add_note = () => {
        var d = new frappe.ui.Dialog({
          title: __("Add a Note"),
          fields: [
            {
              label: "Note",
              fieldname: "note",
              fieldtype: "Text Editor",
              reqd: 1,
              enable_mentions: true
            }
          ],
          primary_action: function() {
            var data = d.get_values();
            frappe.call({
              method: "add_note",
              doc: me.frm.doc,
              args: {
                note: data.note
              },
              freeze: true,
              callback: function(r) {
                if (!r.exc) {
                  me.frm.refresh_field("notes");
                  me.refresh();
                }
                d.hide();
              }
            });
          },
          primary_action_label: __("Add")
        });
        d.show();
      };
      $(".new-note-btn").click(_add_note);
    }
    edit_note(edit_btn) {
      var me = this;
      let row = $(edit_btn).closest(".comment-content");
      let row_id = row.attr("name");
      let row_content = $(row).find(".content").html();
      if (row_content) {
        var d = new frappe.ui.Dialog({
          title: __("Edit Note"),
          fields: [
            {
              label: "Note",
              fieldname: "note",
              fieldtype: "Text Editor",
              default: row_content
            }
          ],
          primary_action: function() {
            var data = d.get_values();
            frappe.call({
              method: "edit_note",
              doc: me.frm.doc,
              args: {
                note: data.note,
                row_id
              },
              freeze: true,
              callback: function(r) {
                if (!r.exc) {
                  me.frm.refresh_field("notes");
                  me.refresh();
                  d.hide();
                }
              }
            });
          },
          primary_action_label: __("Done")
        });
        d.show();
      }
    }
    delete_note(delete_btn) {
      var me = this;
      let row_id = $(delete_btn).closest(".comment-content").attr("name");
      frappe.call({
        method: "delete_note",
        doc: me.frm.doc,
        args: {
          row_id
        },
        freeze: true,
        callback: function(r) {
          if (!r.exc) {
            me.frm.refresh_field("notes");
            me.refresh();
          }
        }
      });
    }
  };

  // frappe-html:/media/n/Files/projects/metactical_v14/apps/metactical/metactical/erpnext_public/js/templates/crm_activities.html
  frappe.templates["crm_activities"] = `<div class="open-activities">
	<div class="new-btn pb-3">
		<span>
			<button class="btn btn-sm small new-task-btn mr-1">
				<svg class="icon icon-sm">
					<use href="#icon-small-message"></use>
				</svg>
				{{ __("New Task") }}
			</button>
			<button class="btn btn-sm small new-event-btn">
				<svg class="icon icon-sm">
					<use href="#icon-calendar"></use>
				</svg>
				{{ __("New Event") }}
			</button>
		</span>
	</div>
	<div class="section-body">
		<div class="open-tasks pr-1">
			<div class="open-section-head">
				<span class="ml-2">{{ __("Open Tasks") }}</span>
			</div>
			{% if (tasks.length) { %}
				{% for(var i=0, l=tasks.length; i<l; i++) { %}
					<div class="single-activity">
						<div class="flex justify-between mb-2">
							<div class="row label-area font-md ml-1">
								<span class="mr-2">
									<svg class="icon icon-sm">
										<use href="#icon-small-message"></use>
									</svg>
								</span>
								<a href="/app/todo/{{ tasks[i].name }}" title="{{ __('Open Task') }}">
									{%= tasks[i].description %}
								</a>
							</div>
							<div class="checkbox">
								<input type="checkbox" class="completion-checkbox"
									name="{{tasks[i].name}}" title="{{ __('Mark As Closed') }}">
							</div>
						</div>
						{% if(tasks[i].date) { %}
							<div class="text-muted ml-1">
								{%= frappe.datetime.global_date_format(tasks[i].date) %}
							</div>
						{% } %}
						{% if(tasks[i].allocated_to) { %}
							<div class="text-muted  ml-1">
								{{ __("Allocated To:") }}
								{%= tasks[i].allocated_to %}
							</div>
						{% } %}
						</div>
			    {% } %}
            {% } else { %}
                <div class="single-activity no-activity text-muted">
                    {{ __("No open task") }}
                </div>
		    {% } %}
		</div>
		<div class="open-events pl-1">
			<div class="open-section-head">
				<span class="ml-2">{{ __("Open Events") }}</span>
			</div>
			{% if (events.length) { %}
                {% let icon_set = {"Sent/Received Email": "mail", "Call": "call", "Meeting": "share-people"}; %}
                {% for(var i=0, l=events.length; i<l; i++) { %}
                    <div class="single-activity">
                        <div class="flex justify-between mb-2">
                            <div class="row label-area font-md ml-1 title">
                                <span class="mr-2">
                                    <svg class="icon icon-sm">
                                        <use href="#icon-{{ icon_set[events[i].event_category] || 'calendar' }}"></use>
                                    </svg>
                                </span>
                                <a href="/app/event/{{ events[i].name }}" title="{{ __('Open Event') }}">
                                    {%= events[i].subject %}
                                </a>
                            </div>
                            <div class="checkbox">
                                <input type="checkbox" class="completion-checkbox"
                                    name="{{ events[i].name }}" title="{{ __('Mark As Closed') }}">
                            </div>
                        </div>
                        <div class="text-muted ml-1">
                            {%= frappe.datetime.global_date_format(events[i].starts_on) %}

                            {% if (events[i].ends_on) { %}
                                {% if (frappe.datetime.obj_to_user(events[i].starts_on) != frappe.datetime.obj_to_user(events[i].ends_on)) %}
                                    -
                                    {%= frappe.datetime.global_date_format(frappe.datetime.obj_to_user(events[i].ends_on)) %}
                                    {%= frappe.datetime.get_time(events[i].ends_on) %}
                                {% } else if (events[i].ends_on) { %}
                                    -
                                    {%= frappe.datetime.get_time(events[i].ends_on) %}
                                {% } %}
                            {% } %}

                        </div>
                    </div>
                {% } %}
            {% } else { %}
            <div class="single-activity no-activity text-muted">
                {{ __("No open event") }}
            </div>
		    {% } %}
		</div>
	</div>
</div>


<style>
.open-activities {
	min-height: 50px;
	padding-left: 0px;
	padding-bottom: 15px !important;
}

.open-activities .new-btn {
	text-align: right;
}

.single-activity {
	min-height: 90px;
	border: 1px solid var(--border-color);
	padding: 10px;
	border-bottom: 0;
	padding-right: 0;
}

.single-activity:last-child {
	border-bottom: 1px solid var(--border-color);
}

.single-activity:hover .completion-checkbox{
	display: block;
}

.completion-checkbox {
	vertical-align: middle;
	display: none;
}

.checkbox {
	min-width: 22px;
}

.open-tasks {
	width: 50%;
}

.open-tasks:first-child {
	border-right: 0;
}

.open-events {
	width: 50%;
}

.open-section-head {
	background-color: var(--bg-color);
	min-height: 30px;
	border-bottom: 1px solid var(--border-color);
	padding: 10px;
	font-weight: bold;
}

.no-activity {
    text-align: center;
    padding-top: 30px;
}

.form-footer {
	background-color: var(--bg-color);
}
</style>`;

  // frappe-html:/media/n/Files/projects/metactical_v14/apps/metactical/metactical/erpnext_public/js/templates/crm_notes.html
  frappe.templates["crm_notes"] = `<div class="notes-section col-xs-12">
	<div class="new-btn pb-3">
		<button class="btn btn-sm small new-note-btn mr-1">
			<svg class="icon icon-sm">
				<use href="#icon-add"></use>
			</svg>
			{{ __("New Note") }}
		</button>
	</div>
	<div class="all-notes">
		{% if (notes.length) { %}
			{% for(var i=0, l=notes.length; i<l; i++) { %}
				<div class="comment-content p-3 row" name="{{ notes[i].name }}">
					<div class="mb-2 head col-xs-3">
						{% if (notes[i].added_by && notes[i].added_on) %}
						<div class="row">
							<div class="col-xs-2">
								{{ frappe.avatar(notes[i].added_by) }}
							</div>
							<div class="col-xs-10">
								<div class="mr-2 title font-weight-bold ellipsis" title="{{ strip_html(notes[i].added_by) }}">
									{{ strip_html(notes[i].added_by) }}
								</div>
								<div class="time small text-muted">
									{{ frappe.datetime.global_date_format(notes[i].added_on) }}
								</div>
							</div>
						</div>
						{% } %}
					</div>
					<div class="content col-xs-8">
						{{ notes[i].note }}
					</div>
					<div class="col-xs-1 text-right">
						<span class="edit-note-btn btn btn-link">
							<svg class="icon icon-sm"><use xlink:href="#icon-edit"></use></svg>
						</span>
						<span class="delete-note-btn  btn btn-link pl-2">
							<svg class="icon icon-xs"><use xlink:href="#icon-delete"></use></svg>
						</span>
					</div>
				</div>
			{% } %}
		{% } else { %}
            <div class="no-activity text-muted pt-6">
                {{ __("No Notes") }}
            </div>
		    {% } %}
	</div>
</div>

<style>

.comment-content {
    border: 1px solid var(--border-color);
	border-bottom: none;
}

.comment-content:last-child {
    border-bottom: 1px solid var(--border-color);
}

.new-btn {
	text-align: right;
}

.notes-section .no-activity {
	min-height: 100px;
	text-align: center;
}

.notes-section .btn {
	padding: 0.2rem 0.2rem;
}

</style>`;
})();
//# sourceMappingURL=erpnext.bundle.IBTYG524.js.map
