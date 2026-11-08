import json
import os
from functools import lru_cache

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from .engine import Dataset, ROOT

app = FastAPI(title='NightShift AI', version='0.1.0')
app.add_middleware(CORSMiddleware, allow_origins=['http://localhost:3000', 'http://127.0.0.1:3000'], allow_methods=['GET', 'POST'], allow_headers=['Content-Type'])


@lru_cache(maxsize=2)
def load(name):
    try:
        return Dataset(name)
    except (ValueError, OSError, KeyError) as e:
        raise HTTPException(400, f'Invalid dataset: {e}') from e


@app.get('/api/health')
def health():
    return {'status':'ok', 'nemotron_configured':bool(os.getenv('NVIDIA_API_KEY'))}


@app.get('/api/datasets')
def datasets():
    return [str(p.parent.relative_to(ROOT)).replace('\\','/') for p in sorted(ROOT.rglob('network.json')) if (p.parent/'ops.json').exists() and (p.parent/'telemetry.csv').exists()]


@app.get('/api/dashboard')
def dashboard(dataset: str = 'history/snapshot_2026-10-09T0330', at: int | None = None):
    return load(dataset).analyze(at)


@app.get('/api/trend')
def trend(dataset: str, asset: str, metric: str, at: int | None = None):
    data = load(dataset)
    return [{'ts':t,'value':v} for t,v in data.values(asset, metric, at or data.end)[-288:]]


@app.get('/api/events')
def events(dataset: str, at: int | None = None):
    result = load(dataset).analyze(at)
    return {'events':[dict(a, event_id=f'{a["facility_id"]}-{a["category"]}-{a["onset_unix"]}', status='ongoing', recommended_actions=a['recommendation']['actions']) for a in result['alerts']]}


class Investigation(BaseModel):
    dataset: str
    facility_id: str
    at: int | None = None
    question: str = Field(default='Explain the evidence, verified plan, and tradeoffs for this facility.', max_length=2000)


@app.post('/api/investigate')
async def investigate(request: Investigation):
    key = os.getenv('NVIDIA_API_KEY')
    if not key:
        raise HTTPException(503, 'Set NVIDIA_API_KEY on the backend to enable live Nemotron tool execution.')
    data = load(request.dataset).analyze(request.at)
    facility = next((f for f in data['facilities'] if f['id']==request.facility_id), None)
    if facility is None:
        raise HTTPException(404, 'Unknown facility')
    alert = next((a for a in data['alerts'] if a['facility_id']==request.facility_id), None)
    tools = [{'type':'function', 'function':{'name':name,'description':description,'parameters':{'type':'object','properties':{},'additionalProperties':False}}} for name,description in [('inspect_telemetry','Read the selected facility and sensor evidence.'),('get_verified_plan','Read the jointly allocated deterministic response plan and alternatives.'),('verify_plan','Check simulation result and planning limitations.')]]
    messages = [{'role':'system','content':'You are NightShift, an oilfield investigation assistant. Use all three tools before explaining a plan. Only cite numbers returned by tools. Actions are simulations requiring operator review. State optimization limitations and never claim global optimality.'}, {'role':'user','content':request.question}]
    executed = []
    try:
        async with httpx.AsyncClient(timeout=90) as client:
            for _ in range(6):
                response = await client.post('https://integrate.api.nvidia.com/v1/chat/completions', headers={'Authorization':f'Bearer {key}'}, json={'model':os.getenv('NVIDIA_MODEL','nvidia/llama-3.3-nemotron-super-49b-v1.5'), 'messages':messages, 'tools':tools, 'temperature':.1, 'max_tokens':1600})
                response.raise_for_status()
                msg = response.json()['choices'][0]['message']
                messages.append(msg)
                if not msg.get('tool_calls'):
                    if not all(n in executed for n in ['inspect_telemetry','get_verified_plan','verify_plan']):
                        messages.append({'role':'user','content':'Call all three required tools before your final explanation.'})
                        continue
                    return {'answer':msg.get('content',''), 'tools_executed':executed, 'model':os.getenv('NVIDIA_MODEL','nvidia/llama-3.3-nemotron-super-49b-v1.5')}
                for call in msg['tool_calls']:
                    name = call['function']['name']
                    if name == 'inspect_telemetry':
                        result = {'facility':facility,'evidence':alert['evidence'] if alert else [],'now':data['now']}
                    elif name == 'get_verified_plan':
                        result = alert['recommendation'] if alert else {'status':'No detected incident'}
                    elif name == 'verify_plan':
                        result = {'verified':alert['recommendation'].get('verified',False) if alert else False, 'scope':data['planning_scope']}
                    else:
                        result = {'error':'Unknown tool'}
                    executed.append(name)
                    messages.append({'role':'tool','tool_call_id':call['id'],'content':json.dumps(result)})
        raise HTTPException(502, 'Nemotron did not complete the required investigation within six steps.')
    except httpx.HTTPError as e:
        raise HTTPException(502, 'NVIDIA request failed. Check server credentials, model availability, and connectivity.') from e
