import secrets
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from .database import get_db
from .models import Company, User, Membership, Challenge, Invitation, now
from .schemas import Register, Login, Verify, Email, Reset, Accept
from .security import hasher, token, digest, current, limit
from .mail import deliver

router = APIRouter(prefix='/api/auth', tags=['Authentication'])

def challenge(db, user, purpose):
    for old in db.scalars(select(Challenge).where(Challenge.user_id == user.id, Challenge.purpose == purpose, Challenge.used == False)):
        old.used = True
    code = f'{secrets.randbelow(1000000):06}'
    db.add(Challenge(user_id=user.id, purpose=purpose, digest=digest(code), expires_at=now()+timedelta(minutes=10)))
    sent = deliver(user.email, 'Your BusinessOS verification code', f'Your code is {code}. It expires in 10 minutes.')
    db.commit()
    return {'message':'Check your email for a verification code.' if sent else 'Development mode: use the code below.', **({} if sent else {'development_code': code})}

def consume(db, email, code, purpose):
    user = db.scalar(select(User).where(User.email == str(email).lower()))
    item = db.scalar(select(Challenge).where(Challenge.user_id == (user.id if user else -1), Challenge.purpose == purpose, Challenge.used == False).order_by(Challenge.id.desc()))
    if not item or item.expires_at < now() or item.attempts >= 5:
        raise HTTPException(400, 'Invalid or expired code.')
    item.attempts += 1
    if not secrets.compare_digest(item.digest, digest(code)):
        db.commit()
        raise HTTPException(400, 'Invalid or expired code.')
    item.used = True
    return user

@router.post('/register', status_code=201)
def register(body: Register, request: Request, db=Depends(get_db)):
    limit(request, 'register', 5)
    if db.scalar(select(User).where(User.email == str(body.email).lower())):
        raise HTTPException(409, 'An account already uses this email. Sign in or reset your password.')
    company = Company(name=body.business_name, industry=body.industry, country=body.country, size=body.size)
    user = User(email=str(body.email).lower(), name=body.name, password_hash=hasher.hash(body.password))
    db.add_all([company,user])
    try:
        db.flush()
        db.add(Membership(user_id=user.id, company_id=company.id, role='owner'))
        return challenge(db, user, 'verify')
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'This account could not be created. Try signing in.')

@router.post('/login')
def login(body: Login, request: Request, db=Depends(get_db)):
    limit(request)
    user = db.scalar(select(User).where(User.email == str(body.email).lower()))
    try:
        if not user or not user.active:
            # Spend hashing time for unknown accounts too.
            hasher.hash(body.password)
            raise ValueError()
        hasher.verify(user.password_hash, body.password)
    except Exception:
        raise HTTPException(401, 'Email or password is incorrect.')
    if not user.verified:
        raise HTTPException(403, 'Verify your email before signing in.')
    return {'access_token':token(user), 'token_type':'bearer'}

@router.post('/verify-otp')
def verify(body: Verify, request: Request, db=Depends(get_db)):
    limit(request)
    user = consume(db, body.email, body.code, 'verify')
    user.verified = True
    db.commit()
    return {'access_token':token(user), 'token_type':'bearer'}

@router.post('/resend-otp')
def resend(body: Email, request: Request, db=Depends(get_db)):
    limit(request, 'email', 3)
    user = db.scalar(select(User).where(User.email == str(body.email).lower(), User.verified == False))
    return challenge(db, user, 'verify') if user else {'message':'If an unverified account exists, a code has been sent.'}

@router.post('/forgot-password')
def forgot(body: Email, request: Request, db=Depends(get_db)):
    limit(request, 'email', 3)
    user = db.scalar(select(User).where(User.email == str(body.email).lower()))
    result = challenge(db, user, 'reset') if user else {}
    return {**result, 'message':'If an account exists, a recovery code has been sent.'}

@router.post('/reset-password')
def reset(body: Reset, request: Request, db=Depends(get_db)):
    limit(request)
    user = consume(db, body.email, body.code, 'reset')
    user.password_hash = hasher.hash(body.password)
    user.token_version += 1
    db.commit()
    return {'message':'Password changed. Sign in with your new password.'}

@router.post('/logout')
def logout(context=Depends(current), db=Depends(get_db)):
    context[0].token_version += 1
    db.commit()
    return {'message':'Signed out.'}

@router.post('/accept-invitation')
def accept(body: Accept, request: Request, db=Depends(get_db)):
    limit(request)
    invitation = db.scalar(select(Invitation).where(Invitation.digest == digest(body.token), Invitation.used == False))
    if not invitation or invitation.expires_at < now():
        raise HTTPException(400, 'Invitation is invalid or expired.')
    if db.scalar(select(User).where(User.email == invitation.email)):
        raise HTTPException(409, 'This email already has an account. Multi-workspace acceptance is not yet available.')
    user = User(email=invitation.email, name=body.name, password_hash=hasher.hash(body.password), verified=True)
    db.add(user)
    db.flush()
    db.add(Membership(user_id=user.id, company_id=invitation.company_id, role=invitation.role))
    invitation.used = True
    db.commit()
    return {'access_token':token(user), 'token_type':'bearer'}
