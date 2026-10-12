import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import full
from pilot import write_jsonl, read_jsonl


class ReviewFailureHandling(unittest.TestCase):
    def test_v070_compares_r61_and_reuses_v060_references(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline, previous, work = [root / name for name in ('v1', '0.6.0', '0.7.0')]
            label = {'row': 2, 'names': ['梁晓芝'], 'status': 'names'}
            title = '关于梁晓芝任职资格的批复'
            item = dict(row=2, rows=[2], title=title, result=dict(label, status='uncertain', length=3, extracted_name='梁晓芝'))
            write_jsonl(baseline / 'script-r29.jsonl', [item])
            write_jsonl(baseline / 'ai-references.jsonl', [])
            write_jsonl(baseline / 'ai-reference-exclusions.jsonl', [])
            write_jsonl(previous / 'script-r61.jsonl', [item])
            write_jsonl(previous / 'labels/review-a-01.jsonl', [label])
            with patch.object(full, 'BASELINE', baseline), patch.object(full, 'V060_STAGE', previous), \
                    patch.object(full, 'DEFAULT_WORK', work), patch.object(full, 'WORK', work), \
                    patch.object(full, 'RELEASE_VERSION', '0.7.0'), contextlib.redirect_stdout(io.StringIO()):
                full.run()
                self.assertEqual(full.labels('a')[2], label)
                self.assertEqual(full.coverage('a', [item])['new_unique_titles'], 0)
            summary = json.loads((work / f'summary-{full.VERSION}.json').read_text())
            self.assertEqual(summary['comparison_baseline_version'], 'r61')
            self.assertEqual(summary['changed_titles_from_r61'], 1)
            self.assertEqual(len(read_jsonl(work / f'changes-from-r61-{full.VERSION}.jsonl')), 1)

    def test_v060_inherits_r56_corrections_and_template_labels_as_old_coverage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline, frozen, work = [root / name for name in ('v1', '0.5.1', '0.6.0')]
            first = {'row': 2, 'names': ['梁晓芝'], 'status': 'uncertain'}
            corrected = dict(first, status='names')
            template = dict(corrected, row=3)
            write_jsonl(baseline / 'ai-references.jsonl', [])
            write_jsonl(baseline / 'ai-reference-exclusions.jsonl', [])
            write_jsonl(frozen / 'labels/review-a-01.jsonl', [first])
            write_jsonl(frozen / 'labels/reference-corrections-a-01.jsonl', [
                dict(row=2, before=first, after=corrected, reason='保留首答的显式更正')])
            write_jsonl(frozen / 'labels/template-semantic-a-01.jsonl', [template])
            inventory = [dict(row=row, rows=[row], title='关于梁晓芝任职资格的批复') for row in (2, 3)]
            with patch.object(full, 'BASELINE', baseline), patch.object(full, 'FROZEN_STAGE', frozen), \
                    patch.object(full, 'DEFAULT_WORK', work), patch.object(full, 'WORK', work):
                self.assertEqual(full.labels('a'), {2: corrected, 3: template})
                self.assertEqual(full.coverage('a', inventory)['new_unique_titles'], 0)
            self.assertEqual(read_jsonl(frozen / 'labels/review-a-01.jsonl'), [first])

    def test_v050_reuses_v040_first_answers_and_corrections(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline, previous, next_stage, latest, work = [root / name for name in ('v1', 'v2', '0.3.0', '0.4.0', '0.5.0')]
            label = {'row': 2, 'names': ['梁晓芝'], 'status': 'names'}
            write_jsonl(baseline / 'ai-references.jsonl', [{'row': 2, 'ai_a': label, 'ai_b': label}])
            write_jsonl(baseline / 'ai-reference-exclusions.jsonl', [])
            first = dict(label, row=3, status='uncertain')
            after = dict(label, row=3)
            write_jsonl(latest / 'labels/review-a-01.jsonl', [first])
            write_jsonl(latest / 'labels/reference-corrections-a-01.jsonl', [
                {'row': 3, 'before': first, 'after': after, 'reason': '原标题边界复核'}])
            inventory = [{'row': row, 'rows': [row], 'title': '关于梁晓芝任职资格的批复'} for row in (2, 3)]
            with patch.object(full, 'BASELINE', baseline), patch.object(full, 'PREVIOUS_STAGE', previous), \
                    patch.object(full, 'NEXT_STAGE', next_stage), patch.object(full, 'LATEST_STAGE', latest), \
                    patch.object(full, 'WORK', work), patch.object(full, 'DEFAULT_WORK', work):
                self.assertEqual(full.labels('a'), {2: label, 3: after})
                self.assertEqual(full.coverage('a', inventory)['new_unique_titles'], 0)
            self.assertEqual(read_jsonl(latest / 'labels/review-a-01.jsonl'), [first])

    def test_v040_inherits_all_saved_stages_and_preserves_reference_conflicts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline, previous, next_stage, work = [root / name for name in ('v1', 'v2', '0.3.0', '0.4.0')]
            label = {'row': 2, 'names': ['梁晓芝'], 'status': 'names'}
            write_jsonl(baseline / 'ai-references.jsonl', [{'row': 2, 'ai_a': label, 'ai_b': label}])
            write_jsonl(baseline / 'ai-reference-exclusions.jsonl', [])
            write_jsonl(previous / 'labels/review-a-01.jsonl', [dict(label, row=3)])
            write_jsonl(next_stage / 'labels/review-a-01.jsonl', [dict(label, row=4)])
            write_jsonl(work / 'labels/review-a-01.jsonl', [dict(label, row=5), dict(label, row=4, status='uncertain')])
            inventory = [{'row': row, 'rows': [row], 'title': '关于梁晓芝任职资格的批复'} for row in (2, 3, 4, 5)]
            with patch.object(full, 'BASELINE', baseline), patch.object(full, 'PREVIOUS_STAGE', previous), \
                    patch.object(full, 'NEXT_STAGE', next_stage), patch.object(full, 'WORK', work), \
                    patch.object(full, 'DEFAULT_WORK', work):
                self.assertEqual(set(full.labels('a')), {2, 3, 4, 5})
                self.assertEqual(full.labels('a')[4]['status'], 'uncertain')
                self.assertEqual(full.coverage('a', inventory)['new_unique_titles'], 1)

    def test_v030_inherits_saved_references_and_counts_only_new_judgments(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);baseline=root/'v1';previous=root/'v2';work=root/'0.3.0'
            labels=[{'row':r,'names':['梁晓芝'],'status':'names'} for r in (2,3,4)]
            write_jsonl(baseline/'ai-references.jsonl',[{'row':2,'ai_a':labels[0],'ai_b':labels[0]}])
            write_jsonl(baseline/'ai-reference-exclusions.jsonl',[])
            for channel in ('a','b'):
                write_jsonl(previous/f'labels/review-{channel}-01.jsonl',[labels[1]])
                write_jsonl(work/f'labels/holdout-{channel}-01.jsonl',[labels[2]])
            inventory=[{'row':r,'rows':[r],'title':'关于梁晓芝任职资格的批复'} for r in (2,3,4)]
            with patch.object(full,'BASELINE',baseline),patch.object(full,'WORK',work),patch.object(full,'NEXT_STAGE',work),patch.object(full,'PREVIOUS_STAGE',previous),patch.object(full,'OLD',root/'missing'):
                for channel in ('a','b'):
                    self.assertEqual(set(full.labels(channel)),{2,3,4})
                    self.assertEqual(full.coverage(channel,inventory)['new_unique_titles'],1)

    def test_v1_reference_cache_without_ignored_local_history(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);baseline=root/'v1';work=root/'v2'
            label={'row':2,'names':['梁晓芝'],'status':'names'}
            write_jsonl(baseline/'ai-references.jsonl',[{'row':2,'ai_a':label,'ai_b':label}])
            write_jsonl(baseline/'ai-reference-exclusions.jsonl',[])
            inventory=[{'row':2,'rows':[2],'title':'关于梁晓芝任职资格的批复'}]
            with patch.object(full,'BASELINE',baseline),patch.object(full,'WORK',work),patch.object(full,'DEFAULT_WORK',work),patch.object(full,'OLD',root/'missing'):
                result=full.coverage('a',inventory)
            self.assertEqual(result['unique_titles'],1)
            self.assertEqual(result['new_unique_titles'],0)

    def test_explicit_correction_preserves_first_answer(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); work,old=root/'work',root/'old'
            (work/'labels').mkdir(parents=True);old.mkdir()
            write_jsonl(old/'holdout-ai-b.jsonl',[])
            first={'row':2,'names':['梁晓芝机构'],'status':'names','reason':'首答'}
            after=dict(first,names=['梁晓芝'],reason='机构边界修正')
            original=work/'labels/review-b-0001.jsonl'
            write_jsonl(original,[first])
            write_jsonl(work/'labels/reference-corrections-b-tail.jsonl',[
                {'row':2,'before':first,'after':after,'reason':'标题机构词不能并入姓名'}])
            with patch.object(full,'WORK',work),patch.object(full,'OLD',old):
                result=full.labels('b')
            self.assertEqual(result[2],after)
            self.assertEqual(read_jsonl(original),[first])

    def test_missing_invalid_and_disputed_labels_do_not_change_script_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            work, old = root/'work', root/'old'
            (work/'labels').mkdir(parents=True)
            old.mkdir()
            for channel in ('a','b'):
                write_jsonl(old/f'holdout-ai-{channel}.jsonl', [])
            items = [{'row':row, 'rows':[row], 'title':'关于梁晓芝任职资格的批复',
                      'result':{'names':['梁晓芝'],'status':'names','length':3,'extracted_name':'梁晓芝'},
                      'checks':{'failures':[],'flags':[]}} for row in range(2,7)]
            write_jsonl(work/f'script-{full.VERSION}.jsonl',items)
            write_jsonl(work/'review-targets.jsonl',[{'row':v['row']} for v in items])
            write_jsonl(work/'holdout-frozen.jsonl',[])
            write_jsonl(work/'labels/review-a-0001.jsonl',[
                {'row':row,'names':['梁晓芝'],'status':'names','reason':'标题原文'} for row in range(2,7)])
            write_jsonl(work/'labels/review-b-0001.jsonl',[
                {'row':3,'names':['另一人'],'status':'names','reason':'故障注入'},
                {'row':4,'names':[],'status':'no_name','reason':'分歧注入'},
                {'row':5,'names':['梁晓芝'],'status':'uncertain','reason':'语义未决'},
                {'row':6,'names':['梁晓芝'],'status':'names','reason':'标题原文'}])
            with patch.object(full,'WORK',work), patch.object(full,'OLD',old), contextlib.redirect_stdout(io.StringIO()):
                full.finish()
            result = read_jsonl(work/'excel-records.jsonl')
            self.assertEqual(result,[{'row':row,'name':'梁晓芝','length':3} for row in range(2,7)])
            summary=json.loads((work/'delivery-summary.json').read_text())
            self.assertEqual(summary['comparison_titles'],{'single_channel':1,'invalid_reference':1,'disputed_reference':2,'match':1})
            self.assertEqual(summary['output_status_titles'],{'names':5})

    def test_consensus_cannot_fill_uncertain_or_replace_conflicting_output(self):
        reference={'names':['梁晓芝'],'status':'names'}
        item={'row':2,'rows':[2,8],'title':'关于梁晓芝任职资格的批复',
              'result':{'names':['梁晓芝'],'status':'uncertain','length':3}}
        self.assertEqual(full.comparison_state(item,reference,reference),'script_unresolved')
        self.assertEqual(full.production_records(item),[{'row':r,'name':None,'length':None} for r in (2,8)])
        item['result']={'names':[],'status':'no_name','length':0}
        self.assertEqual(full.comparison_state(item,reference,reference),'no_name_dispute')
        self.assertEqual(full.production_records(item),[{'row':r,'name':'','length':0} for r in (2,8)])

    def test_historical_coverage_is_not_counted_as_new(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); work,old=root/'work',root/'old'
            (work/'labels').mkdir(parents=True);old.mkdir()
            label={'row':2,'names':['梁晓芝'],'status':'names','reason':'标题原文'}
            write_jsonl(old/'holdout-ai-a.jsonl',[label])
            write_jsonl(work/'labels/review-a-0001.jsonl',[label,dict(label,row=3)])
            write_jsonl(work/'labels/extra-a-0001.jsonl',[label])
            inventory=[{'row':2,'rows':[2,4],'title':'梁晓芝'},{'row':3,'rows':[3],'title':'梁晓芝'}]
            with patch.object(full,'WORK',work),patch.object(full,'OLD',old):
                result=full.coverage('a',inventory)
            self.assertEqual((result['unique_titles'],result['mapped_rows']), (2,3))
            self.assertEqual((result['new_unique_titles'],result['new_mapped_rows']), (1,1))
            self.assertEqual(result['repeated_saved_judgments'],1)


if __name__=='__main__':
    unittest.main()
