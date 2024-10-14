frappe.pages["packing-page-v4"].on_page_load = function (wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: "Packing Page - V4",
        single_column: true,
    });

    var packing_page = new PackingPage(wrapper);
};

class PackingPage {
    constructor(wrapper) {
        this.wrapper = $(wrapper);
        this.page = wrapper.page;
        this.main_section = this.page.main;
        this.main_section.append(`<div id="packing_page_ui"></div>`);
        this.packing_page = new metactical.packing_page.PackingPageV4(
            this.wrapper
        );

        var me = this;
        this.page.set_secondary_action("", () => {
            console.log(me.packing_page.vue_instance);

            me.packing_page.vue_instance.refresh();
        }, "refresh");
    }
}
