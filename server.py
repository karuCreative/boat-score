"""Local BOAT RACE official racelist proxy. pip install requests beautifulsoup4"""
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse,parse_qs
from datetime import datetime
from pathlib import Path
import json,re,os,time,threading
from auth import verify,make_token,current_user,cookie_header,origin_ok,secret
import requests
from bs4 import BeautifulSoup

BASE='https://www.boatrace.jp/owpc/pc/race/racelist'
LOGIN_PAGE = b'''<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Login</title><style>body{background:#101827;color:white;font-family:system-ui;display:grid;place-items:center;min-height:90vh}main{background:#1e293b;padding:25px;border-radius:16px;width:min(85vw,380px)}input,button{box-sizing:border-box;width:100%;padding:12px;margin:8px 0}button{background:#38bdf8}</style><main><h2>Boat Score PRO</h2><p>Purchaser login</p><form action="/login" method="post"><input name="username" placeholder="User ID" required><input name="password" type="password" placeholder="Password" required><button>Login</button></form></main></html>'''
FAILED={}
FAILED_LOCK=threading.Lock()
class Handler(SimpleHTTPRequestHandler):
 def send_secure(self,status,body,ctype='text/html; charset=utf-8',headers=None):
  self.send_response(status)
  for k,v in {'Content-Type':ctype,'Cache-Control':'no-store, private','X-Content-Type-Options':'nosniff','X-Frame-Options':'DENY','Referrer-Policy':'no-referrer','Content-Security-Policy':"frame-ancestors 'none'",'Content-Length':str(len(body)),**(headers or {})}.items():self.send_header(k,v)
  self.end_headers();self.wfile.write(body)
 def logged_in(self):return current_user(self.headers.get('Cookie'))
 def do_POST(self):
  path=urlparse(self.path).path
  if path not in ('/login','/logout'):return self.send_secure(404,b'Not found','text/plain')
  if not origin_ok(self.headers):return self.send_secure(403,b'Forbidden','text/plain')
  if path=='/logout':return self.send_secure(303,b'',headers={'Location':'/login','Set-Cookie':cookie_header('',True)})
  try:
   n=int(self.headers.get('Content-Length','0'))
   if n<1 or n>4096:raise ValueError()
   values=parse_qs(self.rfile.read(n).decode(),keep_blank_values=True)
   username=values.get('username',[''])[0];password=values.get('password',[''])[0]
   if len(username)>40 or len(password)>256:raise ValueError()
  except (ValueError,UnicodeDecodeError):return self.send_secure(400,b'Bad request','text/plain')
  ip=self.client_address[0];now=time.time()
  with FAILED_LOCK:
   attempts=[t for t in FAILED.get(ip,[]) if now-t<900];FAILED[ip]=attempts
   blocked=len(attempts)>=8
  if blocked:return self.send_secure(429,b'Too many attempts. Try again in 15 minutes.','text/plain')
  if not verify(username,password):
   with FAILED_LOCK:FAILED.setdefault(ip,[]).append(now)
   return self.send_secure(401,b'Invalid credentials. Go back and try again.','text/plain')
  with FAILED_LOCK:FAILED.pop(ip,None)
  return self.send_secure(303,b'',headers={'Location':'/','Set-Cookie':cookie_header(make_token(username))})
 def do_GET(self):
  path=urlparse(self.path).path
  if path=='/health':return self.send_secure(200,b'OK','text/plain')
  if path=='/login':return self.send_secure(200,LOGIN_PAGE) if not self.logged_in() else self.send_secure(303,b'',headers={'Location':'/'})
  if not self.logged_in():
   if path.startswith('/api/'):return self.reply(401,{'error':'Login required'})
   return self.send_secure(303,b'',headers={'Location':'/login'})
  if path not in ('/','/index.html','/api/race'):return self.send_secure(404,b'Not found','text/plain')
  if path in ('/','/index.html'):
   return self.send_secure(200,(Path(__file__).resolve().parent/'index.html').read_bytes())
  q=parse_qs(urlparse(self.path).query)
  try:
   date=q.get('date',[''])[0];venue=q.get('venue',[''])[0];race=int(q.get('race',['0'])[0]);datetime.strptime(date,'%Y%m%d')
   if not re.fullmatch(r'\d{8}',date) or not re.fullmatch(r'\d{2}',venue) or not 1<=int(venue)<=24 or not 1<=race<=12:raise ValueError('日付・場・レース番号を確認してください')
   response=requests.get(BASE,params={'hd':date,'jcd':venue,'rno':race},headers={'User-Agent':'Mozilla/5.0 (compatible; personal race-score viewer)'},timeout=15)
   response.raise_for_status();soup=BeautifulSoup(response.content,'html.parser');boats=[]
   # Official site groups each boat's race-history rows inside a tbody.is-fs12.
   for group in soup.select('tbody.is-fs12'):
    tr=group.select_one('tr');
    if not tr:continue
    cells=tr.find_all('td',recursive=False)
    if len(cells)<7:continue
    raw=[c.get_text(' ',strip=True) for c in cells]
    reg=re.search(r'\b(\d{4})\s*/\s*(A1|A2|B1|B2)\b',raw[1] if len(raw)>1 else '')
    if not reg:
     for cell in raw[:4]:
      reg=re.search(r'\b(\d{4})\s*/\s*(A1|A2|B1|B2)\b',cell)
      if reg:break
    if not reg:continue
    # Locate the cells by relative position of the racer registration/grade cell.
    idx=next((i for i,x in enumerate(raw) if re.search(r'\b'+reg.group(1)+r'\s*/\s*'+reg.group(2)+r'\b',x)),None)
    if idx is None:continue
    # Official columns: racer, F/L & avg ST, nationwide stats, local stats, motor stats.
    if idx+4>=len(raw):continue
    st=re.search(r'(?<!\d)0\.\d{1,3}(?!\d)',raw[idx+1]);win=re.search(r'(?<!\d)\d{1,2}\.\d{1,2}(?!\d)',raw[idx+2]);motor_numbers=re.findall(r'\d{1,3}\.\d{1,2}',raw[idx+4])
    if not(st and win and motor_numbers):continue
    number=len(boats)+1
    if number>6:break
    name=re.sub(r'^.*?'+reg.group(1)+r'\s*/\s*'+reg.group(2),'',raw[idx]).split(' / ')[0].strip()
    boats.append({'boat':number,'name':name,'grade':reg.group(2),'win':float(win.group()),'st':float(st.group()),'motor':float(motor_numbers[0])})
   if len(boats)!=6:raise ValueError('公式ページの6艇分を正確に解析できませんでした。ページ構造変更や未開催の可能性があります。誤った採点を防ぐため表示しません。')
   self.reply(200,{'boats':boats,'source':response.url})
  except Exception as e:self.reply(422,{'error':str(e)})
 def reply(self,status,obj):
  data=json.dumps(obj,ensure_ascii=False).encode();self.send_secure(status,data,'application/json; charset=utf-8')
if __name__=='__main__':
 import os
 secret()
 if not os.environ.get('APP_USERS_JSON'):raise RuntimeError('APP_USERS_JSON must be configured')
 os.chdir(Path(__file__).resolve().parent)
 print('ブラウザで http://localhost:8765 を開いてください')
 ThreadingHTTPServer(('0.0.0.0', int(os.environ.get('PORT', 10000))), Handler).serve_forever()
