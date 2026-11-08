#!/usr/bin/env python3
"""Post Company Initiatives call recaps to Slack as the bot (the same bot as the creative dashboard's weekly recaps).

usage: SLACK_BOT_TOKEN=xoxb-... python3 tools/slack_post.py sources/initiatives/outbox/<id>.json [...]
Each file is {"channel": "C...", "text": "markdown"} written by tools/initiatives_add.py.
Run by .github/workflows/initiatives-slack.yml for the outbox files a push adds; the bot must be in the channel.
"""
import json, os, sys, urllib.request

TOKEN = os.environ.get('SLACK_BOT_TOKEN', '').strip()
if not TOKEN:
    raise SystemExit('::error::SLACK_BOT_TOKEN secret is missing (founder-os repo Settings > Secrets and variables > Actions)')
bad = 0
for path in sys.argv[1:]:
    m = json.load(open(path, encoding='utf8'))
    text = m['text']
    first = text.split('\n')[0].strip('*')
    body = {'channel': m['channel'], 'text': first[:150], 'blocks': [{'type': 'markdown', 'text': text[:11900]}],
            'unfurl_links': False, 'unfurl_media': False}
    req = urllib.request.Request('https://slack.com/api/chat.postMessage', data=json.dumps(body).encode(),
                                 headers={'Authorization': 'Bearer ' + TOKEN, 'Content-Type': 'application/json; charset=utf-8'})
    r = json.load(urllib.request.urlopen(req))
    if r.get('ok'):
        print('posted %s to %s (ts %s)' % (os.path.basename(path), m['channel'], r.get('ts')))
    else:
        bad += 1
        print('::error::Slack refused %s: %s' % (os.path.basename(path), r.get('error')))
sys.exit(1 if bad else 0)
