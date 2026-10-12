"""Integration smoke tests: protected API, login, roles, CSRF, session, xlsx."""
import json
import os
import socket
import tempfile
import threading
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path
from http.server import ThreadingHTTPServer

with tempfile.TemporaryDirectory() as t:
    os.environ['INVENTORY_DB']=str(Path(t)/'inventory.db')
    import server, auth
    server.DB=Path(os.environ['INVENTORY_DB'])
    server.MEDIA=Path(t)/'photos'
    server.init_database()
    with server.connection() as c:
        admin_id=auth.create_user(c,'labadmin','A very strong user password!','admin','Lab Admin')
        member_id=auth.create_user(c,'labmember','Long member password 12345','member','Lab Member')
        viewer_id=auth.create_user(c,'labviewer','Long viewer password 12345','viewer','Lab Viewer')
    http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
    port=http.server_address[1]
    thr=threading.Thread(target=http.serve_forever,daemon=True);thr.start()
    origin=f'http://127.0.0.1:{port}'
    def client():return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
    def send(opener,path,method='GET',payload=None,csrf=None,origin_hdr=None):
        body=json.dumps(payload).encode() if payload is not None else None
        headers={'Content-Type':'application/json'} if body is not None else {}
        if csrf:headers['X-CSRF-Token']=csrf
        if origin_hdr:headers['Origin']=origin_hdr
        try:
            with opener.open(urllib.request.Request(origin+path,data=body,method=method,headers=headers),timeout=8) as r:
                response=r.read();return r.status,json.loads(response) if '/api/' in path else response
        except urllib.error.HTTPError as x:
            payload=x.read();return x.code,json.loads(payload) if '/api/' in path else payload
    try:
        a=client()
        assert send(a,'/api/stats')[0]==401
        assert send(a,'/export/inventory.xlsx')[0]==200 # urllib follows redirect to /login (status 200); ensure html not leaked
        r=send(a,'/export/inventory.xlsx')[1];assert b'loginForm' in r and not r.startswith(b'PK')
        bad=send(a,'/api/auth/login','POST',{'username':'labadmin','password':'wrong'},origin_hdr=origin)
        assert bad[0]==401,bad
        cross=send(a,'/api/auth/login','POST',{'username':'labadmin','password':'A very strong user password!'},origin_hdr='https://evil.example')
        assert cross[0]==403,cross
        logged=send(a,'/api/auth/login','POST',{'username':'labadmin','password':'A very strong user password!'},origin_hdr=origin)
        assert logged[0]==200,logged
        me=send(a,'/api/auth/me');assert me[0]==200 and me[1]['role']=='admin',me
        csrf=me[1]['csrf']
        assert send(a,'/api/locations')[0]==200
        assert send(a,'/api/settings','POST',{'public_base_url':'https://inventory.example.org'})[0]==403
        assert send(a,'/api/settings','POST',{'public_base_url':'https://inventory.example.org'},csrf,origin)[0]==200
        assert send(a,'/api/auth/users')[0]==200
        created=send(a,'/api/auth/users','POST',{'username':'newstudent','password':'A new long secure password','role':'viewer'},csrf,origin)
        assert created[0]==200,created
        edited=send(a,'/api/auth/users/'+str(created[1]['id']),'POST',{'active':False},csrf,origin)
        assert edited[0]==200,edited
        excel=send(a,'/export/inventory.xlsx');assert excel[0]==200 and excel[1][:2]==b'PK'
        v=client();assert send(v,'/api/auth/login','POST',{'username':'labviewer','password':'Long viewer password 12345'},origin_hdr=origin)[0]==200
        vm=send(v,'/api/auth/me')[1]
        assert send(v,'/api/stats')[0]==200
        assert send(v,'/api/movement','POST',{},vm['csrf'],origin)[0]==403
        assert send(v,'/api/auth/users')[0]==403
        m=client();assert send(m,'/api/auth/login','POST',{'username':'labmember','password':'Long member password 12345'},origin_hdr=origin)[0]==200
        mm=send(m,'/api/auth/me')[1]
        assert send(m,'/api/settings','POST',{},mm['csrf'],origin)[0]==403
        assert send(m,'/api/auth/users')[0]==403
        assert send(a,'/api/auth/logout','POST',{},csrf,origin)[0]==200
        assert send(a,'/api/stats')[0]==401
        print('PASS: guest blocked, login, CSRF, origin, admin, roles, export, logout')
    finally:http.shutdown();http.server_close()
