补充原文证据复核 title-boundary-supplement-v1
本任务只读原始五字段，不提供已有模型答案或脚本结果。完整识别金融机构全称与姓名衔接，不能把受许可机构的首字误当人名末字，不能仅凭某一名字候选是审批句的前缀子串就认为是完整姓名。优先核对不含机构名的独立请示姓名、称谓、到任句和完整机构全称。除非原文另有独立姓名证据，不假设姓名和机构共用一个字符或原文漏写了重复字。
学衔或尊称如DR.（Doctor）、先生、女士、同志不属于姓名；姓名本体保持原标题原拼写和内部标点。仅姓名和人数真正矛盾保留conflict，不能排除则uncertain；姓名只从标题取，正文不能补入标题不存在字符。
输出格式：input_id,row_id,names,title_evidence,body_evidence,status,reason,adjudication_reason,model=gpt-6-luna,prompt_version=title-body-adjudication-v1,supplemental_prompt_version=title-boundary-supplement-v1。逐字证据与完整Name边界必须写清，不能按常见三字人名印象切断机构。
