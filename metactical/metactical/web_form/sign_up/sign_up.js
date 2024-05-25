var phone_no = null;
frappe.ready(function () {
  frappe.web_form.handle_success = () => {
	frappe.msgprint(frappe.web_form.success_message);
	setTimeout(() => {
		window.location = frappe.web_form.success_url;
	}, 4000);
  };

  frappe.web_form.after_load = () => {
    const input = document.querySelector(
      'input[data-fieldname="inteli_phone_no"]'
    );
    phone_no = window.intlTelInput(input, {
      geoIpLookup: function (callback) {
        $.get("http://ipinfo.io", function () {}, "jsonp").always(function (
          resp
        ) {
          var countryCode = resp && resp.country ? resp.country : "";
          callback(countryCode);
        });
      },
      utilsScript:
        "/assets/metactical/node_modules/intl-tel-input/build/js/utils.js",
    });
    personal_email = new URL(location.href).searchParams.get("uemail");
    if (personal_email == null) {
      frappe.throw(
        "Error: Please use the URL sent to your email to access this page."
      );
    } else {
      frappe.web_form.set_value("personal_email", personal_email);
    }

    // Mask the phone number
    frappe.require(
      "/assets/metactical/node_modules/jquery-mask-plugin/dist/jquery.mask.min.js",
      () => {
        var correct_format_sample = $(
          "input[data-fieldname='inteli_phone_no']"
        ).attr("placeholder");

        // create the mask
        var mask = "(000) 000-0000";
        if (correct_format_sample)
          mask = correct_format_sample.replace(/\d/g, "0");

        $('input[data-fieldname="inteli_phone_no"]').mask(mask);
      }
    );

    frappe.web_form.on("inteli_phone_no", (field, value) => {
      frappe.web_form.set_value("phone_no", phone_no.getNumber());
    });

    if (frappe.web_form.get_value("branch") != "Online") {
    	frappe.web_form.on("bank_transit_no", (field, value) => {
			// show tooltip if transit digit are not 5
			// add a validation if the value is not a number
			if (!/^\d{5}$/.test(value)){
				show_tooltip('bank_transit_no', 'Bank transit number must be a 5-digit number');
			}
			else{
				hide_tooltip('bank_transit_no');
			}	
	

			if (!/^\d+$/.test(value)) {
				show_tooltip("bank_transit_no", "Transit number should be a number");
			}
			else{
				hide_tooltip('bank_transit_no')
			}
      	});

	  frappe.web_form.on("zip_code", (field, value) => {
		if (frappe.web_form.get_value("country") == "Canada") {
			if (value != null && value != "" && !/^[A-Za-z]\d[A-Za-z][ -]?\d[A-Za-z]\d$/.test(value)) {
				show_tooltip('zip_code', 'Invalid zip code');
			}
			else{
				hide_tooltip('zip_code');
			}
		}
	  });

	  frappe.web_form.on("bank_institution_no", (field, value) => {
			if (!/^\d{3}$/.test(value)) {
				show_tooltip('bank_institution_no', 'Bank institution number must be 3 digits');
			}
			else{
				hide_tooltip('bank_institution_no')
			} 
		});

      frappe.web_form.on("bank_account_no", (field, value) => {
        if (value.length > 12) {
          show_tooltip(
            "bank_account_no",
            "Account number should be at most 12 digits"
          );
        } else if (value.length < 7) {
          show_tooltip(
            "bank_account_no",
            "Account number should be at least 7 digits"
          );
        } else {
         	hide_tooltip('bank_account_no');
        }
      });
    }

    // set query for province based on country
    frappe.web_form.on("country", (field, value) => {
      if (value) {
        set_province_query(value, frappe.web_form);
      }
    });

	// validate sin number
	frappe.web_form.on("sin_no", (field, value) => {
		if (!isValidSIN(value)) {
			show_tooltip('sin_no', 'Invalid SIN number');
		}
		else{
			hide_tooltip('sin_no');
		}
	});

    set_province_query(frappe.web_form.get_value("country"), frappe.web_form);
  };

  frappe.web_form.validate = () => {
    let personal_email = frappe.web_form.get_value("personal_email");
    let ret = true;

    if (personal_email == "" || personal_email == null) {
      frappe.throw(
        "Error: Please use the URL sent to your email to access this page. "
      );
      ret = false;
      return false;
    }

    // Validate phone number
    if (phone_no.isValidNumber() == false) {
      let error = phone_no.getValidationError();
      if (error == intlTelInputUtils.validationError.TOO_SHORT) {
        frappe.throw("Error: The phone number is too short");
        return false;
      } else if (error == intlTelInputUtils.validationError.TOO_LONG) {
        frappe.throw("The phone number is too long");
      }
    } else {
      let data = frappe.web_form.get_values();
      data.phone_no = phone_no.getNumber();
    }

    // Validate zip code for canada
    if (frappe.web_form.get_value("country") == "Canada") {
      let zip_code = frappe.web_form.get_value("zip_code");
      if (
        zip_code != null &&
        zip_code != "" &&
        !/^[A-Za-z]\d[A-Za-z][ -]?\d[A-Za-z]\d$/.test(zip_code)
      ) {
		// show error message on the field
		$(`input[data-fieldname="zip_code"]`).addClass("is-invalid");
		show_tooltip('zip_code', 'Invalid zip code');
        ret = false;
      }
    }

    if (frappe.web_form.get_value("branch") != "Online") {
      // Validate bank institution number
      let bank_institution_no = frappe.web_form.get_value(
        "bank_institution_no"
      );
      if (
        bank_institution_no != null &&
        bank_institution_no != "" &&
        !/^\d{3}$/.test(bank_institution_no)
      ) {
		
		// show error message on the field
		$(`input[data-fieldname="bank_institution_no"]`).addClass("is-invalid");
		show_tooltip(
		  "bank_institution_no",
		  "Bank institution number must be 3 digits"
		);
        ret = false;
      }

      // Validate SIN number
      let sin_no = frappe.web_form.get_value("sin_no");
      if (!isValidSIN(sin_no) &&
			sin_no != null &&
			sin_no != "") {
		// show error message on the field
		$(`input[data-fieldname="sin_no"]`).addClass("is-invalid");
		show_tooltip('sin_no', 'Invalid SIN number');
        ret = false;
      }

      // Validate bank transit number
      let bank_transit_no = frappe.web_form.get_value("bank_transit_no");
      if (!/^\d{5}$/.test(bank_transit_no) && bank_transit_no) {
		// show error message on the field
		$(`input[data-fieldname="bank_transit_no"]`).addClass("is-invalid");
		show_tooltip('bank_transit_no', 'Bank transit number must be a 5-digit number');
        ret = false;
      }

	  // Validate bank account number
	  let bank_account_no = frappe.web_form.get_value("bank_account_no");
	  if (!/^\d{7,12}$/.test(bank_account_no) && bank_account_no){
			// show error message on the field
			$(`input[data-fieldname="bank_account_no"]`).addClass("is-invalid");
			show_tooltip(
				"bank_account_no",
				"Account number should be at least 7 digits and at most 12 digits"
			);
		}
    }

    return ret;
  };
});

