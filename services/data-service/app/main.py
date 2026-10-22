import csv, io, random, re, uuid
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, UploadFile, File, HTTPException
from pydantic import BaseModel

app=FastAPI(title="SMA.AI Data Service",version="1.0")
datasets={}
topics={"Camera":["camera","photo","lens","selfie","zoom"],"Battery":["battery","charge","charging","power"],"Price":["price","cost","expensive","deal"],"Design":["design","color","colour","look"],"Performance":["fast","performance","chip","speed"]}
positive=["Loving the new camera on iPhone 17, photos look incredible","Battery life feels much better this year","The design is clean and premium, really impressed","Performance is fast and smooth so far","Great value and an amazing upgrade"]
negative=["iPhone 17 price is too expensive for this upgrade","Battery drains quickly during video recording","Camera focus struggles in low light","Not sure the new design is worth the cost"]
neutral=["Comparing iPhone 17 camera and battery with last year's model","iPhone 17 launch is expected this week","Looking at the available storage options"]
class Search(BaseModel): query:str
def build_demo():
 random.seed(17); now=datetime.now(timezone.utc); rows=[]
 for i in range(5000):
  day=random.randrange(7); late=day>=5
  topic=random.choices(list(topics),[1,2,1,1,1] if late else [1,1,1,1,1])[0]
  pool=random.choices([positive,neutral,negative],[.54,.27,.19])[0]
  phrase=random.choice(pool); text=f"{phrase} #{topic}"
  stamp=now-timedelta(days=6-day,minutes=random.randrange(1440))
  rows.append({"id":str(i),"platform":random.choice(["Reddit","YouTube","News"]),"text":text,"clean_text":text,"author":f"user_{random.randrange(800)}","created_at":stamp.isoformat(),"likes":random.randrange(0,900),"comments":random.randrange(0,180),"shares":random.randrange(0,100),"views":random.randrange(100,50000),"topic":topic,"sentiment":random.choices(["positive","neutral","negative"],[.54,.27,.19])[0]})
 return rows
def clean(s): return re.sub(r'\s+',' ',re.sub(r'https?://\S+','',s)).strip()
def create(query,mode,rows):
 did=str(uuid.uuid4()); datasets[did]={"id":did,"query":query,"mode":mode,"status":"completed","post_count":len(rows),"created_at":datetime.now(timezone.utc).isoformat(),"sources":[],"posts":rows}; return datasets[did]
@app.get('/health')
def health(): return {"status":"ok","service":"data"}
@app.get('/ready')
def ready(): return {"status":"ready"}
@app.post('/datasets/demo')
def demo(): return {k:v for k,v in create("iPhone 17","demo",build_demo()).items() if k!="posts"}
@app.post('/datasets/search')
def search(x:Search): raise HTTPException(503,"No live source is configured. Try the demo dataset or upload a CSV.")
@app.get('/datasets')
def listing(): return [{k:v for k,v in x.items() if k!="posts"} for x in datasets.values()]
@app.get('/datasets/{did}/status')
def status(did:str): return {"status":"completed","post_count":datasets[did]["post_count"]} if did in datasets else (_ for _ in ()).throw(HTTPException(404,"Dataset not found"))
@app.get('/datasets/{did}')
def detail(did:str):
 if did not in datasets: raise HTTPException(404,"Dataset not found")
 return {k:v for k,v in datasets[did].items() if k!="posts"}
@app.get('/datasets/{did}/posts')
def posts(did:str,page:int=1,platform:str|None=None):
 if did not in datasets: raise HTTPException(404,"Dataset not found")
 rows=datasets[did]['posts']; rows=[r for r in rows if not platform or r['platform'].lower()==platform.lower()]
 return {"items":rows[(page-1)*50:page*50],"page":page,"total":len(rows)}
@app.get('/internal/datasets/{did}/posts')
def internal_posts(did:str):
 if did not in datasets: raise HTTPException(404,"Dataset not found")
 return datasets[did]['posts']
@app.post('/datasets/upload')
async def upload(file:UploadFile=File(...)):
 name=file.filename or ''
 try:
  raw=await file.read();
  if name.lower().endswith('.json'):
   import json; records=json.loads(raw)
  elif name.lower().endswith('.csv'): records=list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
  else: raise ValueError('Upload a CSV or JSON file')
  if not isinstance(records,list): raise ValueError('JSON must contain an array of posts')
  if not records: raise ValueError('The file has no rows')
  lookup={str(k).strip().lower():k for k in records[0]}; key=next((lookup[k] for k in ['text','post','content','message'] if k in lookup),None)
  if not key: raise ValueError('A text column is required')
  rows=[]
  for i,r in enumerate(records):
   txt=clean(str(r.get(key,'') or ''))
   if txt: rows.append({"id":str(i),"text":txt,"clean_text":txt,"platform":r.get('platform') or 'Unknown',"author":r.get('author'),"created_at":r.get('date'),"likes":int(r['likes']) if str(r.get('likes','')).isdigit() else None,"comments":int(r['comments']) if str(r.get('comments','')).isdigit() else None,"shares":int(r['shares']) if str(r.get('shares','')).isdigit() else None,"views":int(r['views']) if str(r.get('views','')).isdigit() else None})
  if not rows: raise ValueError('No usable text rows found')
  return {k:v for k,v in create(name,'upload',rows).items() if k!='posts'}
 except Exception as e: raise HTTPException(422,str(e))
@app.get('/datasets/template.csv')
def template(): return "text,date,platform,author,likes,comments,shares,views,hashtags,mentions\n\"Excited about the camera\",2026-10-01,Reddit,analyst,12,2,1,500,#camera,@brand\n"
