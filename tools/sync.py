#!/usr/bin/env python3
"""Rebuild the mirrored sections under public/s/ and the section list the shell reads.

Each section is a read-only copy of a page that lives somewhere else. This script copies the latest
build of each one into the site and records how fresh it is. Run it from the repo root:

  python3 tools/sync.py [--creative DIR] [--wbr DIR] [--wbr-export DIR] [--ci DIR]

  --creative    a clone of maiasuperfoods/maia-creative-dashboard (its public/ folder is the built site)
  --wbr         a clone of maiasuperfoods/maia-weekly-business-review (page source, data snapshot, export script)
  --wbr-export  a folder of the review page's database saved with ArtifactData (optional, newer than the clone's snapshot)
  --ci          a clone of maiasuperfoods/competitor-intelligence (the Avia study's page and datasets)

A source that is not given is left as it is in public/s/. The Haskap study, the org chart and the cash
flow model export live in this repo (public/s/ and sources/cashflow/). Nothing here talks to the network.
"""
import argparse, datetime, json, os, re, shutil, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUB = os.path.join(ROOT, 'public', 's')
SRC = os.path.join(ROOT, 'sources')
STATE = os.path.join(ROOT, 'sources', 'state.json')      # what each section was last built from


def load_state():
    return json.load(open(STATE)) if os.path.exists(STATE) else {}


def replace_dir(src, dst):
    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def git_date(repo):
    try:
        return subprocess.check_output(['git', '-C', repo, 'log', '-1', '--format=%cs'], text=True).strip()
    except Exception:
        return None


def sync_creative(repo, st):
    src = os.path.join(repo, 'public')
    if not os.path.exists(os.path.join(src, 'index.html')):
        sys.exit('creative: %s has no public/index.html' % repo)
    dst = os.path.join(PUB, 'creative')
    replace_dir(src, dst)
    # pages link to each other with the old site's address; point them at this site instead
    n = 0
    for d, _, files in os.walk(dst):
        for f in files:
            if f.endswith('.html'):
                p = os.path.join(d, f)
                t = open(p, encoding='utf8').read()
                t2 = re.sub(r'https://maia-creative-dashboard[a-z0-9-]*\.vercel\.app', '/s/creative', t)
                if t2 != t:
                    open(p, 'w', encoding='utf8').write(t2)
                    n += 1
    st['creative'] = {'asOf': git_date(repo) or str(datetime.date.today()), 'files': sum(len(f) for _, _, f in os.walk(dst)), 'relinked': n}
    print('creative: copied, links rewritten in %d pages, data as of %s' % (n, st['creative']['asOf']))


SERVICE_ONLY = r'''
<style>
html.only-service .tabs, html.only-service #themeSeg, html.only-service .seg[aria-label="Brand"], html.only-service .ctl{display:none!important}
html.only-service .bar-top{padding-block:14px}
html.embedded [role=status][style*="warn-wash"]{display:none}
</style>
<script>
/* Founder OS: ?only=service shows the customer service tab on its own. */
(function(){
  var q = new URLSearchParams(location.search);
  if (window.parent !== window) document.documentElement.classList.add('embedded');
  if (q.get('only') !== 'service') return;
  document.documentElement.classList.add('only-service');
  var keep = function(){ if (location.hash !== '#service') location.replace('#service'); };
  keep(); window.addEventListener('hashchange', keep);
  document.addEventListener('DOMContentLoaded', function(){
    var h = document.querySelector('.bar-top h1'); if (h) h.textContent = 'Customer Service Report';
    document.title = 'Customer Service Report';
  });
})();
</script>
'''


def sync_wbr(repo, export, st):
    dst = os.path.join(PUB, 'wbr')
    os.makedirs(os.path.join(dst, 'data'), exist_ok=True)
    if repo:
        subprocess.check_call([sys.executable, '-I', os.path.join(repo, 'scripts', 'build_page.py')])
        page = open(os.path.join(repo, 'public', 'index.html'), encoding='utf8').read()
        if 'only-service' not in page:
            page = page.replace('</head>', SERVICE_ONLY + '</head>', 1)
        open(os.path.join(dst, 'index.html'), 'w', encoding='utf8').write(page)
        if not export:
            shutil.copy(os.path.join(repo, 'public', 'data', 'db.json'), os.path.join(dst, 'data', 'db.json'))
    if export:
        # the review repo's own export script merges the saved documents into its snapshot (and refuses
        # anything that looks like a customer's email, phone or card number); then that snapshot is copied here
        if not repo:
            sys.exit('wbr: --wbr-export also needs --wbr (the export script lives in that repo)')
        subprocess.check_call([sys.executable, '-I', os.path.join(repo, 'scripts', 'export.py'), export, str(datetime.date.today())])
        shutil.copy(os.path.join(repo, 'public', 'data', 'db.json'), os.path.join(dst, 'data', 'db.json'))
    db = json.load(open(os.path.join(dst, 'data', 'db.json')))
    daily = db['collections'].get('actuals', {}).get('daily', {})
    weeks = sorted(db['collections'].get('weeks', {}))
    st['wbr'] = {'asOf': db.get('exportedAt'), 'through': daily.get('through'), 'lastWeek': weeks[-1] if weeks else None}
    print('wbr: snapshot %s, actuals through %s, last scorecard week %s' % (st['wbr']['asOf'], st['wbr']['through'], st['wbr']['lastWeek']))


