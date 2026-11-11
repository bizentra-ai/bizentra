import os,re,hmac,hashlib,base64,json,time
from urllib.parse import urlencode
from fastapi import HTTPException
from sqlalchemy import select
from .integration_engine import request_json,decrypt,encrypt
from .control_models import ExternalRecord

API_VERSION=os.getenv('SHOPIFY_API_VERSION','2026-10')
SCOPES='read_customers,read_products,read_inventory,read_orders'
SHOP=re.compile(r'^[a-z0-9][a-z0-9-]*\.myshopify\.com$')

def normalize_shop(value):
    shop=value.strip().lower()
    if not SHOP.fullmatch(shop):raise HTTPException(422,'Enter the permanent store domain, for example your-store.myshopify.com.')
    return shop
def authorize_url(shop,state,client_id,redirect_uri):
    return 'https://'+normalize_shop(shop)+'/admin/oauth/authorize?'+urlencode({'client_id':client_id,'scope':SCOPES,'redirect_uri':redirect_uri,'state':state})
def valid_callback(params,secret):
    supplied=params.get('hmac','');message='&'.join(f'{k}={v}' for k,v in sorted(params.items()) if k not in ('hmac','signature'))
    return bool(supplied) and hmac.compare_digest(supplied,hmac.new(secret.encode(),message.encode(),hashlib.sha256).hexdigest())
def exchange(shop,code,client_id,secret):
    return request_json('POST',f'https://{normalize_shop(shop)}/admin/oauth/access_token',allowed_hosts={shop},json={'client_id':client_id,'client_secret':secret,'code':code,'expiring':1})
def graphql(row,query,variables=None):
    config=decrypt(row.encrypted_config);tokens=decrypt(row.encrypted_tokens);shop=normalize_shop(config['shop'])
    if tokens.get('expires_at') and tokens['expires_at']<time.time()+60:
        if not tokens.get('refresh_token'):raise HTTPException(409,'Shopify authorization expired. Reconnect the store.')
        tokens=request_json('POST',f'https://{shop}/admin/oauth/access_token',allowed_hosts={shop},json={'grant_type':'refresh_token','refresh_token':tokens['refresh_token'],'client_id':os.getenv('SHOPIFY_CLIENT_ID',''),'client_secret':os.getenv('SHOPIFY_CLIENT_SECRET','')})
        tokens['expires_at']=time.time()+int(tokens.get('expires_in',3600));row.encrypted_tokens=encrypt(tokens)
    result=request_json('POST',f'https://{shop}/admin/api/{API_VERSION}/graphql.json',allowed_hosts={shop},headers={'X-Shopify-Access-Token':tokens['access_token'],'Content-Type':'application/json'},json={'query':query,'variables':variables or {}})
    if result.get('errors'):raise HTTPException(502,'Shopify rejected the GraphQL request: '+str(result['errors'][0].get('message','unknown error'))[:240])
    return result.get('data') or {}
def identity(row):return graphql(row,'query { shop { id name myshopifyDomain currencyCode } }')['shop']

CUSTOMERS='''query($after:String){customers(first:100,after:$after,sortKey:UPDATED_AT){nodes{id displayName email defaultAddress{company} updatedAt}pageInfo{hasNextPage endCursor}}}'''
PRODUCTS='''query($after:String){products(first:100,after:$after,sortKey:UPDATED_AT){nodes{id title status updatedAt variants(first:1){nodes{sku price inventoryQuantity}}}pageInfo{hasNextPage endCursor}}}'''
ORDERS='''query($after:String){orders(first:100,after:$after,sortKey:UPDATED_AT){nodes{id name createdAt updatedAt cancelledAt displayFulfillmentStatus customer{id} totalPriceSet{shopMoney{amount currencyCode}}}pageInfo{hasNextPage endCursor}}}'''

def pages(row,root,query):
    after=None
    for _ in range(100):
        block=graphql(row,query,{'after':after})[root]
        for node in block['nodes']:yield node
        if not block['pageInfo']['hasNextPage']:return
        after=block['pageInfo']['endCursor']
    raise HTTPException(413,'Shopify sync exceeded 10,000 records for one object type. Use a narrower initial migration process.')
def cents(value):
    try:return int(round(float(value)*100))
    except (TypeError,ValueError):return 0
def mapped(db,row,kind,external_id):
    link=db.scalar(select(ExternalRecord).where(ExternalRecord.company_id==row.company_id,ExternalRecord.integration_id==row.id,ExternalRecord.kind==kind,ExternalRecord.external_id==external_id))
    return link.record_id if link else None
def records(db,row):
    customers=[]
    for n in pages(row,'customers',CUSTOMERS):customers.append({'external_id':n['id'],'name':n.get('displayName') or 'Unnamed Shopify customer','email':n.get('email') or '','organization':(n.get('defaultAddress') or {}).get('company') or '','notes':'Source: Shopify · Updated: '+n.get('updatedAt','')})
    yield 'customers',customers
    products=[]
    for n in pages(row,'products',PRODUCTS):
        v=((n.get('variants') or {}).get('nodes') or [{}])[0];products.append({'external_id':n['id'],'name':n['title'],'status':'Archived' if n.get('status')=='ARCHIVED' else 'Active','sku':v.get('sku') or '','price_cents':cents(v.get('price')),'stock':v.get('inventoryQuantity') or 0,'threshold':0,'supplier_id':None,'notes':'Source: Shopify · Updated: '+n.get('updatedAt','')})
    yield 'products',products
    orders=[]
    for n in pages(row,'orders',ORDERS):
        customer=(n.get('customer') or {}).get('id');customer_id=mapped(db,row,'customers',customer) if customer else None
        if not customer_id:continue
        status='Cancelled' if n.get('cancelledAt') else ('Fulfilled' if n.get('displayFulfillmentStatus')=='FULFILLED' else 'Confirmed')
        money=(n.get('totalPriceSet') or {}).get('shopMoney') or {}
        orders.append({'external_id':n['id'],'name':n['name'],'status':status,'customer_id':customer_id,'order_date':n['createdAt'][:10],'due_date':None,'notes':f"Source: Shopify · Total: {money.get('amount','')} {money.get('currencyCode','')} · Updated: {n.get('updatedAt','')}"})
    yield 'orders',orders

def verify_webhook(raw,signature,secret):
    expected=base64.b64encode(hmac.new(secret.encode(),raw,hashlib.sha256).digest()).decode()
    return bool(signature) and hmac.compare_digest(signature,expected)
