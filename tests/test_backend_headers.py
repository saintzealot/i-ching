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


# ============================================================
# Dev-only 调试页面在非 DEV_MODE 下必须 404
# ============================================================


@pytest.mark.parametrize(
    "url",
    ["/all-hexagrams.html", "/all-hexagrams.js"],
)
def test_dev_only_paths_return_404_without_dev_mode(client, monkeypatch, url):
    """dev-tools/all-hexagrams.* 是本地体检页，生产部署（HF Space Docker 或
    任何未显式设置 DEV_MODE 的部署）必须 404。

    Codex 二轮 adversarial review 指出：.dockerignore 只治 Docker；非
    Docker 部署仍经过 StaticFiles。Codex 三轮进一步发现精确路由可以被
    URL 变体（%2e 编码、双斜杠等）绕过——所以把文件彻底移出 frontend/
    mount 路径，同时保留精确路由的 DEV_MODE 门控。
    """
    monkeypatch.delenv("DEV_MODE", raising=False)
    r = client.get(url)
    assert r.status_code == 404, f"{url} 在无 DEV_MODE 时必须 404，实际 {r.status_code}"


@pytest.mark.parametrize(
    "url",
    ["/all-hexagrams.html", "/all-hexagrams.js"],
)
def test_dev_only_paths_served_when_dev_mode_set(client, monkeypatch, url):
    """DEV_MODE=1 时路由放行；文件在磁盘上则返回 200，文件不存在返回 404。
    （Docker 镜像里 .dockerignore 已删除整个 dev-tools/ 目录，即使误设
    DEV_MODE 也拿不到内容）"""
    monkeypatch.setenv("DEV_MODE", "1")
    r = client.get(url)
    assert r.status_code in (200, 404), (
        f"{url} 在 DEV_MODE=1 下应返回 200（文件存在）或 404（文件缺），实际 {r.status_code}"
    )


# URL 变体 bypass 回归测试——Codex 三轮 adversarial review 发现：
# 原来 /all-hexagrams.html 和 /assets/all-hexagrams.js 在 frontend/ 下，
# StaticFiles mount normalize `/assets/%2e/all-hexagrams.js`、
# `/%2e/all-hexagrams.html`、`/assets//all-hexagrams.js` 等变体后能指到磁盘文件，
# 绕过了精确路由的 DEV_MODE 门控。修法是把文件移到 dev-tools/ 目录（不在 mount 范围内），
# 这样任何 URL 变体 normalize 后落到 frontend/ 都指不到文件，必定 404。
_BYPASS_VARIANTS = [
    # Codex 三轮 review 直接指出的四个 URL 变体——修前 frontend/ 时都能命中
    # StaticFiles、拿到文件；修后 dev-tools/ 下任何 normalize 都落空。
    "/assets/%2e/all-hexagrams.js",
    "/assets/%2e%2e/assets/all-hexagrams.js",
    "/assets//all-hexagrams.js",
    "/%2e/all-hexagrams.html",
    # 旧的 /assets/... 精确路径已作废，也不应再生效
    "/assets/all-hexagrams.js",
    # 注意：`//all-hexagrams.html`（双前导斜杠）不在列表里——TestClient
    # 会把它归一到 root `/`，命中 serve_index 返回主页 index.html（公开资源），
    # 不算 dev 页泄露。如果想覆盖这类，要断言"响应体不含 dev 页指纹"，
    # 比纯看 status 更精确，但当前 4 个变体已覆盖 Codex 报告的全部真泄露点。
]


@pytest.mark.parametrize("url", _BYPASS_VARIANTS)
def test_dev_only_bypass_variants_blocked_without_dev_mode(client, monkeypatch, url):
    """无 DEV_MODE 时，所有已知变体都必须 404（不能泄露体检页内容）"""
    monkeypatch.delenv("DEV_MODE", raising=False)
    r = client.get(url)
    assert r.status_code == 404, f"{url} 在无 DEV_MODE 时必须 404，实际 {r.status_code}"


@pytest.mark.parametrize("url", _BYPASS_VARIANTS)
def test_dev_only_bypass_variants_blocked_even_with_dev_mode(client, monkeypatch, url):
    """关键：即便 DEV_MODE=1，URL 变体也不应能通过 StaticFiles 拿到体检页内容。
    （体检页文件已从 frontend/ 搬走，StaticFiles 扫不到；精确路由只认
    `/all-hexagrams.html` 和 `/all-hexagrams.js`。）"""
    monkeypatch.setenv("DEV_MODE", "1")
    r = client.get(url)
    assert r.status_code == 404, (
        f"{url} 即便 DEV_MODE=1 也必须 404（防 URL 变体绕过），实际 {r.status_code}"
    )
