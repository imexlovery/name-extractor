"""Prepare blind full-input reviews and account for validated, row-level answers.

This module never generates semantic answers or modifies production extraction.
"""
import argparse
from collections import Counter, defaultdict
import csv
from contextlib import redirect_stdout
from datetime import datetime, timezone
import json
import io
import os
from pathlib import Path
import random
import time

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'validation/0.7.0/final-acceptance'
FIELDS = ('标题', '内容', '被许可对象', '颁布机构', '文号')
MODEL = 'gpt-6-luna'
PROMPT_VERSION = 'title-body-blind-v2'
SEED = 20261013


def read(path):
    if not path.exists():
        return []
    with path.open() as stream:
        return [json.loads(line) for line in stream if line.strip()]


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def lines(path, values):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w') as stream:
        for value in values:
            stream.write(json.dumps(value, ensure_ascii=False) + '\n')


def balanced_sample(records, n, rng, key):
    groups = defaultdict(list)
    for record in records:
        groups[key(record)].append(record)
    for group in groups.values():
        rng.shuffle(group)
    keys = sorted(groups)
    rng.shuffle(keys)
    result = []
    while len(result) < n and keys:
        for group in list(keys):
            result.append(groups[group].pop())
            if not groups[group]:
                keys.remove(group)
            if len(result) == n:
                break
    return result


def prepare():
    if (WORK / 'manifest.json').exists():
        raise ValueError('Prepared data already exists; do not replace a running/frozen review.')
    from pilot import stratum
    workbook = load_workbook(ROOT / '任职资格批复汇总测试.xlsx', read_only=True, data_only=True)
    sheet = workbook['Sheet1']
    headers = list(next(sheet.iter_rows(max_row=1, max_col=13, values_only=True)))
    assert len(set(headers)) == 13 and all(field in headers for field in FIELDS)
    original, inputs, mapping, cached = [], [], [], {}
    for excel_row, values in enumerate(sheet.iter_rows(min_row=2, max_row=52147, max_col=13, values_only=True), 2):
        fields = dict(zip(headers, values))
        assert isinstance(fields['标题'], str) and fields['标题']
        row_id = f'Sheet1:{excel_row:05d}'
        original.append(dict(row_id=row_id, excel_row=excel_row, fields=fields))
        # Exact equality on ALL fields supplied to AI, never title-only deduplication.
        key = tuple(fields[field] for field in FIELDS)
        if key not in cached:
            cached[key] = f'input-{len(inputs) + 1:05d}'
            inputs.append(dict(input_id=cached[key], row_id=row_id,
                               **{field: fields[field] for field in FIELDS}))
        mapping.append(dict(row_id=row_id, excel_row=excel_row, input_id=cached[key]))
    workbook.close()
    assert len(original) == 52146
    lines(WORK / 'source-rows.jsonl', original)
    lines(WORK / 'blind/inputs.jsonl', inputs)
    lines(WORK / 'row-map.jsonl', mapping)
    baseline = read(ROOT / 'validation/0.7.0/script-r64.jsonl')
    by_row = {row: item for item in baseline for row in item['rows']}
    candidates = []
    for row in original:
        item = by_row[row['excel_row']]
        result = item['result']
        candidates.append(dict(row_id=row['row_id'], excel_row=row['excel_row'], fields=row['fields'],
                               script_status=result['status'], script_names=result['names'],
                               candidate_names=result['names'] if result['status'] == 'uncertain' else [],
                               candidate_interpretations=result.get('candidate_interpretations', []),
                               missing_candidate=result['status'] == 'uncertain' and not result['names']))
    lines(WORK / 'candidate-review.jsonl', candidates)
    unresolved = [r for r in candidates if r['script_status'] == 'uncertain']
    lines(WORK / 'candidate-missing.jsonl', [r for r in unresolved if r['missing_candidate']])
    unresolved_titles = {r['fields']['标题'] for r in unresolved}
    present = {r['fields']['标题'] for r in unresolved if r['candidate_names']}
    assert (len(unresolved), len(unresolved_titles), len(present), len(unresolved_titles - present)) == (79, 72, 62, 10)
    # Pilot includes each unresolved title and a broad spread of remaining structures.
    pilot = []
    used_titles = set()
    for item in inputs:
        title = item['标题']
        if title in unresolved_titles and title not in used_titles:
            pilot.append(item)
            used_titles.add(title)
    rng = random.Random(SEED)
    source_index = {r['row_id']: r for r in original}
    pool = [r for r in inputs if r['标题'] not in used_titles]
    strata = lambda r: (stratum(r['标题']), str(source_index[r['row_id']]['fields']['发文日期'])[:4],
                         str(source_index[r['row_id']]['fields']['省']))
    pilot += balanced_sample(pool, 200 - len(pilot), rng, strata)
    lines(WORK / 'blind/pilot-200.jsonl', pilot)
    pilot_ids = {r['input_id'] for r in pilot}
    for phase, records in [('pilot', pilot), ('full', [r for r in inputs if r['input_id'] not in pilot_ids])]:
        batches = []
        for offset in range(0, len(records), 20):
            batch_id = f'{phase}-{offset // 20 + 1:04d}'
            path = WORK / 'blind' / phase / f'{batch_id}.jsonl'
            lines(path, records[offset:offset+20])
            batches.append(dict(batch_id=batch_id, path=str(path.relative_to(ROOT)),
                                input_ids=[r['input_id'] for r in records[offset:offset+20]]))
        save(WORK / f'{phase}-batches.json', batches)
    save(WORK / 'manifest.json', dict(date='2026-10-13', baseline_commit='4c42608', baseline_tag='v0.7.0-r64',
         source_rows=len(original), source_headers=headers, unique_full_inputs=len(inputs),
         deduplicated_rows=len(original)-len(inputs), input_fields=list(FIELDS),
         pilot_inputs=len(pilot), pilot_strata=dict(Counter(stratum(r['标题']) for r in pilot)),
         unresolved_rows=79, unresolved_titles=72, candidate_titles=62, missing_candidate_titles=10,
         seed=SEED, model_requested=MODEL, reasoning_effort='xhigh', fast_requested=True,
         fast_verified=False, fast_note='Subagent tool exposes no Fast control.',
         first_round_excludes_script_results=True, human_review_limit=100,
         prior_reference_paths=['validation/0.6.0/human-review.jsonl', 'validation/v1',
                                'validation/0.6.0', 'validation/0.7.0/independent-review',
                                'validation/0.7.0/delivery-closure'],
         reference_set_frozen=False, production_excel_modified=False))
    print((WORK / 'manifest.json').read_text())


