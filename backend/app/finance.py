from fastapi import APIRouter,Depends,HTTPException
from .security import require,allowed
from .database import get_db
from .services import scoped,record,serialize
from .domain_models import MODELS
from .models import now

router=APIRouter(prefix='/api/finance',tags=['Finance'])

def summary(db,context):
    cid=context[1].company_id
    data={key:list(db.scalars(scoped(db,MODELS[key],cid))) for key in ('invoices','payments','expenses','transactions') if allowed(context[1],'finance.'+key+'.view')}
    monthly={}
    for kind,datefield in [('payments','paid_date'),('expenses','paid_date'),('transactions','paid_date')]:
        for row in data.get(kind,[]):
            if row.status not in ('Posted','Paid'):continue
            month=getattr(row,datefield)[:7]
            item=monthly.setdefault(month,{'month':month,'income_cents':0,'expense_cents':0})
            income=kind=='payments' or (kind=='transactions' and row.direction=='Income')
            item['income_cents' if income else 'expense_cents']+=row.amount_cents
    income=sum(m['income_cents'] for m in monthly.values());expense=sum(m['expense_cents'] for m in monthly.values())
    invoices=[]
    for inv in data.get('invoices',[]):
        paid=sum(p.amount_cents for p in data.get('payments',[]) if p.invoice_id==inv.id and p.status=='Posted')
        balance=max(0,inv.amount_cents-paid) if inv.status=='Issued' else 0
        invoices.append({**serialize(inv),'paid_cents':paid,'balance_cents':balance,'overdue':bool(balance and inv.due_date<now().date().isoformat())})
    return {'basis':'Cash basis · payments + standalone transactions − paid expenses. Do not record a payment twice as a transaction.','income_cents':income,'expense_cents':expense,'profit_cents':income-expense,'cash_flow_cents':income-expense,'outstanding_cents':sum(i['balance_cents'] for i in invoices),'overdue_cents':sum(i['balance_cents'] for i in invoices if i['overdue']),'monthly':[monthly[k] for k in sorted(monthly)],'invoices':invoices,'has_data':any(data.values()),'as_of':now().isoformat()+'Z'}

@router.get('/summary')
def report(context=Depends(require('finance.invoices.view')),db=Depends(get_db)):
    if not all(allowed(context[1],'finance.'+key+'.view') for key in ['invoices','payments','expenses','transactions']):raise HTTPException(403,'This combined report requires permission to view invoices, payments, expenses and transactions.')
    return summary(db,context)
