"""Run locally: python make_user.py username; paste the JSON entry into APP_USERS_JSON."""
import getpass,sys,json,secrets,hashlib
if len(sys.argv)!=2 or not (3<=len(sys.argv[1])<=40) or not all(c.isalnum() or c in '_-' for c in sys.argv[1]):
    raise SystemExit('Usage: python make_user.py username (3-40 letters/numbers/_/-)')
username=sys.argv[1]
password=getpass.getpass('New password (12+ characters): ')
if len(password)<12:raise SystemExit('Password too short')
salt=secrets.token_bytes(16)
hash_value=hashlib.pbkdf2_hmac('sha256',password.encode(),salt,310000)
print(json.dumps({username:{'salt':salt.hex(),'hash':hash_value.hex(),'disabled':False}},ensure_ascii=False))
print('Keep the password securely and send it to the buyer separately. Never commit credentials to GitHub.',file=sys.stderr)