function set_province_query(country, web_form) {
  frappe.call({
    method: "metactical.metactical.web_form.sign_up.sign_up.get_provinces",
    args: {
      country: country,
    },
    callback: function (r) {
      if (r.message) {
        frappe.web_form.set_df_property("state", "options", r.message);
      }
    },
  });
}

function isValidSIN(sin) {
  // Remove any non-digit characters
  sin = sin.replace(/\D/g, "");

  // SIN must be 9 digits
  if (sin.length !== 9) {
    return false;
  }

  // Luhn Algorithm
  let sum = 0;
  for (let i = 0; i < sin.length; i++) {
    let digit = parseInt(sin[i]);

    if (i % 2 === 1) {
      // Even index in 0-based index system, i.e., 2nd, 4th, 6th, 8th position in 1-based index system
      digit *= 2;
      if (digit > 9) {
        digit -= 9;
      }
    }

    sum += digit;
  }

  return sum % 10 === 0;
}

function show_tooltip(field, message) {
  $(`input[data-fieldname="${field}"]`)
    .removeAttr("data-original-title")
    .tooltip("hide");
  $(`input[data-fieldname="${field}"]`)
    .attr("data-original-title", message)
    .tooltip("show");
}

function hide_tooltip(field) {
  $(`input[data-fieldname="${field}"]`)
	.removeAttr("data-original-title")
	.tooltip("hide");

	$(`input[data-fieldname="${field}"]`).removeClass("is-invalid");
}