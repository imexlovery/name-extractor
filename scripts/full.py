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
import tomllib

from extract import VERSION, extract, name_length, INSTITUTION_ANCHOR_RESOURCE, AMBIGUITY_RESOURCE, _INSTITUTION_STARTS
from validate import check, reference_length, risk_categories
from pilot import read_jsonl, write_json, write_jsonl, regression_rows

ROOT = Path(__file__).resolve().parents[1]
RELEASE_VERSION = tomllib.loads((ROOT / 'pyproject.toml').read_text())['project']['version']
BASELINE = ROOT / 'validation' / 'v1'
DEFAULT_WORK = ROOT / 'validation' / ('v2' if RELEASE_VERSION=='0.2.0' else RELEASE_VERSION)
WORK = DEFAULT_WORK
PREVIOUS_STAGE = ROOT / 'validation' / 'v2'
NEXT_STAGE = ROOT / 'validation' / '0.3.0'
LATEST_STAGE = ROOT / 'validation' / '0.4.0'
RECENT_STAGE = ROOT / 'validation' / '0.5.0'
FROZEN_STAGE = ROOT / 'validation' / '0.5.1'
OLD = ROOT / '.local' / 'pilot-20261010'


def labels(channel):
    result = {}
    originals = {}
    if WORK in (DEFAULT_WORK, NEXT_STAGE):
        for path in (BASELINE/'ai-references.jsonl', BASELINE/'ai-reference-exclusions.jsonl'):
            for row in read_jsonl(path):
                label = row.get(f'ai_{channel}')
                if label is not None:
                    result[row['row']] = label
                    originals.setdefault(row['row'], []).append(label)
    paths = [p for p in (WORK / 'labels').glob(f'*-{channel}-*.jsonl') if not p.name.startswith('reference-corrections-')]
    if WORK in (DEFAULT_WORK, NEXT_STAGE):
        for stage in (PREVIOUS_STAGE, NEXT_STAGE, LATEST_STAGE, RECENT_STAGE, FROZEN_STAGE):
            if stage != WORK and stage.parent == BASELINE.parent:
                paths += [p for p in (stage/'labels').glob(f'*-{channel}-*.jsonl') if not p.name.startswith('reference-corrections-')]
    if WORK in (DEFAULT_WORK, NEXT_STAGE):
        pass
    elif channel == 'a':
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
    correction_stages = [stage for stage in (PREVIOUS_STAGE, NEXT_STAGE, LATEST_STAGE, RECENT_STAGE, FROZEN_STAGE)
                         if WORK in (DEFAULT_WORK, NEXT_STAGE) and stage != WORK and stage.parent == BASELINE.parent] + [WORK]
    for path in [path for stage in correction_stages for path in sorted(
            list((stage/'labels').glob(f'reference-corrections-{channel}-*.jsonl')) +
            list(stage.glob(f'reference-corrections-{channel}-*.jsonl')))]:
        for correction in read_jsonl(path):
            row, before, after = correction['row'], correction['before'], correction['after']
            if not correction['reason'] or after['row']!=row or not any((v['names'],v['status'])==(before['names'],before['status']) for v in originals.get(row,[])):
                raise ValueError(f'参考答案更正没有对应首答: {path.name} row={row}')
            result[row] = after
    return result


