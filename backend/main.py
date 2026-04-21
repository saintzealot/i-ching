"""
I-Ching FastAPI 后端应用

提供以下接口：
- POST /api/divine     — 算卦
- GET  /api/hexagrams   — 获取64卦列表
- GET  /api/hexagrams/{number} — 获取单卦详情
"""

import os
import json
import time
import hashlib
from collections import defaultdict
from fastapi import FastAPI, HTTPException, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from openai import AsyncOpenAI

from .divination import perform_divination
from .hexagrams_data import HEXAGRAMS, TRIGRAMS, get_hexagram_by_number

# LLM 客户端（支持任何 OpenAI 兼容 API，通过环境变量配置）
lm_client = AsyncOpenAI(
    base_url=os.environ.get("LLM_BASE_URL", "http://localhost:1234/v1"),
    api_key=os.environ.get("LLM_API_KEY", "lm-studio"),
)

# 创建 FastAPI 应用
app = FastAPI(
    title="I-Ching API",
    description="基于铜钱法的周易六十四卦占卜系统",
    version="1.0.0",
)

# 配置 CORS，允许前端跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 开发环境允许所有来源
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# 安全响应头 — 纵深防御
#
# 为什么走 HTTP header 而非 <meta>：
#   1. frame-ancestors / report-uri / sandbox 在 <meta> CSP 中被浏览器忽略（W3C CSP3 §6.1）
#   2. HTTP header 的优先级覆盖 meta，方便统一维护
# ============================================================

_CSP = (
    "default-src 'self'; "
    "script-src 'self'; "  # 无 unsafe-inline，inline JS 已外部化
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "  # inline style 暂保留
    "font-src 'self' https://fonts.gstatic.com; "
    "img-src 'self' data:; "
    # connect-src 选型：纯 'self'，依赖 CSP3 §6.7.2.8 明文覆盖同源 ws:/wss:
    #   http → ws（同 host/port）、https → wss（同 host/port）都是规范内匹配
    #   浏览器基线：Chrome 58+（2017）/ Firefox 50+（2016）/ Safari 15.4+（2022）
    # 反对 scheme-wide 'ws: wss:'：后者允许任意域 WS，XSS 旁路后可外泄数据
    # 反对显式 'wss://<host>'：硬编码 host 伤可移植性（HF Space 域迁移即断）、
    #   本地 dev 还要额外允许 ws://localhost，动态生成则新增 Host 伪造攻击面
    # 部署后必须在 dev-doc/DEPLOY_CHECKLIST.md 列出的多浏览器里实地验证
    "connect-src 'self'; "
    "frame-ancestors 'none'; "  # 只能在 header 里生效
    "base-uri 'self'; "
    "form-action 'self'"
)


@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = _CSP
    response.headers["X-Frame-Options"] = "DENY"  # 旧浏览器兜底
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return response


# ============================================================
# 请求/响应模型
# ============================================================


class DivineRequest(BaseModel):
    """算卦请求"""

    question: str = ""


# ============================================================
# API 接口
# ============================================================


@app.post("/api/divine")
async def divine(request: DivineRequest):
    """
    算卦接口
    模拟铜钱法摇卦，返回本卦、变卦、爻辞等完整信息
    """
    result = perform_divination(question=request.question)
    return result


@app.get("/api/hexagrams")
async def get_hexagrams():
    """
    获取64卦列表
    返回每卦的编号、名称、符号和卦辞
    """
    return [
        {
            "number": h["number"],
            "name": h["name"],
            "symbol": h["symbol"],
            "judgment": h["judgment"],
        }
        for h in HEXAGRAMS
    ]


@app.get("/api/hexagrams/{number}")
async def get_hexagram(number: int):
    """
    获取单卦详情
    返回指定编号卦的完整信息
    """
    if number < 1 or number > 64:
        raise HTTPException(status_code=404, detail="卦序号必须在1-64之间")

    hexagram = get_hexagram_by_number(number)
    if hexagram is None:
        raise HTTPException(status_code=404, detail="未找到该卦")

    # 添加上下卦的符号信息
    upper_symbol = TRIGRAMS[hexagram["upper_trigram"]]["symbol"]
    lower_symbol = TRIGRAMS[hexagram["lower_trigram"]]["symbol"]

    return {
        **hexagram,
        "trigram_symbol": f"{upper_symbol}{lower_symbol}",
        "upper_trigram_info": TRIGRAMS[hexagram["upper_trigram"]],
        "lower_trigram_info": TRIGRAMS[hexagram["lower_trigram"]],
    }


# ============================================================
# AI 卦辞解读（WebSocket 长连接）
# ============================================================


