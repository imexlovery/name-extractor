"""Versioned full-title runs, resumable blind review inputs and transparent export."""
import argparse
from collections import Counter
import importlib.util
import json
import math
from pathlib import Path
import random
import shutil
import re

from extract import VERSION, extract, name_length, INSTITUTION_ANCHOR_RESOURCE, _INSTITUTION_STARTS
from validate import check, reference_length, risk_categories
from pilot import read_jsonl, write_json, write_jsonl, regression_rows

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / '.local' / 'full-20261011'
OLD = ROOT / '.local' / 'pilot-20261010'


def labels(channel):
    result = {}
    originals = {}
    paths = [p for p in (WORK / 'labels').glob(f'*-{channel}-*.jsonl') if not p.name.startswith('reference-corrections-')]
    if channel == 'a':
        paths += list(OLD.glob('ai-a-*.jsonl')) + [OLD / 'holdout-ai-a.jsonl']
    else:
        paths += list(OLD.glob('ai-b-*.jsonl')) + [OLD / 'holdout-ai-b.jsonl']
    for path in sorted(paths):
        for row in read_jsonl(path):
            originals.setdefault(row['row'],[]).append(row)
            if row['row'] in result and (result[row['row']]['names'], result[row['row']]['status']) != (row['names'], row['status']):
                # Conflicting reference versions require an explicit resolution, never last-write-wins.
                result[row['row']] = dict(row, status='uncertain', reason='参考答案版本分歧')
            else:
                result[row['row']] = row
    for path in sorted(list((WORK/'labels').glob(f'reference-corrections-{channel}-*.jsonl'))+list(WORK.glob(f'reference-corrections-{channel}-*.jsonl'))):
        for correction in read_jsonl(path):
            row, before, after = correction['row'], correction['before'], correction['after']
            if not correction['reason'] or after['row']!=row or not any((v['names'],v['status'])==(before['names'],before['status']) for v in originals.get(row,[])):
                raise ValueError(f'参考答案更正没有对应首答: {path.name} row={row}')
            result[row] = after
    return result


def coverage(channel, inventory):
    old_paths = list(OLD.glob(f'ai-{channel}-*.jsonl')) + [OLD / f'holdout-ai-{channel}.jsonl']
    old_ids = {v['row'] for path in old_paths for v in read_jsonl(path)}
    judgments = [v for path in (WORK/'labels').glob(f'*-{channel}-*.jsonl') if not path.name.startswith('reference-corrections-') for v in read_jsonl(path)]
    current_ids = {v['row'] for v in judgments}
    new_ids = current_ids - old_ids
    all_ids = set(labels(channel))
    index = {v['row']:v for v in inventory}
    return {'unique_titles':len(all_ids), 'mapped_rows':sum(len(index[row]['rows']) for row in all_ids),
            'new_unique_titles':len(new_ids), 'new_mapped_rows':sum(len(index[row]['rows']) for row in new_ids),
            'saved_judgments':len(judgments), 'repeated_saved_judgments':len(judgments)-len(current_ids),
            'reference_corrections':sum(len(read_jsonl(p)) for p in list((WORK/'labels').glob(f'reference-corrections-{channel}-*.jsonl'))+list(WORK.glob(f'reference-corrections-{channel}-*.jsonl'))),
            'invalid_reference_titles':[row for row, label in labels(channel).items() if check(index[row]['title'],label)['failures']]}


