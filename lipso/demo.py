"""Clearly marked, synthetic records; never mixed into a real workspace automatically."""
from datetime import date, timedelta


def seed_demo(store):
    today = date.today()
    day = lambda offset: (today + timedelta(days=offset)).isoformat()
    records = [
        ('studio-lease.txt', 'Studio lease · original', 'Cedar studio', day(-120), None,
         f'''CEDAR STUDIO / ORIGINAL LEASE
FICTIONAL SAMPLE — FOR EXPLORATION ONLY

Parties: Cedar Properties and Northline Design.
Effective date: {day(-120)}.
Monthly rent: USD 1,850.00.
Security deposit: USD 3,700.00.
Notice period: 30 days.
Renewal date: {day(45)}.

The studio includes two workrooms and access to the courtyard.
Utilities are billed separately. Written approval is required for structural alterations.
This sample is not a real agreement.
'''),
        ('studio-amendment.txt', 'Studio lease · amendment', 'Cedar studio', day(-7), 'studio-lease.txt',
         f'''CEDAR STUDIO / AMENDED TERMS
FICTIONAL SAMPLE — FOR EXPLORATION ONLY

This amendment replaces the original studio lease terms.
Effective date: {day(-7)}.
Monthly rent: USD 2,050.00.
Security deposit: USD 3,700.00.
Notice period: 60 days.
Renewal date: {day(45)}.
Cancellation notice must be received by {day(12)}.

The courtyard is now included in the leased premises.
This sample is not a real agreement.
'''),
        ('studio-invoice.txt', 'Studio · November statement', 'Cedar studio', None, None,
         f'''CEDAR PROPERTIES / RENT STATEMENT
FICTIONAL SAMPLE — FOR EXPLORATION ONLY

Customer: Northline Design, Cedar studio.
Monthly rent: USD 1,950.00.
Payment is due on {day(5)}.

Please include the studio reference on your payment.
This statement and the amendment show different rent amounts.
Review them together before acting; Lipso cannot decide which is authoritative.
'''),
        ('equipment-cover.txt', 'Equipment protection', 'Equipment cover', day(-180), None,
         f'''FIELDWORK / EQUIPMENT PROTECTION
FICTIONAL SAMPLE — FOR EXPLORATION ONLY

Policyholder: Northline Design.
Effective date: {day(-180)}.
Annual premium: USD 640.00.
Coverage limit: USD 25,000.00.
Policy expiry date: {day(23)}.
Renewal date: {day(24)}.

Covered items: two cameras, lighting equipment, and portable audio recorders.
Accidental damage is included. Unattended equipment in an unlocked vehicle is excluded.
Claims require proof of purchase and a written description of the incident.
'''),
        ('website-scope.txt', 'Website delivery agreement', 'Harbor website', day(-20), None,
         f'''HARBOR / WEBSITE DELIVERY AGREEMENT
FICTIONAL SAMPLE — FOR EXPLORATION ONLY

Client: Harbor Books. Supplier: Northline Design.
Effective date: {day(-20)}.
Invoice total: USD 4,800.00.
Deposit: USD 2,400.00.
Delivery deadline: {day(9)}.
Final payment is due on {day(16)}.

Scope: a five-page website, a searchable catalog, and staff training.
The client supplies approved copy and imagery before the design phase.
Two rounds of design revisions are included. Hosting is outside this agreement.
'''),
        ('hosting-renewal.txt', 'Hosting · next renewal', 'Hosting', day(30), None,
         f'''BRANCH / UPCOMING HOSTING TERMS
FICTIONAL SAMPLE — FOR EXPLORATION ONLY

Effective date: {day(30)}.
Monthly fee: USD 28.00.
Renewal date: {day(31)}.
Notice period: 14 days.

These terms apply next month, not today.
'''),
    ]
    ids = {}
    for filename, title, matter, effective, previous, text in records:
        result = store.import_document(filename, text.encode(), matter=matter, title=title, effective_date=effective,
                                       replaces_id=ids.get(previous), demo=True)
        ids[filename] = result['id']
    snapshot = store.snapshot()
    find = lambda name, key: next(f['id'] for f in snapshot['facts'] if f['document_id'] == ids[name] and f['key'] == key)
    store.save_plan({
        'name': 'Northline · the next 60 days', 'currency': 'USD', 'start': day(0), 'horizon': 60,
        'opening_balance': '3200', 'reserve': '1000', 'capacity': [4, 4, 4, 4, 3, 0, 0],
        'tasks': [
            {'id': 'copy', 'title': 'Approve Harbor copy', 'hours': 6, 'earliest': day(0), 'due': day(3), 'dependencies': [], 'priority': 4},
            {'id': 'design', 'title': 'Design Harbor website', 'hours': 20, 'earliest': day(0), 'due': day(7), 'dependencies': ['copy'], 'priority': 4},
            {'id': 'delivery', 'title': 'Build and deliver website', 'hours': 18, 'earliest': day(0), 'due': day(9), 'dependencies': ['design'], 'priority': 5,
             'source_fact_id': find('website-scope.txt', 'delivery_date')},
            {'id': 'cover', 'title': 'Review equipment cover', 'hours': 2, 'earliest': day(0), 'due': day(23), 'dependencies': [], 'priority': 3,
             'source_fact_id': find('equipment-cover.txt', 'expiry_date')},
        ],
        'flows': [
            {'id': 'rent', 'title': 'Cedar studio rent', 'direction': 'out', 'amount': '2050', 'date': day(5), 'recurrence': 'monthly', 'probability': 1, 'delay_days': 0, 'variance': 0,
             'source_fact_id': find('studio-amendment.txt', 'monthly_rent'), 'source_date_id': find('studio-invoice.txt', 'due_date')},
            {'id': 'harbor', 'title': 'Harbor final payment', 'direction': 'in', 'amount': '2400', 'date': day(16), 'recurrence': 'once', 'probability': .9, 'delay_days': 10, 'variance': 0,
             'depends_on_task': 'delivery', 'lag_days': 2, 'source_date_id': find('website-scope.txt', 'due_date')},
            {'id': 'retainer', 'title': 'Design retainer', 'direction': 'in', 'amount': '1900', 'date': day(10), 'recurrence': 'monthly', 'probability': .95, 'delay_days': 4, 'variance': .1},
            {'id': 'living', 'title': 'Weekly essentials', 'direction': 'out', 'amount': '260', 'date': day(1), 'recurrence': 'weekly', 'probability': 1, 'delay_days': 0, 'variance': .2},
            {'id': 'insurance', 'title': 'Equipment renewal', 'direction': 'out', 'amount': '640', 'date': day(24), 'recurrence': 'once', 'probability': 1, 'delay_days': 0, 'variance': 0,
             'source_fact_id': find('equipment-cover.txt', 'annual_premium'), 'source_date_id': find('equipment-cover.txt', 'renewal_date')},
        ],
    })
    return {'count': len(records)}
