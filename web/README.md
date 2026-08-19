# React 网站与安全代理

React 只负责文件选择、市场选择和结果展示。同源 `/api/analyze` 服务端代理把文件转发到独立 FastAPI 后端，浏览器不会接触后端令牌或 Agent Run 凭证。

## 本地运行

`.env.local`：

```dotenv
BACKEND_BASE_URL=http://127.0.0.1:8001
BACKEND_APP_TOKEN=local-development-token
BACKEND_ANALYSIS_TIMEOUT_SECONDS=660
PUBLIC_SITE_URL=http://localhost:3001
```

运行：

```bash
conda activate inquiry-analysis
../scripts/start-web.sh
```

访问 `http://localhost:3001/`。SEC 当前可选；联交所可见但保持禁用，直到独立后端加入 HKEX Skill。

## 检查

```bash
npm test
npm run lint
```
