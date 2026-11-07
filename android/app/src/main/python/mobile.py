"""One authenticated, app-private workspace per Android process."""
import secrets
import threading
from pathlib import Path

from lipso.server import make_server
from lipso.store import Store

_lock = threading.Lock()
_server = None
_session = None


def start(files_directory):
    global _server, _session
    with _lock:
        if _server is None:
            store = Store(Path(files_directory) / 'workspace' / 'lipso.sqlite3')
            token = secrets.token_urlsafe(32)
            _server = make_server(store, 0, web=Path(__file__).parent / 'web', session_token=token)
            threading.Thread(target=_server.serve_forever, name='Lipso HTTP', daemon=True).start()
            _session = {'url': f'http://127.0.0.1:{_server.server_address[1]}', 'token': token}
        return _session
