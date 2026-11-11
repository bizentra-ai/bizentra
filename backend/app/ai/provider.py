import os,json
from urllib.parse import urlparse
import httpx
from fastapi import HTTPException

def configuration():
    key=os.getenv('AI_API_KEY') or os.getenv('OPENAI_API_KEY')
    model=os.getenv('AI_MODEL','').strip();protocol=os.getenv('AI_PROTOCOL','responses').strip()
    base=os.getenv('AI_BASE_URL','https://api.openai.com/v1').strip().rstrip('/')
    parsed=urlparse(base);local=parsed.hostname in ('localhost','127.0.0.1','::1')
    errors=[]
    if not key:errors.append('AI_API_KEY is missing.')
    if not model:errors.append('AI_MODEL is missing.')
    if protocol not in ('responses','chat_completions'):errors.append('AI_PROTOCOL must be responses or chat_completions.')
    if not parsed.hostname or parsed.scheme not in (('http','https') if local else ('https',)):errors.append('AI_BASE_URL must use HTTPS, except for localhost development.')
    return {'configured':not errors,'model':model,'protocol':protocol,'required':errors}

def generate(messages,tools):
    settings=configuration()
    if not settings['configured']:raise HTTPException(503,'AI provider is not configured: '+' '.join(settings['required']))
    base=os.getenv('AI_BASE_URL','https://api.openai.com/v1').rstrip('/')
    key=os.getenv('AI_API_KEY') or os.getenv('OPENAI_API_KEY')
    protocol=settings['protocol']
    if protocol=='responses':
        payload={'model':settings['model'],'input':messages,'tools':tools,'store':False,'max_output_tokens':2500}
        endpoint=base+'/responses'
    elif protocol=='chat_completions':
        payload={'model':settings['model'],'messages':messages,'tools':[{'type':'function','function':{k:v for k,v in t.items() if k!='type'}} for t in tools]}
        endpoint=base+'/chat/completions'
    else:raise HTTPException(503,'Unsupported AI_PROTOCOL. Choose responses or chat_completions.')
    try:
        with httpx.Client(timeout=75,follow_redirects=False) as client:
            response=client.post(endpoint,headers={'Authorization':'Bearer '+key},json=payload)
        if response.status_code>=400:raise HTTPException(502,f'AI provider returned HTTP {response.status_code}. Check the backend provider configuration and account quota.')
        result=response.json();text=[];calls=[]
        if protocol=='responses':
            for item in result.get('output',[]):
                if item.get('type')=='message':text.extend(c['text'] for c in item.get('content',[]) if c.get('type')=='output_text')
                if item.get('type')=='function_call':calls.append({'name':item['name'],'arguments':json.loads(item['arguments'])})
        else:
            message=result['choices'][0]['message'];text=[message.get('content') or '']
            calls=[{'name':t['function']['name'],'arguments':json.loads(t['function']['arguments'])} for t in message.get('tool_calls',[])]
        if not ''.join(text).strip() and not calls:raise ValueError()
        usage=result.get('usage') or {}
        return {'text':'\n'.join(text),'calls':calls[:5],'usage':{'input_tokens':int(usage.get('input_tokens',usage.get('prompt_tokens',0)) or 0),'output_tokens':int(usage.get('output_tokens',usage.get('completion_tokens',0)) or 0)}}
    except httpx.HTTPError:raise HTTPException(502,'The AI provider could not be reached. No business action was executed.')
    except (ValueError,KeyError,TypeError):raise HTTPException(502,'The AI provider returned an invalid response. No business action was executed.')