def sync_ci(repo, st):
    run = os.path.join(repo, 'runs', 'avia-cortisol-detox-2026-10-24-v3', 'phase2')
    dst = os.path.join(PUB, 'competitors', 'studies', 'avia-cortisol-detox')
    if os.path.exists(dst):
        shutil.rmtree(dst)
    os.makedirs(os.path.join(dst, 'data'))
    shutil.copy(os.path.join(run, 'dash', 'index_v4.html'), os.path.join(dst, 'page.html'))
    manifest = json.load(open(os.path.join(run, 'dash', 'datasets_manifest.json')))
    datasets = {}
    for m in manifest:
        f = os.path.join(run, 'datasets', m['file'])
        if os.path.exists(f):
            shutil.copy(f, os.path.join(dst, 'data', m['file']))
            datasets[m['id']] = 'data/' + m['file']
    study = json.load(open(os.path.join(run, 'study.json')))
    json.dump({'title': study.get('title', 'AVIA Cortisol Detox competitor ad intelligence'), 'asOf': git_date(repo),
               'live': 'https://claude.ai/artifact/CQeeKB3vnqb3utGxfpVTz8', 'params': {}, 'datasets': datasets},
              open(os.path.join(dst, 'study.json'), 'w'), indent=1)
    st['ci-avia'] = {'asOf': git_date(repo), 'datasets': len(datasets)}
    print('competitors: Avia study copied with %d datasets' % len(datasets))


def sync_local(st):
    # The Haskap study and the org chart are kept as finished pages in public/s/ (their only other home is
    # their Claude page); the cash flow section is rebuilt from the model export in sources/cashflow/.
    study = os.path.join(PUB, 'competitors', 'studies', 'haskap', 'study.json')
    st['ci-haskap'] = {'asOf': json.load(open(study)).get('asOf')}
    subprocess.check_call([sys.executable, '-I', os.path.join(ROOT, 'tools', 'build_cashflow.py')])
    src = json.load(open(os.path.join(SRC, 'cashflow', 'source.json')))
    st['cashflow'] = {'asOf': src['exportTaken']}


def write_sections(st):
    meta = json.load(open(os.path.join(SRC, 'sections.json')))
    def stamp(x):
        src = st.get(x.get('state') or x['id']) or {}
        if src.get('asOf') and not x.get('asOfFixed'):
            x['asOf'] = src['asOf']
        if src.get('through'):
            x['through'] = src['through']
    for g in meta['groups']:
        for s in g['items']:
            stamp(s)
            for v in s.get('views', []):
                if v.get('state'):
                    stamp(v)
    meta['builtAt'] = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%MZ')
    os.makedirs(os.path.join(ROOT, 'public', 'assets'), exist_ok=True)
    json.dump(meta, open(os.path.join(ROOT, 'public', 'assets', 'sections.json'), 'w'), indent=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--creative'); ap.add_argument('--wbr'); ap.add_argument('--wbr-export'); ap.add_argument('--ci')
    a = ap.parse_args()
    st = load_state()
    os.makedirs(PUB, exist_ok=True)
    if a.creative: sync_creative(os.path.abspath(a.creative), st)
    if a.wbr or a.wbr_export: sync_wbr(os.path.abspath(a.wbr) if a.wbr else None, os.path.abspath(a.wbr_export) if a.wbr_export else None, st)
    if a.ci: sync_ci(os.path.abspath(a.ci), st)
    sync_local(st)
    json.dump(st, open(STATE, 'w'), indent=1, sort_keys=True)
    write_sections(st)
    print('sections list written')


if __name__ == '__main__':
    main()