def learn_anchors(target_version):
    """Freeze reusable institution spans supported by two blind references."""
    import extract as rules
    a, b = labels('a'), labels('b')
    inventory = {v['row']:v for v in read_jsonl(OLD/'inventory.jsonl')}
    excluded = set()
    for path in WORK.glob('holdout*-frozen.jsonl'):
        suffix = path.name.removeprefix('holdout').split('-')[0]
        if not (WORK/f'rules-frozen{suffix}.json').exists():
            excluded.update(v['row'] for v in read_jsonl(path))
    anchors = {}
    for row, av in a.items():
        bv = b.get(row)
        if row in excluded or not bv or av['status']!='names' or bv['status']!='names' or av['names']!=bv['names'] or not av['names']:
            continue
        core = inventory[row]['title'].split('关于',1)[-1].strip()
        q = re.search('任职资格|任职',core)
        if not q: continue
        core = core[:q.start()].strip()
        while match := rules._PREFIX.match(core): core=core[match.end():].lstrip()
        cursor, valid = 0, True
        for name in av['names']:
            position = core.find(name,cursor)
            if position<0 or re.search(r'[^、，,；;和及与\s]',core[cursor:position]):
                valid=False; break
            cursor=position+len(name)
        candidates=[]
        if valid:
            tail=re.sub(r'^(?:同志|先生|女士|拟任|担任|出任)','',core[cursor:].strip())
            outer, balanced=rules._outside(tail)
            match=rules._INSTITUTION_END.search(outer)
            if match and balanced:candidates.append(tail[:match.end()].strip())
        first=core.find(av['names'][0])
        if first>0:
            prefix=core[:first];outer,balanced=rules._outside(prefix)
            matches=list(rules._INSTITUTION_END.finditer(outer))
            if matches and balanced:candidates.append(prefix[:matches[-1].end()].strip())
        for anchor in candidates:
            if len(anchor)<3 or rules._ROLE.search(anchor) or rules._TO_POST.search(anchor) or rules._BUSINESS_ACTION.search(anchor) or re.search('[、；;及和兼（）()]',anchor): continue
            if re.fullmatch(r'(?:村镇|农商|农村商业|农村信用|商业|股份制)?银行(?:股份有限公司)?|信用社|联社|保险公司|金融机构',anchor): continue
            anchors.setdefault(anchor,[]).append(row)
    write_json(ROOT/'scripts'/f'institution_anchors_{target_version}.json', sorted(anchors))
    write_json(WORK/f'institution-anchors-{target_version}-sources.json', {'anchors':anchors, 'excluded_frozen_rows':sorted(excluded), 'derivation':'独立A/B参考一致，原标题明示姓名前或后的机构片段；非姓名答案表，不代表独立真值。'})
    print(json.dumps({'target_version':target_version,'institution_anchors':len(anchors),'excluded_frozen_titles':len(excluded)},ensure_ascii=False))


