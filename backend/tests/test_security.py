import os
import secrets
from datetime import timedelta
os.environ['SECRET_KEY']=secrets.token_urlsafe(48)
os.environ['ENVIRONMENT']='development'
os.environ['EMAIL_HOST']=''
import pytest
import jwt
from fastapi.testclient import TestClient
from sqlalchemy import create_engine,select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.database import Base,get_db
from app.main import app
from app.models import User,Membership,Customer,Activity,now,Challenge
from app.security import _buckets,hasher
from app.config import SECRET_KEY

@pytest.fixture()
def setup():
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory=sessionmaker(bind=engine,expire_on_commit=False)
    def db():
        with factory() as session: yield session
    app.dependency_overrides[get_db]=db
    _buckets.clear()
    with TestClient(app) as client: yield client,factory
    app.dependency_overrides.clear()
    engine.dispose()

def account(client,email='owner@example.com'):
    r=client.post('/api/auth/register',json={'business_name':'Example Company','name':'Test Owner','email':email,'password':'a-secure-test-password'})
    assert r.status_code==201,r.text
    code=r.json()['development_code']
    r=client.post('/api/auth/verify-otp',json={'email':email,'code':code})
    assert r.status_code==200,r.text
    return {'Authorization':'Bearer '+r.json()['access_token']}

def test_auth_lifecycle_and_password_hash(setup):
    client,factory=setup
    headers=account(client)
    assert client.get('/api/users/me',headers=headers).json()['role']=='owner'
    with factory() as db:
        user=db.scalar(select(User))
        assert user.password_hash.startswith('$argon2')
        assert hasher.verify(user.password_hash,'a-secure-test-password')
    assert client.post('/api/auth/login',json={'email':'owner@example.com','password':'wrong'}).status_code==401
    assert client.post('/api/auth/login',json={'email':'owner@example.com','password':'a-secure-test-password'}).status_code==200
    assert client.post('/api/auth/logout',headers=headers).status_code==200
    assert client.get('/api/users/me',headers=headers).status_code==401

def test_otp_invalid_expired_and_reuse(setup):
    client,factory=setup
    payload={'business_name':'A business','name':'Test Owner','email':'a@example.com','password':'secure-password-123'}
    r=client.post('/api/auth/register',json=payload)
    code=r.json()['development_code']
    assert client.post('/api/auth/login',json={'email':payload['email'],'password':payload['password']}).status_code==403
    assert client.post('/api/auth/verify-otp',json={'email':payload['email'],'code':'000000' if code!='000000' else '111111'}).status_code==400
    with factory() as db:
        row=db.scalar(select(Challenge));row.expires_at=now()-timedelta(seconds=1);db.commit()
    assert client.post('/api/auth/verify-otp',json={'email':payload['email'],'code':code}).status_code==400
    r=client.post('/api/auth/resend-otp',json={'email':payload['email']})
    code=r.json()['development_code']
    assert client.post('/api/auth/verify-otp',json={'email':payload['email'],'code':code}).status_code==200
    assert client.post('/api/auth/verify-otp',json={'email':payload['email'],'code':code}).status_code==400

def test_expired_and_tampered_token(setup):
    client,_=setup
    headers=account(client)
    valid=headers['Authorization'].split()[1]
    claims=jwt.decode(valid,SECRET_KEY,algorithms=['HS256'],audience='businessos')
    claims['exp']=now()-timedelta(seconds=10)
    expired=jwt.encode(claims,SECRET_KEY,algorithm='HS256')
    assert client.get('/api/users/me',headers={'Authorization':'Bearer '+expired}).status_code==401
    assert client.get('/api/users/me',headers={'Authorization':'Bearer '+valid+'x'}).status_code==401
    assert client.get('/api/customers').status_code==401

def test_crud_audit_soft_delete_and_validation(setup):
    client,factory=setup
    h=account(client)
    r=client.post('/api/customers',headers=h,json={'name':'Ada','email':'ada@example.com'})
    assert r.status_code==201,r.text
    rid=r.json()['id']
    assert client.get(f'/api/customers/{rid}',headers=h).json()['name']=='Ada'
    assert client.put(f'/api/customers/{rid}',headers=h,json={'name':'Ada Updated','status':'Customer'}).status_code==200
    assert client.post('/api/customers',headers=h,json={'name':'Bad','company_id':999}).status_code==422
    assert client.post('/api/tasks',headers=h,json={'name':'Bad','due_date':'not-a-date'}).status_code==422
    assert client.delete(f'/api/customers/{rid}',headers=h).status_code==200
    assert client.get(f'/api/customers/{rid}',headers=h).status_code==404
    with factory() as db:
        assert db.get(Customer,rid).deleted_at is not None
        assert len(list(db.scalars(select(Activity))))==3
    assert client.put('/api/activities/1',headers=h,json={}).status_code in [404,405]

