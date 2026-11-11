import os,json,csv,io,hmac,hashlib,base64
from datetime import timedelta
import pytest
from sqlalchemy import select
from cryptography.fernet import Fernet
from test_security import setup,account
from test_departments import create
from app.domain_models import MODELS
from app.catalog import CATALOG
from app.models import Membership,User,now
from app.control_models import Integration,ExternalRecord,AIAction,Subscription,Usage
from app.ai.context import build_context

def payload_for(c,h,kind,cache):
    if kind in cache:return cache[kind]
    values={'name':'Acceptance '+kind}
    for f in CATALOG[kind]['fields']:
        if f['name']=='name':continue
        if f.get('required'):
            if f['type']=='reference':
                values[f['name']]=c.get('/api/team',headers=h).json()[0]['id'] if f['target']=='team' else payload_for(c,h,f['target'],cache)['id']
            elif f['type']=='date':values[f['name']]='2026-09-01'
            elif f['type'] in ('money','integer'):values[f['name']]=100
            elif f['type']=='signed':values[f['name']]=5
            else:values[f['name']]='Acceptance detail'
    if kind=='task_dependencies':values['depends_on_id']=create(c,h,'tasks',{'name':'Separate dependency'})['id']
    row=create(c,h,kind,values);cache[kind]=row;return row

@pytest.mark.parametrize('kind',list(CATALOG))
def test_every_resource_crud_and_company_boundary(setup,kind):
    c,_=setup;a=account(c,'a@example.com');b=account(c,'b@example.com')
    row=payload_for(c,a,kind,{})
    assert c.get(f'/api/{kind}/{row["id"]}',headers=a).status_code==200
    assert c.get(f'/api/{kind}/{row["id"]}',headers=b).status_code==404
    assert c.delete(f'/api/{kind}/{row["id"]}',headers=b).status_code==404
    assert c.get('/api/'+kind,headers=b).json()==[]
    assert c.get('/api/search?q=Acceptance',headers=b).json()==[]
    editable={f['name']:row[f['name']] for f in CATALOG[kind]['fields']}
    editable['notes']='Updated through authorized API'
    changed=c.put(f'/api/{kind}/{row["id"]}',headers=a,json=editable)
    assert changed.status_code==(409 if kind=='stock_movements' else 200),changed.text
    if kind in ('payments','transactions'):editable['status']='Void';assert c.put(f'/api/{kind}/{row["id"]}',headers=a,json=editable).status_code==200
    result=c.delete(f'/api/{kind}/{row["id"]}',headers=a)
    assert result.status_code==(409 if kind=='stock_movements' else 200),result.text

@pytest.mark.parametrize('role,crm_write,finance_write',[('owner',201,201),('admin',201,201),('manager',201,403),('employee',403,403),('viewer',403,403)])
def test_roles_across_departments(setup,role,crm_write,finance_write):
    c,factory=setup;h=account(c)
    with factory() as db:m=db.scalar(select(Membership));m.role=role;db.commit()
    assert c.post('/api/customers',headers=h,json={'name':'Role customer'}).status_code==crm_write
    assert c.post('/api/expenses',headers=h,json={'name':'Role expense','amount_cents':500,'paid_date':'2026-09-01'}).status_code==finance_write
    assert c.post('/api/invitations',headers=h,json={'email':'invite@example.com'}).status_code==(201 if role in ('owner','admin') else 403)

def test_realistic_two_companies_and_employees(setup):
    c,factory=setup;a=account(c,'a@example.com');b=account(c,'b@example.com')
    owner_a=c.get('/api/users/me',headers=a).json();owner_b=c.get('/api/users/me',headers=b).json()
    employee_headers=[]
    for h,email in [(a,'ea@example.com'),(b,'eb@example.com')]:
        invitation=c.post('/api/invitations',headers=h,json={'email':email,'role':'employee'}).json()
        token=invitation['development_link'].split('token=')[1]
        accepted=c.post('/api/auth/accept-invitation',json={'token':token,'name':'Real test employee','password':'employee-test-password'}).json()
        employee_headers.append({'Authorization':'Bearer '+accepted['access_token']})
    row=create(c,a,'tasks',{'name':'A confidential task'})
    assert c.get('/api/tasks/'+str(row['id']),headers=employee_headers[0]).status_code==200
    assert c.get('/api/tasks/'+str(row['id']),headers=employee_headers[1]).status_code==404
    assert c.get('/api/users/me',headers=employee_headers[1]).json()['company']['id']==owner_b['company']['id']

