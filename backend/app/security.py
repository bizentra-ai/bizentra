import hashlib
from datetime import timedelta
from collections import defaultdict, deque
from time import monotonic
from threading import Lock
import jwt
from argon2 import PasswordHasher
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from .config import SECRET_KEY
from .database import get_db
from .models import User, Membership, now

hasher = PasswordHasher()
bearer = HTTPBearer(auto_error=False)
from .catalog import CATALOG
RESOURCES = [d['resource'] for d in CATALOG.values()]
ROLE_PERMISSIONS = {
    'owner': {'*'}, 'admin': {'*'},
    'manager': {f'{r}.{a}' for r in RESOURCES for a in (['view','export'] if r.startswith('finance.') else ['view','create','edit','delete','export'])},
    'employee': {'crm.customers.view','projects.projects.view','projects.tasks.view','projects.tasks.create','projects.tasks.edit'},
    'viewer': {f'{r}.view' for r in RESOURCES},
}

def digest(value):
    return hashlib.sha256((SECRET_KEY + value).encode()).hexdigest()

def token(user):
    return jwt.encode({'sub':str(user.id),'ver':user.token_version,'exp':now()+timedelta(hours=2),'iat':now(),'iss':'businessos','aud':'businessos'}, SECRET_KEY, algorithm='HS256')

def current(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), db=Depends(get_db)):
    try:
        if not credentials:
            raise ValueError()
        claims = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=['HS256'], audience='businessos', issuer='businessos', options={'require':['exp','sub','ver']})
        user = db.get(User, int(claims['sub']))
        if not user or not user.active or not user.verified or user.token_version != claims['ver']:
            raise ValueError()
        membership = db.scalar(select(Membership).where(Membership.user_id == user.id).order_by(Membership.id))
        if not membership:
            raise ValueError()
        return user, membership
    except (jwt.PyJWTError, ValueError, KeyError, TypeError):
        raise HTTPException(401, 'Please sign in again.')

def permissions(membership):
    return ROLE_PERMISSIONS.get(membership.role, set()) | set(membership.permissions)

def allowed(membership, permission):
    grants = permissions(membership)
    return '*' in grants or permission in grants

def require(permission):
    def check(context=Depends(current)):
        if not allowed(context[1], permission):
            raise HTTPException(403, 'Your role does not allow this action.')
        return context
    return check

_buckets = defaultdict(deque)
_lock = Lock()
def limit(request: Request, category='auth', maximum=12):
    key = (request.client.host if request.client else 'local', category)
    moment = monotonic()
    with _lock:
        for stale in [k for k,v in _buckets.items() if not v or v[-1] < moment-60]:
            del _buckets[stale]
        bucket = _buckets[key]
        while bucket and bucket[0] < moment-60:
            bucket.popleft()
        if len(bucket) >= maximum:
            raise HTTPException(429, 'Too many attempts. Try again in a minute.')
        bucket.append(moment)
