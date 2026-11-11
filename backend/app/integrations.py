import os,json,secrets,hashlib,base64,time,csv,io
from datetime import timedelta
from urllib.parse import urlencode,urlparse
import httpx
from fastapi import APIRouter,Depends,HTTPException,UploadFile,File,Request,Query
from fastapi.responses import RedirectResponse,Response
from sqlalchemy import select,update
from pydantic import ValidationError
from .database import get_db
from .security import require,allowed,digest,limit
from .models import Membership,User,now
from .control_models import Integration,OAuthState,SyncLog,ExternalRecord,WebhookDelivery,Notification
from .domain_models import MODELS,SCHEMAS
from .catalog import CATALOG
from .services import serialize,event,record,relations
from .record_hooks import validate,after_write
from .billing import enforce_records,subscription,PLANS
from .config import FRONTEND_URL
from .integration_engine import encrypt,decrypt,request_json,redact_connection
from . import shopify
router=APIRouter(prefix='/api/integrations',tags=['Integrations'])
PROVIDERS={
 'google':{'name':'Google Workspace contacts','authorization':'https://accounts.google.com/o/oauth2/v2/auth','token':'https://oauth2.googleapis.com/token','scope':'https://www.googleapis.com/auth/contacts.readonly','description':'Read your Google contacts and import them into CRM. No email, calendar or external write access.'},
 'microsoft':{'name':'Microsoft 365 contacts','authorization':'https://login.microsoftonline.com/organizations/oauth2/v2.0/authorize','token':'https://login.microsoftonline.com/organizations/oauth2/v2.0/token','scope':'offline_access Contacts.Read','description':'Read your Microsoft work account contacts and import them into CRM. No external write access.'},
 'shopify':{'name':'Shopify','scope':shopify.SCOPES,'description':'Read customers, products, inventory totals, and orders into shared CRM and Operations records. BusinessOS does not write to Shopify.','objects':['customers','products','orders'],'setup_fields':['shop'],'implementation':'ready_for_credentials'},
}

def settings(provider):
    if provider not in PROVIDERS:raise HTTPException(404,'Provider not supported.')
    return {**PROVIDERS[provider],'client_id':os.getenv(provider.upper()+'_CLIENT_ID',''),'client_secret':os.getenv(provider.upper()+'_CLIENT_SECRET',''),'redirect_uri':os.getenv('PUBLIC_API_URL','http://127.0.0.1:8000').rstrip('/')+'/api/integrations/'+provider+'/callback'}

def public(row):return redact_connection(row,serialize)

def notify(db,context,row,status,detail):
    key=f'integration:{row.id}:{status}:{secrets.token_hex(8)}'
    for member in db.scalars(select(Membership).where(Membership.company_id==context[1].company_id)):
        db.add(Notification(company_id=context[1].company_id,user_id=member.user_id,source_key=key+':'+str(member.user_id),category='system',title=row.name+' '+status,detail=detail,entity='integrations',entity_id=row.id,route='/integrations'))

def get_connection(db,provider,context):
    row=db.scalar(select(Integration).where(Integration.company_id==context[1].company_id,Integration.provider==provider))
    if not row:
        sub=subscription(db,context)
        count=len(list(db.scalars(select(Integration).where(Integration.company_id==context[1].company_id,Integration.status!='Disconnected'))))
        if sub.status!='Active' or count>=PLANS[sub.plan]['integrations']:raise HTTPException(403,'Integration allowance reached for this plan.')
        row=Integration(company_id=context[1].company_id,provider=provider,name=PROVIDERS.get(provider,{}).get('name','CSV import'));db.add(row);db.flush()
    return row

@router.get('')
def listing(context=Depends(require('integrations.connections.manage')),db=Depends(get_db)):
    rows=list(db.scalars(select(Integration).where(Integration.company_id==context[1].company_id)))
    return {'available':[{'id':key,'name':p['name'],'description':p['description'],'configured':bool(settings(key)['client_id'] and settings(key)['client_secret'] and os.getenv('INTEGRATION_ENCRYPTION_KEY')),'redirect_uri':settings(key)['redirect_uri'],'required_environment':[key.upper()+'_CLIENT_ID',key.upper()+'_CLIENT_SECRET','INTEGRATION_ENCRYPTION_KEY'],'objects':p.get('objects',['customers']),'setup_fields':p.get('setup_fields',[]),'implementation':p.get('implementation','operational')} for key,p in PROVIDERS.items()],'connections':[public(r) for r in rows],'logs':[serialize(r) for r in db.scalars(select(SyncLog).where(SyncLog.company_id==context[1].company_id).order_by(SyncLog.id.desc()).limit(100))]}

