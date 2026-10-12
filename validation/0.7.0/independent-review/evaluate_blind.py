"""Compare fresh title-only GPT first answers with frozen script r63."""
from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts'))
from validate import check

WORK = Path(__file__).resolve().parent


def read(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def state(script, label):
    if script['status'] == label['status'] == 'uncertain':
        return 'both_uncertain'
    if label['status'] == 'uncertain':
        return 'ai_uncertain'
    if script['status'] == 'uncertain':
        return 'script_unresolved'
    if (script['status'], script['names']) == (label['status'], label['names']):
        return 'match'
    return 'determinate_difference'


def main():
    frozen = {v['row']: v for v in read(WORK.parent / 'script-r63.jsonl')}
    membership = {v['row']: v for v in read(WORK / 'membership.jsonl')}
    judgments = []
    for channel in ('a', 'b'):
        inputs = {v['row']: v for v in read(WORK / f'input-{channel}.jsonl')}
        labels = read(WORK / f'labels-{channel}.jsonl')
        assert len(labels) == len(inputs) == 447
        assert len({v['row'] for v in labels}) == len(labels)
        assert {v['row'] for v in labels} == inputs.keys()
        for label in labels:
            item = inputs[label['row']]
            assert label['title'] == item['title']
            assert label['reason'].strip()
            assert not check(item['title'], label)['failures'], (label['row'], check(item['title'], label))
            script = frozen[label['row']]['result']
            judgments.append(dict(item, scope=membership[label['row']]['scope'],
                ai_context=channel, first_answer=label, script=script,
                comparison_state=state(script, label), independent_human_truth=False))
    assert len(judgments) == len(membership) == 894
    assert len({v['row'] for v in judgments}) == len(judgments)
    scopes = {scope: dict(titles=len(group), mapped_rows=sum(len(v['rows']) for v in group),
              comparison_states=dict(Counter(v['comparison_state'] for v in group)))
              for scope in sorted({v['scope'] for v in judgments})
              for group in [[v for v in judgments if v['scope'] == scope]]}
    summary = dict(version='r63', distinct_titles=len(judgments),
        mapped_rows=sum(len(v['rows']) for v in judgments),
        original_sampling_membership_preserved=True,
        contexts=2, judgments_per_title=1, distinct_model_independence_claimed=False,
        answers_generated_without_script_results=True, new_human_reviews=0,
        scopes=scopes, comparison_states=dict(Counter(v['comparison_state'] for v in judgments)),
        contract_failures=0, true_accuracy=None, production_backfilled=False,
        sampling_limit='694为历史无姓名池；200为r56姓名去重标题随机样本。单次GPT判断及一致不能估计全表真实准确率。')
    for name, values in [('comparison.jsonl', judgments),
                         ('disagreements.jsonl', [v for v in judgments if v['comparison_state'] not in {'match', 'both_uncertain'}]),
                         ('uncertain.jsonl', [v for v in judgments if v['comparison_state'] == 'both_uncertain'])]:
        (WORK / name).write_text(''.join(json.dumps(v, ensure_ascii=False) + '\n' for v in values))
    (WORK / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
