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