@router.post('/{provider}/connect')
def connect(provider:str,request:Request,shop:str='',context=Depends(require('integrations.connections.manage')),db=Depends(get_db)):
    limit(request,'oauth',5)
    if not allowed(context[1],'crm.customers.create') or not allowed(context[1],'crm.customers.edit'):raise HTTPException(403,'CRM customer creation and edit permissions are required for importing contacts.')
    s=settings(provider);from .integration_engine import cipher;cipher()
    if not s['client_id'] or not s['client_secret']:raise HTTPException(503,'Configure '+provider.upper()+'_CLIENT_ID and '+provider.upper()+'_CLIENT_SECRET on the backend first.')
    get_connection(db,provider,context)
    state=secrets.token_urlsafe(32);verifier=secrets.token_urlsafe(48)
    state_data={'shop':shopify.normalize_shop(shop)} if provider=='shopify' else verifier
    db.add(OAuthState(company_id=context[1].company_id,user_id=context[0].id,provider=provider,digest=digest(state),verifier=encrypt(state_data),expires_at=now()+timedelta(minutes=10)))
    if provider=='shopify':
        db.commit();return {'authorization_url':shopify.authorize_url(state_data['shop'],state,s['client_id'],s['redirect_uri'])}
    params={'client_id':s['client_id'],'redirect_uri':s['redirect_uri'],'response_type':'code','scope':s['scope'],'state':state,'code_challenge':base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('='),'code_challenge_method':'S256'}
    if provider=='google':params.update(access_type='offline',prompt='consent')
    db.commit();return {'authorization_url':s['authorization']+'?'+urlencode(params)}

@router.get('/{provider}/callback')
def callback(provider:str,request:Request,state:str=Query(...,max_length=200),code:str=Query('',max_length=8000),error:str=Query('',max_length=200),db=Depends(get_db)):
    item=db.scalar(select(OAuthState).where(OAuthState.digest==digest(state),OAuthState.provider==provider,OAuthState.used==False))
    if not item or item.expires_at<now():raise HTTPException(400,'OAuth state is invalid or expired. Start a new connection.')
    user=db.get(User,item.user_id);member=db.scalar(select(Membership).where(Membership.user_id==item.user_id,Membership.company_id==item.company_id))
    if not user or not user.active or not member or not allowed(member,'integrations.connections.manage'):raise HTTPException(403,'Connection permission is no longer available.')
    updated=db.execute(update(OAuthState).where(OAuthState.id==item.id,OAuthState.used==False).values(used=True))
    if updated.rowcount!=1:raise HTTPException(409,'OAuth response was already processed.')
    db.commit()
    if error or not code:return RedirectResponse(FRONTEND_URL+'/integrations?error=Authorization%20was%20not%20completed',303)
    s=settings(provider)
    if provider=='shopify':
        state_data=decrypt(item.verifier);shop=shopify.normalize_shop(request.query_params.get('shop',''))
        if shop!=state_data['shop'] or not shopify.valid_callback(dict(request.query_params),s['client_secret']):raise HTTPException(400,'Shopify callback signature or store domain is invalid.')
        tokens=shopify.exchange(shop,code,s['client_id'],s['client_secret'])
    else:tokens=request_json('POST',s['token'],data={'grant_type':'authorization_code','code':code,'redirect_uri':s['redirect_uri'],'client_id':s['client_id'],'client_secret':s['client_secret'],'code_verifier':decrypt(item.verifier)})
    if not tokens.get('access_token'):raise HTTPException(502,'Provider did not return an access token.')
    tokens['expires_at']=time.time()+int(tokens.get('expires_in',3600))
    row=get_connection(db,provider,(user,member));row.encrypted_tokens=encrypt(tokens);row.scopes=tokens.get('scope',s['scope']).replace(',',' ').split();row.status='Authorized';row.error=''
    if provider=='shopify':
        row.encrypted_config=encrypt({'shop':shop});identity=shopify.identity(row);row.account_id=identity['id'];row.account_name=identity['name']+' ('+identity['myshopifyDomain']+')'
    event(db,(user,member),'integration.authorized','integrations',row);notify(db,(user,member),row,'connected','Authorization was verified. Run the first synchronization to import records.');db.commit()
    return RedirectResponse(FRONTEND_URL+'/integrations?connected='+provider,303)

