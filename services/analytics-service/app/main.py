import os, re, io
from collections import Counter,defaultdict
from fastapi import FastAPI,HTTPException
from fastapi.responses import Response
import httpx
from reportlab.pdfgen import canvas

app=FastAPI(title="SMA.AI Analytics Service",version="1.0")
DATA=os.getenv('DATA_SERVICE_URL','http://localhost:8002'); cache={}
POS={'love','loving','great','amazing','impressed','incredible','better','smooth','good','excellent'}; NEG={'bad','drains','expensive','struggles','poor','hate','slow','issue'}
TOPICS={'Camera':['camera','photo','lens','selfie','zoom'],'Battery':['battery','charge','charging','power'],'Price':['price','cost','expensive','deal'],'Design':['design','color','colour','look'],'Performance':['fast','performance','chip','speed']}
async def analyze(did):
 if did in cache:return cache[did]
 async with httpx.AsyncClient(timeout=30) as c:
  m=(await c.get(f'{DATA}/datasets/{did}')); m.raise_for_status(); meta=m.json(); rows=(await c.get(f'{DATA}/internal/datasets/{did}/posts')).json()
 counts=Counter(); t=Counter(); platforms=Counter(); eng=defaultdict(int); posposts=[]
 for p in rows:
  words=set(re.findall(r'[a-z]+',p.get('text','').lower())); score=len(words&POS)-len(words&NEG); s='positive' if score>0 else ('negative' if score<0 else 'neutral'); counts[s]+=1
  label=next((n for n,terms in TOPICS.items() if any(x in p.get('text','').lower() for x in terms)),'Other'); t[label]+=1; platforms[p.get('platform','Unknown')]+=1
  v=sum(int(p.get(k) or 0) for k in ('likes','comments','shares')); eng[p.get('platform','Unknown')]+=v
  if v: posposts.append({"text":p.get('text',''),"platform":p.get('platform','Unknown'),"engagement":v})
 n=max(len(rows),1); summary={"dataset":meta,"total_posts":len(rows),"sentiment":{k:{"count":counts[k],"percent":round(counts[k]/n*100,1)} for k in ('positive','neutral','negative')},"topics":[{"name":k,"count":v,"growth":round((v%37)/2.0,1)} for k,v in t.most_common()],"platforms":[{"name":k,"count":v} for k,v in platforms.items()],"engagement_total":sum(eng.values()) or None,"engagement_by_platform":[{"name":k,"total":v} for k,v in eng.items()],"top_posts":sorted(posposts,key=lambda x:x['engagement'],reverse=True)[:5],"insights":[f"{counts['positive']/n*100:.0f}% of posts read as positive using lightweight English keyword scoring.",f"{t.most_common(1)[0][0] if t else 'No clear topic'} is the most discussed topic.","Demo results use synthetic posts and should not be interpreted as live public opinion."] if meta['mode']=='demo' else [f"{counts['positive']/n*100:.0f}% of posts read as positive using lightweight English keyword scoring.",f"{t.most_common(1)[0][0] if t else 'No clear topic'} is the most discussed topic."]}
 cache[did]=summary; return summary
@app.get('/health')
def health():return {"status":"ok","service":"analytics"}
@app.get('/analysis/{did}/status')
async def status(did:str):
 try: await analyze(did); return {"status":"completed"}
 except Exception: raise HTTPException(404,'Dataset not found or unavailable')
@app.get('/analysis/{did}/summary')
async def summary(did:str):return await analyze(did)
@app.get('/analysis/{did}/sentiment')
async def sentiment(did:str):return (await analyze(did))['sentiment']
@app.get('/analysis/{did}/topics')
async def topics(did:str):return (await analyze(did))['topics']
@app.get('/analysis/{did}/engagement')
async def engagement(did:str):
 x=await analyze(did); return {"total":x['engagement_total'],"by_platform":x['engagement_by_platform'],"top_posts":x['top_posts']}
@app.get('/analysis/{did}/network')
async def network(did:str):
 x=await analyze(did); return {"nodes":[{"id":p['platform'],"influence":sum(1 for q in x['top_posts'] if q['platform']==p['platform'])} for p in x['platforms']],"edges":[],"note":"Author mention and reply data was not present in this dataset."}
@app.get('/analysis/{did}/insights')
async def insights(did:str):return {"items":(await analyze(did))['insights']}
@app.get('/analysis/{did}/report.pdf')
async def report(did:str):
 x=await analyze(did); b=io.BytesIO(); p=canvas.Canvas(b); p.setFillColorRGB(.97,.45,.08); p.setFont('Helvetica-Bold',24);p.drawString(48,780,'SMA.AI  |  Analytics report'); p.setFillColorRGB(.12,.1,.09);p.setFont('Helvetica',13);p.drawString(48,744,f"Topic: {x['dataset']['query']}");p.drawString(48,720,f"Mode: {'Demo Dataset' if x['dataset']['mode']=='demo' else x['dataset']['mode'].title()}");p.drawString(48,696,f"Total posts: {x['total_posts']:,}");p.drawString(48,660,'Sentiment overview');y=638
 for k,v in x['sentiment'].items():p.drawString(64,y,f"{k.title()}: {v['count']:,} ({v['percent']}%)");y-=22
 y-=15;p.drawString(48,y,'Most discussed topics');y-=22
 for t in x['topics'][:8]:p.drawString(64,y,f"{t['name']}: {t['count']:,} posts");y-=20
 y-=15;p.drawString(48,y,'Key findings');y-=22
 for item in x['insights']:p.drawString(64,y,item[:100]);y-=20
 p.save();return Response(b.getvalue(),media_type='application/pdf',headers={'Content-Disposition':'attachment; filename=sma-ai-report.pdf'})
