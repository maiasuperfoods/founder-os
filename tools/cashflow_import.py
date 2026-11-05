#!/usr/bin/env python3
"""Import a newer version of the holdco cash flow model from Google Sheets.

The model is kept as a Google Sheet that the holdco cash flow chat in Claude updates (each update is saved
as a new sheet titled "Holdco_CashFlow_Model_..."). Download the newest one as an Excel file
(Google Drive connector: download_file_content with exportMimeType
application/vnd.openxmlformats-officedocument.spreadsheetml.sheet) and pass the result here:

  python3 tools/cashflow_import.py <download> --id <sheet id> --title "<sheet title>" --edited YYYY-MM-DD

<download> is either the .xlsx file or the JSON the connector returns ({"content": "<base64>", ...}),
which is what a session saves to a file when the result is too large to show.

Writes sources/cashflow/model-export.txt (one "## Sheet name: <tab>" block per tab, rows as CSV, values as the
sheet displays them) and sources/cashflow/source.json. Run tools/sync.py afterwards to rebuild the section.
Needs openpyxl (pip install openpyxl).
"""
import argparse, base64, csv, datetime, io, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'sources', 'cashflow')
NEEDED = ['1. Inputs', '7. Cash Flow Weekly', '8. Monthly Summary', '9. Ramp Scenarios', '10. Committed POs']


def decimals(nf):
    m = re.search(r'0\.(0+)', nf or '')
    return len(m.group(1)) if m else 0


def fmt(c):
    v = c.value
    if v is None:
        return ''
    if isinstance(v, bool):
        return str(v)
    if hasattr(v, 'strftime'):
        return v.strftime('%b %-d, %Y')
    if not isinstance(v, (int, float)):
        return str(v)
    nf = c.number_format or ''
    d = decimals(nf)
    if '%' in nf:
        return f'{v * 100:.{max(d - 2, 1) if d else 1}f}%'
    if v == 0 and ('$' in nf or '-' in nf or '#,##0' in nf):
        return '-'
    if '$' in nf:
        s = '${:,.{d}f}'.format(abs(v), d=d)
        return '(' + s + ')' if v < 0 else s
    if 'x' in nf.replace('0x', 'x'):
        return f'{v:.{d or 2}f}x'
    s = '{:,.{d}f}'.format(abs(v), d=d) if ('#,##0' in nf or d) else ('{:,.0f}'.format(abs(v)) if float(v).is_integer() else '{:,.2f}'.format(abs(v)))
    return ('(' + s + ')' if '(' in nf else '-' + s) if v < 0 else s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('download')
    ap.add_argument('--id', required=True)
    ap.add_argument('--title', required=True)
    ap.add_argument('--edited', required=True, help='the day the sheet was last edited, YYYY-MM-DD')
    a = ap.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_-]{20,80}', a.id):
        sys.exit('not a Google Sheet id: ' + a.id)
    raw = open(a.download, 'rb').read()
    if raw[:2] != b'PK':                       # the connector's JSON with the file in base64
        j = json.loads(raw)
        raw = base64.b64decode(j['content'])
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(raw), data_only=True)
    missing = [t for t in NEEDED if t not in wb.sheetnames]
    if missing:
        sys.exit('the workbook has no tab named ' + ', '.join(missing) + '; tabs are: ' + ', '.join(wb.sheetnames))
    out = []
    for ws in wb.worksheets:
        buf = io.StringIO(); w = csv.writer(buf, lineterminator='\n')
        for row in ws.iter_rows():
            cells = [fmt(c) for c in row]
            while cells and cells[-1] == '':
                cells.pop()
            w.writerow(cells)
        out.append('## Sheet name: ' + ws.title + '\n' + buf.getvalue().rstrip('\n') + '\n')
    os.makedirs(OUT, exist_ok=True)
    open(os.path.join(OUT, 'model-export.txt'), 'w', encoding='utf8').write('\n'.join(out))
    json.dump({'title': 'Holdco Cash Flow Model, Oct 2026 to Jun 2027', 'sheetName': a.title,
               'sheetUrl': 'https://docs.google.com/spreadsheets/d/%s/edit' % a.id, 'sheetLastEdited': a.edited,
               'exportTaken': str(datetime.date.today())}, open(os.path.join(OUT, 'source.json'), 'w'), indent=1)
    print('imported %s (%d tabs, edited %s)' % (a.id, len(wb.sheetnames), a.edited))


if __name__ == '__main__':
    main()
