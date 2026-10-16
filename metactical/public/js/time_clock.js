import TimeClock from "./components/time_clock/TimeClock.vue";
import { createApp, h, getCurrentInstance } from "vue";

frappe.provide("metactical.time_clock");

metactical.time_clock.TimeClock = class {
    constructor(wrapper) {
        this.wrapper = wrapper;
        this.init();
    }

    init() {
        const app = createApp({
            setup() {
                const instance = getCurrentInstance();

                function refresh() {
                    const root = instance?.refs?.root;
                    if (root && typeof root.refresh === "function") {
                        root.refresh();
                    }
                }
                return { refresh };
            },
            render() {
                return h(TimeClock, { ref: "root" });
            },
        });

        const vm = app.mount("#time_clock_ui");

        this.vue_instance = vm;
        return this.vue_instance;
    }
};
