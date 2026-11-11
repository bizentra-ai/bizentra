from fastapi import HTTPException
from ..security import allowed
from ..domain_models import SCHEMAS,MODELS
from ..services import relations,event
from ..record_hooks import validate,after_write

def tool(name,description,properties,required):return {'type':'function','name':name,'description':description,'parameters':{'type':'object','properties':properties,'required':required,'additionalProperties':False},'strict':True}
TEXT={'type':'string'};NULL_ID={'type':['integer','null']};NULL_DATE={'type':['string','null'],'description':'ISO YYYY-MM-DD'}
TOOLS={
 'propose_task':tool('propose_task','Propose a task for approval using only IDs in authorized context.',{'name':TEXT,'notes':TEXT,'due_date':NULL_DATE,'customer_id':NULL_ID,'project_id':NULL_ID},['name','notes','due_date','customer_id','project_id']),
 'propose_report':tool('propose_report','Propose saving an evidence-based report document. Cite records and limitations.',{'name':TEXT,'content':TEXT,'customer_id':NULL_ID,'project_id':NULL_ID},['name','content','customer_id','project_id']),
 'propose_crm_activity':tool('propose_crm_activity','Propose a CRM follow-up, call, meeting, note or reminder.',{'name':TEXT,'customer_id':NULL_ID,'lead_id':NULL_ID,'activity_type':{'type':'string','enum':['Call','Meeting','Note','Follow-up','Reminder']},'due_date':NULL_DATE,'notes':TEXT},['name','customer_id','lead_id','activity_type','due_date','notes']),
 'propose_ticket_note':tool('propose_ticket_note','Propose an internal support note, draft response, escalation or resolution record.',{'name':TEXT,'ticket_id':{'type':'integer'},'note_type':{'type':'string','enum':['Internal note','Response recorded','Escalation','Resolution']},'body':TEXT,'notes':TEXT},['name','ticket_id','note_type','body','notes']),
 'propose_purchase_order':tool('propose_purchase_order','Propose a purchase order for approval using authorized supplier and product IDs.',{'name':TEXT,'supplier_id':{'type':'integer'},'product_id':{'type':'integer'},'quantity':{'type':'integer','minimum':1},'amount_cents':{'type':'integer','minimum':0},'due_date':NULL_DATE,'notes':TEXT},['name','supplier_id','product_id','quantity','amount_cents','due_date','notes']),
}
RULES={
 'propose_task':('tasks','projects.tasks.create','low'),
 'propose_report':('documents','documents.documents.create','low'),
 'propose_crm_activity':('crm_activities','crm.crm_activities.create','low'),
 'propose_ticket_note':('ticket_notes','support.ticket_notes.create','medium'),
 'propose_purchase_order':('purchase_orders','operations.purchase_orders.create','medium'),
}
WORKER_TOOLS={'advisor':set(TOOLS),'finance':{'propose_task','propose_report','propose_crm_activity'},'sales':{'propose_task','propose_crm_activity','propose_report'},'marketing':{'propose_task','propose_report'},'support':{'propose_task','propose_ticket_note','propose_report'},'operations':{'propose_task','propose_purchase_order','propose_report'},'projects':{'propose_task','propose_report'},'documents':{'propose_report'},'meetings':{'propose_task','propose_report'},'reporting':{'propose_report'}}
def available(context,worker='advisor'):
    return [TOOLS[name] for name in WORKER_TOOLS.get(worker,set()) if allowed(context[1],RULES[name][1])]
def validate_proposal(tool_name,payload,db,context,worker='advisor'):
    if tool_name not in WORKER_TOOLS.get(worker,set()) or tool_name not in RULES:raise HTTPException(403,'This worker requested a tool outside its allowed scope.')
    kind,permission,risk=RULES[tool_name]
    if not allowed(context[1],permission):raise HTTPException(403,'Your current role cannot execute this tool.')
    data=SCHEMAS[kind].model_validate(payload).model_dump(mode='json');relations(db,data,context[1].company_id);validate(db,kind,data,context)
    return kind,data,risk
def execute(action,db,context,worker='advisor'):
    kind,data,_=validate_proposal(action.tool,action.payload,db,context,worker)
    from ..billing import enforce_records
    enforce_records(db,context);row=MODELS[kind](company_id=context[1].company_id,**data);db.add(row);db.flush();after_write(db,kind,row,context);event(db,context,'ai.'+kind+'.created',kind,row)
    return {'type':kind,'id':row.id,'name':row.name,'verified':True}
