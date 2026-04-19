"""
后端安全响应头测试

断言 FastAPI 中间件为每个响应添加的安全头齐全，且 CSP 的
`script-src` 不含 `unsafe-inline`（inline script 已外部化）。

为什么必须通过 HTTP header 交付 CSP：
- `frame-ancestors` / `report-uri` / `sandbox` 在 <meta> CSP 中被浏览器忽略
  （W3C CSP3 §6.1），只有 HTTP header 才能真正启用防嵌入。
"""

import re

import pytest
from fastapi.testclient import TestClient

from backend.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def index_headers(client):
    r = client.get("/")
    assert r.status_code == 200
    return r.headers


# ============================================================
# CSP
# ============================================================


def test_csp_header_present(index_headers):
    assert "content-security-policy" in index_headers


def test_csp_sets_frame_ancestors_none(index_headers):
    csp = index_headers["content-security-policy"]
    assert "frame-ancestors 'none'" in csp, (
        "frame-ancestors 必须通过 HTTP header 交付才能真正生效"
    )


def test_csp_script_src_no_unsafe_inline(index_headers):
    csp = index_headers["content-security-policy"]
    script_src = re.search(r"script-src([^;]+)", csp)
    assert script_src, "CSP 必须包含 script-src directive"
    value = script_src.group(1)
    assert "'unsafe-inline'" not in value, (
        "script-src 不得含 'unsafe-inline'（inline script 已外部化）"
    )
    assert "'self'" in value


def test_csp_default_src_self(index_headers):
    csp = index_headers["content-security-policy"]
    assert "default-src 'self'" in csp


def test_csp_restricts_connect_src(index_headers):
    csp = index_headers["content-security-policy"]
    connect_src = re.search(r"connect-src([^;]+)", csp)
    assert connect_src, "CSP 必须包含 connect-src directive"
    value = connect_src.group(1)
    assert "'self'" in value, "connect-src 必须允许同源（CSP3: 'self' 覆盖同源 ws/wss）"
    # 不得使用 scheme-wide ws:/wss: 通配（会允许任意域的 WebSocket 外泄数据）
    assert not re.search(r"\bws:(?!//)", value), (
        "connect-src 不得含裸 ws: scheme 通配（应依赖 'self' 覆盖同源 WS）"
    )
    assert not re.search(r"\bwss:(?!//)", value), (
        "connect-src 不得含裸 wss: scheme 通配"
    )


# ============================================================
# 其他硬化响应头
# ============================================================


def test_x_frame_options_deny(index_headers):
    """旧浏览器（不支持 frame-ancestors）兜底"""
    assert index_headers.get("x-frame-options") == "DENY"


def test_x_content_type_options_nosniff(index_headers):
    assert index_headers.get("x-content-type-options") == "nosniff"


def test_referrer_policy(index_headers):
    policy = index_headers.get("referrer-policy", "")
    assert "strict-origin" in policy


def test_permissions_policy_blocks_sensitive_apis(index_headers):
    policy = index_headers.get("permissions-policy", "")
    for feature in ("camera=()", "microphone=()", "geolocation=()"):
        assert feature in policy, f"Permissions-Policy 应禁用 {feature}"


# ============================================================
# API 响应也必须带 CSP（防止攻击者从 API JSON 构造钓鱼）
# ============================================================


def test_api_endpoint_also_has_csp(client):
    r = client.get("/api/hexagrams")
    assert r.status_code == 200
    assert "content-security-policy" in r.headers
    assert r.headers.get("x-frame-options") == "DENY"