def test_tenant_isolation_all_surfaces(setup):
    client,_=setup
    a=account(client,'a@example.com');b=account(client,'b@example.com')
    customer=client.post('/api/customers',headers=a,json={'name':'Secret customer'}).json()
    project=client.post('/api/projects',headers=a,json={'name':'Secret project'}).json()
    rid=customer['id']
    assert client.get('/api/customers',headers=b).json()==[]
    assert client.get(f'/api/customers/{rid}',headers=b).status_code==404
    assert client.put(f'/api/customers/{rid}',headers=b,json={'name':'Stolen'}).status_code==404
    assert client.delete(f'/api/customers/{rid}',headers=b).status_code==404
    assert client.post('/api/tasks',headers=b,json={'name':'Cross tenant','customer_id':rid}).status_code==404
    assert client.post('/api/tasks',headers=b,json={'name':'Cross tenant','project_id':project['id']}).status_code==404
    assert client.get('/api/search?q=Secret',headers=b).json()==[]
    assert client.get('/api/activities',headers=b).json()==[]
    assert 'Secret' not in client.get('/api/customers/export',headers=b).text
    assert client.get('/api/analytics/overview',headers=b).json()['customers']['total']==0

def test_permissions_owner_protection_and_search(setup):
    client,factory=setup
    h=account(client)
    uid=client.get('/api/users/me',headers=h).json()['user']['id']
    assert client.put(f'/api/team/{uid}/role',headers=h,json={'role':'viewer'}).status_code==403
    client.post('/api/customers',headers=h,json={'name':'Hidden customer'})
    with factory() as db:
        member=db.scalar(select(Membership));member.role='employee';member.permissions=[];db.commit()
    assert client.get('/api/customers',headers=h).status_code==200
    assert client.post('/api/customers',headers=h,json={'name':'Blocked'}).status_code==403
    assert client.get('/api/customers/export',headers=h).status_code==403
    assert client.put('/api/company',headers=h,json={'name':'Changed'}).status_code==403
    assert client.post('/api/invitations',headers=h,json={'email':'x@example.com'}).status_code==403
    with factory() as db:
        member=db.scalar(select(Membership));member.role='custom';member.permissions=['projects.tasks.view'];db.commit()
    assert client.get('/api/search?q=Hidden',headers=h).json()==[]
    assert client.get('/api/activities',headers=h).json()==[]
    assert 'customers' not in client.get('/api/analytics/overview',headers=h).json()

def test_invitation_acceptance_and_reset(setup):
    client,_=setup
    h=account(client)
    r=client.post('/api/invitations',headers=h,json={'email':'member@example.com','role':'viewer'})
    assert r.status_code==201,r.text
    token=r.json()['development_link'].split('token=')[1]
    payload={'token':token,'name':'Team Member','password':'member-password-123'}
    r=client.post('/api/auth/accept-invitation',json=payload)
    assert r.status_code==200,r.text
    member={'Authorization':'Bearer '+r.json()['access_token']}
    assert client.get('/api/users/me',headers=member).json()['company']['id']==client.get('/api/users/me',headers=h).json()['company']['id']
    assert client.post('/api/tasks',headers=member,json={'name':'Blocked'}).status_code==403
    assert client.post('/api/auth/accept-invitation',json=payload).status_code==400
    code=client.post('/api/auth/forgot-password',json={'email':'member@example.com'}).json()['development_code']
    assert client.post('/api/auth/reset-password',json={'email':'member@example.com','code':code,'password':'new-password-123456'}).status_code==200
    assert client.get('/api/users/me',headers=member).status_code==401

def test_login_rate_limit(setup):
    client,_=setup
    for _ in range(12): client.post('/api/auth/login',json={'email':'none@example.com','password':'wrong'})
    assert client.post('/api/auth/login',json={'email':'none@example.com','password':'wrong'}).status_code==429

def test_related_records_and_notifications(setup):
    client,_=setup
    h=account(client)
    project=client.post('/api/projects',headers=h,json={'name':'Website'}).json()
    task=client.post('/api/tasks',headers=h,json={'name':'Review','project_id':project['id'],'due_date':'2020-01-01'}).json()
    notice=client.get('/api/notifications',headers=h).json()[0]
    assert notice['entity_id']==task['id'] and notice['read_at'] is None
    assert client.put('/api/notifications/'+str(notice['id'])+'/read',headers=h).json()['read_at'] is not None
    assert client.get('/api/notifications',headers=h).json()[0]['read_at'] is not None
    prefs=client.get('/api/notifications/preferences',headers=h).json()
    prefs['categories']['projects']=False
    assert client.put('/api/notifications/preferences',headers=h,json={'categories':prefs['categories'],'email_enabled':False}).status_code==200
    assert client.get('/api/analytics/overview',headers=h).json()['tasks']['overdue']==1
    assert client.put('/api/tasks/'+str(task['id']),headers=h,json={'name':'Review','status':'Done','project_id':project['id'],'due_date':'2020-01-01'}).status_code==200
    assert client.get('/api/notifications',headers=h).json()==[]
    history=client.get('/api/notifications?include_resolved=true',headers=h).json()
    assert len(history)==1 and history[0]['resolved_at'] is not None
