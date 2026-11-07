import io
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from lipso.__main__ import backup
from lipso.store import Store

ROOT = Path(__file__).resolve().parent.parent


class CLITests(unittest.TestCase):
    def test_cli_import_ask_and_verify(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / 'lease.txt'
            file.write_text('Monthly rent: USD 123.45.')
            prefix = [sys.executable, '-m', 'lipso', '--data', str(Path(tmp) / 'data')]
            imported = subprocess.run(prefix + ['import', str(file), '--collection', 'Lease'], cwd=ROOT, text=True, capture_output=True, check=True)
            self.assertFalse(json.loads(imported.stdout)['duplicate'])
            answer = subprocess.run(prefix + ['ask', 'What is the rent?'], cwd=ROOT, text=True, capture_output=True, check=True)
            self.assertEqual(json.loads(answer.stdout)['citations'][0]['display'], 'USD 123.45')
            report = subprocess.run(prefix + ['verify'], cwd=ROOT, text=True, capture_output=True, check=True)
            self.assertTrue(json.loads(report.stdout)['ok'])

    def test_consistent_backup_restores_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'original.db')
            identifier = store.import_document('lease.txt', b'Monthly rent: USD 123.45.')['id']
            target = Path(tmp) / 'snapshot.db'
            backup(store, target)
            with self.assertRaises(FileExistsError):
                backup(store, target)
            restored = Store(target)
            self.assertTrue(restored.integrity()['ok'])
            self.assertEqual(restored.original(identifier)[1], b'Monthly rent: USD 123.45.')
