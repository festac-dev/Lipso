#!/usr/bin/env python3
"""Run with: python3 app.py [--port 3000] [--data .lipso-data] [--demo]."""
import argparse
from pathlib import Path

from lipso.demo import seed_demo
from lipso.server import make_server
from lipso.store import Store
from lipso.paths import default_data_directory, workspace_database


def main():
    parser = argparse.ArgumentParser(description='Lipso — a local document evidence workspace')
    parser.add_argument('--port', type=int, default=3000)
    parser.add_argument('--data', type=Path, default=default_data_directory())
    parser.add_argument('--demo', action='store_true', help='Load fictional sample records if the workspace is empty')
    args = parser.parse_args()
    store = Store(workspace_database(args.data))
    if args.demo and not store.snapshot()['documents']:
        seed_demo(store)
    try:
        server = make_server(store, args.port)
    except OSError as exc:
        parser.exit(1, f'Could not start Lipso: {exc}\nTry another port with --port 3001.\n')
    print(f'\n  Lipso is ready: http://127.0.0.1:{server.server_address[1]}\n  Workspace: {args.data.resolve()}\n  Press Ctrl+C to stop.\n', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nLipso stopped. Your workspace is saved.')
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
