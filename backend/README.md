# 独立 Python 业务后端

该目录不上传 Agent Run。它负责文件解析、读取 SEC Skill/Prompt、调用最小 Agent、校验 JSON 和把来源编号映射回页码、段落、工作表或 CSV 行号。

## 两种运行模式

- `ANALYSIS_MODE=mock`：无需阿里云配置，用于本地测试完整产品流程。
- `ANALYSIS_MODE=agentrun`：调用 `AGENTRUN_CHAT_COMPLETIONS_URL` 指向的本地或云端最小 Agent。

环境变量见 `.env.example`。网站代理和后端必须使用相同的 `BACKEND_APP_TOKEN`。

## 运行

```bash
conda activate inquiry-analysis
python app/main.py
```

`app/main.py` 会自动读取本目录的 `.env`，并以该文件作为本地开发的配置来源，避免
旧 Terminal 中残留的环境变量误连到已经删除的 Agent。线上部署不应携带 `.env`，而是
使用部署平台注入的环境变量。

默认地址为 `http://127.0.0.1:8001`。项目使用 8001 是为了避免与电脑上已有的旧开发服务占用 8000 端口发生冲突。

## Terminal 日志

后端默认以 `INFO` 级别输出以下关键阶段：

- 每次分析使用独立请求 ID，并从 `阶段 1/8` 到 `阶段 8/8` 连续标记当前进度；
- 收到上传请求、文件名、文件大小和分析模式；
- 解析器选择、Office 文件结构检查、内容提取、裁剪状态，以及解析后的来源块数量、字符数量、警告数量和耗时；
- Agent Run 输入组装、开始调用、输出解析、Schema 校验和来源引用核对；
- Agent Run endpoint（自动移除凭证和查询参数）、模型、消息数量、联网搜索开关和超时；
- Agent Run HTTP 状态、响应大小、请求耗时和 token 用量（endpoint 提供时）；
- 输出结构校验、来源映射、自动修复重试和最终问题摘要；
- 整个请求的完成状态和总耗时。

本地 `.env` 可启用完整模型消息：

```dotenv
LOG_LEVEL=INFO
AGENTRUN_LOG_OUTPUT=true
AGENTRUN_LOG_OUTPUT_MAX_CHARS=30000
```

完整输出会显示在 `Agent Run 原始输出 BEGIN/END` 标记之间。它可能包含从上传文件衍生的财务信息，因此共享或生产环境建议将
`AGENTRUN_LOG_OUTPUT=false`，仅保留阶段日志与问题摘要。需要查看解析后的来源位置时，可以临时使用 `LOG_LEVEL=DEBUG`。

## 修改审查规则

- SEC Skill：`skills/sec-review.md`
- 可变 system prompt：`prompts/system.md`
- 问题生成任务：`prompts/generate-questions.md`

修改后重启后端即可，不需要重新打包 Agent Run。