def validate_answer(answer, source, prompt_versions=None):
    required = ('input_id', 'row_id', 'names', 'title_evidence', 'body_evidence', 'status', 'reason',
                'model', 'prompt_version')
    assert all(key in answer for key in required), 'Missing output fields'
    assert answer['input_id'] == source['input_id'] and answer['row_id'] == source['row_id'], 'Wrong identity'
    versions = prompt_versions or (PROMPT_VERSION, 'title-body-blind-v1')
    assert answer['model'] == MODEL and answer['prompt_version'] in versions, 'Wrong model/prompt'
    assert answer['status'] in ('names', 'no_name', 'conflict', 'uncertain'), 'Invalid status'
    names = answer['names']
    assert isinstance(names, list) and all(isinstance(n, str) and n for n in names), 'Invalid names'
    assert len(names) == len(set(names)), 'Duplicate names'
    assert answer['status'] != 'names' or names, 'Confirmed names cannot be empty'
    assert answer['status'] != 'no_name' or not names, 'No-name answer has names'
    assert isinstance(answer['reason'], str) and answer['reason'].strip(), 'Missing reasoning'
    evidence = answer['title_evidence']
    assert isinstance(evidence, list) and len(evidence) == len(names), 'One title evidence per name required'
    spans = []
    for name, ev in zip(names, evidence):
        assert ev['name'] == name and name in ev['quote'] and ev['quote'] in source['标题'], 'Name/evidence not in title'
        spans.append(dict(name=name, quote=ev['quote'], start=source['标题'].index(ev['quote']),
                          end=source['标题'].index(ev['quote']) + len(ev['quote'])))
    assert isinstance(answer['body_evidence'], list), 'Body evidence must be an array'
    for quote in answer['body_evidence']:
        assert isinstance(quote, str) and quote and quote in (source['内容'] or ''), 'Body quote not in original'
    return dict(answer, title_evidence=spans)


