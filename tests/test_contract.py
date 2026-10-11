import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from extract import extract, name_length
from validate import check, reference_length
from pilot import regression_rows


class BusinessContract(unittest.TestCase):
    def test_real_silent_error_fixes(self):
        cases = [
            ('关于核准宋正周遂宁银行股份有限公司总行营业部总经理任职资格的批复', ['宋正周']),
            ('关于张利信托保障基金公司总裁任职资格的批复', ['张利']),
            ('关于贺琳升华茂林保险销售服务有限公司董事兼总经理任职资格的批复', ['贺琳']),
            ('关于褚晔中信银行扬州分行副行长任职的批复', ['褚晔']),
            ('关于同意李志伟任职英大泰和财产保险股份有限公司新乡中心支公司副总经理（主持工作）资格核准的批复', ['李志伟']),
            ('关于吴海波招商银行长春分行行长助理任职资格的批复', ['吴海波']),
            ('关于核准唐开元四川邻水农村商业银行股份有限公司合规与风险管理部总经理任职资格的批复', ['唐开元']),
            ('关于核准李二兵河南能源化工集团财务有限公司信息科技总监任职资格的批复', ['李二兵']),
            ('关于张婉清等3位同志任职资格的批复', ['张婉清']),
            ('关于众惠财产相互保险社王正莲任职资格的批复', ['王正莲']),
            ('关于郑璐信美人寿相互保险社董事会秘书任职资格的批复', ['郑璐']),
        ]
        for title, expected in cases:
            with self.subTest(title=title):
                self.assertEqual(extract(title)['names'], expected)
                self.assertEqual(extract(title)['status'], 'names')

    def test_connectors_do_not_silently_become_confirmed_names(self):
        title='关于杨宝秀和孟光任职资格的批复'
        result=extract(title)
        self.assertEqual(result['names'], ['杨宝秀', '孟光'])
        self.assertEqual(result['status'], 'uncertain')
        self.assertEqual(sum(map(name_length, result['names'])), 5)
        for person in ['和全', '郑和', '刘金和', '孟和巴拉']:
            self.assertEqual(extract(f'关于{person}任职资格的批复')['names'], [person])
        self.assertEqual(extract('关于和田智岳（TomotakeWada）任职资格的批复')['status'],'names')
        self.assertEqual(extract('关于大连银行毕贺轩重庆分行行长任职资格的批复')['status'],'uncertain')
        long_person=extract('关于核准阿拉腾础鲁任职资格的批复')
        self.assertEqual(long_person['names'],['阿拉腾础鲁'])
        self.assertEqual(long_person['status'],'uncertain')
        for fragment in ['兼','总裁','营业部','开业及高管']:
            self.assertTrue(check(title, {'names':[fragment], 'status':'names'})['flags'])

    def test_regression_includes_later_fixes_and_length(self):
        good={'names':['崔延峰'], 'status':'names', 'length':3, 'extracted_name':'崔延峰'}
        label={652:{'names':['崔延峰'],'status':'names'}}
        for broken in [dict(good,names=[],status='uncertain'),dict(good,length=4),dict(good,extracted_name='错误'),dict(good,checks={'failures':['字数不符']})]:
            self.assertEqual(regression_rows([{}, {652:good}], {652:broken}, label), [652])
    def test_confirmed_examples(self):
        cases = [
            ("关于核准梁晓芝任职资格的批复", ["梁晓芝"], 3),
            ("关于秦铖、蒲涛任职资格的批复", ["秦铖", "蒲涛"], 4),
            ("关于GohYihYee（吴子宇）任职资格的批复", ["GohYihYee（吴子宇）"], 12),
            ("关于孙体虎等4人任职资格的批复", ["孙体虎"], 3),
            ("关于莫里·洪恩工商银行独立董事任职资格的批复", ["莫里·洪恩"], 4),
            ("关于陈料挥（CHEN,LIAO-HUEI）任职资格的批复", ["陈料挥（CHEN,LIAO-HUEI）"], 15),
            ("关于KelvinS.Aquilino（许世堃）任职资格的批复", ["KelvinS.Aquilino（许世堃）"], 18),
        ]
        for title, expected, length in cases:
            with self.subTest(title=title):
                self.assertEqual(extract(title)["names"], expected)
                self.assertEqual(sum(map(name_length, expected)), length)
                self.assertEqual(reference_length(expected), length)

    def test_check_detects_wrong_length_and_unsupported_names(self):
        self.assertIn("字数不符", check("关于梁晓芝任职资格的批复", {
            "names": ["梁晓芝"], "status": "names", "length": 4})["failures"])
        self.assertIn("姓名不在原标题或顺序不符", check("关于梁晓芝任职资格的批复", {
            "names": ["另一人"], "status": "names", "length": 3})["failures"])

    def test_no_name_and_uncertain_are_different(self):
        result = extract("关于某银行分行开业的批复")
        self.assertEqual(result["names"], [])
        self.assertEqual(result["status"], "no_name")
        result = check("关于甲任职资格的批复", {"names": [], "status": "uncertain", "length": 0})
        self.assertIn("提取器未确定", result["flags"])


if __name__ == "__main__":
    unittest.main()
