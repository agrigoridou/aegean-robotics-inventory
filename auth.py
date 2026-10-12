"""Small local-auth module for Aegean Inventory.
Separate accounts; it does not use or store WordPress passwords.
For public deployment put the app behind an authenticated HTTPS reverse proxy.
"""
from __future__ import annotations
import argparse
import getpass
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import sys
import time

SESSION_HOURS = 12
PBKDF2_ROUNDS = 650_000
ROLES = ('admin', 'member', 'viewer')


def setup(con):
    con.executescript('''
    CREATE TABLE IF NOT EXISTS auth_users (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      username TEXT NOT NULL UNIQUE COLLATE NOCASE,
      display_name TEXT NOT NULL,
      role TEXT NOT NULL CHECK(role IN ('admin','member','viewer')),
      pass_hash TEXT NOT NULL,
      active INTEGER NOT NULL DEFAULT 1,
      created_at INTEGER NOT NULL
    );
    CREATE TABLE IF NOT EXISTS auth_sessions (
      token_hash TEXT PRIMARY KEY,
      user_id INTEGER NOT NULL REFERENCES auth_users(id) ON DELETE CASCADE,
      csrf TEXT NOT NULL,
      expires_at INTEGER NOT NULL
    );
    CREATE INDEX IF NOT EXISTS auth_sessions_user ON auth_sessions(user_id);
    CREATE TABLE IF NOT EXISTS auth_attempts (
      attempt_key TEXT PRIMARY KEY,
      failures INTEGER NOT NULL,
      blocked_until INTEGER NOT NULL,
      last_try INTEGER NOT NULL
    );
    CREATE TABLE IF NOT EXISTS auth_activity (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      occurred_at INTEGER NOT NULL,
      user_id INTEGER,
      username TEXT NOT NULL,
      action TEXT NOT NULL,
      detail TEXT NOT NULL DEFAULT ''
    );
    ''')


def validate_password(password):
    if not isinstance(password,str) or len(password)<12 or len(password)>200:
        raise ValueError('Ο κωδικός πρέπει να έχει 12–200 χαρακτήρες.')
    if password.lower() in {'password1234', '123456789012', 'admin12345678'}:
        raise ValueError('Επίλεξε έναν πιο ισχυρό κωδικό.')


def hash_password(password):
    validate_password(password)
    salt=secrets.token_bytes(16)
    key=hashlib.pbkdf2_hmac('sha256',password.encode('utf-8'),salt,PBKDF2_ROUNDS)
    return f'pbkdf2_sha256${PBKDF2_ROUNDS}${salt.hex()}${key.hex()}'


def verify_password(password, stored):
    try:
        algorithm, count, salt, expected=stored.split('$')
        if algorithm!='pbkdf2_sha256' or int(count)<300_000 or int(count)>2_000_000:return False
        actual=hashlib.pbkdf2_hmac('sha256',password.encode('utf-8'),bytes.fromhex(salt),int(count))
        return hmac.compare_digest(actual,bytes.fromhex(expected))
    except (ValueError,TypeError,UnicodeError,AttributeError):return False


def validate_username(username):
    if not isinstance(username,str) or not re.fullmatch(r'[A-Za-z0-9_.-]{3,40}',username):
        raise ValueError('Username: 3–40 λατινικοί χαρακτήρες, ψηφία, _ . ή -')


def create_user(con, username, password, role='member', display_name=None):
    validate_username(username)
    if role not in ROLES:raise ValueError('Μη έγκυρος ρόλος.')
    display_name=(display_name or username)
    if not isinstance(display_name,str):raise ValueError('Μη έγκυρο όνομα εμφάνισης.')
    display_name=display_name.strip()
    if not display_name or len(display_name)>80:raise ValueError('Μη έγκυρο όνομα εμφάνισης.')
    passwd=hash_password(password)
    row=con.execute('INSERT INTO auth_users(username,display_name,role,pass_hash,active,created_at) VALUES(?,?,?,?,1,?)',
                    (username,display_name,role,passwd,int(time.time())))
    return int(row.lastrowid)


def get_session(con, token):
    if not token or len(token)>200:return None
    hashed=hashlib.sha256(token.encode('utf-8')).hexdigest()
    user=con.execute('''SELECT u.id,u.username,u.display_name,u.role,u.active,s.csrf,s.expires_at
                        FROM auth_sessions s JOIN auth_users u ON u.id=s.user_id
                        WHERE s.token_hash=?''',(hashed,)).fetchone()
    if not user or not user['active'] or user['expires_at']<=int(time.time()):return None
    return dict(user)


def new_session(con, user_id):
    token=secrets.token_urlsafe(40)
    csrf=secrets.token_urlsafe(32)
    con.execute('DELETE FROM auth_sessions WHERE expires_at<?',(int(time.time()),))
    con.execute('INSERT INTO auth_sessions(token_hash,user_id,csrf,expires_at) VALUES(?,?,?,?)',
                (hashlib.sha256(token.encode()).hexdigest(),user_id,csrf,int(time.time())+3600*SESSION_HOURS))
    return token


def end_session(con, token):
    if token: con.execute('DELETE FROM auth_sessions WHERE token_hash=?',
                          (hashlib.sha256(token.encode()).hexdigest(),))


