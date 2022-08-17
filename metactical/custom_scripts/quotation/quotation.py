from erpnext.selling.doctype.quotation.quotation import Quotation
import barcode as _barcode
from io import BytesIO

class CustomQuotation(Quotation):
	def before_save(self):
		rv = BytesIO()
		_barcode.get('code128', self.name).write(rv)
		bstring = rv.getvalue()
		self.ais_barcode = bstring.decode('ISO-8859-1')