def collect():
    inputs = {r['input_id']: r for r in read(WORK / 'blind/inputs.jsonl')}
    accepted, rejected, duplicated = {}, [], set()
    for path in sorted((WORK / 'answers/first').glob('*.jsonl')):
        for line_no, line in enumerate(path.read_text().split('\n'), 1):
            if not line.strip():
                continue
            try:
                answer = json.loads(line)
                valid = validate_answer(answer, inputs[answer['input_id']])
                if answer['input_id'] in accepted or answer['input_id'] in duplicated:
                    accepted.pop(answer['input_id'], None)
                    duplicated.add(answer['input_id'])
                    raise ValueError('Duplicate first-round answer; preserve retries separately')
                accepted[answer['input_id']] = dict(valid, answer_file=str(path.relative_to(ROOT)))
            except (AssertionError, ValueError, KeyError, TypeError) as exc:
                rejected.append(dict(file=str(path.relative_to(ROOT)), line=line_no, reason=str(exc)))
    mapping = read(WORK / 'row-map.jsonl')
    # Each original row gets its own acceptance record, including explicitly pending rows.
    lines(WORK / 'row-acceptance.jsonl', [dict(m, review_state='reviewed' if m['input_id'] in accepted else 'pending',
          ai=accepted.get(m['input_id'])) for m in mapping])
    lines(WORK / 'valid-first-answers.jsonl', accepted.values())
    save(WORK / 'invalid-answers.json', rejected)
    pilot_ids = {r['input_id'] for r in read(WORK / 'blind/pilot-200.jsonl')}
    covered = sum(m['input_id'] in accepted for m in mapping)
    human_file = WORK / 'human/confirmations.json'
    human_records = json.loads(human_file.read_text()) if human_file.exists() else {}
    selection = json.loads((WORK / 'human/random-60-selection.json').read_text())
    human_ids = set(selection['row_ids'])
    risk_selection = WORK / 'human/risk-40-selection.json'
    if risk_selection.exists():
        human_ids.update(json.loads(risk_selection.read_text())['row_ids'])
    row_mapping = {m['row_id']: m for m in mapping}
    reference = {a['input_id']: a for a in read(WORK / 'fixed-reference.jsonl')} if (WORK / 'fixed-reference.jsonl').exists() else accepted
    human_status = Counter()
    for row_id, human in human_records.items():
        if row_id not in human_ids or human.get('source') != 'human_confirmation_ui':
            continue
        ai = reference.get(row_mapping[row_id]['input_id'])
        snapshot = json.dumps(dict(names=ai['names'], status=ai['status']), ensure_ascii=False, separators=(',', ':')) if ai else 'null'
        if human.get('answer') == snapshot and human.get('verdict') in ('correct', 'incorrect', 'uncertain'):
            human_status[human['verdict']] += 1
    save(WORK / 'progress.json', dict(updated_at=datetime.now(timezone.utc).isoformat(),
         source_rows=len(mapping), reviewed_rows=covered, ai_review_coverage=covered/len(mapping),
         unique_inputs=len(inputs), reviewed_inputs=len(accepted), pending_inputs=len(inputs)-len(accepted),
         pilot_reviewed_inputs=len(pilot_ids & accepted.keys()), pilot_inputs=len(pilot_ids),
         invalid_answers=len(rejected), status_inputs=dict(Counter(a['status'] for a in accepted.values())),
         human_reviewed_rows=sum(human_status.values()), human_status_rows=dict(human_status),
         human_review_method='non_blind_confirmation', human_review_limit=100, reference_set_frozen=False,
         true_accuracy=None, acceptance_passed=False))
    print((WORK / 'progress.json').read_text())


def human_random():
    path = WORK / 'human/random-60-blind.csv'
    if path.exists():
        raise ValueError('Human sample already exists; preserve selections and reviewer input.')
    from pilot import stratum
    records = read(WORK / 'source-rows.jsonl')
    sample = balanced_sample(records, 60, random.Random(SEED + 1),
         lambda r: (str(r['fields']['发文日期'])[:4], str(r['fields']['省']), stratum(r['fields']['标题'])))
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = ['row_id', '原始行号', '标题', '内容', '省', '市', '发文日期', '被许可对象', '颁布机构', '文号',
               '独立姓名数组JSON', '独立判断状态', '独立判断理由', '检查人', '检查日期', '查看答案后结论', '具体错误理由']
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for r in sample:
            writer.writerow(dict(row_id=r['row_id'], 原始行号=r['excel_row'],
                                 **{k: r['fields'][k] for k in columns if k in r['fields']}))
    save(WORK / 'human/random-60-selection.json', dict(seed=SEED+1, count=60,
         method='year/province/title-structure cell-balanced stratified random sampling, without replacement',
         row_ids=[r['row_id'] for r in sample],
         not_population_weighted=True, accuracy_is_not_full_population_accuracy=True,
         risk_sample_count=40, risk_sample_status='awaiting_full_AI_disagreements', human_completed=0))



