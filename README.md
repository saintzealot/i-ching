---
title: I-Ching 周易算卦
emoji: ☯️
colorFrom: indigo
colorTo: yellow
sdk: docker
app_port: 7860
---

# I-Ching · 周易算卦

基于传统铜钱法的周易六十四卦占卜系统，支持 AI 卦辞解读。

## 功能特色

- **墨玉鎏金视觉** — 深空星幕 + 悬浮八卦（凸起铸造、顺时针流光）+ 鎏金铜钱（`乾亨元利` 凸起铸造字、铜锈 patina、天圆地方）
- **干支编年** — 顶部显示「X 月 · X 日」干支纪月纪日（节气年切换，立春为界；月柱走五虎遁），替代公历数字与整体气质对齐
- **铜钱法摇卦** — 模拟三枚铜钱投掷六次，依据传统规则生成本卦与变卦；摇卦位置有轻微扰动，视觉更真实
- **自动 / 手摇 双模式** — 底部分段按钮切换；手摇模式每爻都要一次独立手势（摇手机或点击铜钱），迟滞双阈值（`SHAKE_HI=18 / SHAKE_LO=6` m/s²）+ 爻间强制静候 300ms 防一次晃动串爆六爻；每爻"握 → 摇 → 落"三段式视觉（摇动最少 600ms + 屏息 1000ms，每爻约 2.6s）；iOS 首次需授权 DeviceMotion，Android / iOS 旧版直接可摇，无传感器设备 2s 后自动提示点击 fallback
- **爻位进度置顶 + 卦象 Progressive** — 顶部实时显示「第 X 爻 · N/6」与 6 段 dash 进度条；中部小卦象从底向上逐爻生长，动爻自带鎏金光晕；底部「字 · 花 · 花」实时显示本爻铜钱正反面
- **移动端优先** — 安全区适配、拇指热区 CTA、触感震动反馈（Android）、右滑关闭抽屉、防 iOS 键盘放大
- **完整卦象数据** — 六十四卦卦辞、象辞、爻辞，八卦符号与五行属性
- **AI 流式解读** — 接入任意 OpenAI 兼容 LLM，WebSocket 流式推送，打字机效果；Markdown 经本地化 `marked` + `DOMPurify` 双层清洗（排版标签白名单、外链仅 http(s)），外链点击有二次确认 modal；失败/中断时显示"重新解读"按钮，只有收到 done 信号的内容才写入历史
- **纵深防御** — CSP 主经 FastAPI 响应头下发（`frame-ancestors 'none'` 真正防嵌入）+ meta 兜底；`script-src` 已去 `unsafe-inline`（inline 脚本与事件全部外部化到 `assets/app.js`，用事件委托路由）；`connect-src 'self'` 依赖 CSP3 覆盖同源 WS，不开 scheme-wide 通配避免外泄；vendor 脚本本地化消除 CDN 供应链风险；双序号防护（`_interpSeq` 防 stale WS、`_divineSeq` 防起卦动画中途切视图导致的 DOM 竞态）；响应头附加 `X-Frame-Options: DENY` / `X-Content-Type-Options: nosniff` / `Referrer-Policy` / `Permissions-Policy`
- **六爻仪式** — 一屏一事：起卦→逐爻落定→结果展开，沉浸式进度与呼吸动效
- **卦象历史** — 近 30 次卦象 localStorage 存储，右侧抽屉回溯
- **六十四卦速查** — 可展开的全卦浏览网格，点击查看完整卦辞与爻辞
- **频率限制** — 按 IP 限制 AI 解读请求频率，防止滥用

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python · FastAPI · Uvicorn · OpenAI SDK |
| 前端 | 原生 HTML / CSS / JS（单文件，无框架） |
| AI | 任意 OpenAI 兼容 API |

## 项目结构

```
i-ching/
├── backend/
│   ├── main.py              # FastAPI 应用 & API 路由 & WebSocket
│   ├── divination.py        # 铜钱法算卦核心算法
│   ├── hexagrams_data.py    # 六十四卦 & 八卦完整数据
│   ├── requirements.txt     # Python 依赖（直接依赖 + 版本约束，生产安装源）
│   └── requirements.lock    # 锁文件（含 sha256，仅本地复现 + 审计基线，不进生产）
├── frontend/
│   ├── index.html              # 单页前端应用（墨玉鎏金视觉方向）
│   └── assets/
│       ├── iching-core.js      # 纯函数模块（爻值/布局/拼音/流状态分类，支持 Node 单测）
│       ├── app.js              # 主应用脚本（从 index.html 外部化，便于 CSP 去 unsafe-inline）
│       └── vendor/             # 本地化的第三方库（marked、DOMPurify）
├── tests/
│   ├── test_divination.py      # 后端算法 & API & 数据完整性
│   ├── test_backend_headers.py # 安全响应头（CSP / XFO / nosniff 等）
│   ├── test_frontend_structure.py  # 前端 HTML/CSS 结构性静态测试
│   └── test_frontend_js.py     # 前端 JS 纯函数（子进程调 node）
├── dev-doc/
│   └── INTERFACE.md         # API 接口契约文档
├── Dockerfile               # Docker 部署配置
├── start.sh                 # 一键安装 & 启动脚本
├── .env.example             # 环境变量示例
└── README.md
```

## 快速开始