def test_profile_updates_only_authenticated_user(setup):
    c,_=setup;a=account(c,'profile-a@example.com');b=account(c,'profile-b@example.com')
    payload={'name':'Updated Owner','phone':'+91 9000000000','job_title':'Founder','department':'Executive','timezone':'Asia/Kolkata','language':'Hindi','avatar':'data:image/png;base64,dGVzdA=='}
    result=c.put('/api/users/me',headers=a,json=payload)
    assert result.status_code==200,result.text
    assert result.json()['user']['job_title']=='Founder'
    assert result.json()['user']['avatar'].startswith('data:image/png')
    assert c.get('/api/users/me',headers=b).json()['user']['name']!='Updated Owner'

def test_ai_context_approval_history_and_replay(setup,monkeypatch):
    c,factory=setup;h=account(c);b=account(c,'other@example.com')
    customer=create(c,h,'customers',{'name':'Authorized customer'})
    create(c,h,'payments',{'name':'Receipt','customer_id':customer['id'],'amount_cents':12000,'paid_date':now().date().isoformat()})
    monkeypatch.setenv('AI_API_KEY','test-key-not-live');monkeypatch.setenv('AI_MODEL','test-model')
    captured=[]
    def generate(messages,tools):
        captured.append(messages)
        return {'text':'The recorded receipts total 12000 minor units.','calls':[{'name':'propose_task','arguments':{'name':'Follow up','notes':'Review customer','customer_id':customer['id'],'project_id':None,'due_date':None}}]}
    monkeypatch.setattr('app.ai.provider.generate',generate)
    result=c.post('/api/ai/chat',headers=h,json={'worker':'advisor','message':'What is my revenue this month? Create a follow-up task.'})
    assert result.status_code==200,result.text
    assert '12000' in captured[0][0]['content']
    action=result.json()['actions'][0];cid=result.json()['conversation']['id']
    assert c.get('/api/tasks',headers=h).json()==[]
    assert c.get('/api/ai/conversations/'+str(cid),headers=b).status_code==404
    assert c.post('/api/ai/actions/'+str(action['id'])+'/approve',headers=b).status_code==404
    for _ in range(2):assert c.post('/api/ai/actions/'+str(action['id'])+'/approve',headers=h).status_code==200
    assert len(c.get('/api/tasks',headers=h).json())==1
    with factory() as db:
        m=db.scalar(select(Membership).order_by(Membership.id));m.role='employee';db.commit()
    assert c.get('/api/ai/conversations/'+str(cid),headers=h).status_code==403
    c.post('/api/ai/chat',headers=h,json={'worker':'finance','message':'What is my revenue?'})
    assert '12000' not in captured[-1][0]['content']

def test_ai_telemetry_and_conversation_deletion_is_private(setup,monkeypatch):
    c,_=setup;a=account(c,'delete-a@example.com');b=account(c,'delete-b@example.com')
    create(c,a,'customers',{'name':'Evidence customer'})
    monkeypatch.setenv('AI_API_KEY','test-key');monkeypatch.setenv('AI_MODEL','test-model')
    monkeypatch.setattr('app.ai.provider.generate',lambda *a,**k:{'text':'Evidence-based answer.','calls':[],'usage':{'input_tokens':12,'output_tokens':7}})
    result=c.post('/api/ai/chat',headers=a,json={'message':'Summarize recorded business data.'});assert result.status_code==200,result.text
    cid=result.json()['conversation']['id'];run=result.json()['runs'][0]
    assert run['input_tokens']==12 and run['output_tokens']==7 and run['duration_ms']>=0
    assert run['mode']=='analyze'
    assistant=[m for m in result.json()['messages'] if m['role']=='assistant'][0]
    assert any(ref['type']=='customers' for ref in assistant['references'])
    assert c.delete('/api/ai/conversations/'+str(cid),headers=b).status_code==404
    assert c.delete('/api/ai/conversations/'+str(cid),headers=a).status_code==200
    assert c.get('/api/ai/conversations/'+str(cid),headers=a).status_code==404

