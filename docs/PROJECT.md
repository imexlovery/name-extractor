# name-extractor · generic-v0.1

更新：2026年10月15日。本分支是通用规则实验；r65 对照保存在 `codex/r65-frozen-20261015`，冻结提交 `9f1a0e2`。原项目要求仍是最高参考，见 [项目要求](项目要求.md)。

当前仅从标题提取姓名，不读取正文、参考姓名或人工答案。移除 12,277 条学习机构片段、44 个内置具体机构锚点、农发行/进出口行两个具体简称，以及 7 条精确标题弃权例外；保留 35 个地名、3 个机构类型锚点、机构后缀、岗位、人数和名单结构规则。移除的内置机构清单仅供检查，不参与运行。

固定 v3 精简为一个 7.50 MB JSONL，保存全部 52,146 原始行的行号、标题、输入标识、状态和姓名，另保留 35 行原始信息冲突标记；完整原文证据与旧版本保存在归档。新入口逐行复现 r65 的全部 v3 分类，得到 52,067 行一致、76 行脚本未决、3 行参考未决，一致率 99.8485%。

generic-v0.1 当前 v3 一致率 **83.2068%**，一致 43,389 行；脚本未决 8,684 行，确定输出分歧 73 行，参考未决 3 行。31 项测试通过；全量输出格式检查失败为 0。实验 Excel 保留 52,146 行和 13 个原字段的值、类型、格式，仅追加 N/O 两列。详见 [冻结实验指标](generic-v0.1-baseline.json) 与 [精简验证记录](架构精简验证.json)。

同时记录 `v3_reference_agreement` 和 `unseen_data_accuracy`。后者目前为 `null`，没有独立新数据结果。v3 已用于历史规则及词库优化，是固定回归集；参考一致率不代表真实准确率。当前实验未达到原项目的最终交付要求，73 行确定分歧、未决与人工验收缺口仍然存在。

## 运行

沿用 Python/uv、项目本地 `.venv` 和 `uv.lock`，依赖未增加。

```sh
uv run python -B evaluate.py
uv run python -B -m unittest discover -s tests
uv run python -B evaluate.py --check-source --export results/generic-v0.1/source-generic-v0.1待复核.xlsx
```

快速评测使用固定参考中冻结的标题，按标题去重执行规则，再按原始行比较。结果覆盖当前版本的 `results/<版本>/summary.json`、`errors.jsonl` 和 `report.md`；错误记录包含原标题、脚本候选、参考、触发规则和风险。快速提取及比较本次约 1.909 秒，读取 Excel、导出和写报告另计。

获得独立确认的新标题标签后，可用同一 JSONL 格式（`row/title/status/names`）执行：

```sh
uv run python -B evaluate.py --unseen-reference 新标题参考.jsonl
```

新样本必须从未参与规则优化和机构词库学习，尤其包含陌生机构；标签需独立确认且姓名有标题依据。工具拒绝与 v3 完全相同的标题和未决标签，但这种检查不能证明完整的历史独立性。单元测试中的合成标题不计入未见数据准确率。

## 历史恢复

历史压缩包为 `.archives/r65-20261015/history.tar.gz`，约 654.85 MB；完整核对 12,033 个文件、约 2.95 GB 原内容。包含全部 Git 跟踪材料和 `.local` 历史，完整 v3、AI 审核、原始材料、r65 源码/词库及最终报告均保留；环境和缓存不打包。

在当前实验改动已保存后，`git switch codex/r65-frozen-20261015` 可恢复旧目录与 `scripts/full.py`、`scripts/acceptance.py` 命令。归档可以用 `tar -xzf .archives/r65-20261015/history.tar.gz -C /另一个空目录` 单独恢复。归档不纳入新分支的 Git 文件；冻结分支仍保存全部已跟踪证据。Git 历史未重写，也没有 push。

[规则方案](通用规则方案.md) · [结构](ARCHITECTURE.md) · [下一步](PLAN.md) · [决策](DECISIONS.md) · [参考来源](reference_v3.json)
