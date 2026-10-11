"""Independent output-contract checks; does not import the extraction implementation."""

import re

COUNTABLE = re.compile(r"[A-Za-z\u3007\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U0002ee5f\U0002f800-\U0002fa1f\U00030000-\U0003347f]")
NON_NAME = re.compile(r"任职|董事|经理|银行|公司|保险|批复|核准|代表处|支行|信用社|分局|联社|农信社|农合行|财险|人寿|信托|总裁|首席|合规官|合规总监|信息科技总监|总审计师|审计责任人|职工|独立理事|营业部|总行|分社|审计部|管理部|风险合规部|合规风险法务部|市场中心|管理中心|业务部|事业部|开业|高管|负责人|^兼$|^及$|^和$")


def reference_length(names):
    return sum(len(COUNTABLE.findall(name)) for name in names)


def check(title, result):
    failures, flags = [], []
    names = result.get("names")
    if not isinstance(names, list) or any(not isinstance(n, str) or not n for n in names):
        return {"failures": ["姓名列表无效"], "flags": []}
    cursor = 0
    for name in names:
        position = title.find(name, cursor)
        if position == -1:
            failures.append("姓名不在原标题或顺序不符")
        else:
            cursor = position + len(name)
        if NON_NAME.search(name):
            flags.append("疑似机构或职位残留")
    if result.get("status") not in {"names", "no_name", "uncertain"}:
        failures.append("状态无效")
    if result.get("status") == "no_name" and names:
        failures.append("无姓名状态带有姓名")
    if result.get("status") == "names" and not names:
        failures.append("姓名状态没有姓名")
    if "length" in result and (type(result["length"]) is not int or result["length"] != reference_length(names)):
        failures.append("字数不符")
    if "extracted_name" in result and result["extracted_name"] != "；".join(names):
        failures.append("多人展示分隔符不符")
    if not names:
        flags.append("空姓名复核")
    if result.get("status") == "uncertain":
        flags.append("提取器未确定")
    if re.search(r"[A-Za-z·•‧・()（）、;；]|等(?:[0-9一二三四五六七八九十百]+)?人", title):
        flags.append("特殊形式复核")
    if re.search(r"银行|公司|联社|代表处|信用社|农商行|农合行|农信社|财险|人寿|寿险|养老|金融机构|保险|信托|金租|消金|理财|农发行|进出口行|村行|互保|株式会社", title):
        flags.append("机构边界复核")
    if re.search(r"和|及|与|兼", title):
        flags.append("连接词语义复核")
    if re.search(r'等|[一二三四五六七八九十两0-9]+位同志|关于对',title):
        flags.append('省略称谓或介词复核')
    if any(reference_length([name]) < 2 or (not re.search(r"[A-Za-z]", name) and reference_length([name]) > 4) for name in names):
        flags.append("异常长度线索")
    return {"failures": sorted(set(failures)), "flags": sorted(set(flags))}


def risk_categories(title, result, checks):
    tags=[]
    if '机构边界复核' in checks['flags']:
        tags.append('机构边界')
    if '疑似机构或职位残留' in checks['flags'] or re.search('兼|营业部|管理部|审计部|合规|总裁|首席',title):
        tags.append('职务或部门残片')
    if re.search('[、；;和及与]',title):
        tags.append('多人连接')
    if re.search('[A-Za-z]',title):
        tags.append('英文及别名')
    if '等' in title:
        tags.append('等人省略')
    if title.count('（')!=title.count('）') or title.count('(')!=title.count(')') or result.get('rule')=='unbalanced_parentheses':
        tags.append('括号异常')
    if '任职' not in title or result.get('rule') in ('missing_qualification','missing_person_segment'):
        tags.append('缺少标准结构')
    if not result['names']:
        tags.append('无姓名候选')
    # These observed structures do not always fit an institution/connector label.
    if '省略称谓或介词复核' in checks['flags']:
        tags.append('称谓或介词结构')
    if '异常长度线索' in checks['flags']:
        tags.append('长连续姓名或异常长度')
    if '特殊形式复核' in checks['flags'] and re.search('[·•‧・()（）]',title):
        tags.append('中点或括号姓名形式')
    return tags
