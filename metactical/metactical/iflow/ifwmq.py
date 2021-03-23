from __future__ import unicode_literals

import frappe

@frappe.whitelist()
def test():
    print("doneEP")
    return "doneER"

@frappe.whitelist()
def getModifiedQOHs(modified, sort_by='modified',start=0, sort_order='asc'):
    try:
        sqlStr='''
		select * from tabBin
		where
			modified > {modified}
		order by
			{sort_by} {sort_order}
		 limit
			{start}, 100
        '''.format(modified=modified,sort_by=sort_by, sort_order=sort_order,start=start)
        #print(" ".join(sqlStr.split("\n")))
        #return " ".join(sqlStr.split("\n"))
        return frappe.db.sql(sqlStr, as_dict=True)
    except:
        print("*****************************")