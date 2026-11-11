import os,json,time,random
from urllib.parse import urlparse
import httpx
from cryptography.fernet import Fernet,InvalidToken
from fastapi import HTTPException

PROVIDERS={}
def register(key,**definition):PROVIDERS[key]={'id':key,**definition}

def cipher():
    key=os.getenv('INTEGRATION_ENCRYPTION_KEY','')
    if not key:raise HTTPException(503,'Set INTEGRATION_ENCRYPTION_KEY in the backend environment before connecting accounts.')
    try:return Fernet(key.encode())
    except ValueError:raise HTTPException(503,'INTEGRATION_ENCRYPTION_KEY must be a valid Fernet key.')
def encrypt(value):return cipher().encrypt(json.dumps(value).encode()).decode()
def decrypt(value):
    try:return json.loads(cipher().decrypt(value.encode()))
    except (InvalidToken,ValueError,TypeError):raise HTTPException(503,'Stored credentials cannot be decrypted. Restore the encryption key or reconnect.')

def request_json(method,url,*,attempts=4,allowed_hosts=None,**kwargs):
    parsed=urlparse(url)
    if parsed.scheme!='https' or (allowed_hosts and parsed.hostname not in allowed_hosts):raise HTTPException(502,'Provider URL was rejected.')
    for attempt in range(attempts):
        try:
            with httpx.Client(timeout=35,follow_redirects=False) as client:response=client.request(method,url,**kwargs)
        except httpx.HTTPError:
            if attempt+1==attempts:raise HTTPException(502,'Provider could not be reached after retries.')
            time.sleep(min(.1*(2**attempt)+random.random()*.05,1));continue
        if response.status_code==429 or response.status_code>=500:
            if attempt+1<attempts:
                delay=response.headers.get('Retry-After','')
                try:delay=min(float(delay),2)
                except ValueError:delay=min(.1*(2**attempt)+random.random()*.05,1)
                time.sleep(delay);continue
        if response.status_code in (401,403):raise HTTPException(409,'Provider authorization expired or was revoked. Reconnect the account.')
        if response.status_code>=400:raise HTTPException(502,'Provider returned HTTP '+str(response.status_code)+'.')
        try:return response.json()
        except ValueError:raise HTTPException(502,'Provider returned an invalid response.')
    raise HTTPException(502,'Provider request failed.')

def redact_connection(row,serialize):
    data=serialize(row)
    for key in ('encrypted_tokens','encrypted_config'):data.pop(key,None)
    return data
