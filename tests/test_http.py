import base64
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from lipso.server import make_server
from lipso.store import Store


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.store = Store(Path(cls.tmp.name) / 'http.db')
        cls.server = make_server(cls.store, 0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = 'http://127.0.0.1:' + str(cls.server.server_address[1])

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(2)
        cls.tmp.cleanup()

    def request(self, path, method='GET', data=None, headers=None):
        request_headers = {'Content-Type': 'application/json', 'X-Lipso-Client': 'workspace'}
        request_headers.update(headers or {})
        body = json.dumps(data).encode() if data is not None else None
        request = urllib.request.Request(self.base + path, data=body, method=method, headers=request_headers)
        try:
            response = urllib.request.urlopen(request, timeout=10)
            self.addCleanup(response.close)
            return response
        except urllib.error.HTTPError as error:
            self.addCleanup(error.close)
            return error

    def test_local_workspace_html_and_csp(self):
        response = self.request('/')
        self.assertEqual(response.status, 200)
        self.assertIn("frame-ancestors 'none'", response.headers['Content-Security-Policy'])
        self.assertIn(b'Lipso', response.read())

    def test_import_and_download_preserve_bytes(self):
        content = 'Monthly rent: EUR 42.00.\nPayment due on 2027-12-31.'.encode()
        response = self.request('/api/documents', 'POST', {'filename': 'lease.txt', 'matter': 'HTTP lease', 'replaces_id': '', 'content_base64': base64.b64encode(content).decode()})
        self.assertEqual(response.status, 201)
        identifier = json.load(response)['id']
        original = self.request(f'/api/documents/{identifier}/original')
        self.assertEqual(original.read(), content)
        self.assertIn('attachment', original.headers['Content-Disposition'])

    def test_dns_rebinding_host_rejected(self):
        self.assertEqual(self.request('/api/state', headers={'Host': 'evil.example'}).status, 403)

    def test_cross_origin_read_and_write_rejected(self):
        self.assertEqual(self.request('/api/state', headers={'Origin': 'https://evil.example'}).status, 403)
        self.assertEqual(self.request('/api/demo', 'POST', {}, {'Origin': 'https://evil.example'}).status, 403)

    def test_mutation_requires_workspace_header(self):
        self.assertEqual(self.request('/api/demo', 'POST', {}, {'X-Lipso-Client': ''}).status, 403)

    def test_static_file_allowlist_protects_database_and_code(self):
        for path in ['/app.py', '/lipso/store.py', '/.margin-data/margin.sqlite3', '/%2e%2e/app.py', '/package.json']:
            with self.subTest(path=path):
                self.assertEqual(self.request(path).status, 404)

    def test_invalid_input_is_an_error_not_partial_import(self):
        before = len(self.store.snapshot()['documents'])
        response = self.request('/api/documents', 'POST', {'filename': 'bad.txt', 'content_base64': '%invalid'})
        self.assertEqual(response.status, 400)
        self.assertEqual(len(self.store.snapshot()['documents']), before)

    def test_invalid_plan_returns_user_error(self):
        response = self.request('/api/plans', 'POST', {'data': {'name': 'broken'}})
        self.assertEqual(response.status, 400)

    def test_unknown_route_and_empty_question(self):
        self.assertEqual(self.request('/api/not-real').status, 404)
        self.assertEqual(self.request('/api/ask', 'POST', {'question': ''}).status, 400)

    def test_body_must_be_object(self):
        self.assertEqual(self.request('/api/ask', 'POST', []).status, 400)

    def test_head_has_headers_without_body(self):
        response = self.request('/api/state', 'HEAD')
        self.assertEqual(response.status, 200)
        self.assertGreater(int(response.headers['Content-Length']), 0)
        self.assertEqual(response.read(), b'')


class EmbeddedHTTPTests(unittest.TestCase):
    def test_android_session_and_bundled_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'index.html').write_text('Bundled Android workspace')
            server = make_server(Store(root / 'workspace.db'), 0, web=root, session_token='secret-session')
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f'http://127.0.0.1:{server.server_address[1]}'
            try:
                for cookie in ['', 'lipso_session=wrong', 'lipso_session="malformed', 'lipso_session="é"']:
                    with self.subTest(cookie=cookie):
                        request = urllib.request.Request(base + '/api/state', headers={'Cookie': cookie})
                        with self.assertRaises(urllib.error.HTTPError) as error:
                            urllib.request.urlopen(request, timeout=5)
                        self.assertEqual(error.exception.code, 403)
                        error.exception.close()
                for path in ['/', '/api/state']:
                    request = urllib.request.Request(base + path, headers={'Cookie': 'lipso_session=secret-session'})
                    with urllib.request.urlopen(request, timeout=5) as response:
                        self.assertEqual(response.status, 200)
                        if path == '/': self.assertEqual(response.read(), b'Bundled Android workspace')
                request = urllib.request.Request(base + '/api/demo', data=b'{}', headers={
                    'Cookie': 'lipso_session=secret-session', 'Content-Type': 'application/json'})
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(request, timeout=5)
                self.assertEqual(error.exception.code, 403)
                error.exception.close()
                request.add_header('X-Lipso-Client', 'workspace')
                with urllib.request.urlopen(request, timeout=5) as response:
                    self.assertEqual(response.status, 201)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(2)
