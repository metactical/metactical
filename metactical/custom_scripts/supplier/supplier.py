from erpnext.buying.doctype.supplier.supplier import Supplier

from metactical.procurement_v3.utils import validate_supplier_po_emails


class CustomSupplier(Supplier):
	def validate(self):
		super(CustomSupplier, self).validate()
		# Metactical Customization: PO V3 Ordering CC / BCC addresses and Main Signature
		validate_supplier_po_emails(self)