def coverage(channel, inventory):
    if WORK in (DEFAULT_WORK, NEXT_STAGE):
        old_ids = {v['row'] for path in (BASELINE/'ai-references.jsonl',BASELINE/'ai-reference-exclusions.jsonl')
                   for v in read_jsonl(path) if v.get(f'ai_{channel}') is not None}
        for stage in (PREVIOUS_STAGE, NEXT_STAGE, LATEST_STAGE, RECENT_STAGE, FROZEN_STAGE):
            if stage != WORK and stage.parent == BASELINE.parent:
                old_ids.update(v['row'] for p in (stage/'labels').glob(f'*-{channel}-*.jsonl')
                               if not p.name.startswith('reference-corrections-') for v in read_jsonl(p))
    else:
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
    inventory = {v['row']:v for v in read_jsonl(BASELINE/'script-r29.jsonl')}
    excluded = set()
    for path in WORK.glob('holdout*-frozen.jsonl'):
        suffix = path.name.removeprefix('holdout').split('-')[0]
        if not (WORK/f'rules-frozen{suffix}.json').exists():
            excluded.update(v['row'] for v in read_jsonl(path))
    anchors = {}
    for row, av in a.items():
        bv = b.get(row)
        if row in excluded or not bv or av['status'] not in ('names','no_name') or bv['status']!=av['status'] or av['names']!=bv['names'] or (av['status']=='names' and not av['names']):
            continue
        core = inventory[row]['title'].split('关于',1)[-1].strip()
        q = re.search('任职资格|任职|职资格|拟任资格|资格',core)
        if q:
            core = core[:q.start()].strip()
        elif av['status']=='names':
            continue
        else:
            core = core.removesuffix('的批复').strip()
        while match := rules._PREFIX.match(core): core=core[match.end():].lstrip()
        if av['status']=='no_name':
            candidate=rules._before_role(core).strip()
            candidate=re.sub(r'(?:[、,，及和并]*开业[、,，及和并]*)$', '', candidate)
            if re.search(r'(?:'+rules._INSTITUTION_END.pattern+r')$', candidate) and not re.search(r'[《》、;；及兼]', candidate):
                anchors.setdefault(candidate,[]).append(row)
            continue
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
        if len(av['names']) == 1 and first >= 0:
            tail = core[first+len(av['names'][0]):].strip()
            tail = re.sub(r'^(?:同志|先生|女士|拟任|担任|出任|任|的)', '', tail)
            outer, balanced = rules._outside(tail)
            match = rules._INSTITUTION_END.search(outer)
            if match and balanced:
                candidates.append(tail[:match.end()].strip())
            # Some titles use an institutional short form without 银行/公司.
            if role := rules._ROLE.search(outer):
                short = tail[:role.start()].strip()
                if short and not rules._ROLE.search(short) and not re.search(r'[、,，;；和及与]',short):
                    candidates.append(short)
        if first>0:
            prefix=core[:first];outer,balanced=rules._outside(prefix)
            matches=list(rules._INSTITUTION_END.finditer(outer))
            if matches and balanced:candidates.append(prefix[:matches[-1].end()].strip())
        for anchor in candidates:
            if len(anchor)<3 or rules._ROLE.search(anchor) or rules._TO_POST.search(anchor) or rules._BUSINESS_ACTION.search(anchor) or re.search('[、；;及兼]',anchor): continue
            if re.fullmatch(r'(?:村镇|农商|农村商业|农村信用|商业|股份制)?银行(?:股份有限公司)?|信用社|联社|保险公司|金融机构',anchor): continue
            anchors.setdefault(anchor,[]).append(row)
    write_json(ROOT/'scripts'/f'institution_anchors_{target_version}.json', sorted(anchors))
    write_json(WORK/f'institution-anchors-{target_version}-sources.json', {'anchors':anchors, 'excluded_frozen_rows':sorted(excluded), 'derivation':'独立A/B确定参考一致；明示姓名前后机构片段、明确岗位前机构简称及无姓名参考支持的完整机构；非姓名答案表，不代表独立真值。'})
    print(json.dumps({'target_version':target_version,'institution_anchors':len(anchors),'excluded_frozen_titles':len(excluded)},ensure_ascii=False))


