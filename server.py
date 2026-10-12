#!/usr/bin/env python3
"""Aegean Smart Inventory — local QR inventory system (standard library + qrcode)."""
from __future__ import annotations
import argparse, csv, html, io, json, os, re, sqlite3, threading, unicodedata
from collections import Counter
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from visual import prepare_image, resemblance
import features_v4 as v4
from local_vision import local_description, text_candidates
from gemini_vision import read_local_config, configured as gemini_configured, ai_status, identify as gemini_identify, test_connection as gemini_test
from urllib.parse import parse_qs, quote, urlencode, urlparse, unquote
from http.cookies import SimpleCookie
import hmac
import auth

ROOT=Path(__file__).resolve().parent
# Code/seed remain in the deployment image; user data is stored on the mounted volume.
DATA=Path(os.environ.get('INVENTORY_DATA_DIR', str(ROOT/'data'))).resolve()
SEED=ROOT/'data'/'seed_sub2.json'
DB=Path(os.environ.get('INVENTORY_DB',str(DATA/'inventory.db')))
STATIC=ROOT/'static'
MEDIA=DATA/'photos'
DB_LOCK=threading.RLock()
read_local_config()

class ApiError(Exception):
    def __init__(self, message, status=400): super().__init__(message); self.status=status


def connection():
    con=sqlite3.connect(DB,timeout=15,isolation_level=None,check_same_thread=False)
    con.row_factory=sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON')
    con.execute('PRAGMA busy_timeout=10000')
    return con


