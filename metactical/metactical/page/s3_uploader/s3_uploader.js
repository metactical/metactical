frappe.pages["s3-uploader"].on_page_load = function (wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: "S3 Uploader",
        single_column: true,
    });

    new S3UploaderPage(wrapper);
};

class S3UploaderPage {
    constructor(wrapper) {
        this.wrapper = $(wrapper);
        this.page = wrapper.page;
        this.main_section = this.page.main;
        this.main_section.append(`<div id="s3_uploader_ui"></div>`);
        this.uploader = new metactical.s3_uploader.S3Uploader(this.wrapper);

        var me = this;
        this.page.set_secondary_action("", () => {
            me.uploader.vue_instance.refresh();
        }, "refresh");
    }
}
