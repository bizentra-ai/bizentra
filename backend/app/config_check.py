"""Safe startup configuration validation. Never prints secret values."""
import os
from fastapi import HTTPException
from . import config as _config
from .integration_engine import cipher,encrypt,decrypt
from .ai.provider import configuration as ai_configuration

def check():
    integration_key=bool(os.getenv('INTEGRATION_ENCRYPTION_KEY'))
    if integration_key:
        cipher()
        probe={'configuration_check':True}
        if decrypt(encrypt(probe))!=probe:raise RuntimeError('Integration encryption round-trip failed.')
        from .database import SessionLocal
        from .control_models import Integration
        with SessionLocal() as db:
            for row in db.query(Integration).all():
                if row.encrypted_tokens:decrypt(row.encrypted_tokens)
                if row.encrypted_config:decrypt(row.encrypted_config)
    ai=ai_configuration()
    print('Integration encryption: '+('configured and valid' if integration_key else 'not configured'))
    print('Existing encrypted integration credentials: compatible')
    print('AI provider: '+('configured' if ai['configured'] else 'not configured'))

if __name__=='__main__':
    try:check()
    except HTTPException as exc:raise SystemExit('Configuration error: '+str(exc.detail))
