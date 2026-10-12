# 项目总览

仅从标题提取任职资格批复明示姓名，保留52,146条记录、13原字段及格式，只追加提取姓名和姓名字数。[项目要求](../项目要求.md)为最高参考，要求超过99.8%、自查错误归零及最终人工检查，当前尚未最终验收。

## 当前状态 2026年10月13日

0.6.0/r61已通过本地提交9259fed及标签v0.6.0-r61封存为待验收工程版，见[封存说明](0.6.0封存说明.md)。封存时71标题78行未决，相对r56新增确定51标题53行，原确定输出不变；源码、资源、Word及Excel保留。

当前0.7.0/r63补齐完整机构与泛称银行的候选确认边界，保存末字任/的及单字称谓剥离的竞争解释。相对r62只有5条未决候选变化，确认状态及52,146行生产输出值变化0，沿用r62 Excel。全量46,760标题：姓名45,997/51,309行，无姓名689/756行，未决74/81行。44项测试及全量合同通过；r62的2条新增姓名、5条残缺转未决及原导出检查保留。

生产为script_only，不读取正文或AI、人工姓名答案。第11008行白玉娥李毅昕仍连写多人漏提。原122条人工记录保留，部分看过正文；119条确定人工答案中53条脚本完整匹配，66条待完成，另3条人工答案未决。本轮按用户安排独立GPT复核固定894标题：889确定匹配、5共同未决、确定分歧0，不要求用户逐条人工填完894条。全量确定输出风险扫描及连写正反例实验另存，不作为人工验收或真实准确率证明。旧AI参考确定差异0，35单渠道、37分歧及22,525缺参考仍保留。

## 成果与入口

- [0.7.0验证报告](../validation/0.7.0/验证报告.md)、[阶段统计](../validation/0.7.0/stage-report.json)、[边界变化](../validation/0.7.0/changes-r63.jsonl)及[894独立GPT复核](../validation/0.7.0/independent-review/summary.json)
- [r62待复核Excel](../outputs/0.7.0/任职资格批复汇总测试-0.7.0-r62纯脚本待复核版.xlsx)、[当前未决](../validation/0.7.0/remaining-unresolved.jsonl)及[连写多人研究](../validation/0.7.0/连写多人研究.md)
- [r61封存Excel](../outputs/0.6.0/任职资格批复汇总测试-0.6.0-r61纯脚本待复核版.xlsx)及[原阶段报告](../validation/0.6.0/验证报告.md)
- [原人工记录](../validation/0.6.0/human-review.jsonl)、[694无姓名检查](../validation/0.6.0/原694无姓名标题-人工盲审.csv)及[冻结200随机检查](../validation/0.6.0/随机200标题-人工盲审.csv)
- [下一步](PLAN.md)及[系统结构](ARCHITECTURE.md)

根目录Word有效规则同步当前版本，历史附录保留。没有push或外发。

## 复现

沿用Python、uv、本地.venv及uv.lock，无新增依赖。默认validation/0.7.0，导出outputs/0.7.0。

```sh
cd /Users/tristana/法询金融科技codex测试
uv run python -B scripts/full.py run
uv run python -B scripts/full.py finish
uv run python -B validation/0.7.0/evaluate_stage.py
uv run python -B -m unittest discover -s tests
uv run python -B validation/0.7.0/independent-review/evaluate_blind.py
uv run python -B validation/0.7.0/independent-review/scan_confirmed.py
uv run python -B validation/0.7.0/concatenated_experiment.py
```

run保存实际源码和资源，首轮及阶段差异比较冻结r61，后续逐轮比较前轮；finish/export复用旧参考，只用脚本写生产单元格。人工检查入口沿用0.6.0文件，不重抽名单、不覆盖原阶段产物。
