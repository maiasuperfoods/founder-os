#!/usr/bin/env python3
"""Turn the cash flow model export (sources/cashflow/model-export.txt) into public/s/cashflow/data.json.

The export is the text form of the Google Sheet: one block per tab, starting with "## Sheet name: <tab>",
rows as CSV. To refresh this section, replace the export file with a newer one and run tools/sync.py.
sources/cashflow/source.json says which sheet the export came from and when it was taken.
"""
import csv, io, json, os, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'sources', 'cashflow')
OUT = os.path.join(ROOT, 'public', 's', 'cashflow', 'data.json')


def num(s):
    """'$544,332' -> 544332.0, '($20,510)' -> -20510.0, '17.6%' -> 0.176, '0.90x' -> 0.9, '-' -> 0.0, '' -> None"""
    if s is None:
        return None
    t = s.strip()
    if t == '':
        return None
    if t == '-':
        return 0.0
    neg = t.startswith('(') and t.endswith(')')
    t = t.strip('()').replace('$', '').replace(',', '')
    mult = 1.0
    if t.endswith('%'):
        t, mult = t[:-1], 0.01
    elif t.endswith('x'):
        t = t[:-1]
    try:
        v = float(t) * mult
    except ValueError:
        return None
    return -v if neg else v


def tabs(text):
    parts = re.split(r'^## Sheet name: (.*)$', text, flags=re.M)
    return {parts[i].strip(): list(csv.reader(io.StringIO(parts[i + 1].strip('\n')))) for i in range(1, len(parts), 2)}


def find(rows, start):
    for r in rows:
        if r and r[0].startswith(start):
            return r
    raise SystemExit('cash flow export: no row starting with %r' % start)


def weekly(rows):
    head = find(rows, 'Line')
    weekno = find(rows, 'Model week #')
    starts = find(rows, 'Week start')
    cols = [i for i in range(1, len(head)) if i < len(weekno) and re.fullmatch(r'\d+', weekno[i].strip() or 'x')]
    out = {'labels': [head[i] for i in cols], 'starts': [starts[i] for i in cols], 'rows': {}}
    want = {
        'revenue': 'Revenue (all lines)', 'payouts': 'Payouts received', 'adCharged': 'Ad spend charged to the card',
        'cardBalance': 'Unpaid ad spend on the card', 'adPaid': 'Ad spend paid in cash', 'inventory': 'Inventory purchases',
        'committed': 'Committed supplier balances', 'fulfillment': 'Fulfillment', 'fixedOpex': 'Fixed opex', 'varOpex': 'Variable opex',
        'net': 'Net cash flow', 'closing': 'Closing cash', 'belowBuffer': 'Below buffer?', 'cardAtLimit': 'Card at its limit?',
        'reserve': 'PayPal reserve outstanding',
    }
    for key, label in want.items():
        r = find(rows, label)
        out['rows'][key] = [num(r[i]) if i < len(r) else None for i in cols]
    first = cols[0]
    def tail(label):
        r = find(rows, label)
        vals = [c for c in r[1:] if c.strip()]
        return vals
    out['summary'] = {
        'minCash': num(tail('Minimum closing cash')[0]), 'minWeek': int(num(tail('Week of minimum')[0])),
        'peakCard': num(tail('Peak unpaid card balance')[0]), 'uncappedCard': num(tail('Uncapped card balance')[0]),
    }
    return out


def monthly(rows):
    head = find(rows, 'Line')
    months = [c for c in head[1:] if re.match(r'^[A-Z][a-z]{2}-\d\d$', c.strip())]
    n = len(months)
    extra = [c for c in head[1 + n:] if c.strip()]
    groups, cur, started = [], None, False
    for r in rows:
        if not r or not r[0].strip():
            continue
        if r[0].startswith('Line'):
            started = True
            continue
        if not started:
            continue
        cells = r[1:1 + n + len(extra)]
        if not any(c.strip() for c in cells):
            if r[0].startswith('Operating profit (accrual) and cas'):
                break
            cur = {'title': r[0].strip(), 'rows': []}
            groups.append(cur)
            continue
        if cur is None:
            cur = {'title': '', 'rows': []}
            groups.append(cur)
        cells = cells + [''] * (n + len(extra) - len(cells))
        cur['rows'].append({'label': r[0].strip(), 'cells': [c.strip() for c in cells[:n]], 'total': [c.strip() for c in cells[n:]],
                            'nums': [num(c) for c in cells[:n]]})
    return {'months': months, 'extra': extra, 'groups': [g for g in groups if g['rows']]}