def build_interpret_prompt(req: dict) -> str:
    """根据卦象数据构建解读 prompt"""
    changing_desc = ""
    changing_lines = req.get("changing_lines", [])
    lines_text = req.get("lines_text", [])
    if changing_lines:
        changing_texts = [
            lines_text[p - 1] for p in changing_lines if 1 <= p <= len(lines_text)
        ]
        changing_desc = f"\n动爻：{', '.join(changing_texts)}"
        if req.get("changed_hexagram_name"):
            changing_desc += f"\n变卦：{req['changed_hexagram_name']}"

    question = (req.get("question") or "").strip()
    name = req.get("hexagram_name", "")
    number = req.get("hexagram_number", 0)
    judgment = req.get("judgment", "")
    image = req.get("image", "")

    if question:
        return f"""你是一位精通周易的国学大师。求问者带着具体的问题来求卦，你必须紧密围绕这个问题来解读卦象。

【求问者的问题】：{question}

【所得卦象】：第{number}卦 · {name}
卦辞：{judgment}
象辞：{image}{changing_desc}

请用通俗易懂的现代中文解读此卦，要求：
1. 开头点明此卦与「{question}」这个问题的关联
2. 用卦辞和爻辞的含义，直接回应求问者关心的事情
3. 给出与问题相关的具体行动建议
4. 语气温和有智慧，像一位长者在指点迷津
重点：你的每一段分析都要紧扣求问者的问题「{question}」，不要泛泛而谈。
控制在200-350字以内。
格式要求：直接输出正文，不要加标题。用**加粗**标注关键词，段落间用换行分隔。"""
    else:
        return f"""你是一位精通周易的国学大师，求问者未提出具体问题，请对所得卦象做综合运势解读。

【所得卦象】：第{number}卦 · {name}
卦辞：{judgment}
象辞：{image}{changing_desc}

请用通俗易懂的现代中文解读此卦，要求：
1. 简要解释卦象的核心含义
2. 从事业、人际、决策等方面给出综合提示
3. 给出行动建议
4. 语气温和有智慧，像一位长者在指点迷津
控制在200-350字以内。
格式要求：直接输出正文，不要加标题。用**加粗**标注关键词，段落间用换行分隔。"""


# ============================================================
# WebSocket 安全：Origin 白名单 + payload 上限
#
# 为什么必须：浏览器对 WebSocket 不走 CORS preflight，任何第三方页面
# （例如 evil.com）都可以从访客浏览器发起 wss:// 连接，把本 Space 的 LLM
# key 当免费 prompt 代理消费（CSWSH 攻击）。Origin header 由浏览器根据
# "当前页面源"自动设置，JS 无法伪造——因此在 accept() 前校验 Origin
# 是防御 CSWSH 的行业标准做法。
#
# 默认含 localhost 开发域以便 clone → uvicorn 即刻可跑。生产通过
# HF Spaces Secret 追加：ALLOWED_ORIGINS=https://saintzealot-i-ching.hf.space
# 默认内置 localhost 不引入风险——公网用户无法冒充 localhost（它只对
# 受害者自己的机器有效，那时候已经输到家了）。
# ============================================================

DEFAULT_ALLOWED_ORIGINS = [
    # 常用开发端口
    "http://localhost:8765",
    "http://127.0.0.1:8765",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    # Docker / HF Spaces 约定端口（Dockerfile: EXPOSE 7860；README: app_port: 7860）
    # 漏了会让 `docker run -p 7860:7860 ...` 本地测 WS 握手直接被拒——见 2026-04-19
    # Codex 第八轮 F2 修复记录
    "http://localhost:7860",
    "http://127.0.0.1:7860",
]
_extra_origins = os.environ.get("ALLOWED_ORIGINS", "")
ALLOWED_ORIGINS: set[str] = set(DEFAULT_ALLOWED_ORIGINS) | {
    o.strip() for o in _extra_origins.split(",") if o.strip()
}

# 单条 WS 消息 payload 上限：合法的 interpret 请求最多 2 KB
# （question ≤ 500 字 UTF-8 + hexagram/lines 元数据约 1 KB）；4 KB 给富余。
WS_MAX_PAYLOAD_BYTES = 4096


# ============================================================
# 简单频率限制（按 IP，5 次/分钟）
# ============================================================

RATE_LIMIT = 5
RATE_WINDOW = 60  # 秒
_rate_records: dict[str, list[float]] = defaultdict(list)