def contacts(row):
    tokens=decrypt(row.encrypted_tokens);s=settings(row.provider)
    if tokens.get('expires_at',0)<time.time()+60:
        if not tokens.get('refresh_token'):raise HTTPException(409,'Connection expired. Reconnect this account.')
        new=request_json('POST',s['token'],data={'grant_type':'refresh_token','refresh_token':tokens['refresh_token'],'client_id':s['client_id'],'client_secret':s['client_secret']})
        tokens.update(new);tokens['expires_at']=time.time()+int(new.get('expires_in',3600));row.encrypted_tokens=encrypt(tokens)
    headers={'Authorization':'Bearer '+tokens['access_token']};output=[]
    if row.provider=='google':
        page=None
        for _ in range(50):
            params={'personFields':'names,emailAddresses,organizations','pageSize':1000}
            if page:params['pageToken']=page
            response=request_json('GET','https://people.googleapis.com/v1/people/me/connections',headers=headers,params=params)
            for person in response.get('connections',[]):
                output.append({'external_id':person['resourceName'],'name':(person.get('names') or [{}])[0].get('displayName','Unnamed contact'),'email':(person.get('emailAddresses') or [{}])[0].get('value',''),'organization':(person.get('organizations') or [{}])[0].get('name','')})
            page=response.get('nextPageToken')
            if not page:return output
        raise HTTPException(413,'Contact import exceeds the 50,000-contact sync limit.')
    url='https://graph.microsoft.com/v1.0/me/contacts?$top=100&$select=id,displayName,emailAddresses,companyName'
    for _ in range(100):
        parsed=urlparse(url)
        if parsed.scheme!='https' or parsed.netloc!='graph.microsoft.com':raise HTTPException(502,'Provider pagination URL was rejected.')
        response=request_json('GET',url,headers=headers)
        for person in response.get('value',[]):output.append({'external_id':person['id'],'name':person.get('displayName') or 'Unnamed contact','email':(person.get('emailAddresses') or [{}])[0].get('address',''),'organization':person.get('companyName') or ''})
        url=response.get('@odata.nextLink')
        if not url:return output
    raise HTTPException(413,'Contact import exceeds the 10,000-contact sync limit.')

def import_rows(db,connection,kind,rows,context):
    if kind not in CATALOG:raise HTTPException(404,'Resource not supported.')
    p=CATALOG[kind]['resource']
    if not allowed(context[1],p+'.create') or not allowed(context[1],p+'.edit'):raise HTTPException(403,'Create and edit permissions are required for this import.')
    processed=0
    for item in rows:
        source=dict(item);external_id=source.pop('external_id',None) or hashlib.sha256(json.dumps(source,sort_keys=True).encode()).hexdigest();checksum=hashlib.sha256(json.dumps(source,sort_keys=True,default=str).encode()).hexdigest()
        try:data=SCHEMAS[kind].model_validate(source).model_dump(mode='json')
        except ValidationError:raise HTTPException(422,f'Invalid data in import row {processed+1}. Check column types and required fields.')
        mapping=db.scalar(select(ExternalRecord).where(ExternalRecord.company_id==context[1].company_id,ExternalRecord.integration_id==connection.id,ExternalRecord.kind==kind,ExternalRecord.external_id==external_id))
        if mapping and mapping.checksum==checksum and not mapping.deleted:processed+=1;continue
        row=record(db,MODELS[kind],context[1].company_id,mapping.record_id) if mapping else None
        relations(db,data,context[1].company_id)
        if row and kind in ('stock_movements','payments','transactions'):
            processed+=1;continue
        validate(db,kind,data,context,row)
        if row:
            for key,value in data.items():setattr(row,key,value)
        else:
            enforce_records(db,context);row=MODELS[kind](company_id=context[1].company_id,**data);db.add(row);db.flush();mapping=ExternalRecord(company_id=context[1].company_id,integration_id=connection.id,kind=kind,external_id=external_id,record_id=row.id);db.add(mapping)
        mapping.checksum=checksum;mapping.deleted=False
        after_write(db,kind,row,context);event(db,context,'integration.imported',kind,row);db.flush();processed+=1
    return processed

@router.post('/{provider}/sync')
def sync(provider:str,request:Request,context=Depends(require('integrations.connections.manage')),db=Depends(get_db)):
    limit(request,'sync',5);settings(provider)
    row=get_connection(db,provider,context)
    if not row.encrypted_tokens:raise HTTPException(409,'Authorize this account before syncing.')
    return perform_sync(provider,row,context,db,'manual')

def perform_sync(provider,row,context,db,trigger='manual'):
    log=SyncLog(company_id=context[1].company_id,integration_id=row.id,status='Running',trigger=trigger);db.add(log);row.status='Syncing';row.last_attempt=now();db.commit()
    try:
        counts={}
        if provider=='shopify':
            for kind,records in shopify.records(db,row):counts[kind]=import_rows(db,row,kind,records,context)
        else:counts['customers']=import_rows(db,row,'customers',contacts(row),context)
        count=sum(counts.values());row.status='Synced';row.last_sync=now();row.next_sync=now()+timedelta(hours=1);row.imported_counts={**(row.imported_counts or {}),**counts};row.error='';log.status='Completed';log.processed=count;log.counts=counts;log.finished_at=now();event(db,context,'integration.synced','integrations',row);notify(db,context,row,'sync completed',f'Imported or verified {count} records.');db.commit()
    except HTTPException as exc:
        db.rollback();row=db.get(Integration,row.id);log=db.get(SyncLog,log.id);row.status='Needs attention';row.error=exc.detail;log.status='Failed';log.error=exc.detail;log.finished_at=now();notify(db,context,row,'sync failed',exc.detail);db.commit();raise
    return {'connection':public(row),'processed':count}

