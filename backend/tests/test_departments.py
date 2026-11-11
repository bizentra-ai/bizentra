from test_security import setup,account
from sqlalchemy import select
from app.models import Membership

def create(client,h,kind,body):
    r=client.post('/api/'+kind,headers=h,json=body)
    assert r.status_code==201,r.text
    return r.json()

def test_finance_balance_and_cash_summary(setup):
    c,_=setup;h=account(c)
    customer=create(c,h,'customers',{'name':'Customer'})
    invoice=create(c,h,'invoices',{'name':'INV-1','customer_id':customer['id'],'amount_cents':10000,'issued_date':'2026-09-01','due_date':'2026-09-10','status':'Issued'})
    create(c,h,'payments',{'name':'Receipt','customer_id':customer['id'],'invoice_id':invoice['id'],'amount_cents':4000,'paid_date':'2026-09-05'})
    create(c,h,'expenses',{'name':'Hosting','amount_cents':1000,'paid_date':'2026-09-05','status':'Paid'})
    summary=c.get('/api/finance/summary',headers=h).json()
    assert summary['income_cents']==4000
    assert summary['profit_cents']==3000
    assert summary['outstanding_cents']==6000
    assert c.post('/api/payments',headers=h,json={'name':'Overpay','customer_id':customer['id'],'invoice_id':invoice['id'],'amount_cents':7000,'paid_date':'2026-09-05'}).status_code==409
    assert c.delete('/api/invoices/'+str(invoice['id']),headers=h).status_code==409

def test_finance_tenant_and_manager_write_permission(setup):
    c,factory=setup;a=account(c,'a@example.com');b=account(c,'b@example.com')
    row=create(c,a,'expenses',{'name':'Private expense','amount_cents':5000,'paid_date':'2026-09-01'})
    assert c.get('/api/expenses/'+str(row['id']),headers=b).status_code==404
    assert c.get('/api/finance/summary',headers=b).json()['expense_cents']==0
    with factory() as db:
        m=db.scalar(select(Membership).order_by(Membership.id));m.role='manager';db.commit()
    assert c.post('/api/expenses',headers=a,json={'name':'Denied','amount_cents':100,'paid_date':'2026-09-01'}).status_code==403

def test_lead_conversion_and_sales_validation(setup):
    c,_=setup;h=account(c)
    lead=create(c,h,'leads',{'name':'Potential customer','email':'customer@example.com','priority':'High'})
    response=c.post('/api/crm/leads/'+str(lead['id'])+'/convert',headers=h)
    assert response.status_code==200,response.text
    customer=response.json()
    assert c.post('/api/crm/leads/'+str(lead['id'])+'/convert',headers=h).json()['id']==customer['id']
    assert len(c.get('/api/customers',headers=h).json())==1
    assert c.post('/api/opportunities',headers=h,json={'name':'Invalid probability','customer_id':customer['id'],'probability':101}).status_code==422
    create(c,h,'opportunities',{'name':'New contract','customer_id':customer['id'],'probability':60,'amount_cents':20000})
    create(c,h,'crm_activities',{'name':'Call follow-up','lead_id':lead['id'],'customer_id':customer['id'],'activity_type':'Call'})

def test_support_resolution_history_and_response_time(setup):
    c,_=setup;h=account(c);customer=create(c,h,'customers',{'name':'Customer'})
    ticket=create(c,h,'tickets',{'name':'Delivery delayed','customer_id':customer['id'],'priority':'Urgent','due_date':'2020-01-01'})
    create(c,h,'ticket_notes',{'name':'First response','ticket_id':ticket['id'],'note_type':'Response recorded','body':'We are investigating the delivery.'})
    create(c,h,'ticket_notes',{'name':'Resolution','ticket_id':ticket['id'],'note_type':'Resolution','body':'Delivery received.'})
    assert c.get('/api/tickets/'+str(ticket['id']),headers=h).json()['status']=='Resolved'
    report=c.get('/api/departments/support/summary',headers=h).json()['metrics']
    assert report['resolved_tickets']==1 and report['open_tickets']==0
    assert report['average_first_response_hours'] is not None

def test_marketing_metrics_and_validation(setup):
    c,_=setup;h=account(c)
    create(c,h,'campaigns',{'name':'Launch','status':'Running','spend_cents':10000,'revenue_cents':30000,'leads_generated':20,'conversions':5})
    m=c.get('/api/departments/marketing/summary',headers=h).json()['metrics']
    assert m['conversion_percent']==25 and m['return_on_spend_percent']==200
    assert c.post('/api/campaigns',headers=h,json={'name':'Invalid','leads_generated':1,'conversions':2}).status_code==422
