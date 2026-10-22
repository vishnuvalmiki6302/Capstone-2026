import os,uuid,asyncio
from fastapi import FastAPI,Request,Response,HTTPException
from fastapi.middleware.cors import CORSMiddleware
import httpx
app=FastAPI(title='SMA.AI API Gateway',version='1.0')
app.add_middleware(CORSMiddleware,allow_origins=os.getenv('CORS_ORIGINS','http://localhost:5173').split(','),allow_credentials=True,allow_methods=['*'],allow_headers=['*'])
UP={'auth':os.getenv('AUTH_URL','http://localhost:8001'),'datasets':os.getenv('DATA_URL','http://localhost:8002'),'analysis':os.getenv('ANALYTICS_URL','http://localhost:8003')}
@app.middleware('http')
async def headers(req:Request,call_next):
 req.state.correlation_id=req.headers.get('X-Correlation-ID',str(uuid.uuid4())); r=await call_next(req);r.headers['X-Correlation-ID']=req.state.correlation_id;return r
@app.get('/health')
async def health():
 async with httpx.AsyncClient(timeout=2) as c:
  async def one(k,u):
   try:return k,(await c.get(u+'/health')).status_code==200
   except:return k,False
  checks=await asyncio.gather(*(one(k,v) for k,v in UP.items()))
 return {'status':'ok' if all(v for _,v in checks) else 'degraded','services':dict(checks)}
async def request(service,path,method='GET',request:Request|None=None,body=None):
 try:
  async with httpx.AsyncClient(timeout=35) as c:
   r=await c.request(method,UP[service]+path,content=await request.body() if request else None,headers={'Content-Type':request.headers.get('content-type','application/json')} if request else None,json=body)
  return Response(content=r.content,status_code=r.status_code,media_type=r.headers.get('content-type','application/json'),headers={'Content-Disposition':r.headers.get('content-disposition','')})
 except httpx.HTTPError:raise HTTPException(503,detail={'error':{'code':'SERVICE_UNAVAILABLE','message':f'{service} service is temporarily unavailable'}})
@app.api_route('/api/auth/{path:path}',methods=['GET','POST','PUT','DELETE'])
async def auth(path:str,request:Request):return await proxy('auth',path,request)
@app.api_route('/api/datasets/{path:path}',methods=['GET','POST','PUT','DELETE'])
async def datasets(path:str,request:Request):return await proxy('datasets',path,request)
@app.api_route('/api/analysis/{path:path}',methods=['GET','POST','PUT','DELETE'])
async def analysis(path:str,request:Request):return await proxy('analysis',path,request)
async def proxy(service,path,req):
 prefix={'auth':'auth/','datasets':'datasets/','analysis':'analysis/'}[service]
 try:
  async with httpx.AsyncClient(timeout=40) as c:r=await c.request(req.method,UP[service]+'/'+prefix+path,params=req.query_params,content=await req.body(),headers={k:v for k,v in req.headers.items() if k.lower() in ('content-type','authorization')})
  return Response(r.content,r.status_code,media_type=r.headers.get('content-type','application/json'),headers={k:v for k,v in r.headers.items() if k.lower() in ('content-disposition',)})
 except httpx.HTTPError:raise HTTPException(503,detail={'error':{'code':'SERVICE_UNAVAILABLE','message':f'{service} service is temporarily unavailable'}})
@app.get('/api/dashboard/{did}')
async def dashboard(did:str):
 try:
  async with httpx.AsyncClient(timeout=40) as c:r=await c.get(UP['analysis']+f'/analysis/{did}/summary');r.raise_for_status();return r.json()
 except httpx.HTTPError:raise HTTPException(503,detail={'error':{'code':'ANALYSIS_UNAVAILABLE','message':'Analysis is not ready yet. Please retry shortly.'}})
