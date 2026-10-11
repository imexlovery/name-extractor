"""Compare saved rules against explicit structure contracts and cached AI references."""
import importlib.util
import json
from pathlib import Path

WORK = Path(__file__).resolve().parent
PREVIOUS = WORK.parent / '0.4.0'


def read(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def evaluate(module, cases):
    results = []
    for case in cases:
        result = module.extract(case['title'])
        matches = result['status'] == case['status'] and (case['status'] == 'uncertain' or result['names'] == case['names'])
        results.append(dict(case, script=result, matches=matches))
    return results


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    cases = read(WORK / 'person-count-cases.jsonl')
    rules = {'r51': load(PREVIOUS / 'extract-r51.py', 'baseline_rules'),
             'r55': load(WORK / 'extract-r55.py', 'current_rules')}
    summaries = {}
    for version, module in rules.items():
        evaluated = evaluate(module, cases)
        (WORK / f'person-count-{version}.jsonl').write_text(''.join(json.dumps(v, ensure_ascii=False) + '\n' for v in evaluated))
        summaries[version] = {purpose: {
            'total': sum(v['purpose'] == purpose for v in evaluated),
            'matched': sum(v['purpose'] == purpose and v['matches'] for v in evaluated),
            'failed': [v['id'] for v in evaluated if v['purpose'] == purpose and not v['matches']],
        } for purpose in ('structure_contract', 'known_risk_replay', 'retention_policy')}
    cached = {}
    for name, af, bf in [
        ('development', 'structure-holdout-reference.jsonl', 'structure-holdout-reference-b.jsonl'),
        ('fresh_then_revealed', 'structure-fresh-reference-a.jsonl', 'structure-fresh-reference-b.jsonl'),
        ('final_then_revealed', 'final-structure-reference-a.jsonl', 'final-structure-reference-b.jsonl'),
    ]:
        a = read(PREVIOUS / af)
        b = {v['id']: v for v in read(PREVIOUS / bf)}
        agreed = [v for v in a if (v['status'], v['names']) == (b[v['id']]['status'], b[v['id']]['names'])]
        cached[name] = {}
        known_titles = set(rules['r55']._TITLE_AMBIGUITIES)
        for version, module in rules.items():
            evaluated = evaluate(module, agreed)
            known = [v for v in evaluated if v['title'] in known_titles]
            general = [v for v in evaluated if v['title'] not in known_titles]
            cached[name][version] = dict(total=len(a), agreed=len(agreed), matched=sum(v['matches'] for v in evaluated),
                known_ambiguity_cases=len(known),known_abstention_replays=sum(v['script']['status'] == 'uncertain' for v in known),
                general_compared=len(general),general_matched=sum(v['matches'] for v in general),
                determinate_mismatches=[dict(id=v['id'],title=v['title'],script=v['script'],reference_status=v['status'])
                                       for v in evaluated if not v['matches'] and v['script']['status'] != 'uncertain'],
                conservative_abstentions=[v['id'] for v in evaluated if not v['matches'] and v['script']['status'] == 'uncertain'])
    report = dict(explicit_structure_contracts=summaries, cached_ai_regressions=cached,
        interpretation='New synthetic cases have explicit structure contracts authored in this chat, not independent blind AI truth. '
        'Known-risk replay and retention policy are separated from general structure capability. '
        'Cached synthetic AI sets were revealed in 0.4.0; all repetitions are regressions, never unseen evidence. '
        'Unmarked four-character ambiguities may remain determinate under the confirmed retention policy.')
    write(WORK / 'person-count-evaluation-summary.json', report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
