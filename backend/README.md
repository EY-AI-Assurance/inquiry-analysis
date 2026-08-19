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

## 修改审查规则

- SEC Skill：`skills/sec-review.md`
- 可变 system prompt：`prompts/system.md`
- 问题生成任务：`prompts/generate-questions.md`

修改后重启后端即可，不需要重新打包 Agent Run。
