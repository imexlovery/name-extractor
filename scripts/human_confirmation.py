"""Local, saved confirmation table for the fixed 60+40 human review sample."""
import argparse
from datetime import datetime, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path

from acceptance import WORK, read, save
from extract import VERSION

HUMAN = WORK / 'human'


def update():
    selection = json.loads((HUMAN / 'random-60-selection.json').read_text())
    random_ids = selection['row_ids']
    risk_path = HUMAN / 'risk-40-selection.json'
    risk_ids = json.loads(risk_path.read_text())['row_ids'] if risk_path.exists() else []
    ids = random_ids + risk_ids
    mapping = {r['row_id']: r for r in read(WORK / 'row-map.jsonl') if r['row_id'] in ids}
    source = {r['row_id']: r for r in read(WORK / 'source-rows.jsonl') if r['row_id'] in ids}
    scripts = {row: r['result'] for r in read(WORK.parent / f'script-{VERSION}.jsonl') for row in r['rows']}
    final_path = WORK / 'fixed-reference.jsonl'
    reference_path = final_path if final_path.exists() else WORK / 'valid-first-answers.jsonl'
    reference = {r['input_id']: r for r in read(reference_path)}
    records = []
    for row_id in ids:
        original = source[row_id]
        records.append(dict(row_id=row_id, excel_row=original['excel_row'],
                            sample_kind='随机' if row_id in random_ids else '风险',
                            fields=original['fields'], script=scripts[original['excel_row']],
                            ai=reference.get(mapping[row_id]['input_id'])))
    save(HUMAN / 'confirmation-data.json', dict(updated_at=datetime.now(timezone.utc).isoformat(),
         script_version=VERSION, reference_stage='固定参考' if final_path.exists() else '首轮AI参考',
         random_count=len(random_ids), risk_count=len(risk_ids), records=records))


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/confirmation-data.json':
            update()
        if self.path == '/confirmations.json' and not (HUMAN / 'confirmations.json').exists():
            save(HUMAN / 'confirmations.json', {})
        super().do_GET()

    def do_POST(self):
        if self.path != '/confirm':
            self.send_error(404)
            return
        record = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        path = HUMAN / 'confirmations.json'
        records = json.loads(path.read_text()) if path.exists() else {}
        record['saved_at'] = datetime.now(timezone.utc).isoformat()
        records[record['row_id']] = record
        save(path, records)
        # Preserve every human edit; the latest checkbox is a view, not the audit history.
        with (HUMAN / 'confirmation-history.jsonl').open('a') as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + '\n')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(b'{"saved":true}')

    def log_message(self, *args):
        pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['update', 'serve'])
    args = parser.parse_args()
    update()
    if args.action == 'serve':
        server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, directory=str(HUMAN)))
        print(f'http://127.0.0.1:{server.server_port}/confirmation.html', flush=True)
        server.serve_forever()
