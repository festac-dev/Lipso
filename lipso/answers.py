"""Question routing that returns evidence, not ungrounded generated prose."""
import re

from .extract import InputError

ALIASES = {
    'rent': 'monthly_rent', 'deposit': 'deposit', 'premium': 'annual_premium',
    'coverage': 'coverage_limit', 'invoice': 'invoice_total', 'fee': 'monthly_fee',
    'salary': 'salary', 'notice': 'notice_days', 'renew': 'renewal_date',
    'renewal': 'renewal_date', 'renews': 'renewal_date', 'expire': 'expiry_date', 'expires': 'expiry_date', 'expiry': 'expiry_date',
    'expiration': 'expiry_date', 'cancel': 'cancellation_deadline',
    'cancellation': 'cancellation_deadline', 'delivery': 'delivery_date',
    'payment': 'payment_amount',
}


def answer(store, question, matter=None, as_of=None):
    if not isinstance(question, str) or not question.strip() or len(question) > 500:
        raise InputError('Ask a question of up to 500 characters.')
    snapshot = store.snapshot(as_of)
    words = set(re.findall(r'\w+', question.lower()))
    # Collection selection can be explicit or an unambiguous name in the query.
    if not matter:
        mentioned = [name for name in snapshot['collections'] if name.casefold() in question.casefold()]
        if len(mentioned) == 1:
            matter = mentioned[0]
    scope = lambda item: not matter or item['matter'] == matter
    base = {'question': question, 'as_of': snapshot['today'], 'collection': matter, 'mode': 'evidence', 'citations': [], 'conflicts': []}
    if words & {'changed', 'changes', 'change', 'difference', 'differences'}:
        changes = [change for change in snapshot['changes'] if scope(change)]
        base.update(kind='changes', title=f'{len(changes)} term changes across linked revisions', changes=changes,
                    summary='These are differences between documents explicitly linked as replacements. Missing terms may simply have been omitted; they are not assumed to be cancelled.')
        base['citations'] = [fact for change in changes for fact in change['before'] + change['after']]
        return base
    if words & {'conflict', 'conflicts', 'conflicting', 'contradiction', 'contradictions', 'contradictory', 'disagree', 'inconsistent'}:
        conflicts = [item for item in snapshot['conflicts'] if scope(item)]
        base.update(kind='conflicts', title=f'{len(conflicts)} possible conflicts need context', conflicts=conflicts,
                    summary='These current sources contain different values under the same label and collection. Review their scope before deciding which applies.')
        base['citations'] = [fact for conflict in conflicts for fact in conflict['facts']]
        return base
    if words & {'due', 'upcoming', 'overdue', 'deadlines', 'commitments'} or {'what', 'next'} <= words:
        obligations = [item for item in snapshot['obligations'] if scope(item) and item['action_state'] == 'open']
        if 'overdue' in words:
            obligations = [item for item in obligations if item['days'] < 0]
        elif 'upcoming' in words or 'next' in words:
            obligations = [item for item in obligations if 0 <= item['days'] <= 30]
        if 'week' in words:
            obligations = [item for item in obligations if 0 <= item['days'] <= 7]
        elif 'month' in words:
            obligations = [item for item in obligations if 0 <= item['days'] <= 30]
        base.update(kind='obligations', title=f'{len(obligations)} open commitments found', obligations=obligations,
                    summary='Dates are extracted from explicit wording. Recurring dates and relative deadlines are not inferred; review each source before relying on it.')
        base['citations'] = obligations[:20]
        return base
    keys = {ALIASES[word] for word in words if word in ALIASES}
    if keys:
        candidates = [fact for fact in snapshot['facts'] if fact['current'] and fact['status'] != 'dismissed' and fact['key'] in keys and scope(fact)]
        conflicts = [conflict for conflict in snapshot['conflicts'] if conflict['key'] in keys and scope(conflict)]
        if candidates:
            base.update(kind='facts', title='The current sources say', citations=candidates[:20], conflicts=conflicts,
                        summary='Multiple values remain separate. Lipso does not silently choose between conflicting documents.' if conflicts else 'These values come directly from your current documents. “Confirmed” means reviewed by you.')
            return base
    results = store.search(question, matter=matter, current_only=True, as_of=snapshot['today'], limit=8)
    base.update(kind='search', citations=results,
                title='Relevant passages from current documents' if results else 'There isn’t enough evidence here',
                summary='These are keyword-ranked source passages, not a generated answer. Open a citation to inspect its context.' if results else 'Try a document name or a specific term, choose another collection, or import the missing source. No answer has been inferred.')
    return base
