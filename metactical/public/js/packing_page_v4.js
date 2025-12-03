import PackingPageV4 from "./components/packing_page/PackingPageV4.vue";
import { createApp, h, getCurrentInstance } from "vue";

frappe.provide("metactical.packing_page");

metactical.packing_page.PackingPageV4 = class {
    constructor(wrapper) {
        this.wrapper = wrapper;
        this.init();
    }

    init() {
        const app = createApp({
            setup() {
                const instance = getCurrentInstance();

                function refresh() {
                    const packingPage = instance?.refs?.packingPage;
                    if (packingPage && typeof packingPage.refresh === "function") {
                        packingPage.refresh();
                    }
                }
                return { refresh };
            },
            render() {
                return h(PackingPageV4, { ref: "packingPage" });
            },
        });

        const vm = app.mount("#packing_page_ui");

        this.vue_instance = vm;
        return this.vue_instance;
    }
};