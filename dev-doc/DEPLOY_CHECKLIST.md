# 部署验证清单

静态测试（`pytest tests/`）只能断言 CSP 字符串与前端结构，**无法**验证真实浏览器是否按规范执行 CSP。部署到 HuggingFace Spaces（或任何新环境）后，必须人工过一遍下列项。

## 前置

- Spaces 状态 Running
- Secrets 已配置：`LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` / **`ALLOWED_ORIGINS=https://saintzealot-i-ching.hf.space`**
- 打开 `https://saintzealot-i-ching.hf.space/`（或自部署地址）

> **`ALLOWED_ORIGINS` 若缺失或写错**：WebSocket 握手会被后端直接 close 1008（policy violation），浏览器 Console 报 `WebSocket closed before connection established`，AI 解读完全不工作——属"显式故障"，不会悄悄挂。本地开发已内置 `localhost:8000` / `localhost:8765` 默认域名，仅生产需配。

## 核心功能验证

### 1. 起卦 → AI 解读（正路径）

| 浏览器 | DevTools Console 无 CSP violation | `/ws/interpret` 状态 `101 Switching Protocols` | AI 解读流式打字正常 |
|---|---|---|---|
| Chrome / Edge |   |   |   |
| Firefox |   |   |   |
| Safari（桌面） |   |   |   |
| Safari（iOS） |   |   |   |

**关键红线 1：** Console 出现 `Refused to connect to 'wss://...' because it violates the following Content Security Policy directive: "connect-src 'self'"` → 说明该浏览器对 CSP3 `'self'` 覆盖同源 WS 的实现有问题，需回退 CSP（见"回退预案"）。

**关键红线 2：** Console 出现 `WebSocket is closed before the connection is established` + Network 面板 `/ws/interpret` 状态 `403 Forbidden` 或无状态码 → 说明 `ALLOWED_ORIGINS` Secret 未配或值写错。HF Space Settings → Variables and secrets 里改，保存会自动重启。

### 2. 起卦中途切视图（race 防护）

| 场景 | 预期 |
|---|---|
| 起卦第 3 爻时点右上角时钟 → 选历史条目 | 立即显示历史，无铜钱残余动画 |
| 起卦第 3 爻时按返回键 | 回首页，所有 shake 相关 class 已清 |
| 起卦完成 AI 流式解读时点历史 | 历史覆盖结果，AI 流静默终止（无 error toast） |

### 3. 安全头人工核对

DevTools → Network → 选 `/`（或任意 API）响应：

- [ ] `Content-Security-Policy` 含 `connect-src 'self'`（**不含** `ws:` 或 `wss:`）
- [ ] `X-Frame-Options: DENY`
- [ ] `X-Content-Type-Options: nosniff`
- [ ] `Referrer-Policy` 含 `strict-origin`
- [ ] `Permissions-Policy` 禁 camera/microphone/geolocation

## 回退预案

### 如果 Safari < 15.4 或某冷门浏览器 block 了同源 WS

改 `backend/main.py` 与 `frontend/index.html` 的 CSP，把 `connect-src 'self'` 改为：

```
connect-src 'self' wss://saintzealot-i-ching.hf.space
```

（本地 dev 另加 `ws://localhost:8000`，用 env var 注入或维护 dev/prod 两份）

**不要**改回 `ws: wss:` scheme-wide 通配——那会重新打开任意域 WS 外泄的攻击面。

### 如果 Spaces 冷启失败

- 查 Spaces Logs 里的 uvicorn 启动输出
- 确认 Dockerfile 里的 `CMD` 能对上 `backend.main:app`
- Secrets 缺失 → AI 解读 fallback 到后端象辞，但不应导致启动失败

## 一次完整验收跑通后

在 PR 描述或 commit message 里记一笔"已过 DEPLOY_CHECKLIST（Chrome / Firefox / Safari 桌面）"。