def _check_rate_limit(ip: str) -> bool:
    """检查 IP 是否超出频率限制，返回 True 表示允许"""
    now = time.time()
    records = _rate_records[ip]
    # 清理过期记录
    _rate_records[ip] = [t for t in records if now - t < RATE_WINDOW]
    if len(_rate_records[ip]) >= RATE_LIMIT:
        return False
    _rate_records[ip].append(now)
    return True


@app.websocket("/ws/interpret")
async def ws_interpret(websocket: WebSocket):
    """WebSocket 端点：流式推送 AI 卦辞解读"""
    # Origin 校验必须在 accept() 之前——否则握手已完成，close 就是事后关门。
    # 严格模式：无 Origin header 也拒（浏览器必带，无 Origin 只可能是服务端脚本伪造）。
    # 关闭码 1008 = policy violation。
    origin = websocket.headers.get("origin")
    if not origin or origin not in ALLOWED_ORIGINS:
        await websocket.close(code=1008)
        return

    await websocket.accept()

    # 频率限制检查
    client_ip = websocket.client.host if websocket.client else "unknown"
    if not _check_rate_limit(client_ip):
        await websocket.send_json({"type": "error", "text": "请求过于频繁，请稍后再试"})
        await websocket.close()
        return

    try:
        raw = await websocket.receive_text()
        # payload 大小检查：防止构造超大 prompt 消耗 LLM 配额
        if len(raw.encode("utf-8")) > WS_MAX_PAYLOAD_BYTES:
            await websocket.send_json({"type": "error", "text": "请求过大"})
            await websocket.close(code=1009)  # 1009 = message too big
            return
        request = json.loads(raw)
        prompt = build_interpret_prompt(request)

        # 通知前端进入思考阶段
        await websocket.send_json({"type": "thinking"})

        create_kwargs = dict(
            model=os.environ.get("LLM_MODEL", "google/gemma-4-26b-a4b"),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4096,
            temperature=0.7,
            stream=True,
        )

        try:
            stream = await lm_client.chat.completions.create(
                **create_kwargs,
                extra_body={"reasoning_split": True},
            )
        except Exception:
            # 回退：不带 reasoning_split，兼容不支持该参数的 LLM 服务
            stream = await lm_client.chat.completions.create(**create_kwargs)

        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta.content:
                await websocket.send_json({"type": "content", "text": delta.content})

        await websocket.send_json({"type": "done"})
    except Exception as e:
        import traceback

        traceback.print_exc()
        try:
            await websocket.send_json({"type": "error", "text": str(e)})
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


# ============================================================
# 静态文件服务（serve frontend/ 目录）
#
# 缓存策略：index.html 走 no-cache，每次必须重新验证（ETag 命中返回 304）；
# 带 ?v= 版本号的 assets 走 1 年 immutable 缓存（URL 变化即新资源）；
# 其余 assets 1 小时兜底。版本号 ASSET_VERSION 由资产文件内容 sha256 自动计算，
# 通过占位符 __ASSET_VERSION__ 在启动时渲染进 index.html，无需手动 bump。
# ============================================================

# 获取项目根目录（backend 的上级目录）
_backend_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_backend_dir)
_frontend_dir = os.path.join(_project_root, "frontend")

# 纳入 hash 计算的资产文件 —— 任一文件内容变则 ASSET_VERSION 变
_ASSET_FILES = (
    "assets/app.js",
    "assets/iching-core.js",
    "assets/vendor/marked-15.0.12.min.js",
    "assets/vendor/dompurify-3.1.5.min.js",
    # scroll-debug.js 故意不在此列表：它是 ?debug=scroll 才注入的调试工具，
    # 改动它不应该 bump 生产版本戳、让正常用户缓存穿透。
    # 调试脚本的 cache bust 由 app.js bootstrap 里的 `?t=${Date.now()}` 独立处理。
)


def _compute_asset_version() -> str:
    """拼接所有 _ASSET_FILES 的字节，sha256 前 10 位作为版本标识。
    缺失文件静默跳过（dev 环境部分文件可能尚未生成）。"""
    hasher = hashlib.sha256()
    for rel in _ASSET_FILES:
        path = os.path.join(_frontend_dir, rel)
        try:
            with open(path, "rb") as f:
                hasher.update(f.read())
        except FileNotFoundError:
            continue
    return hasher.hexdigest()[:10]


def _load_index_bytes(version: str) -> bytes:
    """读 index.html，替换 __ASSET_VERSION__ 占位符为真实哈希。
    启动时一次性执行，结果缓存在模块级变量里，后续请求零 I/O。"""
    with open(os.path.join(_frontend_dir, "index.html"), "rb") as f:
        html = f.read()
    return html.replace(b"__ASSET_VERSION__", version.encode("ascii"))


