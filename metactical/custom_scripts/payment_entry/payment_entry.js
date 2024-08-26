frappe.ui.form.on("Payment Entry", {
  refresh: function (frm) {
    console.log("refresh", frm.doc.mode_of_payment, frm.doc.references);
    if (!frm.doc.mode_of_payment && frm.doc.references) {
      if (frm.doc.references.length == 1)
        frm.trigger("get_mode_of_payment");
    }

    frm.trigger("make_payment_button");
  },
  get_mode_of_payment: function (frm) {
    console.log("get_mode_of_payment");
    frappe.call({
      method: "metactical.custom_scripts.payment_entry.payment_entry.get_mode_of_payment",
      args: {
        reference_doctype: frm.doc.references[0].reference_doctype,
        reference_name: frm.doc.references[0].reference_name,
      },
      callback: function (r) {
        frm.set_value("mode_of_payment", r.mode_of_payment);
        frm.set_value("reference_no", r.reference_no);
      }
    });
  },
  make_payment_button: function (frm) {
    frappe.call({
      "method": "metactical.custom_scripts.usaepay.usaepay_api.get_usaepay_roles",
      callback: function (r) {
        var roles_allowed_to_make_payment = r.message.make_payment;
        var user_roles = frappe.user_roles;

        if (roles_allowed_to_make_payment.some(role => user_roles.includes(role))) {
          if (frm.doc.payment_type == "Receive" && 
              frm.doc.party &&
              !frm.doc.reference_no && 
              frm.doc.docstatus == 0 &&
              !frm.doc.__islocal
            ) {
              frm.add_custom_button(__("Make Payment"), function () {
                goto_payment_form(frm);
            });
          }
        }
      }
    })

  },
  source_exchange_rate: function (frm) {
    if (frm.doc.paid_amount) {
      frm.set_value(
        "base_paid_amount",
        flt(frm.doc.paid_amount) * flt(frm.doc.source_exchange_rate)
      );
      // target exchange rate should always be same as source if both account currencies are same
      if (
        frm.doc.paid_from_account_currency == frm.doc.paid_to_account_currency
      ) {
        frm.set_value("target_exchange_rate", frm.doc.source_exchange_rate);
        frm.set_value("base_received_amount", frm.doc.base_paid_amount);
      }

      frm.events.set_unallocated_amount(frm);
    }

    // Make read only if Accounts Settings doesn't allow stale rates
    frm.set_df_property(
      "source_exchange_rate",
      "read_only",
      erpnext.stale_rate_allowed() ? 0 : 1
    );

    if (frm.doc.received_amount) {
      frm.set_value(
        "paid_amount",
        frm.doc.received_amount / frm.doc.source_exchange_rate
      );
    }
  },
});

var goto_payment_form = function (frm) {
  // get customer information
  frappe.call({
    method:"metactical.custom_scripts.utils.metactical_utils.get_customer_payment_information",
    freeze: true,
    freeze_message: __("Fetching customer information..."),
    args: {
      customer: frm.doc.party,
    },
    callback: (res) => {
      var tokens = res.tokens;
      var options = [];
      tokens.forEach((token) => {
        options.push(token.label + " - " + token.cc_number);
      });

      var d = new frappe.ui.Dialog({
        title: __("Make Payment"),
        fields: [
          {
            fieldtype: "Data",
            label: __("Invoice"),
            fieldname: "invoice",
            default: get_invoice(frm.doc),
            reqd: 1,
          },
          {
            fieldtype: "Select",
            label: __("Payment Method"),
            fieldname: "payment_method",
            options: options,
            reqd: 1,
            onchange: function () {
              if (d.get_value("payment_method")) {
                d.set_df_property("new_card", "value", 0);
              }
            },
          },
          {
            fieldtype: "Check",
            label: __("New Credit Card"),
            fieldname: "new_card",
            onchange: function () {
              if (d.get_value("new_card")) {
                d.set_df_property("payment_method", "reqd", 0);
                d.set_df_property("payment_method", "hidden", 1);
              } else {
                d.set_df_property("payment_method", "reqd", 1);
                d.set_df_property("payment_method", "hidden", 0);
              }
            },
          },
          {
            fieldtype: "Currency",
            label: __("Amount"),
            fieldname: "amount",
            reqd: 1,
            default: frm.doc.paid_amount,
          },
        ],
        primary_action_label: __("Submit"),
        primary_action: function () {
          var values = d.get_values();
          if (!values) return;
          d.hide();

          if (values.new_card) {
            var address = res.address;
            var billing_address = map_fields_to_address(
              address.billing,
              "Billing"
            );
            var shipping_address = map_fields_to_address(
              address.shipping,
              "Shipping"
            );

            add_to_log(frm, values, billing_address);

            var url_params = "";
            if (billing_address) {
              url_params += billing_address;
            }

            if (shipping_address) {
              if (url_params) {
                url_params += "&" + shipping_address;
              } else {
                url_params += shipping_address;
              }
            }

            url_params += "&UMinvoice=" + values.invoice;
            url_params += "&UMamount=" + values.amount;
            url_params += "&UMdescription=" + frm.doc.remarks;
            // url_params += "&UMhash=" + res.hash;
            // url_params += "&UMkey=" + "";

            window.open(res.payment_form_url + "?" + url_params, "_blank");
          } else make_payment(frm, values, tokens);
        },
      });

      d.show();
    },
  });
};

