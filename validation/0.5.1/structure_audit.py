"""Audit frozen r56 titles in full; never import or change production extraction.

Patterns nominate structural risks or check explicit slots. Neither a complete
slot nor agreement with a script is an independently verified semantic answer.
"""
from collections import Counter, defaultdict
import json
from pathlib import Path
import re

from mine import outside, signals

WORK = Path(__file__).resolve().parent
OUT = WORK / 'structure-audit'
DIRECT = re.compile(
    r'关于(?:不予核准|核准|同意)?(?P<subject>[\u4e00-\u9fff]{2,4}?)(?:同志)?'
    r'(?:执行董事|独立董事|董事|理事|高级管理人员|高管人员)?'
    r'任职资格(?:事项|核准|审核)?(?:的)?批复'
)
QUALIFICATION = re.compile(r'任职资格|拟任资格|职资格')
NEUTRAL_TAIL = re.compile(
    r'(?:(?:核准|审核|审查|事项|申请|请示|核准请示|进行审核)?(?:的)?批复|\s*)'
)


def save(name, values):
    (OUT / name).write_text(''.join(json.dumps(v, ensure_ascii=False) + '\n' for v in values))


def audit(item):
    title = item['title']
    found = set(signals(item)) & {'unconsumed_post_tail'}
    # Unlike extraction, retain text after qualification and after omission.
    qualifications = list(QUALIFICATION.finditer(title))
    if len(qualifications) > 1:
        found.add('multiple_qualification_segments')
    if qualifications and not NEUTRAL_TAIL.fullmatch(title[qualifications[0].end():]):
        found.add('qualification_tail_needs_review')
    if item['result']['status'] == 'no_name':
        found.add('no_name_full_title_review')
    omitted = re.search(r'等(?:[0-9０-９一二三四五六七八九十百千万两]+)?(?:人|位|名|同志)', title)
    if omitted and re.search('[、；;和及与并]', outside(title[omitted.end():])):
        found.add('coordination_after_omission')
    # Do not hide a potential second subject just because it is parenthesized.
    remaining = title
    for name in item['result']['names']:
        remaining = remaining.replace(name, ' ', 1)
    if re.search(r'[（(][^（）()]+[）)]', remaining):
        found.add('parentheses_outside_extracted_names')
    if title.count('关于') > 1:
        found.add('multiple_about_segments')
    return sorted(found)


def main():
    data = [json.loads(line) for line in (WORK / 'audit-r56.jsonl').read_text().splitlines()]
    OUT.mkdir(exist_ok=True)
    missing = [v for v in data if v['comparison_state'] == 'missing_reference']
    strata = defaultdict(list)
    discrepancies = []
    for v in missing:
        match = DIRECT.fullmatch(v['title'])
        if match:
            template = v['title'][:match.start('subject')] + '<姓名槽位>' + v['title'][match.end('subject'):]
            if v['result']['status'] != 'names' or v['result']['names'] != [match['subject']]:
                discrepancies.append(dict(row=v['row'], title=v['title'], slot=match['subject'], result=v['result']))
        else:
            template = '<严格完整模板未覆盖>'
            discrepancies.append(dict(row=v['row'], title=v['title'], slot=None, result=v['result']))
        strata[template].append(v)
    candidates = []
    for v in data:
        risks = audit(v)
        if risks:
            candidates.append(dict(row=v['row'], rows=v['rows'], title=v['title'], result=v['result'],
                                   comparison_state=v['comparison_state'], signals=risks,
                                   reference_action='reuse_existing' if v['comparison_state'] == 'match' else
                                   'new_title_only_review' if v['comparison_state'] == 'missing_reference' else
                                   'keep_reference_or_script_dispute_open'))
    save('missing-strata.jsonl', [dict(template=t, titles=len(group), mapped_rows=sum(len(v['rows']) for v in group),
                                     representative=dict(row=group[0]['row'], title=group[0]['title']),
                                     rows=[v['row'] for v in group])
                                  for t, group in sorted(strata.items(), key=lambda x: (len(x[1]), x[0]))])
    save('structural-discrepancies.jsonl', discrepancies)
    save('candidates.jsonl', candidates)
    save('new-review-queue.jsonl', [dict(row=v['row'], title=v['title']) for v in candidates
                                   if v['reference_action'] == 'new_title_only_review'])
    summary = dict(
        baseline_commit='5d4616d', rules='r56', unique_titles=len(data),
        mapped_rows=sum(len(v['rows']) for v in data), missing_reference_titles=len(missing),
        missing_reference_rules=dict(Counter(v['result']['rule'] for v in missing)),
        missing_reference_strata=len(strata), strict_full_title_slot_discrepancies=len(discrepancies),
        candidates=len(candidates), signal_counts=dict(Counter(s for v in candidates for s in v['signals'])),
        candidate_reference_states=dict(Counter(v['comparison_state'] for v in candidates)),
        new_review_queue_titles=sum(v['reference_action'] == 'new_title_only_review' for v in candidates),
        no_name_reference_states=dict(Counter(v['comparison_state'] for v in data if v['result']['status'] == 'no_name')),
        new_ai_judgments=0, production_changes=0, true_accuracy=None, human_review_performed=False,
        interpretation='Full-title structural scan only. Risk flags are not confirmed errors. '
                       'Strict-slot consistency does not add independent semantic references. '
                       'Existing matches are reused, not relabeled or declared human truth.'
    )
    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
