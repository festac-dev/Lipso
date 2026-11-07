import copy
import tempfile
import unittest
from datetime import date
from pathlib import Path

from lipso.extract import InputError
from lipso.planner import money, occurrences, scenario, schedule, simulate, validate_plan
from lipso.store import Store


def plan():
    return {'name': 'Test', 'currency': 'USD', 'start': '2026-11-02', 'horizon': 30, 'opening_balance': '1000', 'reserve': '100',
            'capacity': [4, 4, 4, 4, 4, 0, 0], 'tasks': [], 'flows': []}


def flow(identifier='f', **options):
    return {'id': identifier, 'title': identifier, 'direction': 'out', 'amount': '100', 'date': '2026-11-03',
            'recurrence': 'once', 'probability': 1, 'variance': 0, 'delay_days': 0, **options}


def task(identifier='t', **options):
    return {'id': identifier, 'title': identifier, 'hours': 4, 'due': '2026-11-03', 'earliest': '2026-11-02', 'priority': 3, 'dependencies': [], **options}


class PlannerTests(unittest.TestCase):
    def test_minor_unit_arithmetic(self):
        self.assertEqual(money('0.10') + money('0.20'), 30)
        self.assertEqual(money('-10.01'), -1001)
        for value in ['nan', 'Infinity', '1.001', True, {}, '1,000']:
            with self.subTest(value=value), self.assertRaises(InputError):
                money(value)

    def test_exact_deterministic_cash_path(self):
        value = plan()
        value['flows'] = [flow(), flow('income', direction='in', amount='350.50', date='2026-11-05')]
        result = simulate(value, runs=5)
        self.assertEqual(result['days'][0]['p50'], 100000)
        self.assertEqual(result['days'][1]['p10'], 90000)
        self.assertEqual(result['summary']['ending_p50'], 125050)
        self.assertTrue(all(d['p10'] == d['p50'] == d['p90'] for d in result['days']))

    def test_zero_probability_never_occurs(self):
        value = plan()
        value['flows'] = [flow(amount='10000', probability=0)]
        self.assertEqual(simulate(value, runs=10)['summary']['ending_p50'], 100000)

    def test_known_shortfall_is_certain(self):
        value = plan()
        value['flows'] = [flow(amount='1100')]
        result = simulate(value, runs=12)
        self.assertEqual(result['summary']['negative_probability'], 1)
        self.assertEqual(result['summary']['minimum_p10'], -10000)

    def test_opening_shortfall_not_hidden_by_same_day_income(self):
        value = plan()
        value['opening_balance'] = '-1'
        value['flows'] = [flow(direction='in', date=value['start'])]
        self.assertEqual(simulate(value, runs=2)['summary']['negative_probability'], 1)

    def test_reproducible_uncertainty(self):
        value = plan()
        value['flows'] = [flow(probability=.5, variance=.3, delay_days=8)]
        a, b = simulate(value, runs=150, seed=42), simulate(value, runs=150, seed=42)
        self.assertEqual(a, b)
        self.assertTrue(all(d['p10'] <= d['p50'] <= d['p90'] for d in a['days']))

    def test_monthly_anchor_returns_after_short_month(self):
        f = flow(date='2027-01-31', recurrence='monthly')
        self.assertEqual([d.isoformat() for d in occurrences(f, date(2027, 1, 1), 100)], ['2027-01-31', '2027-02-28', '2027-03-31'])
        f['date'] = '2028-01-31'
        self.assertIn(date(2028, 2, 29), occurrences(f, date(2028, 1, 1), 90))

    def test_weekly_occurrences_do_not_replay_past(self):
        f = flow(date='2026-10-05', recurrence='weekly')
        self.assertEqual(occurrences(f, date(2026, 11, 2), 8), [date(2026, 11, 2), date(2026, 11, 9)])

    def test_dependency_order_and_capacity_conservation(self):
        value = plan()
        value['tasks'] = [task('a', hours=6), task('b', hours=3, dependencies=['a'])]
        result = schedule(validate_plan(value))
        self.assertEqual(result['completed'], {'a': '2026-11-03', 'b': '2026-11-04'})
        for item in result['days']:
            self.assertLessEqual(item['minutes'], item['capacity_minutes'])
            self.assertEqual(item['minutes'], sum(block['minutes'] for block in item['blocks']))
        self.assertEqual(sum(d['minutes'] for d in result['days']), 9 * 60)

    def test_no_capacity_keeps_work_and_income_blocked(self):
        value = plan()
        value['capacity'] = [0] * 7
        value['tasks'] = [task()]
        value['flows'] = [flow(direction='in', depends_on_task='t')]
        result = simulate(value, runs=2)
        self.assertEqual(result['summary']['ending_p50'], 100000)
        self.assertEqual(result['schedule']['tasks'][0]['status'], 'unscheduled')
        self.assertIn('blocked_cashflow', [w['type'] for w in result['warnings']])

    def test_work_completion_shifts_income(self):
        value = plan()
        value['tasks'] = [task(hours=12)]
        value['flows'] = [flow(direction='in', date='2026-11-02', depends_on_task='t', lag_days=2)]
        result = simulate(value, runs=2)
        self.assertEqual(result['events'][0]['date'], '2026-11-06')
        self.assertEqual(result['days'][3]['p50'], 100000)
        self.assertEqual(result['days'][4]['p50'], 110000)

    def test_dependency_cycles_rejected(self):
        value = plan()
        value['tasks'] = [task('a', dependencies=['b']), task('b', dependencies=['a'])]
        with self.assertRaisesRegex(InputError, 'cycle'):
            validate_plan(value)

    def test_missing_dependency_rejected(self):
        value = plan()
        value['tasks'] = [task(dependencies=['missing'])]
        with self.assertRaises(InputError):
            validate_plan(value)

    def test_scenario_isolated_from_original(self):
        original = plan()
        original['flows'] = [flow(), flow('income', direction='in')]
        before = copy.deepcopy(original)
        alternate = scenario(original, {'income_delay': 10, 'expense_increase': .2, 'capacity_change': -.5})
        self.assertEqual(original, before)
        self.assertEqual(alternate['flows'][0]['amount'], '120.00')
        self.assertEqual(alternate['flows'][1]['date'], '2026-11-13')
        self.assertEqual(alternate['capacity'][0], 2)

    def test_bad_bounds_and_types_rejected(self):
        for key, value in [('horizon', 0), ('horizon', 8.5), ('opening_balance', 'NaN'), ('currency', 'usd'), ('capacity', [4]), ('start', '20261102')]:
            with self.subTest(key=key), self.assertRaises(InputError):
                validate_plan({**plan(), key: value})

    def test_plan_evidence_detects_superseded_and_missing_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'test.db')
            identifier = store.import_document('a.txt', b'Monthly rent: USD 100.', matter='Lease')['id']
            fact = store.document(identifier)['facts'][0]
            store.review_fact(fact['id'], 'confirmed')
            value = plan()
            value['flows'] = [flow(source_fact_id=fact['id'])]
            self.assertEqual(store.plan_evidence(value)['warnings'], [])
            store.import_document('b.txt', b'Monthly rent: USD 200.', matter='Lease', replaces_id=identifier)
            self.assertIn('not current', store.plan_evidence(value)['warnings'][0]['message'])
            store.delete_document(identifier)
            self.assertIn('deleted', store.plan_evidence(value)['warnings'][0]['message'])

    def test_persisted_branch_retains_parent_and_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'test.db')
            original = store.save_plan(plan())
            changed = scenario(original['data'], {'cash_change': '50'})
            branch = store.save_plan(changed, parent_id=original['id'])
            self.assertEqual(store.plan(original['id'])['data']['opening_balance'], '1000')
            self.assertEqual(store.plan(branch['id'])['data']['opening_balance'], '1050')
            self.assertEqual(store.plan(branch['id'])['parent_id'], original['id'])

    def test_revision_inside_horizon_flags_recurring_assumptions(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'test.db')
            old = store.import_document('a.txt', b'Monthly rent: USD 100.', matter='Lease')['id']
            fact = store.document(old)['facts'][0]
            store.review_fact(fact['id'], 'confirmed')
            store.import_document('b.txt', b'Monthly rent: USD 200.', matter='Lease', effective_date='2026-11-15', replaces_id=old)
            value = plan()
            value['flows'] = [flow(source_fact_id=fact['id'], recurrence='monthly')]
            self.assertIn('replaced during the forecast', store.plan_evidence(value)['warnings'][0]['message'])