var add_to_log = function (frm, values, billing_address) {
  var log = {
    payment_entry: frm.doc.name,
    invoice: values.invoice,
    amount: values.amount,
    billing_address: billing_address
  };

  frappe.call({
    method: "metactical.custom_scripts.usaepay.usaepay_api.add_to_log",
    args: {
      log: log,
    },
    callback: (res) => {
      if (res.error) {
        frappe.msgprint(res.error);
      }
    }
  });
};

var map_fields_to_address = function (address, address_type) {
  if (!address) {
    return "";
  }

  if (address_type == "Billing") {
    var mapped_object = {
      UMbillstreet: address.address_line1 ? address.address_line1 : "",
      UMbillfname: address.first_name ? address.first_name : "",
      UMbilllname: address.last_name ? address.last_name : "",
      UMbillstreet2: address.address_line2 ? address.address_line2 : "",
      UMbillcity: address.city ? address.city : "",
      UMbillstate: address.state ? address.state : "",
      UMbillcountry: address.country ? address.country : "",
      UMbillphone: address.phone ? address.phone : "",
      UMbillcompany: address.company
        ? address.company
        : address.ais_company
        ? address.ais_company
        : "",
      UMbillzip: address.pincode ? address.pincode : "",
    };
  } else if (address_type == "Shipping") {
    var mapped_object = {
      UMshipstreet: address.address_line1 ? address.address_line1 : "",
      UMshipfname: address.first_name ? address.first_name : "",
      UMshiplname: address.last_name ? address.last_name : "",
      UMshipstreet2: address.address_line2 ? address.address_line2 : "",
      UMshipcity: address.city ? address.city : "",
      UMshipstate: address.state ? address.state : "",
      UMshipcountry: address.country ? address.country : "",
      UMshipphone: address.phone ? address.phone : "",
      UMshipcompany: address.company
        ? address.company
        : address.ais_company
        ? address.ais_company
        : "",
      UMshipzip: address.pincode ? address.pincode : "",
    };
  }

  var search_parms = new URLSearchParams(mapped_object).toString();

  return search_parms;
};

var make_payment = function (frm, values, tokens) {
  var options = [];
  tokens.forEach((token) => {
    options.push(token.label + " - " + token.cc_number);
  });

  var selected_token = "";
  for (var i = 0; i < options.length; i++) {
    if (values.payment_method == options[i]) {
      selected_token = tokens[i].name;
      break;
    }
  }

  frappe.call({
    method: "metactical.custom_scripts.usaepay.usaepay_api.make_payment",
    freeze: true,
    freeze_message: "Charging Customer in USAePay ....",
    args: {
      customer: frm.doc.party,
      amount: values.amount,
      token: selected_token,
      payment_entry: frm.doc.name,
    },
    callback: (res) => {
      if (res.error) {
        frappe.msgprint(res.error);
      } else {
        frappe.msgprint("Payment successful");
        frm.reload_doc();
      }
    },
  });
};

var get_invoice = function (doc) {
  var references = doc.references;

  if (references.length == 1) {
    return references[0].reference_name;
  }

  return doc.name;
};
