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

- **铜钱法摇卦** — 模拟三枚铜钱投掷六次，依据传统规则生成本卦与变卦
- **完整卦象数据** — 六十四卦卦辞、象辞、爻辞，八卦符号与五行属性
- **AI 卦辞解读** — 接入任意 OpenAI 兼容 LLM（LM Studio / Ollama / DeepSeek / OpenAI 等），WebSocket 流式输出
- **3D 铜钱动画** — 逐爻翻转动画，逐行揭示卦象，沉浸式体验
- **六十四卦速查** — 可展开的全卦浏览网格，点击查看完整卦辞与爻辞

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
│   └── requirements.txt     # Python 依赖
├── frontend/
│   └── index.html           # 单页前端应用
├── tests/
│   └── test_divination.py   # 算法 & API & 数据完整性测试
├── dev-doc/
│   └── INTERFACE.md         # API 接口契约文档
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

> AI 卦辞解读依赖 LLM 服务，其余功能（摇卦、卦象查询）不受影响。

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

## 许可证

MIT
