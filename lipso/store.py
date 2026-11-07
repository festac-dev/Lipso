from __future__ import annotations

import hashlib
import io
import json
import re
import sqlite3
import threading
import uuid
import zipfile
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .extract import InputError, extract, read_document


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def digest(value):
    return hashlib.sha256(value if isinstance(value, bytes) else value.encode()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')


def short_text(value, field, limit=160, required=True):
    if not isinstance(value, str) or len(value.strip()) > limit or (required and not value.strip()):
        raise InputError(f'{field} must be text between {1 if required else 0} and {limit} characters.')
    return value.strip()


class Store:
    def __init__(self, location):
        self.location = Path(location)
        self.location.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        with self.connection() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, filename TEXT NOT NULL,
                    sha TEXT NOT NULL, text_sha TEXT NOT NULL, raw BLOB NOT NULL, text TEXT NOT NULL,
                    matter TEXT NOT NULL, effective_date TEXT, replaces_id TEXT REFERENCES documents(id) ON DELETE SET NULL,
                    imported_at TEXT NOT NULL, warnings TEXT NOT NULL, demo INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(sha, matter)
                );
                CREATE TABLE IF NOT EXISTS chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    ordinal INTEGER NOT NULL, start INTEGER NOT NULL, end INTEGER NOT NULL,
                    text TEXT NOT NULL, page INTEGER NOT NULL, line INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS chunk_document ON chunks(document_id);
                CREATE VIRTUAL TABLE IF NOT EXISTS search_index USING fts5(text, title, matter, tokenize='porter unicode61');
                CREATE TABLE IF NOT EXISTS facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    chunk_id INTEGER NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
                    key TEXT NOT NULL, label TEXT NOT NULL, value TEXT NOT NULL, display TEXT NOT NULL,
                    kind TEXT NOT NULL, unit TEXT NOT NULL, start INTEGER NOT NULL, end INTEGER NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('suggested','confirmed','dismissed'))
                );
                CREATE INDEX IF NOT EXISTS fact_document ON facts(document_id);
                CREATE TABLE IF NOT EXISTS actions (
                    fact_id INTEGER PRIMARY KEY REFERENCES facts(id) ON DELETE CASCADE,
                    state TEXT NOT NULL DEFAULT 'open' CHECK(state IN ('open','completed','ignored')),
                    note TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit (
                    sequence INTEGER PRIMARY KEY, at TEXT NOT NULL, event TEXT NOT NULL,
                    payload TEXT NOT NULL, previous TEXT NOT NULL, hash TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS plans (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, data TEXT NOT NULL,
                    parent_id TEXT REFERENCES plans(id) ON DELETE SET NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
            ''')

    @contextmanager
    def connection(self, write=False):
        with self.lock:
            db = sqlite3.connect(self.location, timeout=15)
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('PRAGMA secure_delete=ON')
            try:
                if write:
                    db.execute('BEGIN IMMEDIATE')
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()

    def audit(self, db, event, payload):
        row = db.execute('SELECT sequence, hash FROM audit ORDER BY sequence DESC LIMIT 1').fetchone()
        sequence, previous = (row['sequence'] + 1, row['hash']) if row else (1, '0' * 64)
        at, serialized = now(), canonical(payload)
        checksum = digest(canonical([sequence, at, event, serialized, previous]))
        db.execute('INSERT INTO audit VALUES (?,?,?,?,?,?)', (sequence, at, event, serialized, previous, checksum))

    def import_document(self, filename, content, matter='Unsorted', title='', effective_date=None, replaces_id=None, demo=False):
        if replaces_id is not None and (not isinstance(replaces_id, str) or (replaces_id and not re.fullmatch(r'[a-f0-9]{32}', replaces_id))):
            raise InputError('Choose a valid replacement document.')
        replaces_id = replaces_id or None
        filename = Path(short_text(filename, 'Filename', 240)).name
        matter = short_text(matter, 'Collection', 100)
        title = short_text(title or Path(filename).stem.replace('_', ' '), 'Title')
        if effective_date:
            try:
                effective_date = date.fromisoformat(effective_date).isoformat()
            except (TypeError, ValueError) as exc:
                raise InputError('Effective date must use YYYY-MM-DD.') from exc
        else:
            effective_date = None
        text, warnings = read_document(filename, content)
        chunks, facts = extract(text)
        sha = digest(content)
        identifier = uuid.uuid4().hex
        with self.connection(write=True) as db:
            duplicate = db.execute('SELECT id FROM documents WHERE sha=? AND matter=?', (sha, matter)).fetchone()
            if duplicate:
                return {'id': duplicate['id'], 'duplicate': True, 'warnings': []}
            if replaces_id:
                if not isinstance(replaces_id, str) or not re.fullmatch(r'[a-f0-9]{32}', replaces_id):
                    raise InputError('Choose a valid replacement document.')
                predecessor = db.execute('SELECT matter FROM documents WHERE id=?', (replaces_id,)).fetchone()
                if not predecessor or predecessor['matter'] != matter:
                    raise InputError('The replaced document must exist in the same collection.')
                if db.execute('SELECT 1 FROM documents WHERE replaces_id=?', (replaces_id,)).fetchone():
                    raise InputError('That document already has a replacement. Select the latest document in its chain.')
            db.execute('INSERT INTO documents VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                       (identifier, title, filename, sha, digest(text), content, text, matter, effective_date, replaces_id, now(), canonical(warnings), int(demo)))
            chunk_ids = {}
            for chunk in chunks:
                cursor = db.execute('INSERT INTO chunks(document_id,ordinal,start,end,text,page,line) VALUES (?,?,?,?,?,?,?)',
                                    (identifier, chunk['ordinal'], chunk['start'], chunk['end'], chunk['text'], chunk['page'], chunk['line']))
                chunk_ids[chunk['ordinal']] = cursor.lastrowid
                db.execute('INSERT INTO search_index(rowid,text,title,matter) VALUES (?,?,?,?)', (cursor.lastrowid, chunk['text'], title, matter))
            for fact in facts:
                cursor = db.execute('INSERT INTO facts(document_id,chunk_id,key,label,value,display,kind,unit,start,end,status) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                                    (identifier, chunk_ids[fact['chunk']], fact['key'], fact['label'], fact['value'], fact['display'], fact['kind'], fact['unit'], fact['start'], fact['end'], fact['status']))
                if fact['kind'] == 'date' and fact['key'] != 'effective_date':
                    db.execute('INSERT INTO actions(fact_id,updated_at) VALUES (?,?)', (cursor.lastrowid, now()))
            self.audit(db, 'document.imported', {'id': identifier, 'sha': sha, 'text_sha': digest(text), 'facts': len(facts), 'replaces_id': replaces_id})
        return {'id': identifier, 'duplicate': False, 'warnings': warnings, 'facts': len(facts)}

    def document(self, identifier):
        with self.connection() as db:
            row = db.execute('SELECT id,title,filename,sha,text_sha,text,matter,effective_date,replaces_id,imported_at,warnings,demo FROM documents WHERE id=?', (identifier,)).fetchone()
            if not row:
                raise InputError('Document not found.')
            doc = dict(row)
            doc['warnings'] = json.loads(doc['warnings'])
            doc['chunks'] = [dict(row) for row in db.execute('SELECT * FROM chunks WHERE document_id=? ORDER BY ordinal', (identifier,))]
            doc['facts'] = self._facts(db, identifier)
            return doc

    def original(self, identifier):
        with self.connection() as db:
            row = db.execute('SELECT filename,raw FROM documents WHERE id=?', (identifier,)).fetchone()
            if not row:
                raise InputError('Document not found.')
            return row['filename'], row['raw']

    def _facts(self, db, identifier=None):
        sql = '''SELECT f.*, c.text AS quote, c.page, c.line, c.start AS quote_start,
                        d.title AS document_title, d.matter, d.effective_date,
                        a.state AS action_state, a.note AS action_note
                 FROM facts f JOIN chunks c ON c.id=f.chunk_id JOIN documents d ON d.id=f.document_id
                 LEFT JOIN actions a ON a.fact_id=f.id'''
        return [dict(row) for row in db.execute(sql + (' WHERE f.document_id=?' if identifier else '') + ' ORDER BY f.id', (identifier,) if identifier else ())]

    @staticmethod
    def _active_ids(documents, today):
        """Replacement is explicit; future revisions do not suppress today's source."""
        by_id = {doc['id']: doc for doc in documents}
        active = {doc['id'] for doc in documents if not doc['effective_date'] or doc['effective_date'] <= today}
        for doc in documents:
            if doc['id'] not in active:
                continue
            ancestor = doc['replaces_id']
            visited = set()
            while ancestor and ancestor in by_id and ancestor not in visited:
                visited.add(ancestor)
                active.discard(ancestor)
                ancestor = by_id[ancestor]['replaces_id']
        return active

    def snapshot(self, as_of=None):
        today = as_of or date.today().isoformat()
        try:
            today = date.fromisoformat(today).isoformat()
        except (ValueError, TypeError) as exc:
            raise InputError('The timeline date must use YYYY-MM-DD.') from exc
        with self.connection() as db:
            documents = [dict(row) for row in db.execute('''SELECT d.id,d.title,d.filename,d.sha,d.matter,d.effective_date,d.replaces_id,d.imported_at,d.demo,d.warnings,
                            (SELECT count(*) FROM facts f WHERE f.document_id=d.id AND f.status!='dismissed') AS fact_count
                            FROM documents d ORDER BY d.imported_at DESC, d.id''')]
            facts = self._facts(db)
            events = [dict(row) for row in db.execute('SELECT sequence,at,event,payload,hash FROM audit ORDER BY sequence DESC LIMIT 30')]
        active = self._active_ids(documents, today)
        for doc in documents:
            doc['state'] = 'current' if doc['id'] in active else ('upcoming' if doc['effective_date'] and doc['effective_date'] > today else 'superseded')
            doc['warnings'] = json.loads(doc['warnings'])
        for fact in facts:
            fact['current'] = fact['document_id'] in active
        current = [f for f in facts if f['current'] and f['status'] != 'dismissed']
        conflicts = self._conflicts(current)
        changes = self._changes(documents, facts)
        obligations = [dict(f, days=(date.fromisoformat(f['value']) - date.fromisoformat(today)).days) for f in current if f['action_state'] is not None]
        obligations.sort(key=lambda f: (f['action_state'] != 'open', f['value'], f['id']))
        return {'today': today, 'documents': documents, 'facts': facts, 'conflicts': conflicts, 'changes': changes, 'obligations': obligations,
                'collections': sorted({d['matter'] for d in documents}), 'audit': events,
                'stats': {'documents': len(documents), 'collections': len({d['matter'] for d in documents}),
                          'review': sum(f['status'] == 'suggested' for f in current), 'conflicts': len(conflicts),
                          'upcoming': sum(o['action_state'] == 'open' and 0 <= o['days'] <= 30 for o in obligations),
                          'overdue': sum(o['action_state'] == 'open' and o['days'] < 0 for o in obligations)}}

    @staticmethod
    def _conflicts(facts):
        groups = {}
        for fact in facts:
            if fact['key'] == 'effective_date':
                continue
            groups.setdefault((fact['matter'], fact['key'], fact['unit']), []).append(fact)
        result = []
        for (matter, key, unit), group in groups.items():
            # Compare matching labels within a user-defined collection. A
            # difference is a review candidate, never a declared legal conflict.
            if len({f['value'] for f in group}) > 1:
                result.append({'id': digest(canonical([matter, key, unit]))[:16], 'matter': matter, 'key': key,
                               'label': group[0]['label'], 'unit': unit, 'facts': group,
                               'reviewed': all(f['status'] == 'confirmed' for f in group)})
        return sorted(result, key=lambda c: (c['matter'], c['key']))

    @staticmethod
    def _changes(documents, facts):
        by_doc = {}
        for fact in facts:
            if fact['status'] != 'dismissed':
                by_doc.setdefault(fact['document_id'], {}).setdefault((fact['key'], fact['unit']), []).append(fact)
        result = []
        for doc in documents:
            if not doc['replaces_id']:
                continue
            before, after = by_doc.get(doc['replaces_id'], {}), by_doc.get(doc['id'], {})
            for key in before.keys() | after.keys():
                if key[0] == 'effective_date':
                    continue
                old, new = before.get(key, []), after.get(key, [])
                if {f['value'] for f in old} != {f['value'] for f in new}:
                    result.append({'document_id': doc['id'], 'previous_id': doc['replaces_id'], 'matter': doc['matter'],
                                   'title': doc['title'], 'label': (new or old)[0]['label'], 'before': old, 'after': new,
                                   'effective_date': doc['effective_date'], 'state': doc['state']})
        return sorted(result, key=lambda c: (c['matter'], c['label']))

    def review_fact(self, identifier, status):
        if status not in ('confirmed', 'dismissed', 'suggested'):
            raise InputError('Choose confirmed, dismissed, or suggested.')
        with self.connection(write=True) as db:
            fact = db.execute('SELECT id,status FROM facts WHERE id=?', (identifier,)).fetchone()
            if not fact:
                raise InputError('Finding not found.')
            db.execute('UPDATE facts SET status=? WHERE id=?', (status, identifier))
            self.audit(db, 'finding.reviewed', {'id': identifier, 'before': fact['status'], 'after': status})

    def update_action(self, identifier, state, note=''):
        if state not in ('open', 'completed', 'ignored'):
            raise InputError('Choose open, completed, or ignored.')
        note = short_text(note, 'Note', 1000, required=False)
        with self.connection(write=True) as db:
            row = db.execute('SELECT state FROM actions WHERE fact_id=?', (identifier,)).fetchone()
            if not row:
                raise InputError('Commitment not found.')
            db.execute('UPDATE actions SET state=?,note=?,updated_at=? WHERE fact_id=?', (state, note, now(), identifier))
            self.audit(db, 'commitment.updated', {'id': identifier, 'before': row['state'], 'after': state})

    def delete_document(self, identifier):
        with self.connection(write=True) as db:
            if not db.execute('SELECT 1 FROM documents WHERE id=?', (identifier,)).fetchone():
                raise InputError('Document not found.')
            db.execute('DELETE FROM search_index WHERE rowid IN (SELECT id FROM chunks WHERE document_id=?)', (identifier,))
            db.execute('DELETE FROM documents WHERE id=?', (identifier,))
            self.audit(db, 'document.deleted', {'id': identifier})
        with self.connection() as db:
            db.execute('PRAGMA wal_checkpoint(TRUNCATE)')

    def search(self, query, matter=None, limit=20, current_only=False, as_of=None):
        query = short_text(query, 'Search', 500)
        words = re.findall(r'[^\W_]+', query, re.UNICODE)
        stop = {'what', 'when', 'where', 'which', 'how', 'does', 'have', 'has', 'the', 'a', 'an', 'is', 'are', 'my', 'our', 'we', 'i', 'do', 'did', 'was', 'were', 'on', 'for', 'to', 'of', 'in', 'it', 'be', 'and', 'or', 'please', 'show', 'me', 'current', 'latest'}
        tokens = [word for word in words if word.lower() not in stop][:25]
        if not tokens:
            return []
        # Only quoted tokenizer words enter MATCH, never raw FTS query syntax.
        expression = ' OR '.join('"' + word + '"' for word in tokens)
        with self.connection() as db:
            clauses, values = ['search_index MATCH ?'], [expression]
            if matter:
                clauses.append('d.matter=?')
                values.append(matter)
            if current_only:
                docs = [dict(row) for row in db.execute('SELECT id,effective_date,replaces_id FROM documents')]
                active = self._active_ids(docs, as_of or date.today().isoformat())
                if not active:
                    return []
                clauses.append('d.id IN (' + ','.join('?' for _ in active) + ')')
                values.extend(sorted(active))
            rows = db.execute('''SELECT c.id AS chunk_id,c.document_id,c.text AS quote,c.page,c.line,c.start,c.end,
                                d.title AS document_title,d.matter,d.effective_date,bm25(search_index,1,2,1.5) AS rank
                                FROM search_index JOIN chunks c ON c.id=search_index.rowid JOIN documents d ON d.id=c.document_id
                                WHERE ''' + ' AND '.join(clauses) + ' ORDER BY rank,c.id LIMIT ?', (*values, max(1, min(int(limit), 100))))
            return [dict(row) for row in rows]

    def integrity(self):
        issues = []
        with self.connection() as db:
            documents = list(db.execute('SELECT id,sha,text_sha,raw,text FROM documents'))
            expected_facts = {}
            for doc in documents:
                if digest(doc['raw']) != doc['sha']:
                    issues.append({'type': 'original_checksum', 'id': doc['id']})
                if digest(doc['text']) != doc['text_sha']:
                    issues.append({'type': 'text_checksum', 'id': doc['id']})
                _, extracted = extract(doc['text'])
                expected_facts[doc['id']] = {(f['key'], f['value'], f['unit'], f['start'], f['end'], f['display'], f['kind']) for f in extracted}
            observed_facts = {}
            for fact in db.execute('SELECT * FROM facts'):
                signature = (fact['key'], fact['value'], fact['unit'], fact['start'], fact['end'], fact['display'], fact['kind'])
                observed_facts.setdefault(fact['document_id'], set()).add(signature)
                if signature not in expected_facts.get(fact['document_id'], set()):
                    issues.append({'type': 'finding_evidence', 'id': fact['id']})
            for identifier, expected in expected_facts.items():
                if expected - observed_facts.get(identifier, set()):
                    issues.append({'type': 'missing_findings', 'id': identifier})
            for chunk in db.execute('SELECT c.*,d.text AS original FROM chunks c JOIN documents d ON d.id=c.document_id'):
                if chunk['original'][chunk['start']:chunk['end']] != chunk['text']:
                    issues.append({'type': 'citation_span', 'id': chunk['id']})
            previous, sequence = '0' * 64, 0
            import_records, plan_hashes, review_states = {}, {}, {}
            for row in db.execute('SELECT * FROM audit ORDER BY sequence'):
                sequence += 1
                expected = digest(canonical([row['sequence'], row['at'], row['event'], row['payload'], row['previous']]))
                if row['sequence'] != sequence or row['previous'] != previous or row['hash'] != expected:
                    issues.append({'type': 'audit_chain', 'id': row['sequence']})
                previous = row['hash']
                try:
                    payload = json.loads(row['payload'])
                    if row['event'] == 'document.imported':
                        import_records[payload['id']] = payload
                    elif row['event'] == 'plan.saved':
                        plan_hashes[payload['id']] = payload['sha']
                    elif row['event'] == 'finding.reviewed':
                        review_states[payload['id']] = payload['after']
                except (ValueError, TypeError, KeyError):
                    issues.append({'type': 'audit_payload', 'id': row['sequence']})
            for doc in documents:
                recorded = import_records.get(doc['id'], {})
                if recorded.get('sha') != doc['sha'] or recorded.get('text_sha') != doc['text_sha']:
                    issues.append({'type': 'import_record', 'id': doc['id']})
            for plan in db.execute('SELECT id,data FROM plans'):
                if digest(plan['data']) != plan_hashes.get(plan['id']):
                    issues.append({'type': 'plan_checksum', 'id': plan['id']})
            for fact in db.execute('SELECT id,status FROM facts'):
                if fact['status'] != review_states.get(fact['id'], 'suggested'):
                    issues.append({'type': 'review_record', 'id': fact['id']})
            for row in db.execute('PRAGMA foreign_key_check'):
                issues.append({'type': 'foreign_key', 'id': row[1]})
        return {'ok': not issues, 'documents': len(documents), 'events': sequence, 'head': previous, 'issues': issues, 'checked_at': now()}

    def export(self):
        with self.connection() as db:
            output = io.BytesIO()
            with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
                # The format identifier is a compatibility contract, independent of the product name.
                manifest = {'format': 'margin-export', 'version': 1, 'exported_at': now(), 'documents': [], 'facts': self._facts(db),
                            'plans': [dict(row) for row in db.execute('SELECT * FROM plans ORDER BY created_at')],
                            'audit': [dict(row) for row in db.execute('SELECT * FROM audit ORDER BY sequence')]}
                for row in db.execute('SELECT * FROM documents ORDER BY imported_at'):
                    doc = dict(row)
                    raw, text = doc.pop('raw'), doc.pop('text')
                    safe_filename = re.sub(r'[^\w. -]', '_', doc['filename'])
                    doc['original_path'] = f"originals/{doc['id']}/{safe_filename}"
                    doc['text_path'] = f"text/{doc['id']}.txt"
                    archive.writestr(doc['original_path'], raw)
                    archive.writestr(doc['text_path'], text)
                    manifest['documents'].append(doc)
                archive.writestr('manifest.json', json.dumps(manifest, indent=2, ensure_ascii=False))
            return output.getvalue()

    def plans(self):
        with self.connection() as db:
            return [dict(row, data=json.loads(row['data'])) for row in db.execute('SELECT * FROM plans ORDER BY created_at,id')]

    def save_plan(self, value, identifier=None, parent_id=None):
        from .planner import validate_plan
        plan = validate_plan(value)
        serialized = canonical(plan)
        if len(serialized) > 300_000:
            raise InputError('This plan is too large.')
        with self.connection(write=True) as db:
            for item in plan['tasks'] + plan['flows']:
                for field in ('source_fact_id', 'source_date_id'):
                    if item.get(field) and not db.execute('SELECT 1 FROM facts WHERE id=?', (item[field],)).fetchone():
                        raise InputError('A linked finding no longer exists. Remove its reference before saving.')
            at = now()
            if identifier:
                if not db.execute('SELECT 1 FROM plans WHERE id=?', (identifier,)).fetchone():
                    raise InputError('Plan not found.')
                db.execute('UPDATE plans SET name=?,data=?,updated_at=? WHERE id=?', (plan['name'], serialized, at, identifier))
            else:
                identifier = uuid.uuid4().hex
                if parent_id and not db.execute('SELECT 1 FROM plans WHERE id=?', (parent_id,)).fetchone():
                    raise InputError('The original plan no longer exists.')
                db.execute('INSERT INTO plans VALUES (?,?,?,?,?,?)', (identifier, plan['name'], serialized, parent_id, at, at))
            self.audit(db, 'plan.saved', {'id': identifier, 'sha': digest(serialized), 'parent_id': parent_id})
        return {'id': identifier, 'data': plan}

    def plan(self, identifier):
        with self.connection() as db:
            row = db.execute('SELECT * FROM plans WHERE id=?', (identifier,)).fetchone()
            if not row:
                raise InputError('Plan not found.')
            return dict(row, data=json.loads(row['data']))

    def delete_plan(self, identifier):
        with self.connection(write=True) as db:
            if not db.execute('DELETE FROM plans WHERE id=?', (identifier,)).rowcount:
                raise InputError('Plan not found.')
            self.audit(db, 'plan.deleted', {'id': identifier})

    def plan_evidence(self, plan):
        from .planner import money
        snapshot = self.snapshot(plan['start'])
        final_date = (date.fromisoformat(plan['start']) + timedelta(days=plan['horizon'] - 1)).isoformat()
        final_snapshot = self.snapshot(final_date)
        final_current = {f['id'] for f in final_snapshot['facts'] if f['current']}
        facts = {fact['id']: fact for fact in snapshot['facts']}
        warnings, citations = [], []
        conflicted = {fact['id'] for conflict in snapshot['conflicts'] + final_snapshot['conflicts'] for fact in conflict['facts']}
        for item in plan['tasks'] + plan['flows']:
            for key in ('source_fact_id', 'source_date_id'):
                ref = item.get(key)
                if not ref:
                    continue
                fact = facts.get(ref)
                reasons = []
                if not fact:
                    reasons.append('the source was deleted')
                else:
                    citations.append(fact)
                    if not fact['current']:
                        reasons.append('the source is not current at the plan start')
                    elif fact['id'] not in final_current:
                        reasons.append('the source is replaced during the forecast; later assumptions may need updating')
                    if fact['status'] != 'confirmed':
                        reasons.append('the finding is ' + fact['status'])
                    if ref in conflicted:
                        reasons.append('current sources disagree on this term')
                    if fact['kind'] == 'money' and 'amount' in item:
                        if fact['unit'] != plan['currency']:
                            reasons.append('the source currency differs from the plan currency')
                        if money(fact['value']) != money(item['amount']):
                            reasons.append('the planned amount differs from the source')
                    if fact['kind'] == 'date' and fact['value'] != item.get('due', item.get('date')):
                        reasons.append('the planned date differs from the source')
                if reasons:
                    warnings.append({'type': 'evidence_drift', 'item_id': item['id'], 'fact_id': ref,
                                     'message': f"{item['title']}: " + '; '.join(reasons) + '.'})
        unique = {fact['id']: fact for fact in citations}
        return {'warnings': warnings, 'citations': list(unique.values())}
