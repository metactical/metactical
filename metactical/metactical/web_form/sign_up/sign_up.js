var phone_no = null;
frappe.ready(function() {
	frappe.web_form.after_load = () => {
		const input = document.querySelector('input[data-fieldname="inteli_phone_no"]');
		phone_no = window.intlTelInput(input, {
			geoIpLookup: function(callback) {
				$.get("http://ipinfo.io", function() {}, "jsonp").always(function(resp) {
					var countryCode = (resp && resp.country) ? resp.country : "";
					callback(countryCode);
				});
			},
			utilsScript: "/assets/metactical/node_modules/intl-tel-input/build/js/utils.js"
		});
		personal_email = new URL(location.href).searchParams.get('uemail')
		if(personal_email == null){
			frappe.throw("Error: Please use the URL sent to your email to access this page.")
		}
		else{
			frappe.web_form.set_value('personal_email', personal_email);
		}
		
		frappe.web_form.on('inteli_phone_no', (field, value) => {
			frappe.web_form.set_value("phone_no", phone_no.getNumber());
		});
	}
	
	frappe.web_form.validate = () => {
		let personal_email = frappe.web_form.get_value("personal_email");
		let ret = true
		console.log({"Valid": phone_no.isValidNumber(), "Phone: ": phone_no.getNumber(), "error": phone_no.getValidationError()});
		if(personal_email == "" || personal_email == null){
			frappe.throw("Error: Please use the URL sent to your email to access this page. ");
			ret = false;
			return false;
		}
		
		//Validate phone number
		if(phone_no.isValidNumber() == false){
			let error = phone_no.getValidationError();
			if(error == intlTelInputUtils.validationError.TOO_SHORT){
				frappe.throw("Error: The phone number is too short");
				return false;
			}
			else if(error == intlTelInputUtils.validationError.TOO_LONG){
				frappe.throw("The phone number is too long");
			}
		}
		else{
			let data = frappe.web_form.get_values();
			data.phone_no = phone_no.getNumber();
		}
		return ret;
	}
})
