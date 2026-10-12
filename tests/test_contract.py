import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from extract import extract, name_length
from validate import check, reference_length
from pilot import regression_rows


class BusinessContract(unittest.TestCase):
    def test_complete_clauses_keep_subjects_and_attach_intervening_roles(self):
        cases = [
            ('关于张瑞中国农业银行股份有限公司董事、行长、陈琳任职资格的批复', ['张瑞', '陈琳']),
            ('关于张瑞中国农业银行股份有限公司、陈琳中国银行股份有限公司任职资格的批复', ['张瑞', '陈琳']),
            ('关于中国银行股份有限公司晴川支行开业并核准陈琳董事、张瑞任职资格的批复', ['陈琳', '张瑞']),
            ('关于印发《董事任职资格管理规定》及核准陈琳董事任职资格的通知', ['陈琳']),
            ('关于中国农业银行股份有限公司沐云支行：张瑞、陈琳董事任职资格的批复', ['张瑞', '陈琳']),
            ('关于中国建设银行股份有限公司听澜支行（董事名单：胡铁、张瑞）任职资格的批复', ['胡铁', '张瑞']),
        ]
        for title, names in cases:
            if names is not None:
                self.assertEqual((extract(title)['status'], extract(title)['names']), ('names', names))
        result = {'names': ['陈琳张瑞'], 'status': 'names'}
        self.assertIn('四字姓名内部人数待复核', check('关于陈琳张瑞任职资格的批复', result)['flags'])

    def test_structural_actions_parent_institutions_and_complete_roles(self):
        cases = [
            ('关于中国民生银行股份有限公司信用卡中心东北分中心开业并核准杜振亮任职资格的批复', ['杜振亮']),
            ('关于高辉友太安保险经纪有限公司天津分公司主要负责人任职资格的批复', ['高辉']),
            ('关于核准呼天智金融高级管理人员任职资格的批复', ['呼天智']),
            ('关于林远友太安保险经纪有限公司成都分公司主要负责人任职资格的批复', ['林远']),
            ('关于李斌中国工商银行股份有限公司济南分行副行长、风险官任职资格的批复', ['李斌']),
        ]
        for title, names in cases:
            self.assertEqual((extract(title)['status'], extract(title)['names']), ('names', names))
        for title in [
            '关于张三中国工商银行行长李四任职资格的批复',
            '关于林远友太安保险经纪有限公司成都分公司主要负责人周宁任职资格的批复',
        ]:
            result = extract(title)
            self.assertEqual((result['status'], result['rule']), ('uncertain', 'conflicting_person_boundaries'))
            self.assertEqual(check(title, result)['failures'], [])

    def test_v2_observed_boundaries_and_aliases(self):
        cases = [
            ('关于核准冉洵高管任职资格的批复', ['冉洵']),
            ('关于核准袁斯佳井冈山九银村镇银行有限公司计划财务部负责人任职资格的批复', ['袁斯佳']),
            ('关于HONGYOUNG（洪铃）现代财产保险（中国）有限公司董事、董事长任职资格的批复', ['HONGYOUNG（洪铃）']),
            ('关于姚镇杰中国人寿财产保险股份有限公司防城港市中心支公司副总经理（主持工作）任职资格的批复', ['姚镇杰']),
            ('关于牙哈甫江·阿不都拉中国建设银行股份有限公司阿克苏地区分行副行长任职资格的批复', ['牙哈甫江·阿不都拉']),
            ('关于核准DR.DAHLHEIMCHRISTIAN大众汽车金融（中国）有限公司董事任职资格的批复', ['DAHLHEIMCHRISTIAN']),
            ('关于中国人寿保险股份有限公司襄阳市襄城区支公司溪苑路营业部经理向晓静任职资格的批复', ['向晓静']),
            ('关于注销潘明（PANMING）华美银行（中国）有限公司行长任职资格行政许可决定的通知', ['潘明（PANMING）']),
        ]
        for title,names in cases:
            with self.subTest(title=title):
                result=extract(title)
                self.assertEqual((result['status'],result['names']),('names',names))
                self.assertEqual(check(title,result)['failures'],[])
        self.assertEqual(extract('关于核准何子任高级管理人员任职资格的批复')['status'],'uncertain')
        self.assertEqual(extract('关于德国安顾集团股份公司济南代表处变更首席代表的批复')['status'],'no_name')

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

    def test_complete_connector_rosters_and_internal_name_characters(self):
        title='关于杨宝秀和孟光任职资格的批复'
        result=extract(title)
        self.assertEqual(result['names'], ['杨宝秀', '孟光'])
        self.assertEqual(result['status'], 'names')
        self.assertEqual(sum(map(name_length, result['names'])), 5)
        for person in ['和全', '郑和', '刘金和', '孟和巴拉']:
            self.assertEqual(extract(f'关于{person}任职资格的批复')['names'], [person])
        self.assertEqual(extract('关于和田智岳（TomotakeWada）任职资格的批复')['status'],'names')
        self.assertEqual(extract('关于大连银行毕贺轩重庆分行行长任职资格的批复')['names'],['毕贺轩'])
        self.assertEqual(extract('关于大连银行毕贺轩重庆分行行长任职资格的批复')['status'],'names')
        long_person=extract('关于核准阿拉腾础鲁任职资格的批复')
        self.assertEqual(long_person['names'],['阿拉腾础鲁'])
        self.assertEqual(long_person['status'],'uncertain')
        for fragment in ['兼','总裁','营业部','开业及高管']:
            self.assertTrue(check(title, {'names':[fragment], 'status':'names'})['flags'])

    def test_v030_observed_complete_title_boundaries(self):
        cases = [
            ('关于中国银行股份有限公司大连瓦房店支行行长于鹏任职资格的批复',['于鹏']),
            ('关于刘海松魏县农村信用合作联社主任任职资格的批复',['刘海松']),
            ('关于福海县农村信用合作联社徐兆杰联社主任任职资格的批复',['徐兆杰']),
            ('关于内蒙古自治区农村信用社联合社周秀颖通辽审计中心主任任职资格的批复',['周秀颖']),
            ('关于何春艳法律合规部负责人任职资格的批复',['何春艳']),
            ('关于新疆喀什农村商业银行股份有限公司张洋拟任资格的批复',['张洋']),
            ('关于郑向敏福州农商银行独立董事、陈智力福州农商银行董事任职资格的批复',['郑向敏','陈智力']),
            ('关于卢锡羿任职资格的批复于卢锡羿任职资格的批复',['卢锡羿']),
            ('关于义康安保险代理有限责任公司\u200c纳亮任职资格的批复',['纳亮']),
        ]
        for title,names in cases:
            with self.subTest(title=title):
                self.assertEqual((extract(title)['status'],extract(title)['names']),('names',names))
        for title in [
            '关于《保险公司董事和高级管理人员任职资格管理规定》具体适用问题的通知',
            '关于交通银行娄底分行副行长任职资格的批复',
            '关于核准青海同仁农村商业银行股份有限公司独立董事任职资格的批复',
        ]:
            self.assertEqual(extract(title)['status'],'no_name')

    def test_v030_historical_doubts_remain_explicitly_uncertain(self):
        for title in [
            '关于核准路达的批复',
            '关于核准Stéphanie,Anne,MarieLEGALdeKERANGALép.CLEMENTDEGIVRY法国兴业银行（中国）有限公司董事任职资格的批复',
            '关于DAUNYSandrine，Marie-José广汽汇理汽车金融有限公司董事任职资格的批复',
            '关于纳雍县农村信用合作联社行舒振国任职资格的批复',
            '关于BaronvonPfetten，JeanChristophe任职资格的批复',
            '关于王菲米兰金融机构独立董事任职资格的批复',
            '关于陈\ue863任职资格的批复',
        ]:
            with self.subTest(title=title):
                self.assertEqual(extract(title)['status'],'uncertain')

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
