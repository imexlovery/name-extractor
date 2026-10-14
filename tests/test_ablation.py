"""Check experiment isolation and reference scoring before the full run."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from name_extractor_ablation import category, load_module


class AblationTests(unittest.TestCase):
    def test_unresolved_reference_is_never_a_match(self):
        result = ('uncertain', ())
        self.assertEqual(category(result, result), 'unresolved_reference')
        self.assertEqual(category(('names', ('张三',)), result), 'unresolved_reference')

    def test_abstentions_and_determinate_differences_are_separate(self):
        reference = ('names', ('张三',))
        self.assertEqual(category(reference, reference), 'match')
        self.assertEqual(category(('uncertain', ('张三',)), reference), 'script_unresolved_confirmed_reference')
        self.assertEqual(category(('names', ('张三健',)), reference), 'name_or_status_difference')
        self.assertEqual(category(('no_name', ()), reference), 'count_or_split_difference')
        self.assertEqual(category(reference, reference, ['字数不符']), 'invalid_script')

    def test_empty_resource_rebuilds_trie_and_keeps_other_rules(self):
        scripts = ROOT / 'scripts'
        original = load_module(scripts / 'extract.py', 'ablation_test_original')
        learned = json.loads((scripts / original.INSTITUTION_ANCHOR_RESOURCE).read_text())
        with tempfile.TemporaryDirectory() as work:
            tmp = Path(work)
            shutil.copyfile(scripts / 'extract.py', tmp / 'extract.py')
            shutil.copyfile(scripts / original.AMBIGUITY_RESOURCE, tmp / original.AMBIGUITY_RESOURCE)
            (tmp / original.INSTITUTION_ANCHOR_RESOURCE).write_text('[]\n')
            ablated = load_module(tmp / 'extract.py', 'ablation_test_empty')
            self.assertEqual(ablated._INSTITUTION_STARTS, original._INSTITUTION_STARTS[:-len(learned)])
            self.assertEqual(ablated._TITLE_AMBIGUITIES, original._TITLE_AMBIGUITIES)
            self.assertEqual(ablated._INSTITUTION_END.pattern, original._INSTITUTION_END.pattern)
            self.assertEqual(ablated._ROLE.pattern, original._ROLE.pattern)
            anchor = '健安金汇保险销售服务有限公司'
            span = (0, len(anchor))
            self.assertIn(span, original._registered_spans(anchor))
            self.assertNotIn(span, ablated._registered_spans(anchor))
            self.assertEqual(ablated.extract('关于核准梁晓芝任职资格的批复'), original.extract('关于核准梁晓芝任职资格的批复'))
        self.assertEqual(json.loads((scripts / original.INSTITUTION_ANCHOR_RESOURCE).read_text()), learned)


if __name__ == '__main__':
    unittest.main()
