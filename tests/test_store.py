import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from lipso.answers import answer
from lipso.calendar_export import export_calendar
from lipso.extract import InputError
from lipso.store import Store


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / 'lipso.db')

    def tearDown(self):
        self.tmp.cleanup()

    def add(self, text, **options):
        return self.store.import_document('test.txt', text.encode(), **options)['id']

    def test_duplicate_is_idempotent_within_collection(self):
        original = self.add('Monthly rent: USD 100.', matter='Lease')
        duplicate = self.store.import_document('renamed.txt', b'Monthly rent: USD 100.', matter='Lease')
        self.assertEqual(original, duplicate['id'])
        self.assertTrue(duplicate['duplicate'])
        self.assertEqual(len(self.store.snapshot()['audit']), 1)
        self.assertNotEqual(original, self.add('Monthly rent: USD 100.', matter='Other lease'))

    def test_future_replacement_does_not_replace_current_source(self):
        old = self.add('Monthly rent: USD 100.', matter='Lease', effective_date='2026-01-01')
        new = self.add('Monthly rent: USD 120.', matter='Lease', effective_date='2027-01-01', replaces_id=old)
        before = self.store.snapshot('2026-06-01')
        after = self.store.snapshot('2027-06-01')
        self.assertEqual({d['id']: d['state'] for d in before['documents']}, {old: 'current', new: 'upcoming'})
        self.assertEqual({d['id']: d['state'] for d in after['documents']}, {old: 'superseded', new: 'current'})
        self.assertEqual(before['conflicts'], [])
        self.assertEqual(after['changes'][0]['before'][0]['display'], 'USD 100.00')

    def test_transitive_replacements(self):
        a = self.add('Monthly rent: USD 100.', matter='Lease')
        b = self.add('Monthly rent: USD 200.', matter='Lease', replaces_id=a)
        c = self.add('Monthly rent: USD 300.', matter='Lease', replaces_id=b)
        self.assertEqual([d['id'] for d in self.store.snapshot()['documents'] if d['state'] == 'current'], [c])

    def test_replacement_must_share_collection_and_not_fork(self):
        a = self.add('Monthly rent: USD 100.', matter='Lease')
        with self.assertRaises(InputError):
            self.add('Monthly rent: USD 200.', matter='Other', replaces_id=a)
        self.add('Monthly rent: USD 300.', matter='Lease', replaces_id=a)
        with self.assertRaises(InputError):
            self.add('Monthly rent: USD 400.', matter='Lease', replaces_id=a)

    def test_conflicts_respect_collection_currency_and_review(self):
        self.add('Monthly rent: USD 100.', matter='Lease')
        b = self.add('Monthly rent: USD 200.', matter='Lease')
        self.add('Monthly rent: EUR 500.', matter='Lease')
        self.add('Monthly rent: USD 600.', matter='Other lease')
        conflicts = self.store.snapshot()['conflicts']
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(len(conflicts[0]['facts']), 2)
        fact = self.store.document(b)['facts'][0]
        self.store.review_fact(fact['id'], 'confirmed')
        self.assertEqual(len(self.store.snapshot()['conflicts']), 1)
        self.store.review_fact(fact['id'], 'dismissed')
        self.assertEqual(self.store.snapshot()['conflicts'], [])

    def test_search_citations_and_current_only(self):
        a = self.add('Monthly rent: USD 100.\nThe courtyard includes a pear tree.', matter='Lease')
        self.add('Monthly rent: USD 200.\nThe garden includes lavender.', matter='Lease', replaces_id=a)
        self.assertTrue(self.store.search('courtyard'))
        self.assertFalse(self.store.search('courtyard', current_only=True))
        result = self.store.search('lavender')[0]
        document = self.store.document(result['document_id'])
        self.assertEqual(document['text'][result['start']:result['end']], result['quote'])

    def test_search_query_syntax_is_escaped(self):
        self.add('A plain text note about rent.')
        for query in ['" OR * NEAR(', 'rent: title', '---', 'OR 1=1', "'; DROP TABLE documents;--"]:
            self.assertIsInstance(self.store.search(query), list)
        self.assertEqual(len(self.store.snapshot()['documents']), 1)

    def test_unknown_question_abstains(self):
        self.add('Monthly rent: USD 100.')
        response = answer(self.store, 'Tell me about the astronaut giraffe')
        self.assertEqual(response['citations'], [])
        self.assertIn('enough evidence', response['title'])

    def test_rent_question_retains_conflicting_values(self):
        self.add('Monthly rent: USD 100.', matter='Lease')
        self.add('Monthly rent: USD 200.', matter='Lease')
        response = answer(self.store, 'What is the rent?', matter='Lease')
        self.assertEqual(len(response['citations']), 2)
        self.assertEqual(len(response['conflicts']), 1)

    def test_actions_persist_and_calendar_escapes(self):
        identifier = self.add('Payment due 2026-12-31.', matter='Lease; unit, one')
        fact = self.store.document(identifier)['facts'][0]
        raw = export_calendar(self.store.snapshot('2026-11-01')).decode()
        self.assertIn('DTSTART;VALUE=DATE:20261231', raw)
        self.assertIn(r'Lease\; unit\, one', raw)
        self.store.update_action(fact['id'], 'completed', 'Paid')
        other = Store(self.store.location)
        self.assertEqual(other.snapshot()['obligations'][0]['action_state'], 'completed')
        self.assertNotIn('BEGIN:VEVENT', export_calendar(other.snapshot()).decode())

    def test_delete_removes_original_and_search_index(self):
        identifier = self.add('Monthly rent: USD 100.\nPomegranate trees.')
        self.store.delete_document(identifier)
        self.assertEqual(self.store.search('pomegranate'), [])
        self.assertEqual(self.store.snapshot()['facts'], [])
        with self.assertRaises(InputError):
            self.store.original(identifier)
        self.assertTrue(self.store.integrity()['ok'])

    def test_deleted_evidence_ids_are_never_reused(self):
        old = self.add('Monthly rent: USD 100.')
        old_id = self.store.document(old)['facts'][0]['id']
        self.store.delete_document(old)
        new = self.add('Monthly rent: USD 300.')
        self.assertGreater(self.store.document(new)['facts'][0]['id'], old_id)

    def test_integrity_detects_content_and_log_corruption(self):
        identifier = self.add('Monthly rent: USD 100.')
        self.assertTrue(self.store.integrity()['ok'])
        with self.store.connection(write=True) as db:
            db.execute('UPDATE documents SET raw=? WHERE id=?', (b'changed', identifier))
            db.execute("UPDATE audit SET payload='{}' WHERE sequence=1")
        types = {issue['type'] for issue in self.store.integrity()['issues']}
        self.assertTrue({'original_checksum', 'audit_chain', 'audit_payload', 'import_record'} <= types)

    def test_integrity_checks_findings_against_source(self):
        identifier = self.add('Monthly rent: USD 100.')
        with self.store.connection(write=True) as db:
            db.execute("UPDATE facts SET value='999.00' WHERE document_id=?", (identifier,))
        self.assertIn('finding_evidence', {issue['type'] for issue in self.store.integrity()['issues']})

    def test_integrity_detects_unlogged_removal_of_findings(self):
        identifier = self.add('Monthly rent: USD 100.')
        with self.store.connection(write=True) as db:
            db.execute('DELETE FROM facts WHERE document_id=?', (identifier,))
        self.assertIn('missing_findings', {issue['type'] for issue in self.store.integrity()['issues']})

    def test_conflicting_word_in_question_routes_to_conflicts(self):
        self.add('Monthly rent: USD 100.', matter='Lease')
        self.add('Monthly rent: USD 200.', matter='Lease')
        self.assertEqual(answer(self.store, 'Any conflicting terms?')['kind'], 'conflicts')

    def test_export_preserves_originals_and_facts(self):
        identifier = self.add('Monthly rent: USD 100.')
        archive = zipfile.ZipFile(io.BytesIO(self.store.export()))
        manifest = json.loads(archive.read('manifest.json'))
        self.assertEqual(archive.read(manifest['documents'][0]['original_path']), b'Monthly rent: USD 100.')
        self.assertEqual(manifest['documents'][0]['id'], identifier)
        self.assertEqual(len(manifest['facts']), 1)
