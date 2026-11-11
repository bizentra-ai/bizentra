from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel
from typing import Literal
from sqlalchemy import select,func
from .database import get_db
from .security import current,require
from .models import Company,Membership,now
from .control_models import Subscription,Usage
from .services import REGISTRY,scoped,event,serialize
router=APIRouter(prefix='/api/billing',tags=['Subscriptions and entitlements'])
PLANS={'Starter':{'records':1000,'users':5,'ai_runs':25,'integrations':2},'Pro':{'records':20000,'users':50,'ai_runs':500,'integrations':10},'Business':{'records':100000,'users':500,'ai_runs':5000,'integrations':50}}

def subscription(db,context):
    row=db.scalar(select(Subscription).where(Subscription.company_id==context[1].company_id))
    if not row:
        row=Subscription(company_id=context[1].company_id,plan='Starter',status='Active');db.add(row);db.flush()
    return row

def usage(db,context):
    cid=context[1].company_id
    return {'records':sum(db.scalar(select(func.count()).select_from(scoped(db,m,cid).subquery())) for m,_ in REGISTRY.values()),'users':db.scalar(select(func.count()).select_from(Membership).where(Membership.company_id==cid)),'ai_runs':db.scalar(select(func.coalesce(func.sum(Usage.amount),0)).where(Usage.company_id==cid,Usage.category=='ai_runs',Usage.created_at>=now().replace(day=1,hour=0,minute=0,second=0,microsecond=0)))}

def enforce_records(db,context):
    row=subscription(db,context)
    if row.status=='Cancelled':raise HTTPException(403,'This subscription is cancelled. Reactivate a plan to create records.')
    if usage(db,context)['records']>=PLANS[row.plan]['records']:raise HTTPException(403,'Your plan record limit has been reached. Manage your plan in Billing.')

def consume_usage(db,context,category):
    row=subscription(db,context)
    if row.status!='Active' or usage(db,context).get(category,0)>=PLANS[row.plan][category]:raise HTTPException(403,'Your plan usage allowance is exhausted. Manage your plan in Billing.')
    db.add(Usage(company_id=context[1].company_id,category=category,amount=1))

@router.get('')
def get(context=Depends(require('billing.manage')),db=Depends(get_db)):
    row=subscription(db,context);db.commit()
    return {'subscription':serialize(row),'plans':PLANS,'usage':usage(db,context),'mode':'Self-managed entitlements. No payment processing or charges are enabled.'}

class Change(BaseModel):
    plan:Literal['Starter','Pro','Business']
    status:Literal['Active','Cancelled']='Active'

@router.put('')
def change(body:Change,context=Depends(require('billing.manage')),db=Depends(get_db)):
    row=subscription(db,context);counts=usage(db,context)
    if body.status=='Active' and any(counts[k]>PLANS[body.plan][k] for k in counts):raise HTTPException(409,'Current usage exceeds the selected plan. Reduce usage before downgrading.')
    row.plan=body.plan;row.status=body.status
    company=db.get(Company,context[1].company_id);company.plan=body.plan;event(db,context,'subscription.updated','billing',company);db.commit();return get(context,db)
