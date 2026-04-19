"""
WebSocket Origin 校验 + payload 上限测试

为什么必须显式测 WebSocket Origin：浏览器对 WS 握手不走 CORS preflight，
任何第三方页面都可从访客浏览器发起 wss:// 连接消费本 Space 的 LLM 配额
（CSWSH 攻击）。服务端必须在 accept() 前校验 `Origin` header，否则就是
事后关门。本文件锁定以下契约：

1. 合法 Origin（白名单）→ 握手成功。
2. 非白名单 Origin → accept 前 close 1008（policy violation）。
3. 无 Origin header（服务端脚本 / curl 原始形态）→ 严格拒，同 close 1008。
4. 超大 payload（> WS_MAX_PAYLOAD_BYTES）→ 即便 Origin 合法也被 close 1009。
5. 白名单默认值含四个本地开发域（localhost/127.0.0.1 × 8000/8765）。
"""

import pytest
from fastapi.testclient import TestClient

from backend.main import (
    ALLOWED_ORIGINS,
    DEFAULT_ALLOWED_ORIGINS,
    WS_MAX_PAYLOAD_BYTES,
    app,
)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


# ============================================================
# 白名单默认值
# ============================================================


@pytest.mark.parametrize(
    "dev_origin",
    [
        # 常用开发端口
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:8765",
        "http://127.0.0.1:8765",
        # Docker / HF Spaces 端口（Dockerfile EXPOSE 7860；漏了会让 `docker run -p 7860:7860` 本地测握手被拒）
        "http://localhost:7860",
        "http://127.0.0.1:7860",
    ],
)
def test_default_allowlist_contains_local_dev_origins(dev_origin: str):
    """clone 项目 → uvicorn / docker run 即刻可跑的默认域"""
    assert dev_origin in ALLOWED_ORIGINS, (
        f"{dev_origin} 应在默认 Origin 白名单中；"
        f"否则本地开发需强制配置 ALLOWED_ORIGINS env var"
    )


def test_default_allowlist_is_the_hardcoded_constant():
    """默认值和暴露给模块外的常量保持一致（防止重构时意外漂移）"""
    for o in DEFAULT_ALLOWED_ORIGINS:
        assert o in ALLOWED_ORIGINS


def test_payload_limit_is_reasonable():
    """4 KB 覆盖所有合法 interpret 请求（question ≤ 500 字 + hex 元数据）"""
    assert 2048 <= WS_MAX_PAYLOAD_BYTES <= 16384


# ============================================================
# 握手 Origin 校验
# ============================================================


def _attempt_ws(client: TestClient, headers: dict):
    """尝试建立 WS 连接，返回 (success, error)"""
    try:
        with client.websocket_connect("/ws/interpret", headers=headers) as ws:
            # 建立成功：发送一个最小 payload 立即断开，测试只关心握手是否通过
            return True, ws
    except Exception as e:
        return False, e


def test_ws_allows_whitelisted_origin():
    """白名单 Origin → 握手成功"""
    with TestClient(app) as c:
        # 仅验证握手通过（发送合法 payload 会走 LLM 真实调用，避免此路径）
        try:
            ws_ctx = c.websocket_connect(
                "/ws/interpret",
                headers={"origin": "http://localhost:8765"},
            )
            with ws_ctx:
                pass  # 立即断开，不发 payload 避免触发 LLM
        except Exception as e:
            pytest.fail(f"白名单 Origin 不应被拒：{e!r}")


def test_ws_rejects_foreign_origin():
    """evil.com 这类非白名单 Origin → 握手被拒"""
    with TestClient(app) as c:
        with pytest.raises(Exception):
            with c.websocket_connect(
                "/ws/interpret",
                headers={"origin": "http://evil.com"},
            ):
                pass


def test_ws_rejects_missing_origin():
    """严格模式：无 Origin header → 拒（服务端脚本/curl 原样不带 Origin）"""
    with TestClient(app) as c:
        with pytest.raises(Exception):
            # 不传 headers = 不带 Origin
            with c.websocket_connect("/ws/interpret"):
                pass


# ============================================================
# Payload 大小上限
# ============================================================


def test_ws_rejects_oversized_payload():
    """合法 Origin 但 payload 超过 4 KB → close 1009（message too big）"""
    with TestClient(app) as c:
        with c.websocket_connect(
            "/ws/interpret",
            headers={"origin": "http://localhost:8765"},
        ) as ws:
            # 构造 > 4 KB 的字符串（不必合法 JSON，长度检查先于 json.loads）
            oversized = "A" * (WS_MAX_PAYLOAD_BYTES + 100)
            ws.send_text(oversized)
            # 服务端应发 error 消息然后关闭
            err = ws.receive_json()
            assert err.get("type") == "error"
            assert "过大" in err.get("text", "")
            # 服务端已 close，下一步接收应抛 disconnect
            with pytest.raises(Exception):
                ws.receive_text()