### 前置要求

- Python 3.10+
- （可选）[uv](https://github.com/astral-sh/uv) — 加速依赖安装

### 一键启动

```bash
./start.sh
```

首次运行会自动创建虚拟环境、安装依赖，并交互式配置 LLM 连接信息（保存到 `.env`）。

### 手动启动

```bash
# 1. 创建并激活虚拟环境
uv venv .venv        # 或 python3 -m venv .venv
source .venv/bin/activate

# 2. 安装依赖
uv pip install -r backend/requirements.txt   # 或 pip install -r backend/requirements.txt

# 可选：精确复现本地开发环境（审计基线，HF 部署走 requirements.txt 自动跟安全 patch）
# uv pip sync backend/requirements.lock
# 或 pip install --require-hashes -r backend/requirements.lock

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env 填入你的 LLM 服务信息

# 4. 启动
set -a && source .env && set +a
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

启动后访问 **http://localhost:8000**。

### 环境变量

| 变量 | 说明 | 默认值 |
|---|---|---|
| `LLM_BASE_URL` | LLM API 地址 | `http://localhost:1234/v1` |
| `LLM_API_KEY` | API 密钥 | `lm-studio` |
| `LLM_MODEL` | 模型名称 | `google/gemma-4-26b-a4b` |
| `PORT` | 服务端口 | `8000` |
| `ALLOWED_ORIGINS` | WS 握手允许的额外 Origin（逗号分隔），生产部署必配 | 空 |

> AI 卦辞解读依赖 LLM 服务，其余功能（摇卦、卦象查询）不受影响。
>
> **生产部署必配 `ALLOWED_ORIGINS`**：WebSocket 不走 CORS preflight，后端在握手前校验 `Origin` 防止 CSWSH（第三方页面消费你的 LLM 配额）。本地开发已内置 `localhost:8000` / `localhost:8765` 默认值；部署到 HF Spaces 时在 Secret 里加 `ALLOWED_ORIGINS=https://你的用户名-space名.hf.space` 即可。

## Docker 部署

```bash
docker build -t i-ching .
docker run -p 7860:7860 \
  -e LLM_BASE_URL=你的API地址 \
  -e LLM_API_KEY=你的密钥 \
  -e LLM_MODEL=模型名称 \
  i-ching
```

> **推到公网访问时**需额外传 `-e ALLOWED_ORIGINS=https://你的域名`——浏览器 Origin 不在白名单会被 close 1008，AI 解读不工作。本地 `docker run -p 7860:7860 ...` 访问 `localhost:7860` 已在默认白名单，无需配。

项目已部署到 HuggingFace Spaces，支持 Docker SDK 自动构建。部署后需按 [dev-doc/DEPLOY_CHECKLIST.md](dev-doc/DEPLOY_CHECKLIST.md) 做多浏览器实地验证（字符串级 CSP 测试无法替代真实浏览器执行）。

## API 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/api/divine` | 算卦（可传 `question` 字段） |
| `GET` | `/api/hexagrams` | 获取六十四卦列表 |
| `GET` | `/api/hexagrams/{number}` | 获取单卦详情（1-64） |
| `WebSocket` | `/ws/interpret` | AI 流式解读卦象 |

详细接口契约见 [dev-doc/INTERFACE.md](dev-doc/INTERFACE.md)。

## 算卦原理

采用传统**铜钱法**：每次投掷三枚铜钱，字面（有字）为 3，花面（无字）为 2，三币之和决定爻的阴阳：

| 和值 | 爻 | 性质 |
|---|---|---|
| 6 | ⚋ 老阴 | 变爻（阴→阳） |
| 7 | ⚊ 少阳 | 不变 |
| 8 | ⚋ 少阴 | 不变 |
| 9 | ⚊ 老阳 | 变爻（阳→阴） |

投掷六次，由下而上排列六爻，下三爻为下卦，上三爻为上卦，组合成六十四卦之一。若有变爻（6 或 9），则同时生成变卦。

## 测试

```bash
source .venv/bin/activate
pytest tests/ -v
```

测试分三层：

- **后端（`test_divination.py`）** — 算法、API、数据完整性
- **前端结构（`test_frontend_structure.py`）** — DOM 锚点、关键文案、meta、XSS 配置、安全反模式、函数签名、动画 keyframes、响应式断点
- **前端纯函数（`test_frontend_js.py`）** — 通过 `node` 子进程加载 `iching-core.js`，测试爻值换变、铜钱布局、拼音映射等纯函数；若本机没有 `node` 会 skip

## 调试工具

**滚动诊断 HUD** —— 给 URL 追加 `?debug=scroll` 可在右下角挂出实时诊断面板：视口单位（vh/svh/dvh）、scrollHeight、overflow/overscroll-behavior 计算值、滚动事件日志环，以及一键 A/B 切换 `overscroll-behavior` / `overflow-x` / `min-height` 的按钮。`[copy]` 按钮把快照导出成 JSON 便于排查。正常用户 URL 不带参数则零影响（脚本不下载、不执行）。

## 致谢

本项目由 [Claude Code](https://claude.ai/claude-code)、[OpenAI Codex](https://openai.com/codex) 与 [OpenCode](https://opencode.ai) 协同完成，从架构设计、代码实现到部署上线，全程由 AI 辅助开发。

## 许可证

MIT