def run():
    output = []
    for item in read_jsonl(OLD / 'inventory.jsonl'):
        result = extract(item['title'])
        result.update(length=sum(map(name_length, result['names'])), extracted_name='；'.join(result['names']))
        checks=check(item['title'], result)
        output.append(dict(item, result=result, checks=checks, risk_categories=risk_categories(item['title'],result,checks)))
    write_jsonl(WORK / f'script-{VERSION}.jsonl', output)
    shutil.copyfile(ROOT / 'scripts' / 'extract.py', WORK / f'extract-{VERSION}.py')
    for resource in (ROOT / 'scripts').glob('institution_anchors_*.json'):
        shutil.copyfile(resource, WORK / resource.name)
    summary = {
        'version': VERSION, 'unique_titles': len(output), 'mapped_rows': sum(len(v['rows']) for v in output),
        'runtime_anchor_resource':INSTITUTION_ANCHOR_RESOURCE, 'runtime_anchor_count':len(_INSTITUTION_STARTS),
        'status_titles': dict(Counter(v['result']['status'] for v in output)),
        'status_rows': {s: sum(len(v['rows']) for v in output if v['result']['status'] == s) for s in ('names', 'uncertain', 'no_name')},
        'hard_failure_titles': sum(bool(v['checks']['failures']) for v in output),
        'flagged_titles': sum(bool(v['checks']['flags']) for v in output),
        'flags': dict(Counter(f for v in output for f in v['checks']['flags'])),
        'risk_categories': dict(Counter(f for v in output for f in v['risk_categories'])),
    }
    baseline = {v['row']: v for v in read_jsonl(WORK / 'script-r03.jsonl')}
    summary['status_transitions_from_r03'] = dict(Counter(baseline[v['row']]['result']['status'] + ' -> ' + v['result']['status'] for v in output))
    a = labels('a')
    for path in WORK.glob('holdout*-frozen.jsonl'):
        suffix=path.name.removeprefix('holdout').split('-')[0]
        if not (WORK/f'rules-frozen{suffix}.json').exists():
            frozen={v['row'] for v in read_jsonl(path)}
            a={row:label for row,label in a.items() if row not in frozen}
    summary['ai_a_comparable'] = len(a)
    summary['script_ai_a_matches'] = sum(v['row'] in a and v['result']['names'] == a[v['row']]['names'] and v['result']['status'] == a[v['row']]['status'] for v in output)
    def histories():
        for path in sorted(WORK.glob('script-r*.jsonl')):
            yield {v['row']: v['result'] for v in read_jsonl(path)}
        for path in sorted(OLD.glob('script-r*.jsonl')):
            yield {v['row']: v for v in read_jsonl(path)}
    summary['regression_rows'] = regression_rows(histories(), {v['row']: dict(v['result'],checks=v['checks']) for v in output}, a)
    indexed={v['row']:v for v in output}
    summary['regression_uncertain_downgrades']=[row for row in summary['regression_rows'] if indexed[row]['result']['status']=='uncertain']
    summary['regression_determinate_differences']=[row for row in summary['regression_rows'] if indexed[row]['result']['status']!='uncertain']
    b = labels('b')
    references = {row:av for row,av in a.items() if row in b and av['status']!='uncertain' and (av['names'],av['status'])==(b[row]['names'],b[row]['status']) and not check(indexed[row]['title'],av)['failures'] and not check(indexed[row]['title'],b[row])['failures']}
    def determinate_differences(items):
        return {v['row'] for v in items if v['row'] in references and v['result']['status']!='uncertain' and (v['result']['names'],v['result']['status'])!=(references[v['row']]['names'],references[v['row']]['status'])}
    current_differences = determinate_differences(output)
    baseline_differences = determinate_differences(baseline.values())
    summary['ai_both_supported_comparable'] = len(references)
    summary['ai_both_supported_determinate_difference_rows'] = sorted(current_differences)
    summary['r03_ai_both_supported_determinate_difference_rows'] = sorted(baseline_differences)
    summary['r03_determinate_differences_removed'] = sorted(baseline_differences-current_differences)
    previous_paths = [p for p in WORK.glob('script-r*.jsonl') if int(p.stem[8:]) < int(VERSION[1:])]
    if previous_paths:
        previous_path = max(previous_paths,key=lambda p:int(p.stem[8:]))
        previous = read_jsonl(previous_path)
        previous_index = {v['row']:v for v in previous}
        previous_differences = determinate_differences(previous)
        summary['previous_version'] = previous_path.stem.removeprefix('script-')
        summary['status_transitions_from_previous'] = dict(Counter(previous_index[v['row']]['result']['status']+' -> '+v['result']['status'] for v in output))
        summary['changed_results_from_previous'] = sum(v['result']!=previous_index[v['row']]['result'] for v in output)
        summary['new_determinate_differences_from_previous'] = sorted(current_differences-previous_differences)
        summary['removed_determinate_differences_from_previous'] = sorted(previous_differences-current_differences)
    write_json(WORK / f'summary-{VERSION}.json', summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def prepare_reviews(extra=False):
    data = read_jsonl(WORK / f'script-{VERSION}.jsonl')
    frozen = {v['row'] for path in WORK.glob('holdout*-frozen.jsonl') for v in read_jsonl(path)}
    a, b = labels('a'), labels('b')
    risks, ordinary = [], {}
    for v in data:
        conflict = v['row'] in a and (a[v['row']]['names'] != v['result']['names'] or a[v['row']]['status'] != v['result']['status'])
        if v['checks']['flags'] or v['checks']['failures'] or conflict:
            risks.append(v)
        else:
            ordinary.setdefault(v['stratum'], []).append(v)
    rng = random.Random(20261012)
    original_sample=set(json.loads((WORK/'ordinary-frozen-r11.json').read_text())['sampled_rows']) if (WORK/'ordinary-frozen-r11.json').exists() else set()
    sampled=[]
    for group in sorted(ordinary):
        population=ordinary[group]
        kept=[v for v in population if v['row'] in original_sample]
        target=math.ceil(len(population)*.05)
        if len(kept)<target:
            kept+=rng.sample([v for v in population if v['row'] not in original_sample],target-len(kept))
        sampled+=kept
    targets = {v['row']: v for v in risks + sampled}
    targets.update({v['row']: v for v in data if v['row'] in frozen})
    if extra:
        previous={v['row'] for v in read_jsonl(WORK/'review-targets-initial.jsonl')}
        previous.update(v['row'] for channel in ('a','b') for p in (WORK/'blind'/channel).glob('*.jsonl') for v in read_jsonl(p))
        previous.update(v['row'] for p in WORK.glob('diagnostic-*.jsonl') for v in read_jsonl(p))
        targets.update({v['row']:v for v in data if v['row'] in previous})
    targets = sorted(targets.values(), key=lambda v: (v['result']['status'] != 'uncertain', not bool(v['checks']['flags']), v['row']))
    for channel, cached in [('a', a), ('b', b)]:
        queued={v['row'] for path in (WORK/'blind'/channel).glob('*.jsonl') for v in read_jsonl(path)} if extra else set()
        missing = [{'row': v['row'], 'title': v['title']} for v in targets if v['row'] not in cached and v['row'] not in queued]
        prefix=f'extra-{VERSION}-' if extra else 'batch-'
        for offset in range(0, len(missing), 40):
            write_jsonl(WORK / 'blind' / channel / f'{prefix}{offset//40+1:04d}.jsonl', missing[offset:offset+40])
        write_json(WORK / f'queue-{channel}{"-extra" if extra else ""}.json', {'version': VERSION, 'required_titles': len(targets), 'already_queued_titles':len(queued), 'newly_queued_titles':len(missing), 'remaining_required_titles':len({v['row'] for v in targets}-cached.keys()), 'new_batches': math.ceil(len(missing)/40)})
    write_jsonl(WORK / 'review-targets.jsonl', [{'row':v['row'], 'reasons':v['checks']['flags'], 'sampled':v in sampled, 'holdout':v['row'] in frozen} for v in targets])
    write_json(WORK / f'review-manifest-{VERSION}.json', {'seed':20261012, 'version':VERSION, 'risk_titles':len(risks), 'ordinary_population':sum(map(len,ordinary.values())), 'ordinary_sample':len(sampled), 'frozen_holdout':len(frozen), 'required_titles':len(targets), 'stratum_population':{g:len(v) for g,v in ordinary.items()}})
    shutil.copyfile(WORK/f'review-manifest-{VERSION}.json',WORK/'review-manifest.json')
    print((WORK/'review-manifest.json').read_text())


def evaluate_frozen_sets():
    reports=[]
    for path in sorted(WORK.glob('holdout*-frozen.jsonl')):
        suffix=path.name.removeprefix('holdout').split('-')[0]
        marker=WORK/f'rules-frozen{suffix}.json'
        if not marker.exists():
            continue
        version=json.loads(marker.read_text())['version']
        frozen={v['row'] for v in read_jsonl(path)}
        items=[v for v in read_jsonl(WORK/f'script-{version}.jsonl') if v['row'] in frozen]
        references={}
        for channel in ('a','b'):
            files=list((WORK/'labels').glob(f'holdout{suffix}-{channel}-*.jsonl'))+list((WORK/'labels').glob(f'holdout{suffix}-replacements-{channel}-*.jsonl'))
            references[channel]={v['row']:v for p in files for v in read_jsonl(p)}
        differences=[]; matches=0; disputes=0
        for item in items:
            row=item['row'];av=references['a'].get(row);bv=references['b'].get(row);result=item['result']
            if av and (result['names'],result['status'])==(av['names'],av['status']):
                matches+=1
            agreed=av is not None and bv is not None and av['status']!='uncertain' and (av['names'],av['status'])==(bv['names'],bv['status']) and not check(item['title'],av)['failures'] and not check(item['title'],bv)['failures']
            disputes+=not agreed
            if agreed and result['status']!='uncertain' and (result['names'],result['status'])!=(av['names'],av['status']):
                differences.append(dict(item,ai_a=av,ai_b=bv))
        report={'sample':f'holdout{suffix}','version':version,'titles':len(items),'ai_a_coverage':len(frozen&references['a'].keys()),'ai_b_coverage':len(frozen&references['b'].keys()),'script_matches_a':matches,'script_uncertain':sum(v['result']['status']=='uncertain' for v in items),'script_determinate_mismatches_supported_by_both_ai':len(differences),'ai_cross_disagreements_or_uncertain':disputes,'true_accuracy':None}
        write_json(WORK/f'holdout{suffix}-{version}-summary.json',report)
        write_jsonl(WORK/f'holdout{suffix}-{version}-determinate-differences.jsonl',differences)
        reports.append(report)
    return reports


def finish():
    data = read_jsonl(WORK / f'script-{VERSION}.jsonl')
    a, b = labels('a'), labels('b')
    targets = {v['row'] for v in read_jsonl(WORK / 'review-targets.jsonl')}
    audit, export = [], []
    for v in data:
        row, result = v['row'], v['result']
        av, bv = a.get(row), b.get(row)
        valid_a = av is not None and not check(v['title'], av)['failures']
        valid_b = bv is not None and not check(v['title'], bv)['failures']
        if row in targets:
            if valid_a and valid_b and av['status'] != 'uncertain' and bv['status'] == av['status'] and av['names'] == bv['names']:
                state, names, source = av['status'], av['names'], 'ai_a_b_supported'
            else:
                state, names, source = 'uncertain', (av or bv or result)['names'], 'missing_invalid_or_disputed_review'
        elif v['checks']['failures']:
            state, names, source = 'uncertain', result['names'], 'hard_check_failure'
        else:
            state, names, source = result['status'], result['names'], 'script_only'
        name, length = (None, None) if state == 'uncertain' else ('；'.join(names), reference_length(names))
        audit.append(dict(v, ai_a=av, ai_b=bv, output_state=state, output_source=source, candidate=names, independent_truth=False))
        export.extend({'row':r, 'name':name, 'length':length} for r in v['rows'])
    write_jsonl(WORK / 'audit.jsonl', audit)
    write_jsonl(WORK / 'unresolved.jsonl', [v for v in audit if v['output_state']=='uncertain'])
    write_jsonl(WORK / 'excel-records.jsonl', sorted(export,key=lambda r:r['row']))
    frozen = {v['row'] for v in read_jsonl(WORK/'holdout-frozen.jsonl')}
    holdout = [v for v in audit if v['row'] in frozen]
    summary = {'version':VERSION, 'unique_titles':len(audit), 'mapped_rows':len(export), 'output_status_titles':dict(Counter(v['output_state'] for v in audit)), 'output_status_rows':dict(Counter('uncertain' if r['name'] is None else 'no_name' if not r['name'] else 'names' for r in export)), 'ai_a_coverage':len(a), 'ai_b_coverage':len(b), 'review_required':len(targets), 'review_missing_a':len(targets-a.keys()), 'review_missing_b':len(targets-b.keys()), 'ai_a_b_disagreements':sum(v['ai_a'] is not None and v['ai_b'] is not None and (v['ai_a']['names'],v['ai_a']['status'])!=(v['ai_b']['names'],v['ai_b']['status']) for v in audit), 'ai_supported_script_differences':sum(v['output_source']=='ai_a_b_supported' and (v['result']['names'],v['result']['status'])!=(v['candidate'],v['output_state']) for v in audit), 'holdout_ai_a_covered':sum(v['ai_a'] is not None for v in holdout), 'holdout_ai_b_covered':sum(v['ai_b'] is not None for v in holdout), 'holdout_script_matches_a':sum(v['ai_a'] is not None and (v['result']['names'],v['result']['status'])==(v['ai_a']['names'],v['ai_a']['status']) for v in holdout), 'true_accuracy':None, 'human_review_performed':False}
    summary['ai_coverage'] = {channel:coverage(channel,data) for channel in ('a','b')}
    for channel in ('a','b'):
        summary[f'new_ai_{channel}_titles'] = summary['ai_coverage'][channel]['new_unique_titles']
        summary[f'ai_{channel}_mapped_rows'] = summary['ai_coverage'][channel]['mapped_rows']
        summary[f'new_ai_{channel}_mapped_rows'] = summary['ai_coverage'][channel]['new_mapped_rows']
    summary['invalid_reference_a'] = len(summary['ai_coverage']['a']['invalid_reference_titles'])
    summary['invalid_reference_b'] = len(summary['ai_coverage']['b']['invalid_reference_titles'])
    summary['frozen_samples'] = evaluate_frozen_sets()
    write_json(WORK/'delivery-summary.json',summary)
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['run','reviews','reviews-extra','finish','learn']);p.add_argument('--target-version')
    args=p.parse_args()
    if args.action=='learn':
        if not args.target_version: p.error('learn requires --target-version')
        learn_anchors(args.target_version)
    elif args.action=='reviews-extra': prepare_reviews(extra=True)
    else: {'run':run,'reviews':prepare_reviews,'finish':finish}[args.action]()
