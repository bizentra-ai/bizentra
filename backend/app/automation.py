from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy import select
from pydantic import BaseModel,Field
from typing import Literal
from .database import get_db
from .security import require,allowed
from .models import User,Membership,now
from .control_models import Automation,AutomationRun
from .domain_models import MODELS
from .services import scoped,record,serialize,event
from .billing import enforce_records
router=APIRouter(prefix='/api/automations',tags=['Automation'])
TRIGGERS={'invoice_overdue':('invoices','finance.invoices.view'),'stock_low':('products','operations.products.view'),'ticket_urgent':('tickets','support.tickets.view'),'task_overdue':('tasks','projects.tasks.view'),'lead_followup':('leads','crm.leads.view')}

class Rule(BaseModel):
    name:str=Field(min_length=1,max_length=160)
    trigger:Literal['invoice_overdue','stock_low','ticket_urgent','task_overdue','lead_followup']
    enabled:bool=True

def run_rule(db,rule,context):
    kind,permission=TRIGGERS[rule.trigger]
    if not allowed(context[1],permission) or not allowed(context[1],'projects.tasks.create'):raise HTTPException(403,'The automation owner no longer has the required source and task permissions.')
    today=now().date().isoformat();created=0
    candidates=list(db.scalars(scoped(db,MODELS[kind],context[1].company_id)))
    for row in candidates:
        if rule.trigger=='invoice_overdue':
            from .finance import summary
            eligible=any(i['id']==row.id and i['overdue'] for i in summary(db,context)['invoices'])
        elif rule.trigger=='stock_low':eligible=row.stock<=row.threshold
        elif rule.trigger=='ticket_urgent':eligible=row.priority in ('High','Urgent') and row.status!='Resolved'
        else:eligible=bool(row.due_date and row.due_date<today and row.status not in ('Done','Converted','Lost') and not row.notes.startswith('Automation source:'))
        if not eligible:continue
        source=kind+':'+str(row.id)
        if db.scalar(select(AutomationRun).where(AutomationRun.rule_id==rule.id,AutomationRun.source_key==source)):continue
        enforce_records(db,context)
        task=MODELS['tasks'](company_id=context[1].company_id,name=(rule.name+': '+row.name)[:160],notes='Automation source: '+source,status='To do',priority='High',assignee_id=context[0].id)
        db.add(task);db.flush();event(db,context,'automation.task.created','tasks',task)
        db.add(AutomationRun(company_id=context[1].company_id,rule_id=rule.id,source_key=source,status='Completed',result='Created task '+str(task.id)));created+=1
    return created

@router.get('')
def get(context=Depends(require('automation.manage')),db=Depends(get_db)):
    return {'rules':[serialize(r) for r in db.scalars(scoped(db,Automation,context[1].company_id))],'runs':[serialize(r) for r in db.scalars(select(AutomationRun).where(AutomationRun.company_id==context[1].company_id).order_by(AutomationRun.id.desc()).limit(100))],'triggers':list(TRIGGERS)}

@router.post('')
def create(body:Rule,context=Depends(require('automation.manage')),db=Depends(get_db)):
    kind,p=TRIGGERS[body.trigger]
    if not allowed(context[1],p) or not allowed(context[1],'projects.tasks.create'):raise HTTPException(403,'Source read and task creation permissions are required.')
    row=Automation(company_id=context[1].company_id,user_id=context[0].id,**body.model_dump());db.add(row);db.flush();event(db,context,'automation.created','automations',row);db.commit();return serialize(row)

@router.put('/{rule_id}')
def edit(rule_id:int,body:Rule,context=Depends(require('automation.manage')),db=Depends(get_db)):
    row=record(db,Automation,context[1].company_id,rule_id)
    for k,v in body.model_dump().items():setattr(row,k,v)
    event(db,context,'automation.updated','automations',row);db.commit();return serialize(row)

@router.delete('/{rule_id}')
def delete(rule_id:int,context=Depends(require('automation.manage')),db=Depends(get_db)):
    row=record(db,Automation,context[1].company_id,rule_id);row.enabled=False;row.deleted_at=now();event(db,context,'automation.archived','automations',row);db.commit();return {'message':'Rule archived.'}

@router.post('/{rule_id}/run')
def run(rule_id:int,context=Depends(require('automation.manage')),db=Depends(get_db)):
    row=record(db,Automation,context[1].company_id,rule_id)
    if not row.enabled:raise HTTPException(409,'Enable the automation before running it.')
    owner=db.get(User,row.user_id);membership=db.scalar(select(Membership).where(Membership.user_id==owner.id,Membership.company_id==row.company_id))
    if not owner.active or not membership:raise HTTPException(403,'Automation owner is inactive.')
    count=run_rule(db,row,(owner,membership));db.commit();return {'created':count,'message':f'Created {count} follow-up tasks. Previously handled records were skipped.'}

def tick():
    from .database import SessionLocal
    with SessionLocal() as db:
        rules=list(db.scalars(select(Automation).where(Automation.enabled==True,Automation.deleted_at==None)))
        for rule in rules:
            try:
                user=db.get(User,rule.user_id);m=db.scalar(select(Membership).where(Membership.user_id==rule.user_id,Membership.company_id==rule.company_id))
                if user and user.active and m:run_rule(db,rule,(user,m));db.commit()
            except Exception:
                db.rollback()
                # A run failure is visible without exposing underlying secrets or data.
                source='error:'+now().strftime('%Y-%m-%dT%H:%M')
                if not db.scalar(select(AutomationRun).where(AutomationRun.rule_id==rule.id,AutomationRun.source_key==source)):
                    db.add(AutomationRun(company_id=rule.company_id,rule_id=rule.id,source_key=source,status='Failed',result='Execution failed. Check permissions, plan capacity and source records.'));db.commit()
