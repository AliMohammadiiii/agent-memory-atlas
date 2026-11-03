#!/usr/bin/env python3
"""Loopback production preview: gzip assets, private API proxy, no request logs."""
import argparse
from functools import lru_cache
import gzip
import hashlib
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import ipaddress
import mimetypes
from pathlib import Path
from urllib.parse import unquote,urlsplit
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError


@lru_cache(maxsize=64)
def asset(path,mtime,size,compressed):
    body=Path(path).read_bytes()
    if compressed:body=gzip.compress(body,compresslevel=6,mtime=0)
    return body,'"'+hashlib.sha256(body).hexdigest()+'"'


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass

    def respond(self,status,body=b'',content_type='text/plain; charset=utf-8',headers=None):
        self.send_response(status);self.send_header('Content-Type',content_type)
        self.send_header('Content-Length',str(len(body)));self.send_header('X-Content-Type-Options','nosniff')
        for key,value in (headers or {}).items():self.send_header(key,value)
        self.end_headers()
        if self.command!='HEAD':self.wfile.write(body)

    def do_HEAD(self):self.dispatch()
    def do_GET(self):self.dispatch()
    def do_POST(self):self.dispatch()

    def dispatch(self):
        path=urlsplit(self.path).path;route=self.server.route
        if path in ('/',route.rstrip('/')):
            return self.respond(302,headers={'Location':route,'Cache-Control':'no-store'})
        if not path.startswith(route):return self.respond(404,b'Not found')
        if path.startswith(route+'api/'):
            try:
                length=int(self.headers.get('Content-Length','0'))
                if length<0 or length>262144:return self.respond(413,b'Request too large')
                body=self.rfile.read(length) if self.command=='POST' else None
                suffix=self.path[len(route+'api/'):]
                request=Request(self.server.gateway+'/'+suffix,data=body,
                    headers={'Content-Type':'application/json'},method='GET' if self.command=='HEAD' else self.command)
                try:
                    with urlopen(request,timeout=240) as reply:status=reply.status;payload=reply.read()
                except HTTPError as error:status=error.code;payload=error.read()
                return self.respond(status,payload,'application/json',{'Cache-Control':'no-store'})
            except (URLError,TimeoutError,OSError,ValueError):
                return self.respond(503,b'{"error":"Local literature gateway is unavailable"}','application/json',{'Cache-Control':'no-store'})
        if self.command=='POST':return self.respond(405,b'Method not allowed')
        relative=unquote(path[len(route):]);candidate=(self.server.root/relative).resolve()
        if not candidate.is_relative_to(self.server.root):return self.respond(403,b'Not permitted')
        if candidate.is_dir():candidate=candidate/'index.html'
        if not candidate.is_file():
            if candidate.suffix:return self.respond(404,b'Not found')
            candidate=self.server.root/'index.html'
        if not candidate.is_file():return self.respond(404,b'Build the production site first')
        kind=mimetypes.guess_type(candidate.name)[0] or 'application/octet-stream'
        compress='gzip' in self.headers.get('Accept-Encoding','') and (kind.startswith('text/') or kind in ('application/json','application/javascript','image/svg+xml'))
        stat=candidate.stat();body,etag=asset(str(candidate),stat.st_mtime_ns,stat.st_size,compress)
        headers={'Vary':'Accept-Encoding','ETag':etag,'Cache-Control':'no-cache'}
        if compress:headers['Content-Encoding']='gzip'
        if self.headers.get('If-None-Match')==etag:return self.respond(304,headers=headers)
        return self.respond(200,body,kind,headers)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);parser.add_argument('--port',type=int,default=18090);parser.add_argument('--route',default='/agent-memory/');parser.add_argument('--gateway',default='http://localhost:18086');args=parser.parse_args()
    host=urlsplit(args.gateway).hostname
    try:loopback=host=='localhost' or ipaddress.ip_address(host).is_loopback
    except ValueError:loopback=False
    if not loopback or urlsplit(args.gateway).scheme not in ('http','https'):parser.error('The preview gateway must be a loopback endpoint')
    server=ThreadingHTTPServer(('localhost',args.port),Handler);server.root=args.root.resolve();server.route='/'+args.route.strip('/')+'/';server.gateway=args.gateway.rstrip('/')
    print('Preview: http://localhost:'+str(args.port)+server.route,flush=True)
    server.serve_forever()


if __name__=='__main__':main()