def login(con, username, password, remote_ip):
    username=(username or '').strip() if isinstance(username,str) else ''
    if len(username)>40 or not isinstance(password,str) or len(password)>200: return None, 'Λανθασμένο όνομα ή κωδικός.'
    now=int(time.time())
    key=hashlib.sha256((remote_ip+'|'+username.lower()).encode('utf-8')).hexdigest()
    record=con.execute('SELECT * FROM auth_attempts WHERE attempt_key=?',(key,)).fetchone()
    if record and record['blocked_until']>now: return None,'Πολλές αποτυχημένες προσπάθειες. Ξαναδοκίμασε σε 15 λεπτά.'
    if record and now-record['last_try']>900:
        con.execute('DELETE FROM auth_attempts WHERE attempt_key=?',(key,));record=None
    u=con.execute('SELECT * FROM auth_users WHERE username=? AND active=1',(username,)).fetchone()
    if u and verify_password(password,u['pass_hash']):
        con.execute('DELETE FROM auth_attempts WHERE attempt_key=?',(key,))
        token=new_session(con,u['id'])
        log(con,u,'LOGIN','')
        return token,None
    count=(record['failures'] if record else 0)+1
    con.execute('INSERT OR REPLACE INTO auth_attempts(attempt_key,failures,blocked_until,last_try) VALUES(?,?,?,?)',
                (key,count,now+900 if count>=6 else 0,now))
    return None,'Λανθασμένο όνομα ή κωδικός.'


def log(con,user,action,detail=''):
    con.execute('INSERT INTO auth_activity(occurred_at,user_id,username,action,detail) VALUES(?,?,?,?,?)',
                (int(time.time()),user['id'],user['username'],action,detail[:200]))


def get_users(con):
    return [dict(r) for r in con.execute('SELECT id,username,display_name,role,active,created_at FROM auth_users ORDER BY id')]


def edit_user(con, actor, target_id, role=None, active=None, password=None):
    target=con.execute('SELECT * FROM auth_users WHERE id=?',(target_id,)).fetchone()
    if not target:raise ValueError('Ο χρήστης δεν υπάρχει.')
    next_role=target['role'] if role is None else role
    if active is not None and not isinstance(active,bool):raise ValueError('Μη έγκυρη κατάσταση χρήστη.')
    next_active=target['active'] if active is None else int(active)
    if next_role not in ROLES:raise ValueError('Μη έγκυρος ρόλος.')
    if target_id==actor['id'] and (next_role!='admin' or not next_active):
        raise ValueError('Δεν μπορείς να αφαιρέσεις τον δικό σου λογαριασμό διαχειριστή.')
    if target['role']=='admin' and (next_role!='admin' or not next_active):
        admin_count=con.execute("SELECT COUNT(*) FROM auth_users WHERE role='admin' AND active=1").fetchone()[0]
        if admin_count<=1:raise ValueError('Πρέπει να υπάρχει τουλάχιστον ένας ενεργός διαχειριστής.')
    passwd=hash_password(password) if password is not None else None
    con.execute('UPDATE auth_users SET role=?,active=? WHERE id=?',(next_role,next_active,target_id))
    if passwd:
        con.execute('UPDATE auth_users SET pass_hash=? WHERE id=?',(passwd,target_id))
    if passwd or next_role!=target['role'] or next_active!=target['active']:
        con.execute('DELETE FROM auth_sessions WHERE user_id=?',(target_id,))
    log(con,actor,'USER_UPDATE',f'user_id={target_id}')


def first_admin(db_path):
    con=sqlite3.connect(db_path);con.row_factory=sqlite3.Row;con.execute('PRAGMA foreign_keys=ON')
    setup(con)
    if con.execute("SELECT COUNT(*) FROM auth_users WHERE role='admin'").fetchone()[0]:
        print('Υπάρχει ήδη διαχειριστής. Χρησιμοποίησε την ενότητα Χρήστες μέσα στην εφαρμογή.');return 1
    print('Δημιουργία πρώτου λογαριασμού Aegean Robotics (όχι WordPress).')
    username=input('Username [admin]: ').strip() or 'admin'
    display_name=input('Όνομα εμφάνισης [Administrator]: ').strip() or 'Administrator'
    passwd=getpass.getpass('Νέος κωδικός (τουλάχιστον 12 χαρακτήρες): ')
    confirmation=getpass.getpass('Επιβεβαίωση κωδικού: ')
    if passwd!=confirmation:print('Οι κωδικοί δεν ταιριάζουν.');return 1
    try:
        create_user(con,username,passwd,'admin',display_name);con.commit()
    except (ValueError,sqlite3.IntegrityError) as exc:print('Σφάλμα:',exc);return 1
    finally:con.close()
    print('Ο πρώτος διαχειριστής δημιουργήθηκε. Δεν αποθηκεύεται ο κωδικός σε απλό κείμενο.')
    return 0

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('command',choices=['init-admin','status'])
    parser.add_argument('--db',default=os.path.join(os.path.dirname(__file__),'data','inventory.db'))
    a=parser.parse_args()
    os.makedirs(os.path.dirname(os.path.abspath(a.db)),exist_ok=True)
    if a.command=='status':
        con=sqlite3.connect(a.db);setup(con)
        count=con.execute("SELECT COUNT(*) FROM auth_users WHERE role='admin' AND active=1").fetchone()[0];con.close()
        sys.exit(0 if count else 2)
    sys.exit(first_admin(a.db))
