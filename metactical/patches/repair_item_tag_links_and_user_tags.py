from collections import defaultdict

import frappe

def execute():
	CHUNK_SIZE = 5000
	start = 0

	while True:
		item_names = frappe.get_all(
			"Item",
			order_by="name asc",
			start=start,
			page_length=CHUNK_SIZE,
			pluck="name"
		)

		if not item_names:
			break

		frappe.enqueue(
			repair_item_tag_links_and_user_tags_chunk,
			item_names=item_names,
			queue="default",
			timeout=3600
		)

		start += CHUNK_SIZE


def repair_item_tag_links_and_user_tags_chunk(item_names):
	if not item_names:
		return

	items = frappe.get_all(
		"Item",
		filters={"name": ("in", item_names)},
		fields=["name", "item_name", "_user_tags"],
	)

	if not items:
		return

	items_by_name = {item.name: item for item in items}
	tag_links_by_item = defaultdict(list)
	candidate_tags = set()
	user_tags_by_item = {}

	for item in items:
		user_tags = parse_user_tags(item._user_tags)
		user_tags_by_item[item.name] = user_tags
		candidate_tags.update(user_tags)

	tag_links = frappe.get_all(
		"Tag Link",
		filters={"document_type": "Item", "document_name": ("in", list(items_by_name))},
		fields=["name", "document_name", "tag"],
		order_by="creation asc",
	)

	for tag_link in tag_links:
		tag_links_by_item[tag_link.document_name].append(tag_link)
		if tag_link.tag:
			candidate_tags.add(tag_link.tag)

	valid_tags = get_valid_tags(candidate_tags)

	for item_name in item_names:
		item = items_by_name.get(item_name)
		if not item:
			continue

		final_tags = merge_valid_tags(
			user_tags_by_item.get(item_name, []),
			[tag_link.tag for tag_link in tag_links_by_item.get(item_name, [])],
			valid_tags,
		)
		reconcile_item_tags(item, tag_links_by_item.get(item_name, []), final_tags)

	frappe.db.commit()


def parse_user_tags(user_tags):
	return [tag.strip() for tag in (user_tags or "").split(",") if tag and tag.strip()]


def get_valid_tags(candidate_tags):
	if not candidate_tags:
		return set()

	return set(frappe.get_all("Tag", filters={"name": ("in", list(candidate_tags))}, pluck="name"))


def merge_valid_tags(user_tags, tag_link_tags, valid_tags):
	merged_tags = []
	seen_tags = set()

	# Keep any valid tag that survived on either side instead of dropping it during repair.
	for tag in [*user_tags, *tag_link_tags]:
		if tag not in valid_tags or tag in seen_tags:
			continue

		merged_tags.append(tag)
		seen_tags.add(tag)

	return merged_tags


def reconcile_item_tags(item, tag_links, final_tags):
	final_tag_set = set(final_tags)
	rows_to_delete = []
	existing_tags = set()

	for tag_link in tag_links:
		if tag_link.tag not in final_tag_set or tag_link.tag in existing_tags:
			rows_to_delete.append(tag_link.name)
			continue

		existing_tags.add(tag_link.tag)

	if rows_to_delete:
		frappe.db.delete("Tag Link", {"name": ("in", rows_to_delete)})

	missing_tags = [tag for tag in final_tags if tag not in existing_tags]
	for tag in missing_tags:
		frappe.get_doc(
			{
				"doctype": "Tag Link",
				"document_type": "Item",
				"document_name": item.name,
				"tag": tag,
				"title": item.item_name or item.name,
			}
		).insert(ignore_permissions=True)

	desired_user_tags = build_user_tags_value(final_tags)
	if (item._user_tags or "") != desired_user_tags:
		frappe.db.set_value("Item", item.name, "_user_tags", desired_user_tags, update_modified=False)


def build_user_tags_value(tags):
	if not tags:
		return ""

	return "," + ",".join(tags)