def run():
    baseline = {v['row']: v for v in read_jsonl(BASELINE / 'script-r29.jsonl')}
    output = []
    for item in baseline.values():
        result = extract(item['title'])
        result.update(length=sum(map(name_length, result['names'])), extracted_name='；'.join(result['names']))
        checks = check(item['title'], result)
        output.append(dict(item, result=result, checks=checks, risk_categories=risk_categories(item['title'], result, checks)))
    write_jsonl(WORK / f'script-{VERSION}.jsonl', output)
    shutil.copyfile(ROOT / 'scripts' / 'extract.py', WORK / f'extract-{VERSION}.py')
    shutil.copyfile(ROOT / 'scripts' / INSTITUTION_ANCHOR_RESOURCE, WORK / INSTITUTION_ANCHOR_RESOURCE)
    shutil.copyfile(ROOT / 'scripts' / AMBIGUITY_RESOURCE, WORK / AMBIGUITY_RESOURCE)
    summary = {'release_version': RELEASE_VERSION, 'version': VERSION, 'runtime_anchor_resource':INSTITUTION_ANCHOR_RESOURCE, 'runtime_anchor_count':len(_INSTITUTION_STARTS), 'unique_titles':len(output), 'mapped_rows':sum(len(v['rows']) for v in output),
               'status_titles':dict(Counter(v['result']['status'] for v in output)),
               'status_rows':{s:sum(len(v['rows']) for v in output if v['result']['status']==s) for s in ('names','no_name','uncertain')},
               'hard_failure_titles':sum(bool(v['checks']['failures']) for v in output)}
    previous_paths = [p for p in WORK.glob('script-r*.jsonl') if int(p.stem[8:]) < int(VERSION[1:])]
    stage_baseline = read_jsonl(FROZEN_STAGE/'script-r56.jsonl') if RELEASE_VERSION == '0.6.0' else []
    previous = {v['row']:v for v in read_jsonl(max(previous_paths, key=lambda p:int(p.stem[8:])))} if previous_paths else (
        {v['row']:v for v in stage_baseline} if stage_baseline else
        {v['row']:v for v in read_jsonl(PREVIOUS_STAGE/'script-r38.jsonl')} if WORK == NEXT_STAGE else baseline)
    summary['comparison_baseline_version'] = max(previous_paths, key=lambda p:int(p.stem[8:])).stem.removeprefix('script-') if previous_paths else ('r56' if stage_baseline else 'r38' if WORK == NEXT_STAGE else 'r29')
    fields = ('names', 'status', 'extracted_name', 'length')
    changed = [dict(v, before=previous[v['row']]['result']) for v in output
               if any(v['result'].get(key) != previous[v['row']]['result'].get(key) for key in fields)]
    if stage_baseline:
        frozen = {v['row']:v for v in stage_baseline}
        stage_changes = [dict(v, before=frozen[v['row']]['result']) for v in output
                         if any(v['result'].get(key) != frozen[v['row']]['result'].get(key) for key in fields)]
        write_jsonl(WORK/f'changes-from-r56-{VERSION}.jsonl', stage_changes)
        summary['changed_titles_from_r56'] = len(stage_changes)
        summary['changed_rows_from_r56'] = sum(len(v['rows']) for v in stage_changes)
    summary['changed_titles'] = len(changed)
    summary['status_transitions'] = dict(Counter(v['before']['status']+' -> '+v['result']['status'] for v in changed))
    write_jsonl(WORK/f'changes-{VERSION}.jsonl', changed)
    write_json(WORK/f'summary-{VERSION}.json',summary)
    print(json.dumps(summary,ensure_ascii=False,indent=2))


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


def production_records(item):
    """AI references never participate in production values."""
    result = item['result']
    name, length = (None, None) if result['status']=='uncertain' else ('；'.join(result['names']), result['length'])
    return [{'row':row,'name':name,'length':length} for row in item['rows']]


def comparison_state(item, av, bv):
    if check(item['title'], item['result'])['failures']:
        return 'invalid_script'
    if av is None or bv is None:
        return 'missing_reference' if av is None and bv is None else 'single_channel'
    if check(item['title'], av)['failures'] or check(item['title'], bv)['failures']:
        return 'invalid_reference'
    if av['status']=='uncertain' or bv['status']=='uncertain' or (av['names'],av['status'])!=(bv['names'],bv['status']):
        return 'disputed_reference'
    result = item['result']
    if result['status']=='uncertain':
        return 'script_unresolved'
    if (result['names'],result['status'])==(av['names'],av['status']):
        return 'match'
    return 'no_name_dispute' if 'no_name' in (result['status'],av['status']) else 'determinate_difference'