def compare():
    answers = {r['input_id']: r for r in read(WORK / 'valid-first-answers.jsonl')}
    baseline = {row: item for item in read(ROOT / 'validation/0.7.0/script-r64.jsonl') for row in item['rows']}
    diffs, categories, review = [], Counter(), set()
    # Corrected first answers still need an independent reread even if they now agree.
    corrected = set()
    for path in (WORK / 'answers/retries').rglob('*.jsonl'):
        for old in read(path):
            current = answers.get(old.get('input_id'))
            if current and 'names' in old and 'status' in old and \
                    (old['names'] != current['names'] or old['status'] != current['status']):
                corrected.add(old['input_id'])
    for m in read(WORK / 'row-map.jsonl'):
        a = answers.get(m['input_id'])
        b = baseline[m['excel_row']]
        s = b['result']
        if a is None:
            category = 'pending_ai'
        elif a['status'] in ('conflict', 'uncertain'):
            category = 'disputed'
        elif s['status'] == 'uncertain':
            category = 'script_unresolved'
        elif a['status'] == s['status'] and a['names'] == s['names']:
            category = 'consistent_supported' if a['status'] == 'names' else 'consistent_no_name'
        elif len(a['names']) != len(s['names']):
            category = 'script_empty_ai_names' if not s['names'] and a['names'] else 'count_or_split_different'
        else:
            category = 'names_different'
        categories[category] += 1
        # Also re-read consistent high-risk cases; never pass them purely on agreement.
        focused_risks = {'四字姓名人数边界', '长连续姓名或异常长度', '英文及别名',
                         '多人连接', '括号异常', '职务或部门残片', '称谓或介词结构'}
        risky = bool(focused_risks.intersection(b.get('risk_categories', []))) or \
                s['status'] in ('uncertain', 'no_name') or len(s['names']) > 1
        if a is not None and (category not in ('consistent_supported', 'consistent_no_name') or risky or m['input_id'] in corrected):
            review.add(m['input_id'])
        if category not in ('consistent_supported', 'consistent_no_name', 'pending_ai'):
            diffs.append(dict(m, category=category, script=s, ai=a))
    lines(WORK / 'first-differences.jsonl', diffs)
    # Second round receives only original material, no prior answer or script classification.
    original = read(WORK / 'blind/inputs.jsonl')
    lines(WORK / 'blind/second-inputs.jsonl', [r for r in original if r['input_id'] in review])
    if len(answers) == len(original):
        ordered = [r for r in original if r['input_id'] in review]
        for offset in range(0, len(ordered), 20):
            lines(WORK / 'blind/second' / f'second-{offset // 20 + 1:04d}.jsonl', ordered[offset:offset+20])
    save(WORK / 'first-comparison.json', dict(categories_rows=dict(categories), second_round_inputs=len(review),
         corrected_first_inputs_requiring_reread=len(corrected),
         final_reference_agreement=None, reference_set_frozen=False, true_accuracy=None))
    print((WORK / 'first-comparison.json').read_text())


