from datetime import datetime, timedelta, timezone


def escape(text):
    return str(text).replace('\\', '\\\\').replace('\r', '').replace('\n', '\\n').replace(';', '\\;').replace(',', '\\,')


def fold(line):
    # RFC 5545 lines are limited in octets, not Unicode character count.
    output, current, size = [], '', 0
    for char in line:
        encoded = len(char.encode('utf-8'))
        if size + encoded > 75:
            output.append(current)
            current, size = ' ', 1
        current += char
        size += encoded
    output.append(current)
    return '\r\n'.join(output)


def export_calendar(snapshot):
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    lines = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Lipso//Commitments//EN', 'CALSCALE:GREGORIAN', 'METHOD:PUBLISH']
    for item in snapshot['obligations']:
        if item['action_state'] != 'open':
            continue
        due = datetime.strptime(item['value'], '%Y-%m-%d')
        # Stable UIDs prevent duplicate calendar entries after an application rename.
        lines.extend(['BEGIN:VEVENT', f"UID:margin-{item['document_id']}-{item['id']}@localhost", f'DTSTAMP:{stamp}',
                      'DTSTART;VALUE=DATE:' + due.strftime('%Y%m%d'), 'DTEND;VALUE=DATE:' + (due + timedelta(days=1)).strftime('%Y%m%d'),
                      'SUMMARY:' + escape(item['label'] + ' · ' + item['matter']),
                      'DESCRIPTION:' + escape(item['quote'] + '\nSource: ' + item['document_title'] + '\nReview status: ' + item['status']),
                      'TRANSP:TRANSPARENT', 'END:VEVENT'])
    lines.append('END:VCALENDAR')
    return ('\r\n'.join(fold(line) for line in lines) + '\r\n').encode('utf-8')
