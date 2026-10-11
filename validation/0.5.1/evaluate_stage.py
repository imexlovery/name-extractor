"""Report frozen baseline, blind first answers, explicit corrections and regressions."""
import collections
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
WORK = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT/'scripts'))
import full
from validate import check


def read(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def save(name, values):
    (WORK/name).write_text(''.join(json.dumps(v,ensure_ascii=False)+'\n' for v in values))


def load(path, name):
    spec = importlib.util.spec_from_file_location(name,path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def compare(module, cases):
    return [dict(v,script=(result:=module.extract(v['title'])),
                 matches=result['status']==v['status'] and (v['status']=='uncertain' or result['names']==v['names'])) for v in cases]


if __name__ == '__main__':
    index = {v['row']:v for v in read(WORK/'script-r56.jsonl')}
    baseline = {v['row']:v for v in read(ROOT/'validation/0.5.0/audit-r55.jsonl')}
    full.WORK = WORK
    refs = {channel:full.labels(channel) for channel in ('a','b')}
    report = {}
    exported = []
    for group in ('four-character','silent-screen'):
        blind = read(WORK/f'blind/{group}.jsonl')
        first = {ch:{v['row']:v for v in read(WORK/f'labels/{group}-{ch}-01.jsonl')} for ch in ('a','b')}
        ids = {v['row'] for v in blind}
        assert len(ids)==len(blind)
        for ch in ('a','b'):
            assert len(first[ch])==len(read(WORK/f'labels/{group}-{ch}-01.jsonl'))==len(ids)
            assert set(first[ch])==ids
            for v in blind:
                label=first[ch][v['row']]
                assert label['title']==v['title'] and label['reason'] and not check(v['title'],label)['failures']
                assert baseline[v['row']]['comparison_state']=='missing_reference'
        audit = []
        for v in blind:
            row = v['row']
            a,b=refs['a'][row],refs['b'][row]
            state=full.comparison_state(index[row],a,b)
            initial_agreed=(first['a'][row]['status'],first['a'][row]['names'])==(first['b'][row]['status'],first['b'][row]['names'])
            audit.append(dict(v,rows=index[row]['rows'],ai_a=a,ai_b=b,initial_agreed=initial_agreed,comparison_state=state,
                              production_result=index[row]['result'],person_count_proven=a.get('person_count_proven') is True and b.get('person_count_proven') is True, independent_truth=False))
        save(f'{group}-comparison.jsonl',audit)
        exported.extend(audit)
        report[group]=dict(titles=len(audit),mapped_rows=sum(len(v['rows']) for v in audit),
                           initial_consensus=sum(v['initial_agreed'] for v in audit),
                           final_comparison=dict(collections.Counter(v['comparison_state'] for v in audit)),
                           proved_single_person=sum(v['person_count_proven'] for v in audit) if group=='four-character' else None)
    save('new-ai-references.jsonl',[v for v in exported if v['comparison_state']=='match'])
    save('new-ai-exclusions.jsonl',[v for v in exported if v['comparison_state']!='match'])
    baseline_rules=load(ROOT/'validation/0.5.0/extract-r55.py','r55_frozen')
    rules=load(WORK/'extract-r56.py','r56_frozen')
    cases=[]
    for connector in '及和与、':
        for first,second in [('张明','李华'),('欧阳鹏飞','林远'),('GohYihYee（吴子宇）','王五')]:
            cases.append(dict(title=f'关于核准{first}董事{connector}{second}监事任职资格的批复',status='names',names=[first,second],purpose='complete_named_clauses'))
        for count,status in [('两','names'),('一','uncertain')]:
            cases.append(dict(title=f'关于张明董事{connector}李华监事共{count}人任职资格的批复',status=status,names=['张明','李华'],purpose='joint_cardinality'))
    for title in ['关于张明董事李华监事任职资格的批复','关于张明中国银行董事李华任职资格的批复']:
        cases.append(dict(title=title,status='uncertain',names=[],purpose='unconsumed_subject'))
    for title,name in [('关于张明董事及监事任职资格的批复','张明'),('关于张明董事兼监事任职资格的批复','张明'),
                       ('关于任庆和董事任职资格的批复','任庆和'),('关于张明内控与风险合规部负责人任职资格的批复','张明'),
                       ('关于梁居正大连银行营业部总经理助理任职资格的批复','梁居正'),('关于核准区琨瑜理事会秘书任职资格的批复','区琨瑜')]:
        cases.append(dict(title=title,status='names',names=[name],purpose='retention'))
    save('clause-cases.jsonl',cases)
    results={version:compare(module,cases) for version,module in [('r55',baseline_rules),('r56',rules)]}
    for version,values in results.items(): save(f'clause-{version}.jsonl',values)
    report['synthetic_contracts']={ver:dict(total=len(v),matched=sum(x['matches'] for x in v),failed=[x['title'] for x in v if not x['matches']]) for ver,v in results.items()}
    old=read(ROOT/'validation/0.5.0/person-count-cases.jsonl')
    previous=compare(rules,old)
    report['old_person_count_regressions']={purpose:dict(total=sum(v['purpose']==purpose for v in previous),matched=sum(v['purpose']==purpose and v['matches'] for v in previous)) for purpose in ['structure_contract','known_risk_replay','retention_policy']}
    cached = {}
    previous_stage = ROOT/'validation/0.4.0'
    for key,af,bf in [('development','structure-holdout-reference.jsonl','structure-holdout-reference-b.jsonl'),
                      ('fresh_then_revealed','structure-fresh-reference-a.jsonl','structure-fresh-reference-b.jsonl'),
                      ('final_then_revealed','final-structure-reference-a.jsonl','final-structure-reference-b.jsonl')]:
        a=read(previous_stage/af);b={v['id']:v for v in read(previous_stage/bf)}
        agreed=[v for v in a if (v['status'],v['names'])==(b[v['id']]['status'],b[v['id']]['names'])]
        r55=compare(baseline_rules,agreed);r56=compare(rules,agreed)
        cached[key]=dict(agreed=len(agreed),r55_matched=sum(v['matches'] for v in r55),r56_matched=sum(v['matches'] for v in r56),
                         new_regressions=[a['id'] for a,b in zip(r55,r56) if a['matches'] and not b['matches']])
    report['cached_synthetic_regressions']=cached
    report['full_comparison']=json.loads((WORK/'comparison-r56.json').read_text())
    report['mining']=json.loads((WORK/'mining-summary.json').read_text())
    report['interpretation']='337 new title-only A/B references; 5 B evidence-classification corrections preserve raw first answers. No single-person count proof for 34 four-character titles. Synthetic improvement is not real-data accuracy improvement. Full saved-title output is unchanged; no confirmed new real-data silent error. Existing uncertainties and historical reference disputes remain. No new abstention exceptions. True accuracy unmeasured.'
    (WORK/'stage-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('full_comparison','mining')},ensure_ascii=False,indent=2))