def finish():
    data = read_jsonl(WORK / f'script-{VERSION}.jsonl')
    a,b = labels('a'),labels('b')
    baseline = {v['row']:v for v in read_jsonl(BASELINE/'script-r29.jsonl')}
    audit,export=[],[]
    regressions=[]
    for v in data:
        if check(v['title'], v['result'])['failures']:
            raise ValueError(f"Script output contract failure at row {v['row']}")
        row=v['row']; av,bv=a.get(row),b.get(row)
        state=comparison_state(v,av,bv)
        audit.append(dict(v, ai_a=av,ai_b=bv,comparison_state=state,output_state=v['result']['status'],output_source='script_only',independent_truth=False))
        export.extend(production_records(v))
        if row in baseline and comparison_state(baseline[row],av,bv)=='match' and state!='match':
            regressions.append(row)
    write_jsonl(WORK/f'audit-{VERSION}.jsonl',audit)
    write_jsonl(WORK/f'unresolved-{VERSION}.jsonl',[v for v in audit if v['output_state']=='uncertain'])
    write_jsonl(WORK/'excel-records.jsonl',sorted(export,key=lambda r:r['row']))
    summary={'release_version':RELEASE_VERSION,'version':VERSION,'unique_titles':len(data),'mapped_rows':len(export),
             'output_status_titles':dict(Counter(v['output_state'] for v in audit)),
             'output_status_rows':dict(Counter('uncertain' if r['name'] is None else 'no_name' if not r['name'] else 'names' for r in export)),
             'comparison_titles':dict(Counter(v['comparison_state'] for v in audit)),
             'regression_rows_from_v1':regressions,
             'ai_a_coverage':len(a),'ai_b_coverage':len(b),
             'true_accuracy':None,'human_review_performed':False,'production_source':'script_only'}
    if (WORK/'human-review-scope.json').exists():
        summary['human_review_scope'] = json.loads((WORK/'human-review-scope.json').read_text())
        summary['human_review_performed'] = True
        summary['full_human_review_complete'] = False
    if WORK in (DEFAULT_WORK, NEXT_STAGE):
        index = {v['row']:v for v in data}
        summary['v1_reference_comparison'] = dict(Counter(comparison_state(index[v['row']],v['ai_a'],v['ai_b'])
                                                         for v in read_jsonl(BASELINE/'ai-references.jsonl')))
        summary['ai_coverage'] = {channel:coverage(channel,data) for channel in ('a','b')}
    write_json(WORK/f'comparison-{VERSION}.json',summary)
    write_json(WORK/'delivery-summary.json',summary)
    print(json.dumps(summary,ensure_ascii=False,indent=2))


def export(source, output):
    from excel_output import export_workbook
    finish()
    verification = export_workbook(source, output, read_jsonl(WORK/'excel-records.jsonl'))
    write_json(WORK/'excel-verification.json',verification)
    print(json.dumps(verification,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['run','reviews','reviews-extra','finish','learn','export']);p.add_argument('--target-version')
    p.add_argument('--work',type=Path,default=DEFAULT_WORK)
    p.add_argument('--source',type=Path,default=ROOT/'任职资格批复汇总测试.xlsx')
    p.add_argument('--output',type=Path,default=ROOT/f'outputs/{"v2" if RELEASE_VERSION=="0.2.0" else RELEASE_VERSION}/任职资格批复汇总测试-{RELEASE_VERSION}纯脚本待复核版.xlsx')
    args=p.parse_args()
    WORK = args.work.resolve()
    if args.action=='export':
        export(args.source,args.output)
    elif args.action=='learn':
        if not args.target_version: p.error('learn requires --target-version')
        learn_anchors(args.target_version)
    elif args.action=='reviews-extra': prepare_reviews(extra=True)
    else: {'run':run,'reviews':prepare_reviews,'finish':finish}[args.action]()
