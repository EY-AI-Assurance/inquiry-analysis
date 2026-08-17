# 任务

审阅服务端提供的财务披露文件，并生成 8–12 个最可能的 SEC 监管质询问题，目标数量约为 10 个。

## 输出要求

1. 问题应互不重复，优先覆盖最可能触发监管关注的事项。
2. `question` 应采用正式、直接的监管问询语气。
3. 每项 `evidence.sourceId` 必须逐字使用文档来源中已有的短编号，例如 `S001`；不得输出 location、页码描述或组合多个编号。
4. `evidence.observation` 说明文件中的具体触发事实；引用表格时优先使用实际列标题、项目名称和期间（例如“2025 年收入”），不要只写 A/B/C 等列字母。
5. `regulatoryBasis` 说明适用规则及其与该事实的关联；不得编造条款。
6. `answerDirections` 给出 2–4 个可核实、可准备材料的拟答复策略。
7. 全部内容使用中文，法规名称和必要的会计术语可以保留英文。
8. 只输出 JSON，不要使用 Markdown 代码块。
9. `priority` 只能是字符串 `high`、`medium` 或 `low`。
10. `evidence`、`regulatoryBasis` 和 `answerDirections` 必须都是非空数组，不得输出单个对象或单个字符串。
11. 不得因为案例模板中出现过某个行业、公司、分部或调整项就假设当前文件也存在。只有文档来源明确出现或文档本身应当提供但明显缺失的事项才可以提问。
12. 不得把“未提及某个与当前文件无关的事项”作为触发依据，例如文件没有保险负债内容时，不得生成保险负债重估问题。

## 输出前自检

- 顶层只能是一个包含 `questions` 的 JSON 对象。
- `questions` 数量必须为 8–12，优先正好生成 10 个。
- 每个问题必须同时包含 `question`、`category`、`priority`、`evidence`、`regulatoryBasis`、`answerDirections`。
- 所有 `sourceId` 必须从 document.sources 中逐字复制 `S001` 形式的短编号。
- 删除重复问题以及无法由文档事实支持的问题后再输出。
