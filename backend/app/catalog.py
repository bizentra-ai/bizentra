"""Shared resource contracts. Every resource has its own relational table."""
def field(name, label, kind='text', default='', **options):
    return dict(name=name,label=label,type=kind,default=default,**options)

def reference(name,label,target,required=False):
    return field(name,label,'reference',None,target=target,required=required)

def resource(label,department,fields,statuses=('Active','Archived')):
    return dict(label=label,department=department,resource=department+'.'+label.lower().replace(' ','_'),fields=[field('name','Name',required=True),field('status','Status','select',statuses[0],options=list(statuses)),*fields,field('notes','Notes','longtext')])

CATALOG={
 'customers':resource('Customers','crm',[field('email','Email','email'),field('organization','Organization')],('Lead','Qualified','Customer','Inactive')),
 'projects':resource('Projects','projects',[],('Planning','In progress','Complete','On hold')),
 'tasks':resource('Tasks','projects',[field('priority','Priority','select','Medium',options=['Low','Medium','High']),field('due_date','Due date','date',None),reference('customer_id','Customer','customers'),reference('project_id','Project','projects'),reference('assignee_id','Assigned to','team')],('To do','In progress','Done')),
 'invoices':resource('Invoices','finance',[reference('customer_id','Customer','customers',True),field('amount_cents','Invoice total','money',0,required=True),field('issued_date','Issue date','date',None,required=True),field('due_date','Due date','date',None,required=True)],('Draft','Issued','Void')),
 'payments':resource('Payments','finance',[reference('customer_id','Customer','customers',True),reference('invoice_id','Invoice','invoices'),field('amount_cents','Amount received','money',0,required=True),field('paid_date','Payment date','date',None,required=True),field('method','Method','select','Bank transfer',options=['Bank transfer','Cash','Card','Other']),field('external_id','External reference')],('Posted','Void')),
 'expenses':resource('Expenses','finance',[field('amount_cents','Amount','money',0,required=True),field('paid_date','Date','date',None,required=True),field('category','Category'),field('recurrence','Recurrence','select','None',options=['None','Monthly']),field('next_due','Next occurrence','date',None)],('Draft','Paid','Void')),
 'transactions':resource('Transactions','finance',[field('amount_cents','Amount','money',0,required=True),field('direction','Direction','select','Income',options=['Income','Expense']),field('paid_date','Date','date',None,required=True),field('category','Category')],('Posted','Void')),
}
CATALOG.update({
 'leads':resource('Leads','crm',[field('email','Email','email'),field('organization','Organization'),reference('assignee_id','Owner','team'),field('priority','Priority','select','Medium',options=['Low','Medium','High']),field('due_date','Follow-up date','date',None),reference('customer_id','Converted customer','customers')],('New','Contacted','Qualified','Converted','Lost')),
 'opportunities':resource('Opportunities','crm',[reference('customer_id','Customer','customers',True),reference('assignee_id','Owner','team'),field('amount_cents','Expected value','money',0),field('probability','Probability (%)','integer',0),field('close_date','Expected close','date',None)],('Discovery','Proposal','Negotiation','Won','Lost')),
 'crm_activities':resource('CRM activities','crm',[reference('customer_id','Customer','customers'),reference('lead_id','Lead','leads'),reference('assignee_id','Owner','team'),field('activity_type','Activity type','select','Note',options=['Call','Meeting','Note','Follow-up','Reminder']),field('due_date','Date','date',None)],('Planned','Done','Cancelled')),
})
CATALOG.update({
 'tickets':resource('Tickets','support',[reference('customer_id','Customer','customers',True),reference('assignee_id','Assigned to','team'),field('priority','Priority','select','Medium',options=['Low','Medium','High','Urgent']),field('due_date','Response due','date',None),field('description','Issue description','longtext')],('Open','In progress','Waiting on customer','Escalated','Resolved')),
 'ticket_notes':resource('Ticket notes','support',[reference('ticket_id','Ticket','tickets',True),field('note_type','Type','select','Internal note',options=['Internal note','Response recorded','Escalation','Resolution']),field('body','Note / response','longtext',required=True)],('Recorded',)),
})

