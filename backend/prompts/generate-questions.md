# 任务

审阅服务端提供的财务披露文件，并生成 8–12 个最可能的 SEC 监管质询问题，目标数量约为 10 个，如果数量达不到8个不需要强行提问。

## 输出要求

1. 问题应互不重复，优先覆盖最可能触发监管关注的事项。
2. `question` 应采用正式、直接的监管问询语气。
3. 每项 `evidence.sourceId` 必须逐字使用文档来源中已有的短编号，例如 `S001`；不得输出 location、页码描述或组合多个编号。
4. `evidence.references` 必须是数组，并逐字复制该 `sourceId` 对应 content 中与触发事实直接相关的精确锚点。Excel/CSV 使用 `A13` 等单元格坐标，Word 段落使用 `P5`，Word 表格使用 `T1:R2:C3`；不要填写行范围或 location。来源 content 没有锚点时使用空数组，不得猜测。
5. `evidence.observation` 说明文件中的具体触发事实；引用表格时优先使用实际列标题、项目名称和期间（例如“2025 年收入”），不要只写 A/B/C 等列字母。
6. `regulatoryBasis` 说明适用规则及其与该事实的关联；不得编造条款。
7. `answerDirections` 给出 2–4 个可核实、可准备材料的拟答复策略。
8. 全部内容使用中文，法规名称和必要的会计术语可以保留英文。
9. 只输出 JSON，不要使用 Markdown 代码块。
10. `priority` 只能是字符串 `high`、`medium` 或 `low`。
11. `evidence`、`evidence.references`、`regulatoryBasis` 和 `answerDirections` 必须都是数组；除允许为空的 `references` 外，其余数组不得为空。
12. 不得因为案例模板中出现过某个行业、公司、分部或调整项就假设当前文件也存在。只有文档来源明确出现或文档本身应当提供但明显缺失的事项才可以提问。
13. 不得把“未提及某个与当前文件无关的事项”作为触发依据，例如文件没有保险负债内容时，不得生成保险负债重估问题。

## 输出前自检

- 顶层只能是一个包含 `questions` 的 JSON 对象。
- `questions` 数量必须为 8–12，优先正好生成 10 个。
- 每个问题必须同时包含 `question`、`category`、`priority`、`evidence`、`regulatoryBasis`、`answerDirections`。
- 所有 `sourceId` 必须从 document.sources 中逐字复制 `S001` 形式的短编号。
- 所有 `references` 必须能在对应 source 的 content 中逐字找到；有精确锚点的表格或段落不得省略。
- 删除重复问题以及无法由文档事实支持的问题后再输出。
