import PackingPageV4 from "./components/packing_page/PackingPageV4.vue";
frappe.provide("metactical.packing_page");

metactical.packing_page.PackingPageV4 = class {
      constructor(wrapper) {
            this.wrapper = wrapper;
            this.init();
      }

      init() {
            this.vue_instance = new Vue({
                  el: "#packing_page_ui",
                  render: (h) => h(PackingPageV4, { ref: "packingPage" }),
                  methods: {
                        refresh() {
                              // Access the child component using ref and call its refresh method
                              if (
                                    this.$refs.packingPage &&
                                    this.$refs.packingPage.refresh
                              ) {
                                    this.$refs.packingPage.refresh();
                              }
                        },
                  },
            });

            return this.vue_instance;
      }

      // refresh() {
      //   this.vue_instance.$children[0].refresh();
      // }
};