CATALOG.update({
 'segments':resource('Segments','marketing',[field('criteria','Audience definition','longtext')]),
 'campaigns':resource('Campaigns','marketing',[reference('segment_id','Audience segment','segments'),field('channel','Channel','select','Email',options=['Email','Search','Social','Events','Referral','Other']),field('start_date','Start date','date',None),field('end_date','End date','date',None),field('spend_cents','Tracked spend','money',0),field('leads_generated','Leads generated','integer',0),field('conversions','Conversions','integer',0),field('revenue_cents','Attributed revenue','money',0)],('Draft','Scheduled','Running','Paused','Complete')),
 'segment_members':resource('Segment members','marketing',[reference('segment_id','Segment','segments',True),reference('customer_id','Customer','customers',True)]),
})
CATALOG['crm_activities']['fields'].insert(-1,reference('campaign_id','Campaign','campaigns'))

# These are manually recorded cash movements. Invoice-linked payments must not also
# be recorded as transactions; the UI and reports explicitly distinguish the two.
CATALOG.update({
 'suppliers':resource('Suppliers','operations',[field('email','Email','email'),field('phone','Phone'),field('address','Address','longtext')]),
 'products':resource('Products','operations',[field('sku','SKU'),field('price_cents','Unit price','money',0),field('stock','Stock on hand','integer',0),field('threshold','Low-stock threshold','integer',0),reference('supplier_id','Supplier','suppliers')]),
 'stock_movements':resource('Stock movements','operations',[reference('product_id','Product','products',True),field('quantity','Quantity change','signed',0,required=True),field('reason','Reason'),field('movement_date','Date','date',None,required=True)],('Posted',)),
 'orders':resource('Orders','operations',[reference('customer_id','Customer','customers',True),field('order_date','Order date','date',None,required=True),field('due_date','Fulfillment due','date',None)],('Draft','Confirmed','Fulfilled','Cancelled')),
 'order_items':resource('Order items','operations',[reference('order_id','Order','orders',True),reference('product_id','Product','products',True),field('quantity','Quantity','integer',1,required=True),field('unit_price_cents','Unit price','money',0,required=True)],('Active',)),
 'purchase_orders':resource('Purchase orders','operations',[reference('supplier_id','Supplier','suppliers',True),reference('product_id','Product','products',True),field('quantity','Quantity','integer',1,required=True),field('amount_cents','Purchase total','money',0),field('due_date','Expected delivery','date',None)],('Draft','Ordered','Received','Cancelled')),
 'milestones':resource('Milestones','projects',[reference('project_id','Project','projects',True),field('due_date','Due date','date',None)],('Open','Complete')),
 'project_members':resource('Project members','projects',[reference('project_id','Project','projects',True),reference('assignee_id','Member','team',True)]),
 'task_dependencies':resource('Task dependencies','projects',[reference('task_id','Task','tasks',True),reference('depends_on_id','Depends on','tasks',True)]),
 'documents':resource('Documents','documents',[field('content','Document content','longtext'),reference('customer_id','Customer','customers'),reference('project_id','Project','projects')]),
 'meetings':resource('Meetings','documents',[field('due_date','Meeting date','date',None),reference('project_id','Project','projects'),field('content','Notes and decisions','longtext'),reference('assignee_id','Organizer','team')]),
})
CATALOG['projects']['fields'][2:2]=[reference('assignee_id','Project owner','team'),field('due_date','Deadline','date',None),field('priority','Priority','select','Medium',options=['Low','Medium','High'])]
CATALOG['tasks']['fields'].insert(-1,reference('parent_id','Parent task','tasks'))
CATALOG['tickets']['fields'].insert(-1,reference('order_id','Order','orders'))
