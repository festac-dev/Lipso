from __future__ import annotations

import base64
import binascii
import json
import mimetypes
import re
import secrets
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlsplit

from .answers import answer
from .calendar_export import export_calendar
from .demo import seed_demo
from .extract import InputError, MAX_FILE
from .planner import simulate, scenario

WEB = Path(__file__).resolve().parent.parent / 'web'
MAX_BODY = (MAX_FILE * 4 // 3) + 65536


def handler_for(store):
    class Handler(BaseHTTPRequestHandler):
        server_version = 'Lipso/1.0'

        def log_message(self, format, *args):
            # Avoid logging document titles, query strings, or file contents.
            if str(args[1] if len(args) > 1 else '').startswith('5'):
                super().log_message(format, *args)

        def _headers(self, status=200, content_type='application/json; charset=utf-8', length=0, disposition=None):
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(length))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('X-Frame-Options', 'DENY')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
            if disposition:
                self.send_header('Content-Disposition', disposition)
            self.end_headers()

        def send_json(self, value, status=200):
            raw = json.dumps(value, ensure_ascii=False).encode()
            self._headers(status, length=len(raw))
            if self.command != 'HEAD':
                self.wfile.write(raw)

        def _guard(self, mutation=False):
            # Loopback Host validation prevents DNS rebinding. Custom headers +
            # no CORS prevent drive-by form posts from other websites.
            host = self.headers.get('Host', '')
            expected_port = self.server.server_address[1]
            if host not in {f'127.0.0.1:{expected_port}', f'localhost:{expected_port}'}:
                self.send_json({'error': 'Use the localhost address printed by Lipso.'}, 403)
                return False
            origin = self.headers.get('Origin')
            if origin and origin not in {f'http://127.0.0.1:{expected_port}', f'http://localhost:{expected_port}'}:
                self.send_json({'error': 'Cross-origin requests are not allowed.'}, 403)
                return False
            # Keep already-open browser tabs and local clients working after the rename.
            client_header = self.headers.get('X-Lipso-Client') or self.headers.get('X-Margin-Client')
            if mutation and client_header != 'workspace':
                self.send_json({'error': 'Missing local workspace request header.'}, 403)
                return False
            return True

        def body(self):
            length = self.headers.get('Content-Length', '')
            if not length.isdigit() or int(length) > MAX_BODY:
                raise InputError('The request is missing a length or is larger than 16 MB.')
            if self.headers.get_content_type() != 'application/json':
                raise InputError('Expected an application/json request.')
            try:
                value = json.loads(self.rfile.read(int(length)))
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise InputError('The request contains invalid JSON.') from exc
            if not isinstance(value, dict):
                raise InputError('Expected a JSON object.')
            return value

        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            if not self._guard():
                return
            try:
                parsed = urlsplit(self.path)
                path = unquote(parsed.path)
                query = {key: values[0] for key, values in parse_qs(parsed.query).items()}
                if path == '/api/state':
                    self.send_json(store.snapshot(query.get('as_of')))
                elif path == '/api/plans':
                    self.send_json({'plans': store.plans()})
                elif path == '/api/calendar':
                    raw = export_calendar(store.snapshot())
                    self._headers(content_type='text/calendar; charset=utf-8', length=len(raw), disposition='attachment; filename="lipso-commitments.ics"')
                    if self.command != 'HEAD':
                        self.wfile.write(raw)
                elif re.fullmatch(r'/api/plans/[a-f0-9]{32}', path):
                    self.send_json(store.plan(path.split('/')[-1]))
                elif path == '/api/search':
                    self.send_json({'results': store.search(query.get('q', ''), matter=query.get('matter'), current_only=query.get('current') == 'true', as_of=query.get('as_of'))})
                elif path == '/api/integrity':
                    self.send_json(store.integrity())
                elif path == '/api/export':
                    raw = store.export()
                    self._headers(content_type='application/zip', length=len(raw), disposition='attachment; filename="lipso-workspace.zip"')
                    if self.command != 'HEAD':
                        self.wfile.write(raw)
                elif re.fullmatch(r'/api/documents/[a-f0-9]{32}/original', path):
                    filename, raw = store.original(path.split('/')[3])
                    self._headers(content_type='application/octet-stream', length=len(raw), disposition="attachment; filename*=UTF-8''" + quote(filename, safe=''))
                    if self.command != 'HEAD':
                        self.wfile.write(raw)
                elif re.fullmatch(r'/api/documents/[a-f0-9]{32}', path):
                    self.send_json(store.document(path.split('/')[3]))
                elif path in {'/', '/index.html', '/style.css', '/app.js', '/theme.js', '/icon.svg'}:
                    file = WEB / ('index.html' if path == '/' else path[1:])
                    raw = file.read_bytes()
                    mime = {'.js': 'text/javascript', '.css': 'text/css', '.html': 'text/html', '.svg': 'image/svg+xml'}[file.suffix]
                    self._headers(content_type=mime + '; charset=utf-8', length=len(raw))
                    if self.command != 'HEAD':
                        self.wfile.write(raw)
                else:
                    self.send_json({'error': 'Not found.'}, 404)
            except InputError as exc:
                self.send_json({'error': str(exc)}, 400)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception:
                traceback.print_exc()
                self.send_json({'error': 'An internal error occurred. Your original files have not been changed.'}, 500)

        def do_POST(self):
            self.mutate('POST')

        def do_PATCH(self):
            self.mutate('PATCH')

        def do_DELETE(self):
            self.mutate('DELETE')

        def mutate(self, method):
            if not self._guard(mutation=True):
                return
            try:
                path = urlsplit(self.path).path
                data = self.body() if method != 'DELETE' else {}
                if method == 'POST' and path == '/api/documents':
                    encoded = data.get('content_base64', '')
                    if not isinstance(encoded, str) or len(encoded) > MAX_BODY:
                        raise InputError('Invalid file content.')
                    try:
                        content = base64.b64decode(encoded, validate=True)
                    except (ValueError, binascii.Error) as exc:
                        raise InputError('Invalid file encoding.') from exc
                    result = store.import_document(data.get('filename', ''), content, matter=data.get('matter', 'Unsorted'),
                                                   title=data.get('title', ''), effective_date=data.get('effective_date'), replaces_id=data.get('replaces_id'))
                    self.send_json(result, 200 if result['duplicate'] else 201)
                elif method == 'POST' and path == '/api/ask':
                    self.send_json(answer(store, data.get('question'), data.get('matter'), data.get('as_of')))
                elif method == 'POST' and path == '/api/plans':
                    self.send_json(store.save_plan(data.get('data'), parent_id=data.get('parent_id')), 201)
                elif method == 'PATCH' and re.fullmatch(r'/api/plans/[a-f0-9]{32}', path):
                    self.send_json(store.save_plan(data.get('data'), identifier=path.split('/')[-1]))
                elif method == 'POST' and path == '/api/simulate':
                    plan = data.get('data')
                    if data.get('scenario'):
                        plan = scenario(plan, data['scenario'])
                    result = simulate(plan, runs=400)
                    result['evidence'] = store.plan_evidence(plan)
                    result['warnings'] += result['evidence']['warnings']
                    self.send_json(result)
                elif method == 'POST' and re.fullmatch(r'/api/plans/[a-f0-9]{32}/branch', path):
                    identifier = path.split('/')[3]
                    original = store.plan(identifier)
                    variant = scenario(original['data'], data.get('edits', {}))
                    variant['name'] = data.get('name') or original['name'] + ' · alternate'
                    self.send_json(store.save_plan(variant, parent_id=identifier), 201)
                elif method == 'POST' and path == '/api/demo':
                    if store.snapshot()['documents']:
                        raise InputError('Sample records can only be loaded into an empty workspace.')
                    self.send_json(seed_demo(store), 201)
                elif method == 'PATCH' and re.fullmatch(r'/api/facts/\d+', path):
                    store.review_fact(int(path.split('/')[-1]), data.get('status'))
                    self.send_json({'ok': True})
                elif method == 'PATCH' and re.fullmatch(r'/api/actions/\d+', path):
                    store.update_action(int(path.split('/')[-1]), data.get('state'), data.get('note', ''))
                    self.send_json({'ok': True})
                elif method == 'DELETE' and re.fullmatch(r'/api/documents/[a-f0-9]{32}', path):
                    store.delete_document(path.split('/')[-1])
                    self.send_json({'ok': True})
                elif method == 'DELETE' and re.fullmatch(r'/api/plans/[a-f0-9]{32}', path):
                    store.delete_plan(path.split('/')[-1])
                    self.send_json({'ok': True})
                else:
                    self.send_json({'error': 'Not found.'}, 404)
            except InputError as exc:
                self.send_json({'error': str(exc)}, 400)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception:
                traceback.print_exc()
                self.send_json({'error': 'An internal error occurred. The change was not completed.'}, 500)

    return Handler


def make_server(store, port=3000):
    server = ThreadingHTTPServer(('127.0.0.1', port), handler_for(store))
    server.daemon_threads = True
    return server
