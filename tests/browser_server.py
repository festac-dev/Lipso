import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lipso.demo import seed_demo
from lipso.server import make_server
from lipso.store import Store

with tempfile.TemporaryDirectory(prefix='lipso-browser-') as directory:
    store = Store(Path(directory) / 'lipso.db')
    seed_demo(store)
    server = make_server(store, 3091)
    print('Browser test workspace ready', flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
