"""Local BOAT RACE official racelist proxy. pip install requests beautifulsoup4"""
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse,parse_qs
from datetime import datetime
from pathlib import Path
import json,re
import requests
from bs4 import BeautifulSoup

BASE='https://www.boatrace.jp/owpc/pc/race/racelist'
class Handler(SimpleHTTPRequestHandler):
 def do_GET(self):
  if urlparse(self.path).path!='/api/race':return super().do_GET()
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
  data=json.dumps(obj,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
if __name__=='__main__':
 import os
 os.chdir(Path(__file__).resolve().parent)
 print('ブラウザで http://localhost:8765 を開いてください')
 ThreadingHTTPServer(('0.0.0.0', int(os.environ.get('PORT', 10000))), Handler).serve_forever()