def test_ai_missing_provider_and_invalid_action(setup,monkeypatch):
    c,_=setup;h=account(c)
    monkeypatch.delenv('AI_API_KEY',raising=False);monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    assert c.post('/api/ai/chat',headers=h,json={'message':'Revenue?'}).status_code==503
    monkeypatch.setenv('AI_API_KEY','test-key');monkeypatch.setenv('AI_MODEL','test-model')
    monkeypatch.setattr('app.ai.provider.generate',lambda *a:{'text':'','calls':[{'name':'delete_database','arguments':{}}]})
    assert c.post('/api/ai/chat',headers=h,json={'message':'Do something'}).status_code==403
    assert c.get('/api/ai/conversations',headers=h).status_code==200

def test_support_worker_executes_verified_ticket_action_and_rejects_wrong_tool(setup,monkeypatch):
    c,_=setup;h=account(c)
    customer=create(c,h,'customers',{'name':'Support customer'})
    ticket=create(c,h,'tickets',{'name':'Refund request','customer_id':customer['id']})
    monkeypatch.setenv('AI_API_KEY','test-key');monkeypatch.setenv('AI_MODEL','test-model')
    calls=[
        {'name':'propose_ticket_note','arguments':{'name':'Escalate refund request','ticket_id':ticket['id'],'note_type':'Escalation','body':'Escalated after reviewing the authorized ticket.','notes':'Needs owner review.'}},
        {'name':'propose_ticket_note','arguments':{'name':'Wrong worker action','ticket_id':ticket['id'],'note_type':'Internal note','body':'Should not run.','notes':''}},
    ]
    monkeypatch.setattr('app.ai.provider.generate',lambda *a,**k:{'text':'Prepared from the ticket record.','calls':[calls.pop(0)]})
    result=c.post('/api/ai/chat',headers=h,json={'worker':'support','message':'Escalate the refund ticket.'})
    assert result.status_code==200,result.text
    action=result.json()['actions'][0]
    assert action['risk']=='medium' and action['status']=='Pending'
    approved=c.post('/api/ai/actions/'+str(action['id'])+'/approve',headers=h)
    assert approved.status_code==200,approved.text
    assert approved.json()['result']['verified'] is True
    notes=c.get('/api/ticket_notes',headers=h).json()
    assert len(notes)==1 and notes[0]['ticket_id']==ticket['id'] and notes[0]['note_type']=='Escalation'
    denied=c.post('/api/ai/chat',headers=h,json={'worker':'sales','message':'Add a ticket note.'})
    assert denied.status_code==403
    assert len(c.get('/api/ticket_notes',headers=h).json())==1

def test_csv_import_idempotency_rollback_and_permissions(setup):
    c,factory=setup;a=account(c,'a@example.com');b=account(c,'b@example.com')
    source='external_id,name,email\nc1,Imported Customer,imported@example.com\n'
    for _ in range(2):
        r=c.post('/api/integrations/csv/import/customers',headers=a,files={'file':('customers.csv',source,'text/csv')});assert r.status_code==200,r.text
    assert len(c.get('/api/customers',headers=a).json())==1
    assert c.get('/api/customers',headers=b).json()==[]
    bad='external_id,name,email\nc2,Should roll back,valid@example.com\nc3,Invalid,not-an-email\n'
    assert c.post('/api/integrations/csv/import/customers',headers=a,files={'file':('customers.csv',bad,'text/csv')}).status_code==422
    assert len(c.get('/api/customers',headers=a).json())==1
    assert c.get('/api/integrations',headers=a).json()['logs'][0]['status']=='Failed'
    with factory() as db:m=db.scalar(select(Membership).order_by(Membership.id));m.role='viewer';db.commit()
    assert c.post('/api/integrations/csv/import/customers',headers=a,files={'file':('x.csv',source)}).status_code==403

