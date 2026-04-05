"""
I-Ching FastAPI 后端应用

提供以下接口：
- POST /api/divine     — 算卦
- GET  /api/hexagrams   — 获取64卦列表
- GET  /api/hexagrams/{number} — 获取单卦详情
"""

import os
import json
from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
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
        changing_texts = [lines_text[p - 1] for p in changing_lines if 1 <= p <= len(lines_text)]
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
控制在200-350字以内。"""
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
控制在200-350字以内。"""


@app.websocket("/ws/interpret")
async def ws_interpret(websocket: WebSocket):
    """WebSocket 端点：流式推送 AI 卦辞解读"""
    await websocket.accept()
    try:
        raw = await websocket.receive_text()
        request = json.loads(raw)
        prompt = build_interpret_prompt(request)

        # 通知前端进入思考阶段
        await websocket.send_json({"type": "thinking"})

        stream = await lm_client.chat.completions.create(
            model=os.environ.get("LLM_MODEL", "google/gemma-4-26b-a4b"),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4096,
            temperature=0.7,
            stream=True,
        )

        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            # 只推送 content，跳过 reasoning_content
            if delta.content:
                await websocket.send_json({"type": "content", "text": delta.content})

        await websocket.send_json({"type": "done"})
    except Exception as e:
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
# ============================================================

# 获取项目根目录（backend 的上级目录）
_backend_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_backend_dir)
_frontend_dir = os.path.join(_project_root, "frontend")


@app.get("/")
async def serve_index():
    """返回前端首页"""
    index_path = os.path.join(_frontend_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "I-Ching API 已启动。前端页面尚未部署。"}


# 挂载静态文件目录（如果存在）
if os.path.isdir(_frontend_dir):
    app.mount("/", StaticFiles(directory=_frontend_dir, html=True), name="frontend")
