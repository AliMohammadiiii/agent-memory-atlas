import contextlib
import gzip
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import io
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from preview import Handler,asset


class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.root=Path(self.directory.name).resolve()
        (self.root/'index.html').write_text('Synthetic public preview '*100)
        class Upstream(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                body=self.rfile.read(int(self.headers['Content-Length']))
                self.send_response(200);self.end_headers();self.wfile.write(body)
        self.upstream=ThreadingHTTPServer(('localhost',0),Upstream)
        self.server=ThreadingHTTPServer(('localhost',0),Handler)
        self.server.root=self.root;self.server.route='/agent-memory/';self.server.gateway='http://localhost:'+str(self.upstream.server_port)
        for server in (self.upstream,self.server):threading.Thread(target=server.serve_forever,daemon=True).start()
        self.base='http://localhost:'+str(self.server.server_port)

    def tearDown(self):
        for server in (self.server,self.upstream):server.shutdown();server.server_close()
        self.directory.cleanup();asset.cache_clear()

    def test_real_gzip_response_and_conditional_static_request(self):
        with urlopen(Request(self.base+'/agent-memory/',headers={'Accept-Encoding':'gzip'})) as response:
            self.assertEqual(response.headers['Content-Encoding'],'gzip')
            self.assertEqual(gzip.decompress(response.read()),(self.root/'index.html').read_bytes())
            etag=response.headers['ETag']
        with self.assertRaises(HTTPError) as caught:urlopen(Request(self.base+'/agent-memory/',headers={'If-None-Match':etag,'Accept-Encoding':'gzip'}))
        self.assertEqual(caught.exception.code,304)
        caught.exception.close()

    def test_question_proxy_uses_no_store_and_no_static_cache_or_logs(self):
        canary=b'{"question":"SYNTHETIC_CHAT_BODY"}'
        with contextlib.redirect_stderr(io.StringIO()) as captured:
            with urlopen(Request(self.base+'/agent-memory/api/ask',data=canary,headers={'Content-Type':'application/json'})) as response:
                self.assertEqual(response.read(),canary)
                self.assertEqual(response.headers['Cache-Control'],'no-store')
        self.assertNotIn('SYNTHETIC_CHAT_BODY',captured.getvalue())
        self.assertEqual(asset.cache_info().currsize,0)

    def test_static_path_cannot_escape_public_root(self):
        with self.assertRaises(HTTPError) as caught:urlopen(self.base+'/agent-memory/%2e%2e/not-public')
        self.assertEqual(caught.exception.code,403)
        caught.exception.close()