def test_oauth_state_secure_sync_and_failure(setup,monkeypatch):
    from urllib.parse import urlparse,parse_qs
    c,factory=setup;h=account(c)
    monkeypatch.setenv('GOOGLE_CLIENT_ID','test-client');monkeypatch.setenv('GOOGLE_CLIENT_SECRET','test-secret');monkeypatch.setenv('INTEGRATION_ENCRYPTION_KEY',Fernet.generate_key().decode())
    start=c.post('/api/integrations/google/connect',headers=h);assert start.status_code==200,start.text
    state=parse_qs(urlparse(start.json()['authorization_url']).query)['state'][0]
    assert c.get('/api/integrations/google/callback?state=wrong&code=x',follow_redirects=False).status_code==400
    monkeypatch.setattr('app.integrations.request_json',lambda *a,**k:{'access_token':'private-access-token','refresh_token':'refresh','expires_in':3600})
    r=c.get('/api/integrations/google/callback',params={'state':state,'code':'test-code'},follow_redirects=False);assert r.status_code==303,r.text
    assert c.get('/api/integrations/google/callback',params={'state':state,'code':'test-code'},follow_redirects=False).status_code==400
    with factory() as db:assert 'private-access-token' not in db.scalar(select(Integration)).encrypted_tokens
    monkeypatch.setattr('app.integrations.contacts',lambda row:[{'external_id':'contact/1','name':'Synced person','email':'synced@example.com','organization':'Company'}])
    for _ in range(2):assert c.post('/api/integrations/google/sync',headers=h).status_code==200
    assert len(c.get('/api/customers',headers=h).json())==1
    assert 'private-access-token' not in c.get('/api/integrations',headers=h).text
    from fastapi import HTTPException
    def failure(row):raise HTTPException(502,'Provider unavailable')
    monkeypatch.setattr('app.integrations.contacts',failure)
    assert c.post('/api/integrations/google/sync',headers=h).status_code==502
    assert c.get('/api/integrations',headers=h).json()['connections'][0]['status']=='Needs attention'

def test_shopify_signed_oauth_sync_and_webhook_replay_protection(setup,monkeypatch):
    from urllib.parse import urlparse,parse_qs,urlencode
    c,factory=setup;headers=account(c)
    secret='shopify-test-secret'
    monkeypatch.setenv('SHOPIFY_CLIENT_ID','shopify-client');monkeypatch.setenv('SHOPIFY_CLIENT_SECRET',secret);monkeypatch.setenv('INTEGRATION_ENCRYPTION_KEY',Fernet.generate_key().decode())
    start=c.post('/api/integrations/shopify/connect?shop=example-store.myshopify.com',headers=headers)
    assert start.status_code==200,start.text
    state=parse_qs(urlparse(start.json()['authorization_url']).query)['state'][0]
    params={'code':'authorization-code','shop':'example-store.myshopify.com','state':state,'timestamp':'1792179000'}
    params['hmac']=hmac.new(secret.encode(),'&'.join(f'{k}={v}' for k,v in sorted(params.items())).encode(),hashlib.sha256).hexdigest()
    monkeypatch.setattr('app.shopify.exchange',lambda *a,**k:{'access_token':'shpat_private','scope':'read_customers,read_products,read_inventory,read_orders','expires_in':3600,'refresh_token':'refresh_private'})
    monkeypatch.setattr('app.shopify.identity',lambda row:{'id':'gid://shopify/Shop/1','name':'Example Store','myshopifyDomain':'example-store.myshopify.com','currencyCode':'USD'})
    callback=c.get('/api/integrations/shopify/callback?'+urlencode(params),follow_redirects=False)
    assert callback.status_code==303,callback.text
    with factory() as db:
        connection=db.scalar(select(Integration).where(Integration.provider=='shopify'))
        assert 'shpat_private' not in connection.encrypted_tokens and 'example-store' not in connection.encrypted_config
    def records(db,row):
        yield 'customers',[{'external_id':'gid://shopify/Customer/1','name':'Shopper','email':'shopper@example.com','organization':'','notes':'Source: Shopify'}]
        yield 'products',[{'external_id':'gid://shopify/Product/1','name':'Widget','status':'Active','sku':'W1','price_cents':1299,'stock':4,'threshold':0,'supplier_id':None,'notes':'Source: Shopify'}]
        customer=db.scalar(select(ExternalRecord).where(ExternalRecord.integration_id==row.id,ExternalRecord.kind=='customers'))
        yield 'orders',[{'external_id':'gid://shopify/Order/1','name':'#1001','status':'Confirmed','customer_id':customer.record_id,'order_date':'2026-10-16','due_date':None,'notes':'Source: Shopify · Total: 12.99 USD'}]
    monkeypatch.setattr('app.shopify.records',records)
    for _ in range(2):
        result=c.post('/api/integrations/shopify/sync',headers=headers);assert result.status_code==200,result.text
    assert len(c.get('/api/customers',headers=headers).json())==1
    assert len(c.get('/api/products',headers=headers).json())==1
    assert len(c.get('/api/orders',headers=headers).json())==1
    body=b'{"id":1,"title":"Widget"}';signature=base64.b64encode(hmac.new(secret.encode(),body,hashlib.sha256).digest()).decode()
    webhook_headers={'X-Shopify-Hmac-Sha256':signature,'X-Shopify-Shop-Domain':'example-store.myshopify.com','X-Shopify-Webhook-Id':'delivery-1','X-Shopify-Topic':'products/update'}
    first=c.post('/api/integrations/shopify/webhook',content=body,headers=webhook_headers);second=c.post('/api/integrations/shopify/webhook',content=body,headers=webhook_headers)
    assert first.json()=={'accepted':True,'duplicate':False} and second.json()=={'accepted':True,'duplicate':True}

