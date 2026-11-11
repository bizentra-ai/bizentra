import logging,asyncio,os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from .config import FRONTEND_URL
from .auth import router as auth
from .records import router as records
from .workspace import router as workspace

@asynccontextmanager
async def lifespan(app):
    async def loop():
        from .automation import tick
        from .integrations import integration_tick
        while True:
            await asyncio.sleep(60)
            try:
                await asyncio.to_thread(tick)
                await asyncio.to_thread(integration_tick)
            except Exception:logging.getLogger('businessos').error('Automation cycle failed; inspect application state.')
    task=asyncio.create_task(loop()) if os.getenv('BACKGROUND_AUTOMATIONS','true')=='true' else None
    yield
    if task:
        task.cancel()
        try:await task
        except asyncio.CancelledError:pass

app=FastAPI(title='BusinessOS API', version='0.2.0',lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=[FRONTEND_URL],allow_credentials=False,allow_methods=['GET','POST','PUT','DELETE'],allow_headers=['Authorization','Content-Type'])
app.include_router(auth)
app.include_router(records)
app.include_router(workspace)
from .finance import router as finance
from .metadata import router as metadata
app.include_router(finance)
app.include_router(metadata)
from .crm import router as crm
app.include_router(crm)
from .department_metrics import router as department_metrics
app.include_router(department_metrics)
from .operations import router as operations
from .brain import router as brain
app.include_router(operations)
app.include_router(brain)
from .ai.service import router as ai
from .predictions import router as predictions
from .integrations import router as integrations
from .domains import router as domains
from .billing import router as billing
from .automation import router as automation
from .marketplace import router as marketplace
from .documents import router as documents
from .notifications import router as notifications
for router in [ai,predictions,integrations,domains,billing,automation,marketplace,documents,notifications]:app.include_router(router)

@app.middleware('http')
async def headers(request: Request,call_next):
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Cache-Control']='no-store'
    response.headers['Referrer-Policy']='same-origin'
    return response

@app.exception_handler(Exception)
async def unexpected(request: Request,exc):
    logging.getLogger('businessos').error('Request failed: %s %s (%s)',request.method,request.url.path,type(exc).__name__)
    return JSONResponse(status_code=500,content={'detail':'Something went wrong. Please try again.'})

@app.get('/api/health')
def health():
    return {'status':'ok'}

