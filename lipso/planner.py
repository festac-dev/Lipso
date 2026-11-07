"""A reproducible, bounded cash-flow simulator coupled to a work scheduler.

Amounts are integer minor units. Probabilities are user assumptions, never
learned predictions. Scheduling is a deadline-first heuristic, not an optimality
proof. Scenarios keep the original plan unchanged.
"""
from __future__ import annotations

import calendar
import copy
import math
import random
import re
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from .extract import InputError


def money(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise InputError('Amounts must be finite decimal numbers.')
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or abs(amount) > 1_000_000_000 or amount.as_tuple().exponent < -2:
            raise InputError('Amounts must have at most two decimal places and be below one billion.')
        return int(amount * 100)
    except (InvalidOperation, ValueError) as exc:
        raise InputError('Amounts must be finite decimal numbers.') from exc


def day(value, label='Date'):
    try:
        if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
            raise ValueError()
        parsed = date.fromisoformat(value)
        if not 1900 <= parsed.year <= 2200:
            raise ValueError()
        return parsed
    except (ValueError, TypeError) as exc:
        raise InputError(f'{label} must use YYYY-MM-DD.') from exc


def number(value, low, high, label):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or not low <= value <= high:
        raise InputError(f'{label} must be between {low} and {high}.')
    return value


def validate_plan(value):
    if not isinstance(value, dict):
        raise InputError('Expected a plan object.')
    plan = copy.deepcopy(value)
    if not isinstance(plan.get('name'), str) or not 1 <= len(plan['name'].strip()) <= 120:
        raise InputError('A plan needs a name of up to 120 characters.')
    if not isinstance(plan.get('currency'), str) or not re.fullmatch(r'[A-Z]{3}', plan['currency']):
        raise InputError('Choose one three-letter currency per plan. Currencies are never silently converted.')
    day(plan.get('start'), 'Start date')
    number(plan.get('horizon'), 7, 180, 'Forecast days')
    if not isinstance(plan['horizon'], int):
        raise InputError('Forecast days must be a whole number.')
    money(plan.get('opening_balance'))
    if money(plan.get('reserve', '0')) < 0:
        raise InputError('The cash reserve cannot be negative.')
    plan.setdefault('reserve', '0')
    if not isinstance(plan.get('capacity'), list) or len(plan['capacity']) != 7:
        raise InputError('Capacity needs seven daily hour values, Monday through Sunday.')
    for hours in plan['capacity']:
        number(hours, 0, 24, 'Daily hours')
    for collection in ('tasks', 'flows'):
        if not isinstance(plan.get(collection), list) or len(plan[collection]) > 200:
            raise InputError(f'Plans support up to 200 {collection}.')
        ids = set()
        for item in plan[collection]:
            if not isinstance(item, dict) or not isinstance(item.get('id'), str) or not re.fullmatch(r'[\w-]{1,80}', item['id']):
                raise InputError('Every task and cash flow needs a simple, unique ID.')
            if item['id'] in ids:
                raise InputError(f'Duplicate ID in {collection}.')
            ids.add(item['id'])
            if not isinstance(item.get('title'), str) or not 1 <= len(item['title']) <= 160:
                raise InputError('Every item needs a title of up to 160 characters.')
            for ref in ('source_fact_id', 'source_date_id'):
                if item.get(ref) is not None and (type(item[ref]) is not int or item[ref] <= 0):
                    raise InputError('Evidence references must be finding IDs.')
    task_ids = {task['id'] for task in plan['tasks']}
    for task in plan['tasks']:
        number(task.get('hours'), 0.25, 1000, 'Task effort')
        day(task.get('due'), 'Task deadline')
        day(task.get('earliest', plan['start']), 'Earliest start')
        task.setdefault('earliest', plan['start'])
        task.setdefault('priority', 3)
        number(task['priority'], 1, 5, 'Priority')
        dependencies = task.setdefault('dependencies', [])
        if not isinstance(dependencies, list) or not all(isinstance(dep, str) and dep in task_ids for dep in dependencies) or len(set(dependencies)) != len(dependencies):
            raise InputError('Dependencies must refer to unique tasks in this plan.')
    # Reject dependency cycles with a concrete path.
    by_id = {task['id']: task for task in plan['tasks']}
    visited, visiting = set(), []

    def visit(identifier):
        if identifier in visiting:
            raise InputError('Dependency cycle: ' + ' → '.join(visiting[visiting.index(identifier):] + [identifier]))
        if identifier in visited:
            return
        visiting.append(identifier)
        for dependency in by_id[identifier]['dependencies']:
            visit(dependency)
        visiting.pop()
        visited.add(identifier)

    for identifier in by_id:
        visit(identifier)
    for flow in plan['flows']:
        if flow.get('direction') not in ('in', 'out') or money(flow.get('amount')) <= 0:
            raise InputError('Cash flows need an in/out direction and a positive amount.')
        day(flow.get('date'), 'Cash-flow date')
        flow.setdefault('recurrence', 'once')
        if flow['recurrence'] not in ('once', 'weekly', 'monthly'):
            raise InputError('Recurrence must be once, weekly, or monthly.')
        for key, default, low, high in [('probability', 1, 0, 1), ('delay_days', 0, 0, 60), ('variance', 0, 0, 1), ('lag_days', 0, 0, 60)]:
            flow.setdefault(key, default)
            number(flow[key], low, high, key.replace('_', ' '))
        if type(flow['delay_days']) is not int or type(flow['lag_days']) is not int:
            raise InputError('Delay and lag days must be whole numbers.')
        if flow.get('depends_on_task') and flow['depends_on_task'] not in task_ids:
            raise InputError('The cash flow depends on a task that is not in this plan.')
    return plan


def schedule(plan):
    start = day(plan['start'])
    remaining = {task['id']: round(task['hours'] * 60) for task in plan['tasks']}
    completed, allocation = {}, []
    # Propagate a successor's deadline backward so an early dependency is not
    # starved by unrelated work with a later effective deadline.
    effective_due = {task['id']: task['due'] for task in plan['tasks']}
    for _ in plan['tasks']:
        changed = False
        for task in plan['tasks']:
            for dep in task['dependencies']:
                if effective_due[dep] > effective_due[task['id']]:
                    effective_due[dep] = effective_due[task['id']]
                    changed = True
        if not changed:
            break
    for index in range(plan['horizon']):
        current = start + timedelta(days=index)
        capacity = round(plan['capacity'][current.weekday()] * 60)
        used = 0
        blocks = []
        while capacity > 0:
            ready = [task for task in plan['tasks'] if remaining[task['id']] > 0 and task['earliest'] <= current.isoformat() and all(dep in completed for dep in task['dependencies'])]
            if not ready:
                break
            ready.sort(key=lambda task: (effective_due[task['id']], -task['priority'], task['id']))
            task = ready[0]
            minutes = min(remaining[task['id']], capacity)
            remaining[task['id']] -= minutes
            capacity -= minutes
            used += minutes
            blocks.append({'task_id': task['id'], 'title': task['title'], 'minutes': minutes})
            if remaining[task['id']] == 0:
                completed[task['id']] = current.isoformat()
        allocation.append({'date': current.isoformat(), 'minutes': used, 'capacity_minutes': round(plan['capacity'][current.weekday()] * 60), 'blocks': blocks})
    outcomes, warnings = [], []
    for task in plan['tasks']:
        finish = completed.get(task['id'])
        late = (day(finish) - day(task['due'])).days if finish else None
        outcome = {'id': task['id'], 'title': task['title'], 'due': task['due'], 'finish': finish, 'remaining_hours': remaining[task['id']] / 60,
                   'late_days': max(0, late) if late is not None else None, 'status': 'unscheduled' if not finish else ('late' if late > 0 else 'on_time')}
        outcomes.append(outcome)
        if outcome['status'] != 'on_time':
            warnings.append({'type': 'capacity', 'task_id': task['id'], 'title': task['title'],
                             'message': f"{task['title']} finishes {late} days after its deadline." if finish else f"{task['title']} has {remaining[task['id']] / 60:g} hours left beyond this forecast."})
    return {'days': allocation, 'tasks': outcomes, 'completed': completed, 'warnings': warnings,
            'hours': sum(task['hours'] for task in plan['tasks']), 'capacity_hours': sum(item['capacity_minutes'] for item in allocation) / 60}


def occurrences(flow, start, horizon):
    original = day(flow['date'])
    end = start + timedelta(days=horizon - 1)
    if flow['recurrence'] == 'once':
        return [original] if original <= end else []
    if flow['recurrence'] == 'weekly':
        difference = max(0, (start - original).days)
        current = original + timedelta(days=(difference // 7) * 7)
        results = []
        while current <= end:
            if current >= start:
                results.append(current)
            current += timedelta(days=7)
        return results
    # Anchor to the original day of month: Jan 31 -> Feb 28 -> Mar 31.
    first_month = max(original.year * 12 + original.month - 1, start.year * 12 + start.month - 1)
    last_month = end.year * 12 + end.month - 1
    results = []
    for month_number in range(first_month, last_month + 1):
        year, month0 = divmod(month_number, 12)
        month = month0 + 1
        current = date(year, month, min(original.day, calendar.monthrange(year, month)[1]))
        if start <= current <= end and current >= original:
            results.append(current)
    return results


def quantile(values, q):
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    left = int(position)
    return round(ordered[left] + (ordered[min(left + 1, len(ordered) - 1)] - ordered[left]) * (position - left))


def simulate(value, runs=400, seed=1729):
    plan = validate_plan(value)
    number(runs, 1, 1000, 'Simulation runs')
    if type(runs) is not int or type(seed) is not int:
        raise InputError('Runs and random seed must be whole numbers.')
    work = schedule(plan)
    start, horizon = day(plan['start']), plan['horizon']
    opening, reserve = money(plan['opening_balance']), money(plan['reserve'])
    base_events, flow_notes = [], []
    for flow in plan['flows']:
        due_dates = occurrences(flow, start, horizon)
        completion = None
        if flow.get('depends_on_task'):
            finish = work['completed'].get(flow['depends_on_task'])
            if not finish:
                flow_notes.append({'type': 'blocked_cashflow', 'flow_id': flow['id'], 'message': f"{flow['title']} is excluded because its prerequisite work cannot finish in this forecast."})
                continue
            completion = day(finish) + timedelta(days=flow['lag_days'])
        for due in due_dates:
            original_due = due
            if completion:
                due = max(due, completion)
            if due < start:
                flow_notes.append({'type': 'past_cashflow', 'flow_id': flow['id'], 'message': f"{flow['title']} is dated before the plan starts; include it in the opening balance if already settled."})
                continue
            index = (due - start).days
            if index >= horizon:
                continue
            base_events.append({'day': index, 'date': due.isoformat(), 'original_date': original_due.isoformat(), 'flow_id': flow['id'], 'title': flow['title'],
                                'amount': money(flow['amount']) * (1 if flow['direction'] == 'in' else -1),
                                'probability': flow['probability'], 'variance': flow['variance'], 'delay_days': flow['delay_days']})
    randomizer = random.Random(seed)
    paths, minimums, negatives, breaches = [], [], 0, 0
    for _ in range(runs):
        deltas = [0] * horizon
        for event in base_events:
            if randomizer.random() >= event['probability']:
                continue
            index = event['day'] + randomizer.randint(0, event['delay_days'])
            if index >= horizon:
                continue
            multiplier = randomizer.triangular(1 - event['variance'], 1 + event['variance'], 1) if event['variance'] else 1
            deltas[index] += round(event['amount'] * multiplier)
        balance, path = opening, []
        for delta in deltas:
            balance += delta
            path.append(balance)
        minimum = min(opening, *path)
        paths.append(path)
        minimums.append(minimum)
        negatives += minimum < 0
        breaches += minimum < reserve
    days = []
    for index in range(horizon):
        values = [path[index] for path in paths]
        days.append({'date': (start + timedelta(days=index)).isoformat(), 'p10': quantile(values, .1), 'p50': quantile(values, .5), 'p90': quantile(values, .9)})
    cash_warnings = []
    if negatives:
        cash_warnings.append({'type': 'cash_shortfall', 'message': f'{negatives} of {runs} simulated paths go below zero under these assumptions.'})
    return {'currency': plan['currency'], 'runs': runs, 'seed': seed, 'days': days, 'events': sorted(base_events, key=lambda e: (e['day'], e['flow_id'])),
            'schedule': work, 'warnings': work['warnings'] + flow_notes + cash_warnings,
            'summary': {'negative_probability': negatives / runs, 'reserve_breach_probability': breaches / runs,
                        'minimum_p10': quantile(minimums, .1), 'ending_p50': days[-1]['p50'], 'reserve': reserve,
                        'late_tasks': sum(task['status'] != 'on_time' for task in work['tasks'])},
            'assumptions': ['Money is reported in integer minor units; currencies are not converted.',
                            'Cash uncertainty is independent per occurrence; delays are uniform from zero to the entered maximum.',
                            'Amounts use a triangular distribution around the entered value and variance.',
                            'Task estimates and capacity are fixed. Deadline-first scheduling is a heuristic, not an optimality proof.',
                            'Daily balances net same-day flows and do not model intraday payment order.',
                            'Simulation frequencies reflect supplied assumptions, not calibrated real-world probabilities.']}


def scenario(plan, edits):
    if not isinstance(edits, dict):
        raise InputError('Scenario edits must be an object.')
    result = copy.deepcopy(plan)
    allowed = {'income_delay', 'expense_increase', 'capacity_change', 'cash_change'}
    if set(edits) - allowed:
        raise InputError('Unknown scenario adjustment.')
    delay = number(edits.get('income_delay', 0), 0, 60, 'Income delay')
    if type(delay) is not int:
        raise InputError('Income delay must be whole days.')
    expense = number(edits.get('expense_increase', 0), -0.9, 2, 'Expense change')
    capacity = number(edits.get('capacity_change', 0), -1, 1, 'Capacity change')
    cash = money(edits.get('cash_change', '0'))
    result['opening_balance'] = str(Decimal(money(result['opening_balance']) + cash) / 100)
    result['capacity'] = [min(24, round(hours * (1 + capacity), 2)) for hours in result['capacity']]
    for flow in result['flows']:
        if flow['direction'] == 'in':
            flow['date'] = (day(flow['date']) + timedelta(days=delay)).isoformat()
        else:
            result_amount = (Decimal(str(flow['amount'])) * (1 + Decimal(str(expense)))).quantize(Decimal('.01'))
            flow['amount'] = str(result_amount)
    return validate_plan(result)
