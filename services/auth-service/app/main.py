import os, hashlib
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, EmailStr
from passlib.context import CryptContext
from jose import jwt
from sqlalchemy import create_engine, text

app=FastAPI(title="SMA.AI Auth Service", version="1.0")
pwd=CryptContext(schemes=["bcrypt"], deprecated="auto")
engine=create_engine(os.getenv("DATABASE_URL","sqlite:///./auth.db"), connect_args={"check_same_thread":False} if os.getenv("DATABASE_URL","").startswith("sqlite") else {})
SECRET=os.getenv("JWT_SECRET","local-only-change-me")
with engine.begin() as c:
 c.execute(text("CREATE TABLE IF NOT EXISTS users(id SERIAL PRIMARY KEY,name TEXT NOT NULL,email TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,role TEXT NOT NULL DEFAULT 'user',created_at TIMESTAMPTZ DEFAULT now())"))
 c.execute(text("CREATE TABLE IF NOT EXISTS refresh_tokens(id SERIAL PRIMARY KEY,user_id INTEGER REFERENCES users(id),token_hash TEXT NOT NULL,expires_at TIMESTAMPTZ NOT NULL,revoked BOOLEAN DEFAULT false)"))
 if os.getenv('SEED_ADMIN','true').lower()=='true':
  with engine.begin() as c:
   exists=c.execute(text("SELECT id FROM users WHERE email='admin@sma.ai'")).first()
   if not exists:c.execute(text("INSERT INTO users(name,email,password_hash,role) VALUES('SMA Admin','admin@sma.ai',:p,'admin')"),{"p":pwd.hash(os.getenv('ADMIN_PASSWORD','DemoSMA2026!'))})
class Credentials(BaseModel):
 email: EmailStr
 password: str
 name: str|None=None
def token(user,minutes=15): return jwt.encode({"sub":str(user["id"]),"role":user["role"],"exp":datetime.now(timezone.utc)+timedelta(minutes=minutes)},SECRET,algorithm="HS256")
@app.get('/health')
def health(): return {"status":"ok","service":"auth"}
@app.post('/auth/register')
def register(x:Credentials):
 if len(x.password)<8: raise HTTPException(422,"Password must be at least 8 characters")
 try:
  with engine.begin() as c: c.execute(text("INSERT INTO users(name,email,password_hash) VALUES(:n,:e,:p)"),{"n":x.name or x.email.split('@')[0],"e":x.email.lower(),"p":pwd.hash(x.password)})
 except Exception: raise HTTPException(409,"Email is already registered")
 return {"message":"Account created"}
@app.post('/auth/login')
def login(x:Credentials):
 with engine.begin() as c: u=c.execute(text("SELECT * FROM users WHERE email=:e"),{"e":x.email.lower()}).mappings().first()
 if not u or not pwd.verify(x.password,u["password_hash"]): raise HTTPException(401,"Email or password is incorrect")
 access=token(u); refresh=jwt.encode({"sub":str(u['id']),"exp":datetime.now(timezone.utc)+timedelta(days=7),"type":"refresh"},SECRET,algorithm="HS256")
 with engine.begin() as c: c.execute(text("INSERT INTO refresh_tokens(user_id,token_hash,expires_at) VALUES(:id,:h,:exp)"),{"id":u['id'],"h":hashlib.sha256(refresh.encode()).hexdigest(),"exp":datetime.now(timezone.utc)+timedelta(days=7)})
 return {"access_token":access,"refresh_token":refresh,"token_type":"bearer","user":{"id":u['id'],"name":u['name'],"email":u['email'],"role":u['role']}}
@app.post('/auth/refresh')
def refresh(body:dict):
 try:
  raw=body['refresh_token']; data=jwt.decode(raw,SECRET,algorithms=['HS256']); digest=hashlib.sha256(raw.encode()).hexdigest()
  with engine.begin() as c:
   row=c.execute(text("SELECT * FROM refresh_tokens WHERE token_hash=:h AND revoked=false AND expires_at>now()"),{"h":digest}).first()
   user=c.execute(text("SELECT * FROM users WHERE id=:i"),{"i":int(data['sub'])}).mappings().first()
  if not row or not user: raise ValueError()
  return {"access_token":token(user),"token_type":"bearer"}
 except Exception: raise HTTPException(401,"Refresh token is invalid or revoked")
@app.get('/auth/verify')
def verify(authorization:str|None=None):
 try: return jwt.decode(authorization.split()[1],SECRET,algorithms=['HS256'])
 except Exception: raise HTTPException(401,"Invalid token")
