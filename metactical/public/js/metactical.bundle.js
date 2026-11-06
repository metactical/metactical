// Override Frappe's bundled (outdated) tz rules with newer IANA data so the
// browser matches the server's pytz (e.g. BC's move to permanent UTC-7).
import tzdata from "moment-timezone/data/packed/latest.json";
moment.tz.load(tzdata);

import "./template/shipment_rate.html";
import "./packing_page_v4.js";
import "./s3_uploader.js";
import "./item_merge.js";
import "./canada_post_management.js";
import "./shipment_rate.js";
import "./utils.js";
import "./item_dashboard.js";
import "./email_pills.js";
