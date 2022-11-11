frappe.ui.form.on('Customer', {
    setup(frm){
      show_hide(frm);  
    },
    onload(frm){
      show_hide(frm);  
    },
    refresh(frm) {
        show_hide(frm);
    } ,
    mobile(frm){
        frm.set_value("mobile_no", frm.doc.mobile);
    },
    email(frm){
        frm.set_value("email_id", frm.doc.email);
    },
    validate(frm) {
		if(frm.doc.first_name!=null && frm.doc.last_name==null){
		    frm.set_value("customer_name", frm.doc.first_name);
		}
		else if(frm.doc.first_name!=null && frm.doc.last_name!=null){
	        frm.set_value("customer_name", frm.doc.first_name + " " +frm.doc.last_name);
		}
	//	frappe.db.set_value('Customer', frm.doc.name,  "customer_name", full_name )
    } 
})

var show_hide = function(frm){
    frm.toggle_reqd("default_price_list", true);
	//frm.toggle_reqd("tax_category", true);
	frm.toggle_reqd("first_name", true);
	frm.toggle_reqd("last_name", true);
    if((frm.doc.first_name== null)  && (frm.doc.last_name == null)){
        frm.set_value("first_name", frm.doc.customer_name);
    }
    if(frm.doc.__islocal){
        frm.toggle_enable("mobile", true);
        frm.toggle_display("mobile", true);

        // frm.toggle_display("primary_address_and_contact_detail", false);
        frm.toggle_display("customer_primary_contact", false);
        frm.toggle_display("customer_primary_address", false);

        
        frm.toggle_enable("email", true);
        frm.toggle_display("email", true);
        
        frm.toggle_display("mobile_no", false);
        frm.toggle_display("email_id", false);
        
        $("[data-fieldname=mobile_no]").hide();
        $("[data-fieldname=email_id]").hide();
    }
    else{
        frm.toggle_enable("mobile", false);
        frm.toggle_display("mobile", false);

        frm.toggle_display("customer_primary_contact", true);
        frm.toggle_display("customer_primary_address", true);

        
        frm.toggle_enable("email", false);
        frm.toggle_display("email", false);
        
        frm.toggle_display("mobile_no", true);
        frm.toggle_display("email_id", true);
        
        $("[data-fieldname=mobile_no]").show();
        $("[data-fieldname=email_id]").show();
    }
}
