# -*- coding: utf-8 -*-
from __future__ import unicode_literals
#from  import custom_calculate_taxes_and_totals
#from  import calculate_taxes_and_totals
import erpnext
from metactical.custom_scripts.controllers.taxes_and_totals import custom_calculate_taxes_and_totals

__version__ = '0.0.1'

#set_total_amount_to_default_mop = custom_default_mop
erpnext.controllers.taxes_and_totals.calculate_taxes_and_totals.set_total_amount_to_default_mop = custom_calculate_taxes_and_totals.set_total_amount_to_default_mop
