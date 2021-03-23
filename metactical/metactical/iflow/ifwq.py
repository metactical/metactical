from __future__ import unicode_literals

import frappe

@frappe.whitelist()
def test():
    print("done")
    return "done"

@frappe.whitelist()
def getAdjustItems(item_code, warehouse,vals ,start=0, sort_by='actual_qty', sort_order='desc'):
    conditions=[]
    #return "also done"
	#itemStrList = "("+ item_code +")"
    for i,y in zip(item_code.split(","),vals.split(",")):
        conditions.append('(i.item_code = %s and COALESCE(b.actual_qty,0) < %s)' %(i,y))
    
    conditions = ' or '.join(conditions)
    print(conditions)
    vallll=[]
    try:
        sqlStr='''
        select
            i.item_code, b.warehouse, COALESCE(b.actual_qty,0)  actual_qty,
            COALESCE(b.valuation_rate,i.valuation_rate) valuation_rate
        from tabItem i
        left join tabBin b
        on b.item_code = i.item_code and b.warehouse = '{warehouse}'
        where
            ({conditions})
        order by
            {sort_by} {sort_order}
        limit
            {start}, 100
        '''.format(conditions=conditions,warehouse=warehouse ,sort_by=sort_by, sort_order=sort_order,
            start=start)
        #print(" ".join(sqlStr.split("\n")))
        #return " ".join(sqlStr.split("\n"))
        return frappe.db.sql(sqlStr, as_dict=True)
    except:
        print("*****************************")

	#return frappe.db.sql(sqlStr, [], as_dict=True)