if os.path.isdir(_frontend_dir):
    ASSET_VERSION = _compute_asset_version()
    _INDEX_BYTES = _load_index_bytes(ASSET_VERSION)
    # ETag 从渲染后的 HTML 字节派生，而非 asset-only ASSET_VERSION：
    # index.html 变 → _INDEX_BYTES 变；asset 变 → 占位符替换结果变 → _INDEX_BYTES 变。
    # "HTML 响应内容"和"ETag"严格一一对应，符合 RFC 7232。
    # 若用 ASSET_VERSION 直接做 ETag，仅改 HTML/CSS 但 asset 不变时 ETag 不变，
    # 浏览器会持续拿到旧 HTML（Codex 第十轮 F1）。
    _INDEX_HASH = hashlib.sha256(_INDEX_BYTES).hexdigest()[:10]
    _INDEX_ETAG = f'"{_INDEX_HASH}"'
else:
    ASSET_VERSION = "dev"
    _INDEX_BYTES = b""
    _INDEX_HASH = "dev"
    _INDEX_ETAG = '"dev"'


@app.middleware("http")
async def add_cache_headers(request: Request, call_next):
    """按路径分流 Cache-Control：
    - /, *.html → no-cache（必须重验证，配合 ETag 走 304）
    - /assets/*?v=… → 1 年 immutable（URL 随版本变，永不过期）
    - /assets/* 无 ?v → 1 小时兜底
    API 路由不设置，交由调用方或默认行为处理。"""
    response = await call_next(request)
    path = request.url.path
    if path == "/" or path.endswith(".html"):
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
    elif path.startswith("/assets/"):
        query = request.url.query or ""
        if "v=" in query:
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            response.headers["Cache-Control"] = "public, max-age=3600"
    return response


@app.api_route("/", methods=["GET", "HEAD"])
async def serve_index(request: Request):
    """返回渲染后的 index.html；带 ETag + If-None-Match 的 304 短路。
    显式覆盖 HEAD：否则会落到 StaticFiles mount、拿到它基于 mtime/size 的
    32 字符 md5 ETag，与 GET 返回的 10 字符 ASSET_VERSION 不一致，破坏代理缓存键。
    若 frontend/ 目录不存在（纯 API 模式），退回 JSON 兜底。"""
    if not _INDEX_BYTES:
        return {"message": "I-Ching API 已启动。前端页面尚未部署。"}
    if request.headers.get("if-none-match") == _INDEX_ETAG:
        return Response(status_code=304, headers={"ETag": _INDEX_ETAG})
    body = _INDEX_BYTES if request.method == "GET" else b""
    return Response(
        content=body,
        media_type="text/html; charset=utf-8",
        headers={"ETag": _INDEX_ETAG},
    )


# ============================================================
# Dev-only 调试页面路由门控
# ------------------------------------------------------------
# frontend/all-hexagrams.html 是本地 dev 时才用的 64 卦视觉体检页。
# .dockerignore 排除了镜像，但 git clone + 直跑 uvicorn 的非 Docker
# 部署（HF Space 以外任何人自行部署）仍会被 StaticFiles mount 暴露。
#
# 所以在 mount 之前挂两条精确路径：env DEV_MODE=1 才返回文件，否则 404。
# 生产部署（HF Space Dockerfile）不会设置 DEV_MODE，默认 404。
# ./start.sh 会 export DEV_MODE=1，本地 uvicorn 访问体检页正常。
# Codex 第 N 轮 adversarial review 采纳。
# ============================================================
_DEV_ONLY_FILES = {
    "/all-hexagrams.html": ("all-hexagrams.html", "text/html; charset=utf-8"),
    "/assets/all-hexagrams.js": ("assets/all-hexagrams.js", "application/javascript"),
}


@app.get("/all-hexagrams.html", include_in_schema=False)
async def _serve_dev_all_hexagrams_html():
    return _serve_dev_only("/all-hexagrams.html")


@app.get("/assets/all-hexagrams.js", include_in_schema=False)
async def _serve_dev_all_hexagrams_js():
    return _serve_dev_only("/assets/all-hexagrams.js")


def _serve_dev_only(url_path: str):
    if os.environ.get("DEV_MODE") != "1":
        raise HTTPException(status_code=404)
    rel, mime = _DEV_ONLY_FILES[url_path]
    full = os.path.join(_frontend_dir, rel)
    if not os.path.isfile(full):
        raise HTTPException(status_code=404)
    return FileResponse(full, media_type=mime)


# 挂载静态文件目录（如果存在）
if os.path.isdir(_frontend_dir):
    app.mount("/", StaticFiles(directory=_frontend_dir, html=True), name="frontend")
