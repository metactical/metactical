frappe.pages["time-clock"].on_page_load = function (wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: "Time Clock",
        single_column: true,
    });

    new TimeClockPage(wrapper);
};

class TimeClockPage {
    constructor(wrapper) {
        this.wrapper = $(wrapper);
        this.page = wrapper.page;
        this.main_section = this.page.main;
        this.main_section.append(`<div id="time_clock_ui"></div>`);
        this.clock = new metactical.time_clock.TimeClock(this.wrapper);

        var me = this;
        this.page.set_secondary_action("", () => {
            me.clock.vue_instance.refresh();
        }, "refresh");
    }
}