def cm_weekly(rows):
    """Tab 7b: contribution margin by week, one block per line (MAIA Cacao, Haskap, AVIA, consolidated)."""
    if rows is None:
        return None
    head = find(rows, 'Line')
    n = len([c for c in head[1:] if c.strip()])
    starts = find(rows, 'Week start')
    groups, cur, on = [], None, False
    for r in rows:
        if not r or not r[0].strip():
            continue
        if r[0].startswith('Line'):
            on = True
            continue
        if not on or r[0].startswith('Week start'):
            continue
        cells = (r[1:1 + n] + [''] * n)[:n]
        if not any(c.strip() for c in cells):
            cur = {'title': r[0].strip(), 'rows': []}
            groups.append(cur)
            continue
        if cur is None:
            cur = {'title': '', 'rows': []}
            groups.append(cur)
        cur['rows'].append({'label': r[0].strip(), 'cells': [c.strip() for c in cells]})
    intro = [r[0] for r in rows[:2] if r and r[0].strip()]
    return {'labels': [c.strip() for c in head[1:1 + n]], 'starts': (starts[1:1 + n] + [''] * n)[:n], 'groups': [g for g in groups if g['rows']], 'intro': intro}


def pos(rows):
    out, on = [], False
    for r in rows:
        if r and r[0].startswith('Pay date'):
            on = True
            continue
        if on and r and r[0].strip():
            if r[0].startswith('Total'):
                return {'rows': out, 'total': r[1].strip()}
            out.append({'date': r[0].strip(), 'amount': r[1].strip(), 'what': r[2].strip() if len(r) > 2 else '', 'n': num(r[1])})
    return {'rows': out, 'total': ''}


def scenarios(rows):
    out, cur = [], None
    intro = [r[0] for r in rows[:2] if r and r[0].strip()]
    for r in rows[2:]:
        if not r or not r[0].strip():
            continue
        filled = [c for c in r[1:] if c.strip()]
        if not filled:
            if r[0].startswith('Read:') and cur:
                cur['read'] = r[0][5:].strip()
            else:
                cur = {'title': r[0].strip(), 'head': None, 'rows': [], 'read': ''}
                out.append(cur)
            continue
        if cur is None:
            continue
        width = max(len(filled) + 1, len(cur['head']) if cur['head'] else 0)
        cells = [c.strip() for c in r[:width]]
        if cur['head'] is None:
            cur['head'] = cells
        else:
            cur['rows'].append(cells)
    return {'intro': intro, 'tables': [t for t in out if t['head']]}


def inputs(rows):
    out, cur = [], None
    for r in rows[2:]:
        if not r or not r[0].strip():
            continue
        vals = [c.strip() for c in r[1:4]] if len(r) > 1 else []
        note = r[4].strip() if len(r) > 4 else ''
        if not any(vals) and not note:
            cur = {'title': r[0].strip(), 'cols': None, 'rows': []}
            out.append(cur)
            continue
        if cur is None:
            cur = {'title': '', 'cols': None, 'rows': []}
            out.append(cur)
        if r[0].strip() in ('Input', 'Pool'):
            cur['cols'] = vals + [note]
            continue
        cur['rows'].append({'label': r[0].strip(), 'vals': vals, 'note': note})
    return [s for s in out if s['rows']]


def main():
    text = open(os.path.join(SRC, 'model-export.txt'), encoding='utf8').read()
    T = tabs(text)
    src = json.load(open(os.path.join(SRC, 'source.json')))
    inp = T['1. Inputs']
    data = {
        'source': src,
        'title': inp[0][0],
        'buffer': num(find(inp, 'Minimum cash buffer')[1]),
        'cardLimit': num(find(inp, 'Card limit')[1]),
        'openingCash': num(find(inp, 'Cash on hand')[1]),
        'weekly': weekly(T['7. Cash Flow Weekly']),
        'monthly': monthly(T['8. Monthly Summary']),
        'payments': pos(T['10. Committed POs']),
        'cmWeekly': cm_weekly(T.get('7b. CM Weekly')),
        'scenarios': scenarios(T['9. Ramp Scenarios']),
        'inputs': inputs(inp),
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(data, open(OUT, 'w', encoding='utf8'), separators=(',', ':'), ensure_ascii=False)
    w = data['weekly']
    lo = min(v for v in w['rows']['closing'] if v is not None)
    print('cash flow: %d weeks, %d months, lowest closing cash %s in %s, %d scenario tables' % (
        len(w['labels']), len(data['monthly']['months']), '{:,.0f}'.format(lo), w['labels'][w['rows']['closing'].index(lo)], len(data['scenarios']['tables'])))
    assert abs(lo - w['summary']['minCash']) < 1, 'lowest weekly cash does not match the model summary row'


if __name__ == '__main__':
    main()
