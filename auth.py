"""Small environment-backed authentication module for manual account issuance."""
import os, json, hmac, hashlib, secrets, time, base64
from http.cookies import SimpleCookie
from urllib.parse import urlparse

COOKIE='boat_score_session'
TTL=60*60*24*14

def b64(b): return base64.urlsafe_b64encode(b).decode().rstrip('=')
def unb64(s): return base64.urlsafe_b64decode(s+'='*(-len(s)%4))
def secret():
    s=os.environ.get('SESSION_SECRET','')
    if len(s)<32: raise RuntimeError('SESSION_SECRET must be set to a random value of at least 32 characters')
    return s.encode()
def users():
    value=os.environ.get('APP_USERS_JSON','')
    data=json.loads(value or '{}')
    if not isinstance(data,dict): raise ValueError('APP_USERS_JSON must be a JSON object')
    return data

def verify(username,password):
    entry=users().get(username)
    if not isinstance(entry,dict) or entry.get('disabled'): return False
    try:
        salt=bytes.fromhex(entry['salt']); expected=bytes.fromhex(entry['hash'])
        actual=hashlib.pbkdf2_hmac('sha256',password.encode(),salt,310000)
        return hmac.compare_digest(actual,expected)
    except (KeyError,ValueError,TypeError): return False

def make_token(username):
    data=b64(json.dumps({'u':username,'exp':int(time.time())+TTL,'nonce':secrets.token_hex(8)},separators=(',',':')).encode())
    signature=b64(hmac.new(secret(),data.encode(),hashlib.sha256).digest())
    return data+'.'+signature

def current_user(cookie_header):
    try:
        c=SimpleCookie();c.load(cookie_header or '')
        token=c[COOKIE].value; payload,signature=token.split('.',1)
        expected=b64(hmac.new(secret(),payload.encode(),hashlib.sha256).digest())
        if not hmac.compare_digest(signature,expected):return None
        data=json.loads(unb64(payload))
        if data['exp']<time.time():return None
        entry=users().get(data['u'])
        if not isinstance(entry,dict) or entry.get('disabled'):return None
        return data['u']
    except (KeyError,ValueError,TypeError,IndexError):return None

def cookie_header(token,clear=False):
    base=f'{COOKIE}={token}; HttpOnly; Secure; SameSite=Lax; Path=/'
    return base+('; Max-Age=0' if clear else f'; Max-Age={TTL}')

def origin_ok(headers):
    origin=headers.get('Origin')
    if not origin:return False
    try:
        a=urlparse(origin); host=headers.get('Host','')
        return a.scheme == 'https' and a.netloc == host.split(':')[0]
    except ValueError:return False
