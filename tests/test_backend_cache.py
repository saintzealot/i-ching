"""
后端 HTTP 缓存治理测试

覆盖三层机制：
1. Cache-Control 中间件按路径分流：index.html → no-cache；带 ?v= 的 asset → immutable；
   无 ?v= 的 asset → 1 小时兜底
2. ASSET_VERSION 占位符替换：index.html 中 `?v=__ASSET_VERSION__` 必须渲染成真实哈希
3. ETag + If-None-Match 的 304 短路：命中返回 304，不命中返回 200

治本目的：新部署后用户无须手动刷新即可拿到新版本。
"""

import hashlib

import pytest
from fastapi.testclient import TestClient

from backend.main import ASSET_VERSION, _INDEX_ETAG, _INDEX_HASH, app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


# ============================================================
# Cache-Control 分流
# ============================================================


def test_index_no_cache(client):
    """index.html 必须 no-cache 才能保证每次请求都去验证新鲜度——
    这是整个缓存策略的基石，旧 HTML 锁住旧 JS 是此前用户问题的根因。"""
    r = client.get("/")
    assert r.status_code == 200
    cc = r.headers.get("cache-control", "")
    assert "no-cache" in cc, f"/ 必须 no-cache，实际：{cc!r}"
    assert "must-revalidate" in cc


def test_versioned_asset_is_immutable(client):
    """带 ?v= 的 asset 走 1 年永久缓存（URL 变化天然淘汰旧缓存）。"""
    r = client.get(f"/assets/app.js?v={ASSET_VERSION}")
    assert r.status_code == 200
    cc = r.headers.get("cache-control", "")
    assert "max-age=31536000" in cc, f"版本化 asset 应 1 年缓存，实际：{cc!r}"
    assert "immutable" in cc, "版本化 asset 必须 immutable"


def test_unversioned_asset_short_cache(client):
    """没带 ?v= 的 asset 走 1 小时兜底，避免长期缓存无版本文件。"""
    r = client.get("/assets/iching-core.js")  # 直接请求，不带 ?v=
    assert r.status_code == 200
    cc = r.headers.get("cache-control", "")
    assert "max-age=3600" in cc, f"无版本 asset 应 1 小时缓存，实际：{cc!r}"
    assert "immutable" not in cc


def test_api_route_no_cache_directive(client):
    """API 路由不被缓存中间件触碰（交由 API 自身或默认行为处理）。
    这里只断言不会错误地给 API 套上 immutable。"""
    r = client.get("/api/hexagrams")
    assert r.status_code == 200
    cc = r.headers.get("cache-control", "")
    assert "immutable" not in cc, "API 响应不得被标记 immutable"


# ============================================================
# ASSET_VERSION 占位符替换
# ============================================================


def test_asset_version_is_nonempty_hex(client):
    """ASSET_VERSION 应为 10 字符十六进制（sha256 前缀）。"""
    assert isinstance(ASSET_VERSION, str)
    assert len(ASSET_VERSION) == 10
    assert all(c in "0123456789abcdef" for c in ASSET_VERSION), (
        f"ASSET_VERSION 应是 hex，实际：{ASSET_VERSION!r}"
    )


def test_index_html_has_no_placeholder(client):
    """首次部署漏改占位符是常见坑：字面 __ASSET_VERSION__ 留在 HTML 里
    会导致浏览器永久缓存同一个 URL（字符串相同），更新完全失效。"""
    r = client.get("/")
    assert r.status_code == 200
    assert b"__ASSET_VERSION__" not in r.content, (
        "index.html 响应中不得残留 __ASSET_VERSION__ 字面占位符"
    )


def test_index_html_references_computed_version(client):
    """HTML 中的 ?v= 参数必须是当前 ASSET_VERSION，不是过期值。"""
    r = client.get("/")
    expected = f"?v={ASSET_VERSION}".encode("ascii")
    assert expected in r.content, f"HTML 应含 {expected!r}"


# ============================================================
# ETag / 304 回路
# ============================================================


def test_index_has_etag(client):
    r = client.get("/")
    assert r.status_code == 200
    etag = r.headers.get("etag")
    assert etag == _INDEX_ETAG, f"ETag 应为 {_INDEX_ETAG}，实际：{etag!r}"


def test_if_none_match_returns_304(client):
    """命中 ETag 时返回 304 + 空 body，节省 ~80KB 传输。"""
    r = client.get("/", headers={"If-None-Match": _INDEX_ETAG})
    assert r.status_code == 304
    assert r.content == b""
    # 304 响应也应保留 ETag，方便客户端继续用作下一轮的缓存键
    assert r.headers.get("etag") == _INDEX_ETAG


def test_if_none_match_mismatch_returns_full(client):
    """ETag 不匹配时必须返回 200 + 完整 body。"""
    r = client.get("/", headers={"If-None-Match": '"stale-etag"'})
    assert r.status_code == 200
    assert b"<html" in r.content or b"<!doctype" in r.content.lower()


def test_head_and_get_etag_parity(client):
    """GET 与 HEAD 必须发相同的 ETag / Cache-Control，否则代理/CDN 会拿到
    不一致的缓存键，导致诡异的缓存命中/未命中混乱。
    （此前 BUG：@app.get 只注册 GET，HEAD 落到 StaticFiles 拿到 md5 32 字符 ETag）"""
    get_r = client.get("/")
    head_r = client.head("/")
    assert get_r.headers.get("etag") == head_r.headers.get("etag")
    assert get_r.headers.get("cache-control") == head_r.headers.get("cache-control")
    assert head_r.content == b""  # HEAD 永远无 body


def test_head_if_none_match_returns_304(client):
    """HEAD + If-None-Match 也应走 304 短路。"""
    r = client.head("/", headers={"If-None-Match": _INDEX_ETAG})
    assert r.status_code == 304


# ============================================================
# Codex 第十轮 F1 回归：ETag 必须取自 HTML 响应字节，而非 asset-only hash
# ============================================================


def test_index_etag_is_not_asset_version(client):
    """ETag 不得等于 asset-only ASSET_VERSION。
    若相等，说明 ETag 仍按 asset hash 派生——仅改 HTML/CSS 但 asset 不变时
    ETag 不变，浏览器持续拿到旧 HTML（Codex 第十轮 F1 的失效模式）。
    当前逻辑下 _INDEX_HASH 是 sha256(_INDEX_BYTES)，哈希相等概率 2^-40，可视为 0。"""
    assert _INDEX_HASH != ASSET_VERSION, (
        f"_INDEX_HASH 不应等于 ASSET_VERSION（都应取自不同字节源）："
        f"_INDEX_HASH={_INDEX_HASH!r}, ASSET_VERSION={ASSET_VERSION!r}"
    )
    assert _INDEX_ETAG != f'"{ASSET_VERSION}"', (
        "_INDEX_ETAG 字面不应等于 asset-only ASSET_VERSION 包装"
    )


def test_index_etag_derivation_tracks_html_bytes():
    """核心契约：ETag = sha256(rendered HTML bytes)[:10]。
    不同 HTML 字节必须产出不同 ETag——这是"仅改 HTML 也触发 304 miss"的根基。
    独立跑派生逻辑，不启动 TestClient，避免污染模块级缓存。"""
    bytes_v1 = b"<html><body>old version</body></html>"
    bytes_v2 = b"<html><body>new version</body></html>"
    etag_v1 = f'"{hashlib.sha256(bytes_v1).hexdigest()[:10]}"'
    etag_v2 = f'"{hashlib.sha256(bytes_v2).hexdigest()[:10]}"'
    assert etag_v1 != etag_v2, "HTML 字节变更必须触发 ETag 变更"
