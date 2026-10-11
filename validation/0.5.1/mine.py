"""Offline r55 risk census: no extraction imports, no production decisions."""
import collections
import json
from pathlib import Path
import random
import re

ROOT = Path(__file__).resolve().parents[2]
WORK = Path(__file__).resolve().parent

def read(path):
    return [json.loads(line) for line in path.read_text().splitlines()]

def save(path, values):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(v, ensure_ascii=False) + '\n' for v in values))

def outside(text):
    depth = 0
    chars = []
    for char in text:
        if char in '(（':
            depth += 1
        chars.append(' ' if depth else char)
        if char in ')）':
            depth = max(0, depth - 1)
    return ''.join(chars)

# Independent lexical signals; they nominate review candidates, never name answers.
ROLE = re.compile(r'董事会秘书|行长助理|总经理助理|主任助理|副首席代表|首席代表|副董事长|董事长|独立董事|执行董事|董事|副理事长|理事长|理事|副监事长|监事长|监事|副行长|行长|副总经理|总经理|副主任|主任|风险总监|财务总监|总精算师|负责人|高级管理人员|高管人员|高管')
ROLE_TAIL = re.compile(r'(?:(?:兼|及|和|与|、|，|,|;|；|的|拟任|担任|出任|任)?(?:' + ROLE.pattern + r'|助理|会秘书|金融机构))*')
QUALIFICATION = re.compile(r'任职资格|拟任资格|职资格|任职|董事资格')
INSTITUTION = re.compile(r'银行|公司|联社|信用社|合作社|分行|支行|农商行|农合行|农信社|保险|信托|代表处|财务')
COUNT = re.compile(r'(等)?([0-9０-９一二三四五六七八九十两]+)(人|位同志|名同志)')
SIMPLE = re.compile(r'关于(?:核准|不予核准|注销|核定|终止审查|批准|同意)?[\u4e00-\u9fff]{2,4}(?:同志)?(?:' + ROLE.pattern + r')?(?:任职资格|拟任资格)(?:核准|审核|审查|事项)?(?:的)?批复')

def signals(item):
    title, result = item['title'], item['result']
    text = outside(title)
    q = QUALIFICATION.search(text)
    found = []
    if result['status'] == 'uncertain':
        return ['existing_abstention']
    if result['status'] == 'names':
        if INSTITUTION.search(text): found.append('institution_adjacency')
        if ROLE.search(text): found.append('post_structure')
        if not SIMPLE.fullmatch(text): found.append('noncanonical_complete_title')
        # Check content after first role against a complete role chain, not a first-match cut.
        if q:
            pre = text[:q.start()]
            for match in ROLE.finditer(pre):
                tail = pre[match.end():].strip()
                if tail and not ROLE_TAIL.fullmatch(tail) and not any(name in tail for name in result['names']):
                    found.append('unconsumed_post_tail')
                    break
        if re.search('[、；;和及与]', text): found.append('list_or_connector')
        if q and text[q.end():] not in ('的批复', '批复', ''): found.append('qualification_tail')
        for match in COUNT.finditer(text):
            if not match[1]: found.append('explicit_count_without_omission')
        if any(re.search(r'任|的|和|及|与|等|拟', name) for name in result['names']):
            found.append('name_lexical_overlap')
    else:
        found.append('no_name_assertion')
        if re.search(r'同志|先生|女士|核准|任职|拟任|及|并|和|、', text): found.append('potential_subject_in_no_name')
    return sorted(set(found))

if __name__ == '__main__':
    data = read(ROOT/'validation/0.5.0/audit-r55.jsonl')
    four = {v['row'] for v in read(ROOT/'validation/0.5.0/four-character-review.jsonl')}
    census = [dict(row=v['row'], rows=v['rows'], title=v['title'], result=v['result'],
                   comparison_state=v['comparison_state'], signals=signals(v)) for v in data]
    save(WORK/'risk-census.jsonl', census)
    # Review all unlabeled determinate non-simple structures, outside the separate four-character set.
    candidates = [v for v in census if v['comparison_state']=='missing_reference' and v['row'] not in four
                  and ('institution_adjacency' in v['signals'] or 'noncanonical_complete_title' in v['signals'] or 'list_or_connector' in v['signals'] or ('post_structure' in v['signals'] and not re.search(r'(?:高级管理人员|高管人员|高管|董事|理事)任职资格',v['title'])))]
    simple = [v for v in census if v['comparison_state']=='missing_reference' and v['row'] not in four and v not in candidates]
    strata = collections.defaultdict(list)
    for v in simple:
        strata[(len(v['result']['names'][0]), '核准' in v['title'], 'post_structure' in v['signals'], 'qualification_tail' in v['signals'])].append(v)
    rng = random.Random(20261012)
    sample = [v for key in sorted(strata) for v in rng.sample(strata[key], min(5,len(strata[key])))]
    selected = candidates + sample
    save(WORK/'selection.jsonl', [dict(v, selection='new_structure_census' if v in candidates else 'ordinary_stratified_sample') for v in selected])
    save(WORK/'blind/silent-screen.jsonl', [{'row':v['row'],'title':v['title']} for v in selected])
    summary = dict(baseline_commit='21fdfdb', rules='r55', titles=len(census), mapped_rows=sum(len(v['rows']) for v in census),
                   status= dict(collections.Counter(v['result']['status'] for v in census)),
                   signal_counts=dict(collections.Counter(s for v in census for s in v['signals'])),
                   missing_reference_titles=sum(v['comparison_state']=='missing_reference' for v in census),
                   newly_reviewed_non_four_structure_titles=len(candidates), ordinary_sample_titles=len(sample),
                   ordinary_pool=len(simple), seed=20261012,
                   interpretation='Signals are risk nominations, not errors. Prior semantic references are reused. Full census is not full independent semantic labeling.')
    (WORK/'mining-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False,indent=2))