def runtime():
    """Read only this chat's subagent metadata and aggregate recorded token counters."""
    thread_id = os.environ.get('CODEX_THREAD_ID')
    if not thread_id:
        raise ValueError('CODEX_THREAD_ID is needed to restrict metadata to this chat.')
    records = []
    for path in (Path.home() / '.codex/sessions/2026/10/13').glob('*.jsonl'):
        with path.open() as stream:
            first = json.loads(next(stream))
            source = first.get('payload', {}).get('source')
            spawn = source.get('subagent', {}).get('thread_spawn', {}) if isinstance(source, dict) else {}
            if spawn.get('parent_thread_id') != thread_id:
                continue
            context, usage = {}, {}
            for line in stream:
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                if record.get('type') == 'turn_context':
                    context = record['payload']
                payload = record.get('payload', {})
                if record.get('type') == 'event_msg' and payload.get('type') == 'token_count':
                    usage = (payload.get('info') or {}).get('total_token_usage', {})
            records.append(dict(agent=spawn['agent_path'], rollout=str(path), model=context.get('model'),
                 effort=context.get('effort'), service_tier=context.get('service_tier'), usage=usage))
    totals = {key: sum(r['usage'].get(key, 0) for r in records) for key in
              ('input_tokens', 'cached_input_tokens', 'output_tokens', 'reasoning_output_tokens', 'total_tokens')}
    save(WORK / 'runs/current-runtime.json', dict(updated_at=datetime.now(timezone.utc).isoformat(),
         agents=records, cumulative_token_usage=totals, currency_cost=None,
         cost_note='Codex subscription accounting is not exposed; tokens include repeated and cached contexts.',
         fast_requested=True, fast_verified=False))
    print(json.dumps(totals))


def collect_second():
    """Validate independent rereads; disagreements still require explicit adjudication."""
    first = {r['input_id']: r for r in read(WORK / 'valid-first-answers.jsonl')}
    original = read(WORK / 'blind/inputs.jsonl')
    if len(first) != len(original):
        raise ValueError('Complete valid first-round coverage before second-round collection.')
    sources = {r['input_id']: r for r in read(WORK / 'blind/second-inputs.jsonl')}
    accepted, invalid, duplicated = {}, [], set()
    for path in sorted((WORK / 'answers/second').glob('*.jsonl')):
        for line_no, line in enumerate(path.read_text().split('\n'), 1):
            if not line.strip():
                continue
            try:
                answer = json.loads(line)
                key = answer['input_id']
                valid = validate_answer(answer, sources[key], ('title-body-independent-v1',))
                if key in accepted or key in duplicated:
                    accepted.pop(key, None)
                    duplicated.add(key)
                    raise ValueError('Duplicate second-round answer; preserve retries separately')
                accepted[key] = dict(valid, answer_file=str(path.relative_to(ROOT)))
            except (AssertionError, ValueError, KeyError, TypeError) as exc:
                invalid.append(dict(file=str(path.relative_to(ROOT)), line=line_no, reason=str(exc)))
    disagreements = []
    for key, second in accepted.items():
        prior = first[key]
        if second['status'] not in ('names', 'no_name') or prior['status'] != second['status'] or prior['names'] != second['names']:
            disagreements.append(dict(input_id=key, first=prior, second=second))
    lines(WORK / 'valid-second-answers.jsonl', accepted.values())
    save(WORK / 'invalid-second-answers.json', invalid)
    lines(WORK / 'second-disagreements.jsonl', disagreements)
    save(WORK / 'second-progress.json', dict(required_inputs=len(sources), reviewed_inputs=len(accepted),
         pending_inputs=len(sources)-len(accepted), invalid_answers=len(invalid),
         needs_adjudication_inputs=len(disagreements), reference_set_frozen=False))
    if len(accepted) == len(sources) and not invalid:
        disputed = {r['input_id'] for r in disagreements}
        ordered = [r for r in original if r['input_id'] in disputed]
        lines(WORK / 'blind/third-inputs.jsonl', ordered)
        for offset in range(0, len(ordered), 20):
            lines(WORK / 'blind/third' / f'third-{offset // 20 + 1:04d}.jsonl', ordered[offset:offset+20])
    print((WORK / 'second-progress.json').read_text())


def watch():
    """Checkpoint active subagent batches once a minute; exit when coverage is complete."""
    while True:
        with redirect_stdout(io.StringIO()):
            collect()
            compare()
        progress = json.loads((WORK / 'progress.json').read_text())
        comparison = json.loads((WORK / 'first-comparison.json').read_text())
        print(json.dumps(dict(reviewed_rows=progress['reviewed_rows'], total_rows=progress['source_rows'],
             invalid_answers=progress['invalid_answers'],
             disputed_rows=comparison['categories_rows'].get('disputed', 0))), flush=True)
        if progress['reviewed_rows'] == progress['source_rows']:
            return
        time.sleep(60)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'collect', 'compare', 'collect_second', 'human_random', 'runtime', 'watch'])
    args = parser.parse_args()
    globals()[args.action]()
