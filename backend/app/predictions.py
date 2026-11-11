import statistics
from datetime import date
from fastapi import APIRouter,Depends
from sqlalchemy import select
from .database import get_db
from .security import current,allowed
from .models import now
from .control_models import Prediction
from .services import REGISTRY,scoped,serialize,event
from .finance import summary
router=APIRouter(prefix='/api/predictions',tags=['Predictive Intelligence'])

def calculate(db,context):
    warnings=[];forecast=None;monthly=[];scopes=[];cid=context[1].company_id
    if all(allowed(context[1],'finance.'+k+'.view') for k in ['invoices','payments','expenses','transactions']):
        scopes += ['finance.'+k+'.view' for k in ['invoices','payments','expenses','transactions']]
        finance=summary(db,context);monthly=[m for m in finance['monthly'] if m['month']<now().strftime('%Y-%m')]
        if len(monthly)>=3:
            # Require consecutive complete months: missing months are not silently treated as zero.
            selected=monthly[-6:];ordinals=[int(m['month'][:4])*12+int(m['month'][5:]) for m in selected]
            if all(b-a==1 for a,b in zip(ordinals,ordinals[1:])) and ordinals[-1]==now().year*12+now().month-1:
                values=[m['income_cents'] for m in selected];mean=statistics.mean(values);spread=statistics.pstdev(values)
                forecast={'expected_cents':round(mean),'low_cents':max(0,round(mean-2*spread)),'high_cents':round(mean+2*spread),'confidence':'Low' if len(values)<6 else 'Medium','basis':f'Mean of {len(values)} consecutive complete months of recorded cash receipts. Range is mean ± 2 historical standard deviations; it is not a statistical confidence interval. Current month excluded.','history':selected}
        if finance['overdue_cents']:warnings.append({'type':'finance','title':'Overdue receivables','detail':f"{finance['overdue_cents']} minor currency units remain overdue.",'basis':'Issued invoices less posted payments; due date before today.'})
    for kind,rule,title in [('products',lambda r:r.stock<=r.threshold,'Low stock'),('tasks',lambda r:r.status!='Done' and r.due_date and r.due_date<now().date().isoformat(),'Overdue project work'),('tickets',lambda r:r.status!='Resolved' and r.priority in ('High','Urgent'),'Urgent customer issue')]:
        model,permission=REGISTRY[kind]
        if allowed(context[1],permission+'.view'):
            scopes.append(permission+'.view')
            for row in db.scalars(scoped(db,model,cid)):
                if rule(row):warnings.append({'type':kind,'id':row.id,'title':title+': '+row.name,'detail':f'Stock {row.stock}; threshold {row.threshold}' if kind=='products' else ('Due '+row.due_date if kind=='tasks' else row.priority+' priority'),'basis':'Rule applied to current authorized records; this is a warning, not a guaranteed outcome.'})
    return {'forecast':forecast,'message':None if forecast else 'Not enough company data yet. Revenue forecasts require at least three consecutive complete months of receipts through last month.','warnings':warnings,'as_of':now().isoformat()+'Z','scopes':sorted(set(scopes))}

@router.get('')
def get(context=Depends(current),db=Depends(get_db)):return calculate(db,context)

@router.post('/run')
def run(context=Depends(current),db=Depends(get_db)):
    result=calculate(db,context);row=Prediction(company_id=context[1].company_id,user_id=context[0].id,name='Business forecast '+now().date().isoformat(),scopes=result['scopes'],result=result)
    db.add(row);db.flush();event(db,context,'prediction.generated','predictions',row);db.commit();return serialize(row)

@router.get('/history')
def history(context=Depends(current),db=Depends(get_db)):
    return [serialize(r) for r in db.scalars(scoped(db,Prediction,context[1].company_id).where(Prediction.user_id==context[0].id).order_by(Prediction.id.desc()).limit(30)) if all(allowed(context[1],p) for p in r.scopes)]