def test_domain_requires_actual_txt_match(setup,monkeypatch):
    c,_=setup;h=account(c)
    r=c.post('/api/domain',headers=h,json={'domain':'business.example'});assert r.status_code==200,r.text
    assert r.json()['domain']['verified_at'] is None
    token=r.json()['domain']['token']
    monkeypatch.setattr('app.domains.lookup',lambda d:['unrelated-token'])
    assert c.post('/api/domain/verify',headers=h).status_code==409
    monkeypatch.setattr('app.domains.lookup',lambda d:[token])
    assert c.post('/api/domain/verify',headers=h).json()['domain']['verified_at'] is not None
    assert c.post('/api/domain',headers=h,json={'domain':'https://localhost/a'}).status_code==422

def test_subscription_limits_and_automation(setup,monkeypatch):
    c,_=setup;h=account(c)
    create(c,h,'tasks',{'name':'Overdue task','due_date':'2020-01-01'})
    rule=c.post('/api/automations',headers=h,json={'name':'Follow overdue work','trigger':'task_overdue'}).json()
    assert c.post('/api/automations/'+str(rule['id'])+'/run',headers=h).json()['created']==1
    assert c.post('/api/automations/'+str(rule['id'])+'/run',headers=h).json()['created']==0
    assert len(c.get('/api/automations',headers=h).json()['runs'])==1
    assert c.put('/api/billing',headers=h,json={'plan':'Pro'}).status_code==200
    assert c.put('/api/billing',headers=h,json={'plan':'Pro','status':'Cancelled'}).status_code==200
    assert c.post('/api/customers',headers=h,json={'name':'Blocked by cancellation'}).status_code==403
    assert c.get('/api/tasks',headers=h).status_code==200

def test_template_install_idempotent_and_text_upload(setup):
    c,_=setup;h=account(c)
    for _ in range(2):assert c.post('/api/marketplace/customer-onboarding/install',headers=h).status_code==200
    assert len(c.get('/api/projects',headers=h).json())==1
    assert len(c.get('/api/tasks',headers=h).json())==3
    r=c.post('/api/documents-tools/upload',headers=h,files={'file':('meeting.md','# Decisions\nShip next week.','text/markdown')});assert r.status_code==200,r.text
    assert 'Ship next week' in r.json()['content']
    assert c.post('/api/documents-tools/upload',headers=h,files={'file':('bad.exe','binary','application/octet-stream')}).status_code==422

def test_forecasts_require_real_consecutive_history(setup):
    c,_=setup;h=account(c)
    assert c.get('/api/predictions',headers=h).json()['forecast'] is None
    customer=create(c,h,'customers',{'name':'Paying customer'})
    today=now();serial=today.year*12+today.month-1
    for offset,amount in [(3,10000),(2,20000),(1,30000)]:
        month_index=serial-offset;year=month_index//12;month=month_index%12+1
        create(c,h,'payments',{'name':f'Receipt {offset}','customer_id':customer['id'],'amount_cents':amount,'paid_date':f'{year:04}-{month:02}-01'})
    forecast=c.get('/api/predictions',headers=h).json()['forecast'];assert forecast['expected_cents']==20000
    assert forecast['confidence']=='Low'
    assert c.post('/api/predictions/run',headers=h).status_code==200
    assert len(c.get('/api/predictions/history',headers=h).json())==1
