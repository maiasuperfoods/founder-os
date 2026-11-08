#!/usr/bin/env python3
"""Add one recurring call to an initiatives board:
  Company Initiatives  (--board company, the default): Performance Call, Creative Call -> #growth-performance
  Executive Initiatives (--board executive): the founders' Morning Brief -> #maia-ambitions

usage:
  python3 -I tools/initiatives_add.py --id <Fireflies meeting id> --kind performance|creative|morning [--board company|executive] \
      --recap recap.json --tasks tasks.json [--share-url URL] [--transcript FILE] [--no-slack]

  recap.json  {"summary": "two or three sentences", "points": ["what was discussed", ...], "decisions": ["...", ...]}
  tasks.json  [{"title": "...", "owner": "First Last", "due": "YYYY-MM-DD"}, ...]  (the list given to os_init_ingest)
  --transcript  a file holding the fireflies_get_transcript result. Without it, the script looks for that
                result in this machine's Claude session files (~/.claude/projects), the way the review's
                helper scripts do, so the transcript never has to be retyped.

Writes (and nothing else):
  public/s/<initiatives|executive>/data/calls/<id>.json   the call: recap, tasks as imported, and the full transcript
  public/s/<initiatives|executive>/data/calls.json        the list of calls the page shows
  sources/initiatives/outbox/<id>.json        the Slack recap; the GitHub workflow posts it when it is pushed
  sources/state.json                          freshness of the section
Attendee email addresses in the Fireflies result are never copied.
"""
import argparse, datetime, glob, json, os, re, sys
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTBOX = os.path.join(ROOT, 'sources', 'initiatives', 'outbox')
STATE = os.path.join(ROOT, 'sources', 'state.json')
BOARDS = {  # board -> (page folder, Slack channel, state key, kinds)
    'company': ('initiatives', 'C09KUNCFP16', 'initiatives', ('performance', 'creative')),    # #growth-performance
    'executive': ('executive', 'C092A5TJY6Q', 'executive', ('morning',)),                     # #maia-ambitions (private: invite the bot)
}
NAMES = {'Admin Account': 'Brandon', 'Damian Media Buyer': 'Damian', 'Youssef B': 'Youssef', 'Youssef Bouzaien': 'Youssef',
         'Chitrakar Sujal': 'Sujal Chitrakar', 'Sujal': 'Sujal Chitrakar'}   # Fireflies speaker labels shown under the person's name
KINDS = {'performance': 'Performance Call', 'creative': 'Creative Call', 'morning': 'Morning Brief'}
ID = re.compile(r'^[0-9A-Z]{20,40}$')
LINE = re.compile(r'^\[(\d+(?::\d+){1,2}) - [\d:]+\] ([^:]{1,80}): (.*)$')


def strings(v):
    if isinstance(v, str):
        yield v
    elif isinstance(v, dict):
        for x in v.values():
            yield from strings(x)
    elif isinstance(v, list):
        for x in v:
            yield from strings(x)


def find_transcript(mid):
    """The newest text block that is a fireflies_get_transcript result for this meeting."""
    head = 'Id: ' + mid + '\n'
    base = os.path.expanduser('~/.claude/projects')
    files = glob.glob(base + '/**/*.json*', recursive=True) + glob.glob(base + '/**/tool-results/*.txt', recursive=True)
    best = None
    for f in sorted(files, key=os.path.getmtime):
        try:
            raw = open(f, encoding='utf8', errors='replace').read()
        except OSError:
            continue
        if mid not in raw or 'Sentences:' not in raw:
            continue
        docs = []
        if f.endswith('.txt'):
            docs = [raw]
        try:
            docs = docs or [json.loads(raw)]
        except ValueError:
            for ln in raw.splitlines():
                if mid in ln:
                    try: docs.append(json.loads(ln))
                    except ValueError: pass
        for d in docs:
            for s in strings(d):
                if s.startswith(head) and 'Sentences:' in s:
                    best = s
    return best


def parse(text):
    meta, sent = {}, []
    body = False
    for ln in text.split('\n'):
        if ln.startswith('Sentences: '):
            body = True
            ln = ln[len('Sentences: '):]
        m = LINE.match(ln) if body else None
        if m:
            parts = [int(p) for p in m.group(1).split(':')]
            secs = parts[0] * 60 + parts[1] if len(parts) == 2 else parts[0] * 3600 + parts[1] * 60 + parts[2]
            who = m.group(2).strip()
            sent.append([secs, NAMES.get(who, who), m.group(3).strip()])
            continue
        if body and sent and not re.match(r'^[A-Z][A-Za-z ]{1,30}: ', ln):
            if ln.strip():
                sent[-1][2] += ' ' + ln.strip()      # a sentence that ran onto a second line
            continue
        mm = re.match(r'^([A-Z][A-Za-z ]{1,30}): (.*)$', ln)
        if mm:
            body = False if mm.group(1) != 'Sentences' else body
            meta.setdefault(mm.group(1), mm.group(2))
    return meta, sent