def integration_tick():
    from .database import SessionLocal
    with SessionLocal() as db:
        due=list(db.scalars(select(Integration).where(Integration.next_sync!=None,Integration.next_sync<=now(),Integration.status=='Synced')))
        for row in due:
            member=db.scalar(select(Membership).where(Membership.company_id==row.company_id,Membership.role.in_(['owner','admin'])).order_by(Membership.id))
            user=db.get(User,member.user_id) if member else None
            if not user:continue
            try:perform_sync(row.provider,row,(user,member),db,'scheduled')
            except HTTPException:pass

@router.delete('/{provider}')
def disconnect(provider:str,context=Depends(require('integrations.connections.manage')),db=Depends(get_db)):
    row=get_connection(db,provider,context);row.encrypted_tokens='';row.encrypted_config='';row.status='Disconnected';row.scopes=[];row.account_id='';row.account_name='';event(db,context,'integration.disconnected','integrations',row);notify(db,context,row,'disconnected','Stored credentials were removed. Imported records were preserved.');db.commit()
    return {'message':'Local tokens removed. Imported records are preserved. You can also revoke consent in the provider account settings.'}

@router.post('/shopify/webhook')
async def shopify_webhook(request:Request,db=Depends(get_db)):
    raw=await request.body();signature=request.headers.get('X-Shopify-Hmac-Sha256','');shop=shopify.normalize_shop(request.headers.get('X-Shopify-Shop-Domain',''));delivery_id=request.headers.get('X-Shopify-Webhook-Id','')
    if not delivery_id:raise HTTPException(400,'Missing Shopify webhook delivery ID.')
    connection=None
    for candidate in db.scalars(select(Integration).where(Integration.provider=='shopify',Integration.status!='Disconnected')):
        try:
            if decrypt(candidate.encrypted_config).get('shop')==shop:connection=candidate;break
        except HTTPException:continue
    if not connection or not shopify.verify_webhook(raw,signature,os.getenv('SHOPIFY_CLIENT_SECRET','')):raise HTTPException(401,'Invalid Shopify webhook signature.')
    existing=db.scalar(select(WebhookDelivery).where(WebhookDelivery.provider=='shopify',WebhookDelivery.delivery_id==delivery_id))
    if existing:return {'accepted':True,'duplicate':True}
    try:payload=json.loads(raw)
    except ValueError:raise HTTPException(422,'Webhook payload is not valid JSON.')
    db.add(WebhookDelivery(company_id=connection.company_id,integration_id=connection.id,provider='shopify',delivery_id=delivery_id,topic=request.headers.get('X-Shopify-Topic',''),payload=payload,status='Received'));db.commit()
    return {'accepted':True,'duplicate':False}

@router.get('/csv/template/{kind}')
def template(kind:str,context=Depends(require('integrations.connections.manage'))):
    if kind not in CATALOG or not allowed(context[1],CATALOG[kind]['resource']+'.create'):raise HTTPException(403,'Resource not available.')
    buffer=io.StringIO();csv.writer(buffer).writerow(['external_id']+[f['name'] for f in CATALOG[kind]['fields']]);return Response(buffer.getvalue(),media_type='text/csv')

@router.post('/csv/import/{kind}')
async def import_csv(kind:str,file:UploadFile=File(...),context=Depends(require('integrations.connections.manage')),db=Depends(get_db)):
    raw=await file.read(2*1024*1024+1)
    if len(raw)>2*1024*1024:raise HTTPException(413,'CSV files must be 2 MB or smaller.')
    try:
        reader=csv.DictReader(io.StringIO(raw.decode('utf-8-sig')));rows=[{k:v for k,v in r.items() if v not in ('',None)} for r in reader]
        if len(rows)>1000:raise HTTPException(413,'Import at most 1,000 rows at a time.')
        if not rows:raise HTTPException(422,'The file contains no records.')
    except (UnicodeError,csv.Error):raise HTTPException(422,'Upload a valid UTF-8 CSV file.')
    connection=get_connection(db,'csv',context);log=SyncLog(company_id=context[1].company_id,integration_id=connection.id,status='Running');db.add(log);db.commit()
    try:
        count=import_rows(db,connection,kind,rows,context);log.status='Completed';log.processed=count;connection.status='Synced';connection.last_sync=now();db.commit()
    except HTTPException as exc:
        db.rollback();log=db.get(SyncLog,log.id);log.status='Failed';log.error=exc.detail;db.commit();raise
    return {'processed':count,'message':f'Imported {count} records.'}