def init_database():
    DATA.mkdir(parents=True,exist_ok=True)
    with DB_LOCK, connection() as con:
        con.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS locations(
          id TEXT PRIMARY KEY, cabinet INTEGER NOT NULL, slot INTEGER NOT NULL,
          label TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS items(
          sku TEXT PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL,
          notes TEXT NOT NULL DEFAULT '', source_row INTEGER, quantity_unknown INTEGER NOT NULL DEFAULT 0,
          default_location TEXT REFERENCES locations(id));
        CREATE TABLE IF NOT EXISTS stock(
          sku TEXT NOT NULL REFERENCES items(sku), location_id TEXT NOT NULL REFERENCES locations(id),
          quantity INTEGER NOT NULL CHECK(quantity>=0), PRIMARY KEY(sku,location_id));
        CREATE TABLE IF NOT EXISTS issues(
          id INTEGER PRIMARY KEY AUTOINCREMENT, sku TEXT NOT NULL REFERENCES items(sku),
          holder TEXT NOT NULL, quantity_open INTEGER NOT NULL CHECK(quantity_open>=0),
          location_id TEXT REFERENCES locations(id), created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS movements(
          id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, sku TEXT NOT NULL REFERENCES items(sku),
          action TEXT NOT NULL, quantity INTEGER NOT NULL, from_location TEXT, to_location TEXT,
          holder TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '', issue_id INTEGER,
          FOREIGN KEY(issue_id) REFERENCES issues(id));
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS item_photos(
          id INTEGER PRIMARY KEY AUTOINCREMENT, sku TEXT NOT NULL REFERENCES items(sku),
          feature_json TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_item_photos_sku ON item_photos(sku);
        CREATE TABLE IF NOT EXISTS location_photos(
          location_id TEXT PRIMARY KEY REFERENCES locations(id), created_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_movements_sku ON movements(sku,id DESC);
        CREATE INDEX IF NOT EXISTS idx_issues_sku ON issues(sku,quantity_open);
        ''')
        v4.init_schema(con)
        auth.setup(con)
        if con.execute('SELECT COUNT(*) FROM items').fetchone()[0]==0:
            seed=json.loads(SEED.read_text(encoding='utf-8'))
            con.execute('BEGIN IMMEDIATE')
            try:
                con.execute("INSERT OR IGNORE INTO locations(id,cabinet,slot,label) VALUES('C99-S00',99,0,'Χωρίς καταγεγραμμένη θέση')")
                for x in seed['locations']:
                    con.execute('INSERT OR IGNORE INTO locations(id,cabinet,slot,label) VALUES(?,?,?,?)',
                                (x['id'],x['cabinet'],x['slot'],x['label']))
                for x in seed['items']:
                    con.execute('INSERT INTO items(sku,name,category,notes,source_row,quantity_unknown,default_location) VALUES(?,?,?,?,?,?,?)',
                                (x['sku'],x['name'],x['category'],x['notes'],x['source_row'],int(x['quantity_unknown']),x['location_id']))
                    if x['quantity'] is not None:
                        con.execute('INSERT INTO stock(sku,location_id,quantity) VALUES(?,?,?)',
                                    (x['sku'],x['location_id'] or 'C99-S00',x['quantity']))
                con.execute('COMMIT')
            except Exception:
                con.execute('ROLLBACK'); raise


def dictrow(x): return dict(x) if x else None

def now(): return datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')

def item_by_id(con,sku):
    r=con.execute('SELECT * FROM items WHERE sku=?',(sku,)).fetchone()
    if not r:raise ApiError('Το αντικείμενο δεν βρέθηκε.',404)
    return r

def location_by_id(con,loc):
    r=con.execute('SELECT * FROM locations WHERE id=?',(loc,)).fetchone()
    if not r:raise ApiError('Η θέση δεν υπάρχει. Καταχώρισέ την πρώτα.',404)
    return r

def list_locations(con):
    locs=[]
    for r in con.execute('SELECT * FROM locations ORDER BY cabinet,slot'):
        p=dict(r)
        rows=con.execute('SELECT i.category,st.quantity FROM stock st JOIN items i ON st.sku=i.sku WHERE st.location_id=? AND st.quantity>0',(r['id'],)).fetchall()
        ranks=Counter(x['category'] for x in rows)
        p.update(item_types=len(rows),units=sum(x['quantity'] for x in rows),dominant_category=ranks.most_common(1)[0][0] if ranks else '',category_mix=dict(ranks),photo_url=f"/media/location/{r['id']}" if con.execute('SELECT 1 FROM location_photos WHERE location_id=?',(r['id'],)).fetchone() else None)
        locs.append(p)
    return locs

def recommendation(con,sku):
    item=item_by_id(con,sku)
    stocks=con.execute("SELECT location_id,quantity FROM stock WHERE sku=? AND quantity>0 AND location_id!='C99-S00' ORDER BY quantity DESC",(sku,)).fetchall()
    if stocks:
        return {'location_id':stocks[0]['location_id'],'reason':'Το αντικείμενο βρίσκεται ήδη σε αυτή τη θέση.'}
    # Learned choice from physically confirmed moves, without claiming to know shelf capacity.
    learned=con.execute("""SELECT to_location,COUNT(*) AS n FROM movements
      WHERE sku=? AND action IN ('RECEIVE','RETURN','TRANSFER')
      AND to_location IS NOT NULL AND to_location!='C99-S00'
      GROUP BY to_location ORDER BY n DESC LIMIT 1""",(sku,)).fetchone()
    if learned and learned['n']>=2:
        return {'location_id':learned['to_location'],'reason':f'Προσαρμοσμένη πρόταση από {learned["n"]} επιβεβαιωμένες τοποθετήσεις.'}
    if item['default_location']:
        return {'location_id':item['default_location'],'reason':'Αρχική θέση καταγραφής στο SUB.2 Inventory.'}
    category=item['category']
    res=con.execute('''SELECT s.location_id,COUNT(DISTINCT s.sku) AS n
        FROM stock s JOIN items i ON i.sku=s.sku
        WHERE s.quantity>0 AND s.location_id!='C99-S00' AND i.category=? GROUP BY s.location_id ORDER BY n DESC,s.location_id LIMIT 1''',(category,)).fetchone()
    if res:return {'location_id':res['location_id'],'reason':'Πρόταση από την ομαδοποίηση παρόμοιων αντικειμένων. Απαιτείται επιβεβαίωση.'}
    return {'location_id':None,'reason':'Δεν υπάρχει τεκμηριωμένη θέση. Επίλεξε χειροκίνητα.'}

def item_detail(con,sku):
    item=dict(item_by_id(con,sku))
    item['stocks']=[dict(r) for r in con.execute('''SELECT st.location_id,l.label,st.quantity FROM stock st
       JOIN locations l ON l.id=st.location_id WHERE st.sku=? AND st.quantity>0 ORDER BY st.quantity DESC''',(sku,))]
    item['on_hand']=None if item['quantity_unknown'] else sum(r['quantity'] for r in item['stocks'])
    item['issues']=[dict(r) for r in con.execute('SELECT * FROM issues WHERE sku=? AND quantity_open>0 ORDER BY id DESC',(sku,))]
    item['checked_out']=sum(r['quantity_open'] for r in item['issues'])
    item['recommendation']=recommendation(con,sku)
    item['smart_placement']=v4.smart_placement(__import__(__name__),con,sku)
    item['photos']=[{'id':r['id'],'url':f"/media/item/{r['id']}"} for r in con.execute('SELECT id FROM item_photos WHERE sku=? ORDER BY id DESC LIMIT 12',(sku,))]
    return item

def items_api(con,args):
    q=args.get('q',[''])[0].strip().casefold()
    cat=args.get('category',[''])[0]
    loc=args.get('location',[''])[0]
    unknown=args.get('unknown',[''])[0]=='1'
    sql='''SELECT i.* FROM items i WHERE 1=1'''
    params=[]
    if q:sql+=' AND (LOWER(i.name) LIKE ? OR LOWER(i.sku) LIKE ?)';params += [f'%{q}%',f'%{q}%']
    if cat:sql+=' AND i.category=?';params.append(cat)
    if unknown:sql+=' AND i.quantity_unknown=1'
    if loc:sql+=' AND (i.default_location=? OR EXISTS(SELECT 1 FROM stock st WHERE st.sku=i.sku AND st.location_id=? AND st.quantity>0))';params += [loc,loc]
    sql+=' ORDER BY i.name COLLATE NOCASE,i.sku LIMIT 500'
    out=[]
    for i in con.execute(sql,params):
        r=dict(i)
        r['on_hand']=None if r['quantity_unknown'] else con.execute('SELECT COALESCE(SUM(quantity),0) FROM stock WHERE sku=?',(r['sku'],)).fetchone()[0]
        r['checked_out']=con.execute('SELECT COALESCE(SUM(quantity_open),0) FROM issues WHERE sku=?',(r['sku'],)).fetchone()[0]
        out.append(r)
    return out

# Search inventory from natural-language questions, without relying on AI output for stock facts.
FIND_STOPWORDS = set(('που πουθε πως ειναι βρισκεται βρισκονται βρω βρεις βρισκω ' 
 'υπαρχει υπαρχουν εχετε εχουμε θελω χρειαζομαι χρειαζομαστε παρω παρεις ' 
 'μπορω μπορουμε εντοπισω εντοπισε δειξε θεση σημειο μερος ντουλαπα ραφι '
 'το τα τη την της τον της ενα μια εναν ενος οι ο η στο στην στον στα στη ' 
 'μου μας για απο στο εργαστηριο παρακαλω θελα θα ποσα ποσες ποσο ποση συνολικα διαθεσιμα διαθεσιμο διαθεσιμη τεμαχια στοκ αποθεμα').split())
FIND_ALIASES = {'rpi':'raspberry pi','raspberrypi':'raspberry pi',
 'arduino-uno':'arduino uno', 'αισθητηρας':'sensor','αισθητηρες':'sensor',
 'καμερα':'camera','κινητηρας':'motor','σερβο':'servo',
 'οθονη':'display'}

def find_normalize(value):
    t=unicodedata.normalize('NFKD',str(value or '').casefold())
    t=''.join(c for c in t if not unicodedata.combining(c))
    t=re.sub(r'(?<=\w)(?=\d)|(?<=\d)(?=\w)', ' ', t)
    t=re.sub(r'[^\w]+',' ',t,flags=re.UNICODE)
    tokens=t.split()
    return ' '.join(FIND_ALIASES.get(w,w) for w in tokens).strip()

def find_query(value):
    q=find_normalize(value)
    tokens=[x for x in q.split() if x not in FIND_STOPWORDS]
    return ' '.join(tokens)[:160]

def find_items(con,raw_query):
    if len(raw_query)>300:raise ApiError('Η αναζήτηση είναι υπερβολικά μεγάλη.',400)
    phrase=find_query(raw_query)
    if not phrase:
        return {'query':raw_query,'search_term':'','matches':[],'message':'Γράψε ποιο εξάρτημα ψάχνεις, π.χ. Raspberry Pi 4.'}
    terms=phrase.split()
    candidates=[]
    for item in con.execute('SELECT * FROM items'):
        name=find_normalize(item['name'])
        name_terms=name.split()
        name_words=set(name_terms)
        if find_normalize(item['sku'])==phrase:score=140
        elif name==phrase:score=120
        elif phrase in name and len(phrase)>2:score=98-(len(name_terms)-len(terms))*2
        elif all(t in name_words for t in terms):score=84-(len(name_terms)-len(terms))*3
        elif len(terms)>1 and sum(t in name_words for t in terms)>=len(terms)-1:
            score=42-(len(name_terms)-len(terms))*2
        elif len(terms)==1 and len(terms[0])>=4 and terms[0] in name_words:
            score=62
        else:continue
        if score>=35:candidates.append((score,dict(item),name))
    candidates.sort(key=lambda x:(-x[0], len(x[2]), x[1]['name'].casefold()))
    if not candidates:
        return {'query':raw_query,'search_term':phrase,'matches':[],
         'message':'Δεν εντοπίστηκε καταχώριση. Δοκίμασε πιο συγκεκριμένο όνομα ή φωτογραφία.'}
    # If the product is an exact match, hide weaker guesses (e.g. Pi 3 or Pi 5).
    best=candidates[0][0]
    if best>=110:candidates=[x for x in candidates if x[0]>=110]
    elif best>=80:candidates=[x for x in candidates if x[0]>=75]
    grouped={}
    # Merge ONLY identical normalized product names, avoiding accidental mixing of Pi 4 / Pi 5 etc.
    for score,item,key in candidates:
        if key not in grouped:
            grouped[key]={'name':item['name'],'category':item['category'],'match_score':score,
             'skus':[],'quantity':0,'quantity_unknown':False,'checked_out':0,
             '_locs':{},'_photos':[],'initial_positions':set()}
        g=grouped[key]
        g['skus'].append(item['sku'])
        if item['default_location']:g['initial_positions'].add(item['default_location'])
        if item['quantity_unknown']:g['quantity_unknown']=True
        for row in con.execute('SELECT st.location_id,l.label,st.quantity FROM stock st LEFT JOIN locations l ON st.location_id=l.id WHERE st.sku=? AND st.quantity>0',(item['sku'],)):
            g['quantity']+=row['quantity']
            location_id=row['location_id']
            if location_id=='C99-S00':continue
            loc=g['_locs'].setdefault(location_id,{'id':location_id,'label':row['label'] or location_id,
                'quantity':0,'photo_url':None})
            loc['quantity']+=row['quantity']
        g['checked_out']+=con.execute('SELECT COALESCE(SUM(quantity_open),0) FROM issues WHERE sku=?',(item['sku'],)).fetchone()[0]
        p=con.execute('SELECT id FROM item_photos WHERE sku=? ORDER BY id DESC LIMIT 1',(item['sku'],)).fetchone()
        if p:g['_photos'].append(f'/media/item/{p["id"]}')
    final=[]
    for key,g in grouped.items():
        g['locations']=sorted(g.pop('_locs').values(), key=lambda l:(-l['quantity'],l['id']))
        for loc in g['locations']:
            if con.execute('SELECT 1 FROM location_photos WHERE location_id=?',(loc['id'],)).fetchone():
                loc['photo_url']=f'/media/location/{loc["id"]}'
        g['photos']=g.pop('_photos')
        g['initial_positions']=sorted(g['initial_positions'])
        g['known_total']=not g['quantity_unknown']
        final.append(g)
    final.sort(key=lambda x:(-x['match_score'], len(find_normalize(x['name'])),x['name'].casefold()))
    return {'query':raw_query,'search_term':phrase,'matches':final[:8],
      'message': 'Το αποτέλεσμα βασίζεται στα αποθηκευμένα δεδομένα και στις καταγεγραμμένες κινήσεις, όχι σε φυσική επαλήθευση.'}

def stats(con):
    d={}
    d['items']=con.execute('SELECT COUNT(*) FROM items').fetchone()[0]
    d['unknown']=con.execute('SELECT COUNT(*) FROM items WHERE quantity_unknown=1').fetchone()[0]
    d['units_in']=con.execute('SELECT COALESCE(SUM(quantity),0) FROM stock').fetchone()[0]
    d['units_out']=con.execute('SELECT COALESCE(SUM(quantity_open),0) FROM issues').fetchone()[0]
    d['locations']=con.execute("SELECT COUNT(*) FROM locations WHERE id!='C99-S00'").fetchone()[0]
    d['movements']=con.execute('SELECT COUNT(*) FROM movements').fetchone()[0]
    d['loans']=con.execute('SELECT COUNT(*) FROM issues WHERE quantity_open>0').fetchone()[0]
    d['categories']=[r['category'] for r in con.execute('SELECT DISTINCT category FROM items ORDER BY category')]
    return d

def positive_int(value,name='Η ποσότητα'):
    try:
        n=int(value)
        if isinstance(value,bool) or (str(value).strip() != str(n) and not isinstance(value,int)):raise ValueError
    except (ValueError,TypeError):raise ApiError(f'{name} πρέπει να είναι ακέραιος αριθμός.')
    if n<=0 or n>1000000:raise ApiError(f'{name} πρέπει να είναι από 1 έως 1.000.000.')
    return n

def nonnegative_int(value):
    try:
        n=int(value)
        if isinstance(value,bool) or (str(value).strip() != str(n) and not isinstance(value,int)):raise ValueError
    except (ValueError,TypeError):raise ApiError('Η ποσότητα απογραφής πρέπει να είναι ακέραιος αριθμός.')
    if n<0 or n>1000000:raise ApiError('Η ποσότητα απογραφής πρέπει να είναι από 0 έως 1.000.000.')
    return n

def add_stock(con,sku,loc,delta):
    old=con.execute('SELECT quantity FROM stock WHERE sku=? AND location_id=?',(sku,loc)).fetchone()
    v=(old['quantity'] if old else 0)+delta
    if v<0:raise ApiError('Η ποσότητα στη συγκεκριμένη θέση δεν επαρκεί.')
    con.execute('INSERT INTO stock(sku,location_id,quantity) VALUES(?,?,?) ON CONFLICT(sku,location_id) DO UPDATE SET quantity=excluded.quantity',(sku,loc,v))
    return v

def transact(payload):
    action=str(payload.get('action','')).upper()
    if action not in ('OUT','RETURN','RECEIVE','TRANSFER','COUNT'):raise ApiError('Άγνωστη ενέργεια.')
    sku=str(payload.get('sku','')).strip()
    note=str(payload.get('note') or '').strip()[:300]
    holder=str(payload.get('holder') or '').strip()[:120]
    with DB_LOCK,connection() as con:
        con.execute('BEGIN IMMEDIATE')
        try:
            item=item_by_id(con,sku)
            frm=str(payload.get('from_location') or '').strip() or None
            to=str(payload.get('to_location') or '').strip() or None
            if frm:location_by_id(con,frm)
            if to:location_by_id(con,to)
            if to=='C99-S00':raise ApiError('Η θέση «Χωρίς καταγεγραμμένη θέση» είναι μόνο προσωρινή. Επίλεξε μια πραγματική θέση.')
            if action=='COUNT':
                if not to:raise ApiError('Επίλεξε τη θέση που μέτρησες.')
                n=nonnegative_int(payload.get('quantity'))
                old=con.execute('SELECT quantity FROM stock WHERE sku=? AND location_id=?',(sku,to)).fetchone()
                prev=old['quantity'] if old else None
                con.execute('INSERT INTO stock(sku,location_id,quantity) VALUES(?,?,?) ON CONFLICT(sku,location_id) DO UPDATE SET quantity=excluded.quantity',(sku,to,n))
                con.execute('UPDATE items SET quantity_unknown=0,default_location=COALESCE(default_location,?) WHERE sku=?',(to,sku))
                con.execute('INSERT INTO movements(ts,sku,action,quantity,to_location,note) VALUES(?,?,?,?,?,?)',
                            (now(),sku,action,n,to,f'Απογραφή: προηγούμενο={prev if prev is not None else "άγνωστο"}. '+note))
            else:
                if item['quantity_unknown']:raise ApiError('Πρώτα κάνε απογραφή: η αρχική ποσότητα στο Excel είναι άγνωστη.')
                n=positive_int(payload.get('quantity'))
                issue_id=None
                if action=='OUT':
                    if not frm:raise ApiError('Επίλεξε από ποια θέση το αφαιρείς.')
                    add_stock(con,sku,frm,-n)
                    holder=holder or 'Χωρίς όνομα'
                    cur=con.execute('INSERT INTO issues(sku,holder,quantity_open,location_id,created_at) VALUES(?,?,?,?,?)',
                                    (sku,holder,n,frm,now()))
                    issue_id=cur.lastrowid
                    project=str(payload.get('project') or '').strip()[:150]
                    due=str(payload.get('due_date') or '').strip()
                    if due:
                        from datetime import date
                        try:date.fromisoformat(due)
                        except ValueError:raise ApiError('Μη έγκυρη ημερομηνία επιστροφής.')
                    con.execute('UPDATE issues SET project=?,due_date=? WHERE id=?',(project,due,issue_id))
                elif action=='RETURN':
                    if not to:raise ApiError('Επίλεξε πού το επέστρεψες.')
                    try: issue_id=int(payload.get('issue_id'))
                    except (TypeError,ValueError):raise ApiError('Επίλεξε προηγούμενη εκκρεμή αφαίρεση.')
                    issue=con.execute('SELECT * FROM issues WHERE id=? AND sku=?',(issue_id,sku)).fetchone()
                    if not issue or issue['quantity_open']<n:raise ApiError('Η επιστροφή υπερβαίνει την εκκρεμή ποσότητα.')
                    add_stock(con,sku,to,n)
                    con.execute('UPDATE issues SET quantity_open=quantity_open-? WHERE id=?',(n,issue_id))
                    holder=issue['holder']; frm=issue['location_id']
                elif action=='RECEIVE':
                    if not to:raise ApiError('Επίλεξε πού το τοποθέτησες.')
                    add_stock(con,sku,to,n)
                elif action=='TRANSFER':
                    if not frm or not to:raise ApiError('Επίλεξε προέλευση και προορισμό.')
                    if frm==to:raise ApiError('Επίλεξε διαφορετική θέση προορισμού.')
                    add_stock(con,sku,frm,-n)
                    add_stock(con,sku,to,n)
                con.execute('INSERT INTO movements(ts,sku,action,quantity,from_location,to_location,holder,note,issue_id) VALUES(?,?,?,?,?,?,?,?,?)',
                            (now(),sku,action,n,frm,to,holder,note,issue_id))
            con.execute('COMMIT')
            return item_detail(con,sku)
        except Exception:
            con.execute('ROLLBACK');raise

def update_category(data):
    sku=str(data.get('sku') or '')
    cat=str(data.get('category') or '').strip()[:100]
    if not cat:raise ApiError('Συμπλήρωσε κατηγορία.')
    with DB_LOCK,connection() as con:
        item_by_id(con,sku)
        con.execute('UPDATE items SET category=? WHERE sku=?',(cat,sku))
        return item_detail(con,sku)

def add_new_item(data):
    name=str(data.get('name') or '').strip()[:220]
    cat=str(data.get('category') or 'Λοιπά').strip()[:100] or 'Λοιπά'
    loc=str(data.get('location_id') or '').strip() or None
    if len(name)<2:raise ApiError('Συμπλήρωσε όνομα αντικειμένου.')
    quantity=data.get('quantity')
    qty=None if quantity is None or quantity=='' else nonnegative_int(quantity)
    with DB_LOCK,connection() as con:
        con.execute('BEGIN IMMEDIATE')
        try:
            if loc:location_by_id(con,loc)
            cur=con.execute("SELECT MAX(CAST(SUBSTR(sku,4) AS INTEGER)) FROM items WHERE sku LIKE 'AR-%'").fetchone()[0] or 350
            sku=f'AR-{max(cur+1,1000):04d}'
            con.execute('INSERT INTO items(sku,name,category,notes,source_row,quantity_unknown,default_location) VALUES(?,?,?,?,?,?,?)',
                        (sku,name,cat,str(data.get('notes') or '')[:500],None,int(qty is None),loc))
            if qty is not None and loc:con.execute('INSERT INTO stock(sku,location_id,quantity) VALUES(?,?,?)',(sku,loc,qty))
            elif qty is not None and qty>0:raise ApiError('Επίλεξε θέση για θετική ποσότητα.')
            con.execute('COMMIT')
            return item_detail(con,sku)
        except Exception:
            con.execute('ROLLBACK');raise

def add_new_location(data):
    cab=positive_int(data.get('cabinet'),'Η ντουλάπα')
    slot=positive_int(data.get('slot'),'Η θέση')
    if cab>99 or slot>99:raise ApiError('Ο κωδικός ντουλάπας/θέσης δεν μπορεί να ξεπερνά το 99.')
    code=f'C{cab:02}-S{slot:02}'
    label=str(data.get('label') or f'Ντουλάπα {cab} · Θέση {slot}').strip()[:130]
    with DB_LOCK,connection() as con:
        try:con.execute('INSERT INTO locations(id,cabinet,slot,label) VALUES(?,?,?,?)',(code,cab,slot,label))
        except sqlite3.IntegrityError:raise ApiError('Αυτή η θέση υπάρχει ήδη.')
    return {'id':code,'cabinet':cab,'slot':slot,'label':label}

def settings(con):
    rows=con.execute('SELECT key,value FROM settings').fetchall()
    return {r['key']:r['value'] for r in rows}

def save_settings(body):
    url=str(body.get('public_base_url') or '').strip().rstrip('/')
    if url:
        p=urlparse(url)
        if p.scheme not in ('http','https') or not p.netloc or p.username or p.password or p.path not in ('','/'):
            raise ApiError('Συμπλήρωσε μόνο τη διεύθυνση server, π.χ. http://192.168.1.20:8765')
    with DB_LOCK,connection() as con:
        con.execute('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',('public_base_url',url))
        return settings(con)

def history(con, args):
    sku=args.get('sku',[''])[0]
    limit=max(1,min(150,int(args.get('limit',['60'])[0])))
    wh='WHERE m.sku=?' if sku else ''
    params=(sku,limit) if sku else (limit,)
    return [dict(r) for r in con.execute(f'''SELECT m.*,i.name FROM movements m JOIN items i ON i.sku=m.sku {wh}
                                         ORDER BY m.id DESC LIMIT ?''',params)]

def save_photo(data):
    kind=str(data.get('kind') or 'item')
    ident=str(data.get('id') or '')
    try:contents,feat=prepare_image(data.get('image'))
    except ValueError as exc:raise ApiError(str(exc))
    MEDIA.mkdir(parents=True,exist_ok=True)
    with DB_LOCK,connection() as con:
        if kind=='item':
            item_by_id(con,ident)
            con.execute('BEGIN IMMEDIATE')
            try:
                cur=con.execute('INSERT INTO item_photos(sku,feature_json,created_at) VALUES(?,?,?)',(ident,json.dumps(feat,separators=(',',':')),now()))
                pid=cur.lastrowid
                (MEDIA/f'item-{pid}.jpg').write_bytes(contents)
                con.execute('COMMIT')
            except Exception:
                con.execute('ROLLBACK');raise
            return {'url':f'/media/item/{pid}','id':pid,'item':item_detail(con,ident)}
        if kind=='location':
            location_by_id(con,ident)
            (MEDIA/f'location-{ident}.jpg').write_bytes(contents)
            con.execute('INSERT INTO location_photos(location_id,created_at) VALUES(?,?) ON CONFLICT(location_id) DO UPDATE SET created_at=excluded.created_at',(ident,now()))
            return {'url':f'/media/location/{ident}'}
        raise ApiError('Άγνωστος τύπος φωτογραφίας.')


def visual_search(data):
    try:
        image_bytes, query_feat = prepare_image(data.get('image'))
    except ValueError as exc:
        raise ApiError(str(exc))
    with connection() as con:
        photos=con.execute('SELECT p.id,p.sku,p.feature_json,i.name,i.category FROM item_photos p JOIN items i ON p.sku=i.sku').fetchall()
        catalog=con.execute('SELECT sku,name,category,default_location FROM items ORDER BY sku').fetchall()
    best={}
    for x in photos:
        sc=resemblance(query_feat,json.loads(x['feature_json']))
        if x['sku'] not in best or sc>best[x['sku']]['similarity']:
            best[x['sku']]={'sku':x['sku'],'name':x['name'],'category':x['category'],'similarity':sc,'photo_url':f'/media/item/{x["id"]}'}
    photo_results=sorted(best.values(),key=lambda x:x['similarity'],reverse=True)[:8]
    vision=None
    warning=None
    local_desc=None
    local_candidates=[]
    if gemini_configured():
        try:
            vision=gemini_identify(image_bytes,catalog)
        except RuntimeError as exc:
            warning=str(exc)
    elif os.environ.get('OLLAMA_VISION_MODEL','').strip():
        local_desc,warning=local_description(data.get('image'))
        local_candidates=text_candidates(local_desc,catalog)
    return {'mode':'gemini' if gemini_configured() else 'photo_examples',
            'photos_indexed':len(photos), 'results':photo_results,
            'gemini':vision, 'gemini_warning':warning if gemini_configured() else None,
            'ai_description':local_desc, 'ai_candidates':local_candidates,
            'ai_warning':warning if not gemini_configured() else None,
            'ai_configured':gemini_configured(),
            'message':('Το Gemini αναγνωρίζει το αντικείμενο σε σχέση με τις εγγραφές του Excel. '
                       'Πάντα επιβεβαίωσε την επιλογή πριν από οποιαδήποτε κίνηση.'
                       if vision else
                       'Οι οπτικές ομοιότητες χρειάζονται φωτογραφίες αναφοράς. Η αναζήτηση ονόματος παραμένει διαθέσιμη.')}

class Handler(BaseHTTPRequestHandler):
    server_version='AegeanInventory/4.2'
    def log_message(self, fmt,*a):
        print('%s %s'%(self.log_date_time_string(),fmt%a),flush=True)
    def send_bytes(self, payload, code=200, content_type='application/json; charset=utf-8', attachment=None, headers=None):
        self.send_response(code)
        self.send_header('Content-Type',content_type)
        self.send_header('Content-Length',str(len(payload)))
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Cache-Control','no-store')
        self.send_header('Referrer-Policy','same-origin')
        self.send_header('X-Frame-Options','DENY')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; media-src 'self' blob:; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")
        if os.environ.get('AUTH_SECURE_COOKIE')=='1':self.send_header('Strict-Transport-Security','max-age=31536000')
        if headers:
            for name,value in headers.items():self.send_header(name,value)
        if attachment:self.send_header('Content-Disposition',f'attachment; filename="{attachment}"')
        self.end_headers();self.wfile.write(payload)
    def send_json(self,obj,code=200,headers=None):self.send_bytes(json.dumps(obj,ensure_ascii=False).encode('utf-8'),code,headers=headers)
    def qp(self):return parse_qs(urlparse(self.path).query,keep_blank_values=True)
    def body(self):
        length=int(self.headers.get('Content-Length','0'))
        if length>7_500_000:raise ApiError('Υπερβολικά μεγάλα δεδομένα.')
        try:data=json.loads(self.rfile.read(length))
        except (json.JSONDecodeError,UnicodeDecodeError):raise ApiError('Μη έγκυρο JSON.')
        if not isinstance(data,dict):raise ApiError('Τα δεδομένα πρέπει να είναι αντικείμενο.')
        return data
    def cookie_token(self):
        raw=self.headers.get('Cookie','')
        if len(raw)>4096:return ''
        cookie=SimpleCookie()
        try:cookie.load(raw)
        except Exception:return ''
        return cookie['ar_inventory_session'].value if 'ar_inventory_session' in cookie else ''
    def cookie_header(self, token='', expire=False):
        secure='; Secure' if os.environ.get('AUTH_SECURE_COOKIE')=='1' else ''
        if expire:return f'ar_inventory_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0{secure}'
        return f'ar_inventory_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={auth.SESSION_HOURS*3600}{secure}'
    def current_user(self):
        with connection() as con:return auth.get_session(con,self.cookie_token())
    def enforce_origin(self):
        # Origin and Fetch Metadata checks are defense in depth, together with CSRF session token.
        if self.headers.get('Sec-Fetch-Site','') not in ('','none','same-origin'):
            raise ApiError('Cross-site request blocked.',403)
        origin=self.headers.get('Origin','')
        if origin:
            host=self.headers.get('Host','')
            if urlparse(origin).netloc.lower()!=host.lower() or urlparse(origin).scheme not in ('http','https'):
                raise ApiError('Invalid request origin.',403)
    def require_session(self,method,path):
        user=self.current_user()
        if not user:raise ApiError('Η συνεδρία έληξε. Συνδέσου ξανά.',401)
        if method=='POST':
            self.enforce_origin()
            csrf=self.headers.get('X-CSRF-Token','')
            if not hmac.compare_digest(csrf,user['csrf']):raise ApiError('Η επιβεβαίωση ασφαλείας απέτυχε. Ανανέωσε τη σελίδα.',403)
            if user['role']=='viewer':raise ApiError('Ο λογαριασμός σου έχει δικαιώματα μόνο προβολής.',403)
            if path in {'/api/settings','/api/ai/test','/api/category','/api/locations','/api/location/settings'} and user['role']!='admin':
                raise ApiError('Μόνο ο διαχειριστής μπορεί να αλλάξει αυτές τις ρυθμίσεις.',403)
        return user
    def auth_api(self,method,path):
        if method=='POST' and path=='/api/auth/login':
            self.enforce_origin()
            with connection() as con:
                # Parse once, do not ever log or send the password back.
                data=self.body()
                token,error=auth.login(con,data.get('username'),data.get('password'),self.client_address[0])
                if error:raise ApiError(error,429 if '15 λεπτά' in error else 401)
                return self.send_json({'ok':True},headers={'Set-Cookie':self.cookie_header(token)})
        if method=='GET' and path=='/api/auth/me':
            user=self.current_user()
            if not user:return self.send_json({'authenticated':False},401)
            return self.send_json({'authenticated':True,'username':user['username'],
              'display_name':user['display_name'],'role':user['role'],'csrf':user['csrf']})
        user=self.current_user()
        if not user:raise ApiError('Πρέπει να συνδεθείς.',401)
        if method=='POST':
            self.enforce_origin()
            csrf=self.headers.get('X-CSRF-Token','')
            if not hmac.compare_digest(csrf,user['csrf']):raise ApiError('Invalid CSRF token.',403)
            if path=='/api/auth/logout':
                with connection() as con:
                    auth.log(con,user,'LOGOUT')
                    auth.end_session(con,self.cookie_token())
                return self.send_json({'ok':True},headers={'Set-Cookie':self.cookie_header(expire=True)})
            if path=='/api/auth/password':
                data=self.body()
                with connection() as con:
                    u=con.execute('SELECT pass_hash FROM auth_users WHERE id=?',(user['id'],)).fetchone()
                    if not auth.verify_password(data.get('current_password',''),u['pass_hash']):raise ApiError('Ο τρέχων κωδικός είναι λάθος.',403)
                    try:new_pass=auth.hash_password(data.get('new_password'))
                    except ValueError as exc:raise ApiError(str(exc))
                    con.execute('UPDATE auth_users SET pass_hash=? WHERE id=?',(new_pass,user['id']))
                    con.execute('DELETE FROM auth_sessions WHERE user_id=?',(user['id'],))
                    auth.log(con,user,'PASSWORD_CHANGE')
                return self.send_json({'ok':True},headers={'Set-Cookie':self.cookie_header(expire=True)})
            if user['role']=='admin' and path=='/api/auth/users':
                data=self.body()
                with connection() as con:
                    try:
                        uid=auth.create_user(con,data.get('username'),data.get('password'),data.get('role','member'),data.get('display_name'))
                    except (ValueError,sqlite3.IntegrityError) as exc:raise ApiError(str(exc))
                    auth.log(con,user,'USER_CREATE',f'user_id={uid}')
                return self.send_json({'ok':True,'id':uid})
            if user['role']=='admin' and re.fullmatch(r'/api/auth/users/\d+',path):
                data=self.body()
                with connection() as con:
                    try:auth.edit_user(con,user,int(path.split('/')[-1]),data.get('role'),data.get('active'),data.get('password'))
                    except ValueError as exc:raise ApiError(str(exc))
                return self.send_json({'ok':True})
        if method=='GET' and path=='/api/auth/users' and user['role']=='admin':
            with connection() as con:return self.send_json({'users':auth.get_users(con)})
        raise ApiError('Δεν επιτρέπεται αυτή η ενέργεια.',403)
    def full_base(self,con):
        configured=settings(con).get('public_base_url') or os.environ.get('PUBLIC_BASE_URL','')
        if configured:return configured.rstrip('/')
        return f'http://{self.headers.get("Host", "localhost:8765")}'
    def handle_api(self,method,path):
        with connection() as con:
            if method=='GET':
                if path=='/api/stats':return stats(con)
                if path=='/api/locations':return list_locations(con)
                if path=='/api/items':return items_api(con,self.qp())
                if path=='/api/find':return find_items(con,self.qp().get('q',[''])[0])
                if re.fullmatch(r'/api/items/AR-\d+',path):return item_detail(con,path.split('/')[-1])
                if path=='/api/history':return history(con,self.qp())
                if path=='/api/settings':return dict(settings(con),computed_base=self.full_base(con))
                if path=='/api/ai/status':return ai_status()
                if path=='/api/loans':return v4.loan_rows(con)
                if path=='/api/alerts':return v4.alerts(con)
                if path=='/api/audits':return v4.get_audits(__import__(__name__))
                if re.fullmatch(r'/api/location/C\d{2}-S\d{2}',path):return v4.details_location(__import__(__name__),path.split('/')[-1])
            else:
                data=self.body()
                if path=='/api/movement':return transact(data)
                if path=='/api/category':return update_category(data)
                if path=='/api/items':return add_new_item(data)
                if path=='/api/locations':return add_new_location(data)
                if path=='/api/settings':return save_settings(data)
                if path=='/api/photos':return save_photo(data)
                if path=='/api/vision/search':return visual_search(data)
                if path=='/api/item/settings':return v4.item_settings(__import__(__name__),data)
                if path=='/api/location/settings':return v4.location_settings(__import__(__name__),data)
                if path=='/api/loan/settings':return v4.save_loan(__import__(__name__),data)
                if path=='/api/audit/shelf':return v4.audit_shelf(__import__(__name__),data)
                if path=='/api/audit/confirm':return v4.confirm_audit(__import__(__name__),data)
                if path=='/api/assistant':return v4.assistant(__import__(__name__),data)
                if path=='/api/ai/test':
                    if not gemini_configured():raise ApiError('Δεν έχει ρυθμιστεί το Gemini API key.',400)
                    try:return gemini_test()
                    except RuntimeError as exc:raise ApiError(str(exc),503)
        raise ApiError('Δεν υπάρχει αυτή η λειτουργία.',404)
    def do_GET(self):self.respond('GET')
    def do_POST(self):self.respond('POST')
    def respond(self,method):
        try:
            parsed=urlparse(self.path)
            path=unquote(parsed.path)
            if path.startswith('/api/auth/'):
                return self.auth_api(method,path)
            if path in ('/static/app.css','/static/app.js','/static/features_v4.js','/static/login.js') and method=='GET':
                extension='javascript' if path.endswith('.js') else 'css'
                return self.send_bytes((STATIC/Path(path).name).read_bytes(),content_type=f'text/{extension}; charset=utf-8')
            if path=='/health' and method=='GET':return self.send_json({'status':'ok'})
            if path=='/login' and method=='GET':
                if self.current_user():return self.send_redirect('/')
                return self.send_bytes((STATIC/'login.html').read_bytes(),content_type='text/html; charset=utf-8')
            user=self.current_user()
            if not user:
                if method=='GET' and not path.startswith('/api/'):
                    return self.send_redirect('/login')
                raise ApiError('Χρειάζεται σύνδεση.',401)
            if path.startswith('/api/'):
                self.require_session(method,path)
                result=self.handle_api(method,path)
                if method=='POST':
                    with connection() as con:auth.log(con,user,'API_WRITE',path)
                return self.send_json(result)
            if method!='GET':raise ApiError('Μη υποστηριζόμενη μέθοδος.',405)
            if path in ('/','/index.html') or re.fullmatch(r'/i/AR-\d+',path) or re.fullmatch(r'/l/C\d{2}-S\d{2}',path):
                return self.send_bytes((STATIC/'index.html').read_bytes(),content_type='text/html; charset=utf-8')
            if re.fullmatch(r'/media/(?:item|audit)/\d+',path) or re.fullmatch(r'/media/location/C\d{2}-S\d{2}',path):
                return self.render_photo(path)
            if re.fullmatch(r'/qr/(?:item/AR-\d+|location/C\d{2}-S\d{2})',path):
                return self.render_qr(path)
            if path=='/labels':return self.render_labels()
            if path=='/export/inventory.xlsx':return self.export_excel()
            if path=='/export/inventory.csv':return self.export_inventory()
            if path=='/export/history.csv':return self.export_history()
            raise ApiError('Η σελίδα δεν βρέθηκε.',404)
        except ApiError as exc:self.send_json({'error':str(exc)},exc.status)
        except Exception:
            import traceback; traceback.print_exc()
            self.send_json({'error':'Εσωτερικό σφάλμα του διακομιστή.'},500)
    def send_redirect(self,location):
        self.send_response(303)
        self.send_header('Location',location)
        self.send_header('Cache-Control','no-store')
        self.send_header('Content-Length','0')
        self.end_headers()
    def render_photo(self,path):
        parts=path.strip('/').split('/')
        kind,ident=parts[1],parts[2]
        with connection() as con:
            if kind=='item':
                if not con.execute('SELECT 1 FROM item_photos WHERE id=?',(int(ident),)).fetchone():raise ApiError('Η φωτογραφία δεν βρέθηκε.',404)
            elif kind=='audit':
                if not con.execute('SELECT 1 FROM shelf_audits WHERE id=?',(int(ident),)).fetchone():raise ApiError('Η οπτική απογραφή δεν βρέθηκε.',404)
            else:
                if not con.execute('SELECT 1 FROM location_photos WHERE location_id=?',(ident,)).fetchone():raise ApiError('Η φωτογραφία δεν βρέθηκε.',404)
        fname=f'item-{ident}.jpg' if kind=='item' else f'audit-{ident}.jpg' if kind=='audit' else f'location-{ident}.jpg'
        target=MEDIA/fname
        if not target.is_file():raise ApiError('Η φωτογραφία λείπει από τον δίσκο.',404)
        self.send_bytes(target.read_bytes(),content_type='image/jpeg')
    def render_qr(self,path):
        try:import qrcode
        except ImportError:raise ApiError('Χρειάζεται εγκατάσταση της βιβλιοθήκης qrcode. Δες το README.',503)
        args=self.qp()
        kind,ident=path.split('/')[2:4]
        with connection() as con:
            if kind=='item':item_by_id(con,ident)
            else:location_by_id(con,ident)
            base=args.get('base',[''])[0].strip().rstrip('/') or self.full_base(con)
        address=f'{base}/{"i" if kind=="item" else "l"}/{ident}'
        pic=qrcode.make(address,box_size=6,border=2)
        output=io.BytesIO();pic.save(output,format='PNG')
        self.send_bytes(output.getvalue(),content_type='image/png')
    def render_labels(self):
        p=self.qp();category=p.get('category',[''])[0];loc=p.get('location',[''])[0]
        typ=p.get('type',['both'])[0]
        if typ not in ('both','items','locations'):typ='both'
        with connection() as con:
            base=self.full_base(con)
            items=items_api(con,{'category':[category],'location':[loc]}) if typ in ('items','both') else []
            locs=list_locations(con) if typ in ('locations','both') else []
            if loc:locs=[l for l in locs if l['id']==loc]
            cards=[]
            for x in items:
                img=f'/qr/item/{x["sku"]}?{urlencode({"base":base})}'
                cards.append(f'<article class="label"><img src="{html.escape(img,quote=True)}"><div><strong>{html.escape(x["name"])}</strong><small>{html.escape(x["sku"])} · {html.escape(x["default_location"] or "χωρίς θέση")}</small><small>{html.escape(x["category"])}</small></div></article>')
            for x in locs:
                if x['id']=='C99-S00': continue
                img=f'/qr/location/{x["id"]}?{urlencode({"base":base})}'
                cards.append(f'<article class="label location"><img src="{html.escape(img,quote=True)}"><div><strong>{html.escape(x["label"])}</strong><small>{html.escape(x["id"])}</small><small>QR θέσης</small></div></article>')
        document='''<!doctype html><html lang="el"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>QR Ετικέτες — Aegean Robotics</title><style>
          *{box-sizing:border-box}body{font:14px system-ui,Arial;margin:24px;color:#162a3a}.toolbar{margin-bottom:20px}.toolbar button{padding:10px 20px;cursor:pointer}.labels{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}.label{display:flex;align-items:center;gap:8px;border:1px dashed #8394a6;border-radius:6px;padding:7px;height:105px;break-inside:avoid;overflow:hidden}.label img{width:88px;height:88px;object-fit:contain}.label div{min-width:0}.label strong{font-size:12px;line-height:1.25;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}.label small{display:block;font-size:10px;margin-top:6px;overflow-wrap:anywhere;color:#576476}.location{border:1.5px solid #155e75}@media print{body{margin:8mm}.toolbar{display:none}.labels{grid-template-columns:repeat(3,1fr)}@page{size:A4;margin:8mm}}@media(max-width:720px){.labels{grid-template-columns:repeat(2,1fr)}}
          </style></head><body><div class="toolbar"><h1>QR ετικέτες</h1><p>Οι κωδικοί οδηγούν στο <strong>SERVER_BASE</strong>. Βεβαιώσου ότι αυτή η διεύθυνση ανοίγει και από το κινητό. </p><button onclick="window.print()">🖨️ Εκτύπωση</button> <a href="/">Επιστροφή</a></div><main class="labels">CARDS</main></body></html>'''
        document=document.replace('SERVER_BASE',html.escape(base)).replace('CARDS',''.join(cards))
        self.send_bytes(document.encode('utf-8'),content_type='text/html; charset=utf-8')
    def export_excel(self):
        payload=v4.export_live_xlsx(__import__(__name__))
        self.send_bytes(payload,content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',attachment='Aegean_Robotics_Inventory_Live.xlsx')
    def export_inventory(self):
        with connection() as con:
            rows=items_api(con,{})
            dest=io.StringIO();wr=csv.writer(dest)
            wr.writerow(['SKU','Name','Category','On Hand','Checked Out','Original Location','Notes','Original SUB.2 Row','Quantity Unverified'])
            for x in rows:wr.writerow([x['sku'],x['name'],x['category'],x['on_hand'] if x['on_hand'] is not None else '',x['checked_out'],x['default_location'] or '',x['notes'],x['source_row'] or '',x['quantity_unknown']])
        self.send_bytes(('\ufeff'+dest.getvalue()).encode('utf-8'),content_type='text/csv; charset=utf-8',attachment='Aegean_Inventory.csv')
    def export_history(self):
        with connection() as con:
            rows=con.execute('SELECT * FROM movements ORDER BY id').fetchall()
            dest=io.StringIO();wr=csv.writer(dest)
            wr.writerow(['ID','Date','SKU','Action','Qty','From','To','Holder','Note','Issue ID'])
            for x in rows:wr.writerow([x['id'],x['ts'],x['sku'],x['action'],x['quantity'],x['from_location'] or '',x['to_location'] or '',x['holder'],x['note'],x['issue_id'] or ''])
        self.send_bytes(('\ufeff'+dest.getvalue()).encode('utf-8'),content_type='text/csv; charset=utf-8',attachment='Aegean_Movements.csv')


def serve(host='127.0.0.1',port=8765,open_browser=False):
    init_database()
    srv=ThreadingHTTPServer((host,port),Handler)
    print(f'\nAegean Smart Inventory: http://localhost:{port}\n')
    print('Για κινητό: εκτέλεσε με --host 0.0.0.0 σε ΕΜΠΙΣΤΟ τοπικό Wi-Fi και άνοιξε την IP του υπολογιστή.')
    print('Σύνδεση χρήστη: υποχρεωτική. Δημιούργησε τον πρώτο διαχειριστή με CREATE_ADMIN_WINDOWS.bat.')
    print('Για δημόσιο Internet απαιτείται HTTPS reverse proxy και έλεγχος ασφάλειας, όχι απλό άνοιγμα θύρας.\n')
    if open_browser:
        import webbrowser
        threading.Timer(0.6, lambda: webbrowser.open(f'http://127.0.0.1:{port}')).start()
    try:srv.serve_forever()
    except KeyboardInterrupt:pass
    finally:srv.server_close()

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--host',default='127.0.0.1')
    parser.add_argument('--port',default=8765,type=int)
    parser.add_argument('--open',action='store_true',help='Open local browser after the server is ready')
    options=parser.parse_args()
    serve(options.host,options.port,open_browser=options.open)
