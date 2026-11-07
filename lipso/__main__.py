"""Command-line interface for the same workspace and engines used by the UI."""
import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

from .answers import answer
from .calendar_export import export_calendar
from .extract import InputError
from .planner import simulate
from .store import Store
from .paths import default_data_directory, workspace_database


def write_new(path, content):
    with Path(path).open('xb') as file:
        file.write(content)


def backup(store, destination):
    target = Path(destination)
    # Exclusive creation: a typo cannot silently replace another backup.
    with target.open('xb'):
        pass
    try:
        with store.connection() as source:
            destination_db = sqlite3.connect(target)
            try:
                source.backup(destination_db)
            finally:
                destination_db.close()
    except Exception:
        target.unlink(missing_ok=True)
        raise


def main():
    parser = argparse.ArgumentParser(prog='python3 -m lipso', description='Lipso document and planning tools')
    parser.add_argument('--data', type=Path, default=default_data_directory())
    commands = parser.add_subparsers(dest='command', required=True)
    ingest = commands.add_parser('import', help='Import a local document')
    ingest.add_argument('file', type=Path)
    ingest.add_argument('--collection', default='Unsorted')
    ingest.add_argument('--title', default='')
    ingest.add_argument('--effective')
    ingest.add_argument('--replaces')
    commands.add_parser('list', help='List documents, findings, and commitments')
    ask = commands.add_parser('ask', help='Find source-grounded answers')
    ask.add_argument('question')
    ask.add_argument('--collection')
    ask.add_argument('--as-of')
    model = commands.add_parser('simulate', help='Simulate an exported plan JSON file')
    model.add_argument('file', type=Path)
    model.add_argument('--runs', type=int, default=400)
    model.add_argument('--seed', type=int, default=1729)
    commands.add_parser('verify', help='Check original content, findings, plans, and audit records')
    for name, help_text in [('export', 'Export original files and structured records as ZIP'), ('calendar', 'Export open commitments as ICS'), ('backup', 'Create a consistent SQLite snapshot; never overwrites a file')]:
        sub = commands.add_parser(name, help=help_text)
        sub.add_argument('output', type=Path)
    args = parser.parse_args()
    try:
        if args.command == 'simulate':
            if args.file.stat().st_size > 300_000:
                raise InputError('The plan file is too large.')
            result = simulate(json.loads(args.file.read_text()), runs=args.runs, seed=args.seed)
        else:
            store = Store(workspace_database(args.data))
            if args.command == 'import':
                result = store.import_document(args.file.name, args.file.read_bytes(), matter=args.collection, title=args.title, effective_date=args.effective, replaces_id=args.replaces)
            elif args.command == 'list':
                result = store.snapshot()
            elif args.command == 'ask':
                result = answer(store, args.question, matter=args.collection, as_of=args.as_of)
            elif args.command == 'verify':
                result = store.integrity()
            elif args.command == 'backup':
                backup(store, args.output)
                result = {'saved': str(args.output), 'type': 'sqlite-snapshot'}
            else:
                content = store.export() if args.command == 'export' else export_calendar(store.snapshot())
                write_new(args.output, content)
                result = {'saved': str(args.output), 'bytes': len(content)}
        print(json.dumps(result, indent=2, ensure_ascii=False))
        if args.command == 'verify' and not result['ok']:
            return 1
    except (InputError, OSError, json.JSONDecodeError) as exc:
        print(f'Lipso: {exc}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
