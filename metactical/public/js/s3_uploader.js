import FileUploader from "./components/s3_uploader/FileUploader.vue";
import { createApp, h, getCurrentInstance } from "vue";

frappe.provide("metactical.s3_uploader");

metactical.s3_uploader.S3Uploader = class {
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
                return h(FileUploader, { ref: "root" });
            },
        });

        const vm = app.mount("#s3_uploader_ui");

        this.vue_instance = vm;
        return this.vue_instance;
    }
};