def fmt_due(d):
    try:
        x = datetime.date.fromisoformat(d)
        return x.strftime('%b ') + str(x.day)
    except (TypeError, ValueError):
        return 'no due date'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--id', required=True); ap.add_argument('--kind', required=True, choices=sorted(KINDS))
    ap.add_argument('--recap', required=True); ap.add_argument('--tasks', required=True)
    ap.add_argument('--share-url'); ap.add_argument('--transcript'); ap.add_argument('--no-slack', action='store_true')
    ap.add_argument('--board', default='company', choices=sorted(BOARDS))
    a = ap.parse_args()
    folder, channel, state_key, kinds = BOARDS[a.board]
    if a.kind not in kinds:
        sys.exit('kind %s does not belong on the %s board' % (a.kind, a.board))
    DATA = os.path.join(ROOT, 'public', 's', folder, 'data')
    if not ID.match(a.id):
        sys.exit('not a Fireflies meeting id: ' + a.id)
    text = open(a.transcript, encoding='utf8').read() if a.transcript else find_transcript(a.id)
    if a.transcript and text.lstrip().startswith('['):
        text = next(s for s in strings(json.loads(text)) if s.startswith('Id: '))
    if not text:
        sys.exit('no fireflies_get_transcript result for %s was found in this session; fetch it first' % a.id)
    meta, sent = parse(text)
    if len(sent) < 20:
        sys.exit('only %d transcript lines were read; stopping' % len(sent))
    recap = json.load(open(a.recap, encoding='utf8'))
    tasks = json.load(open(a.tasks, encoding='utf8'))
    if not isinstance(recap.get('summary'), str) or not isinstance(tasks, list):
        sys.exit('recap.json needs a summary; tasks.json must be a list')
    when = meta.get('DateString', '')
    dt = datetime.datetime.fromisoformat(when.replace('Z', '+00:00')) if when else None
    local = dt.astimezone(ZoneInfo('America/Toronto')) if dt else None
    speakers = []
    for s in sent:
        if s[1] not in speakers: speakers.append(s[1])
    call = {
        'id': a.id, 'kind': a.kind, 'kindLabel': KINDS[a.kind], 'title': meta.get('Title', KINDS[a.kind]),
        'at': when, 'date': local.date().isoformat() if local else None,
        'minutes': round(float(meta.get('Duration', 0) or 0)), 'speakers': speakers,
        'fireflies': 'https://app.fireflies.ai/view/' + a.id,
        'summary': recap['summary'].strip(), 'points': [p for p in recap.get('points', []) if p],
        'decisions': [p for p in recap.get('decisions', []) if p],
        'tasksImported': [{'title': t.get('title', ''), 'owner': t.get('owner', ''), 'due': t.get('due') or None} for t in tasks],
    }
    os.makedirs(os.path.join(DATA, 'calls'), exist_ok=True)
    full = dict(call, transcript=sent)
    json.dump(full, open(os.path.join(DATA, 'calls', a.id + '.json'), 'w', encoding='utf8'), ensure_ascii=False, separators=(',', ':'))
    idx_path = os.path.join(DATA, 'calls.json')
    idx = json.load(open(idx_path, encoding='utf8')) if os.path.exists(idx_path) else []
    idx = [c for c in idx if c['id'] != a.id] + [call]
    idx.sort(key=lambda c: c.get('at') or '', reverse=True)
    json.dump(idx, open(idx_path, 'w', encoding='utf8'), ensure_ascii=False, indent=1)

    st = json.load(open(STATE)) if os.path.exists(STATE) else {}
    st[state_key] = {'asOf': idx[0].get('date'), 'calls': len(idx)}
    json.dump(st, open(STATE, 'w'), indent=1)

    if not a.no_slack:
        day = local.strftime('%a %b ') + str(local.day) if local else ''
        lines = ['**%s recap · %s**' % (KINDS[a.kind], day), call['summary']]
        if call['points']:
            lines += ['', '**Discussed**'] + ['- ' + p for p in call['points'][:8]]
        if call['decisions']:
            lines += ['', '**Decided**'] + ['- ' + p for p in call['decisions'][:6]]
        if tasks:
            lines += ['', '**Tasks (%d)**' % len(tasks)]
            lines += ['- %s — %s · due %s' % (t['title'], t.get('owner') or 'no owner yet', fmt_due(t.get('due'))) for t in tasks[:15]]
        if a.share_url:
            lines += ['', '[Open the tasks and the full transcript](%s#call-%s)' % (a.share_url, a.id)]
        os.makedirs(OUTBOX, exist_ok=True)
        json.dump({'channel': channel, 'text': '\n'.join(lines)}, open(os.path.join(OUTBOX, a.id + '.json'), 'w', encoding='utf8'), ensure_ascii=False, indent=1)
    print('imported %s: %s %s, %d min, %d transcript lines, %d speakers, %d tasks%s' % (
        a.id, KINDS[a.kind], call['date'], call['minutes'], len(sent), len(speakers), len(tasks), '' if a.no_slack else ', Slack recap queued'))


if __name__ == '__main__':
    main()
