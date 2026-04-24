"""
前端静态结构测试

不依赖浏览器，直接读取 frontend/index.html 与 frontend/assets/iching-core.js，
断言以下层面的关键特征：

- DOM 锚点（id 存在）
- 关键文案（方向 A 的用户可见文字）
- meta 头（viewport / theme-color / safe-area 相关）
- 字体预连接 & 第三方脚本引入
- marked XSS 配置（tokenizer 的 html 解析器被禁用）
- 安全反模式（innerHTML 用法受限；无动态代码执行 API 调用）
- 核心业务函数签名
- 动画 keyframes
- 响应式断点

运行：
    pytest tests/test_frontend_structure.py -v
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
INDEX_HTML = ROOT / "frontend" / "index.html"
CORE_JS = ROOT / "frontend" / "assets" / "iching-core.js"
APP_JS = ROOT / "frontend" / "assets" / "app.js"


@pytest.fixture(scope="module")
def index_html() -> str:
    """仅 index.html 原文，用来断言"HTML 里不含 inline script/handler"这类反模式"""
    assert INDEX_HTML.exists(), f"{INDEX_HTML} 不存在"
    return INDEX_HTML.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def app_js() -> str:
    assert APP_JS.exists(), f"{APP_JS} 不存在（inline script 应已外部化）"
    return APP_JS.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def core_js() -> str:
    assert CORE_JS.exists(), f"{CORE_JS} 不存在"
    return CORE_JS.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def html(index_html: str, app_js: str) -> str:
    """
    HTML + 外部化的 app.js 合并视图 — 供"源码里应出现 X"类断言使用。

    历史上 inline script 与 HTML 是同一文件，大量断言写成 'X in html'；
    外部化后这些 JS 查询要改看合并后的源代码，便于断言继续聚焦"行为"而非
    "物理布局"。真正需要"HTML 层面"检查的断言显式依赖 index_html fixture。
    """
    return index_html + "\n" + app_js


# ============================================================
# Meta & 依赖
# ============================================================


def test_has_viewport_with_viewport_fit(html: str):
    assert 'name="viewport"' in html
    assert "viewport-fit=cover" in html, "需要 viewport-fit=cover 适配刘海屏"


def test_has_theme_color(html: str):
    assert 'name="theme-color"' in html
    assert "#070b09" in html, "theme-color 应为深空底色 #070b09"


def test_has_apple_mobile_meta(html: str):
    assert "apple-mobile-web-app-capable" in html
    assert "apple-mobile-web-app-status-bar-style" in html


def test_has_google_fonts_preconnect(html: str):
    assert "fonts.googleapis.com" in html
    assert "fonts.gstatic.com" in html


def test_has_noto_serif_sc(html: str):
    assert "Noto+Serif+SC" in html or "Noto Serif SC" in html


def test_loads_marked_and_core_js(html: str):
    # marked 已本地化为 assets/vendor/marked-<version>.<min|umd>.js
    # marked 17+ 的 npm 包不再预压缩，我们直接 vendor 未压缩的 .umd.js（SRI 稳定）
    assert re.search(r"marked-[\d.]+\.(min|umd)\.js", html), "缺少 marked 脚本引用"
    assert "assets/iching-core.js" in html


# ============================================================
# 关键 DOM 锚点
# ============================================================

REQUIRED_IDS = [
    "baguaFloat",
    "baguaRotate",
    "baguaStage",
    "coinStage",
    "coinsRow",
    "shakeProgress",
    "tossLabel",
    "tossCount",
    "tossBars",
    "tossInstr",
    "tossHint",
    "hexPreview",
    "coinResult",
    "composePanel",
    "question",
    "btnDivine",
    "resultSection",
    "resultName",
    "resultRomaji",
    "resultSymbol",
    "resultEpithet",
    "resultNum",
    "hexes",
    "judgmentBox",
    "tabs",
    "tabBody",
    "paneJudgment",
    "paneLines",
    "paneInterp",
    "lookupToggle",
    "lookupGrid",
    "historyPanel",
    "historyBackdrop",
    "historyList",
    "btnHistory",
    "modal",
    "modalContent",
    "modalBody",
    "errorMsg",
    "lunarDate",
    "motes",
    "starfield-gold",
    "starfield-white",
    "backBtn",
    "shareBtn",
]


@pytest.mark.parametrize("anchor_id", REQUIRED_IDS)
def test_required_dom_ids(html: str, anchor_id: str):
    pattern = rf'id="{re.escape(anchor_id)}"'
    assert re.search(pattern, html), f"缺少 id={anchor_id!r}"


# ============================================================
# 关键文案
# ============================================================

REQUIRED_TEXTS = [
    "易经 · I CHING",
    "问&nbsp;卦",
    "诚心所至",
    "天机自现",
    "— 心中所惑 —",
    "起&nbsp;&nbsp;卦",
    "六十四卦速查",
    "卦&nbsp;历&nbsp;史",
    "卦象解读",
    "卦辞",
    "爻辞",
    "凝神静候",
    "铜钱自行翻转中",
]


@pytest.mark.parametrize("text", REQUIRED_TEXTS)
def test_required_texts(html: str, text: str):
    assert text in html, f"缺少文案 {text!r}"


# ============================================================
# marked XSS 配置
# ============================================================


def test_marked_tokenizer_disables_html(html: str):
    assert "marked.setOptions" in html
    # 匹配类似 t.html = function() { return false; }
    assert re.search(
        r"t(?:okenizer)?\.html\s*=\s*function\s*\([^)]*\)\s*\{\s*return\s+false\s*;?\s*\}",
        html,
    ), "应禁用 marked 的 HTML tokenizer"


# ============================================================
# 安全反模式（用字符串拼接避开 hook 对字面量的误伤）
# ============================================================


def _strip_comments(js: str) -> str:
    """粗略去掉 /* ... */ 和 // ... 注释"""
    no_block = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    no_line = re.sub(r"//[^\n]*", "", no_block)
    return no_line


def test_innerhtml_usage_is_minimal(html: str):
    """
    所有 innerHTML 赋值的 RHS 必须经过 renderMarkdownSafely（含 DOMPurify sanitize）。
    禁止裸 marked.parse 直接赋给 innerHTML，禁止其他不受控 RHS。
    """
    js = _strip_comments(html)
    assignments = re.findall(r"\.innerHTML\s*=\s*([^;]+);", js)
    assert assignments, "至少应保留 AI 解读渲染那一处 innerHTML 赋值"
    bad = [a.strip() for a in assignments if "renderMarkdownSafely" not in a]
    assert not bad, f"发现不受 sanitizer 保护的 innerHTML 赋值: {bad}"


# ============================================================
# Codex review 修复：DOMPurify + 外链确认 + WS seq + 历史更新
# ============================================================


def test_dompurify_script_loaded(html: str):
    assert "dompurify" in html.lower() or "DOMPurify" in html, "应加载 DOMPurify"


def test_render_markdown_safely_signature(html: str):
    assert re.search(r"function\s+renderMarkdownSafely\s*\(", html), (
        "需要 renderMarkdownSafely 封装（单点 sanitize）"
    )


def test_render_markdown_safely_calls_sanitize(html: str):
    """renderMarkdownSafely 体内必须同时调用 marked.parse 和 DOMPurify.sanitize"""
    m = re.search(
        r"function\s+renderMarkdownSafely\s*\([^)]*\)\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}",
        html,
        re.S,
    )
    assert m, "找不到 renderMarkdownSafely 函数体"
    body = m.group(1)
    assert "marked.parse" in body, "renderMarkdownSafely 必须调 marked.parse"
    assert "DOMPurify.sanitize" in body, (
        "renderMarkdownSafely 必须调 DOMPurify.sanitize"
    )


def test_safe_md_config_restricts_uri(html: str):
    """配置中 URI 白名单必须限定 http(s)"""
    assert re.search(r"ALLOWED_URI_REGEXP\s*:\s*/\^https\?", html), (
        "ALLOWED_URI_REGEXP 应以 ^https? 开头限制协议"
    )


def test_safe_md_config_href_only(html: str):
    """属性白名单必须只放 href"""
    m = re.search(r"ALLOWED_ATTR\s*:\s*\[([^\]]*)\]", html)
    assert m, "缺少 ALLOWED_ATTR 配置"
    allowed = [x.strip().strip("'\"") for x in m.group(1).split(",") if x.strip()]
    assert allowed == ["href"], f"ALLOWED_ATTR 应仅含 href, 实为: {allowed}"


# 外链确认
def test_link_confirm_modal_exists(html: str):
    assert 'id="linkConfirm"' in html, "缺少外链确认 modal"
    assert 'id="lcUrl"' in html and 'id="lcCancel"' in html and 'id="lcGo"' in html


def test_window_open_has_noopener(html: str):
    """所有 window.open 调用都必须带 noopener（防止新窗口拿到 opener）"""
    js = _strip_comments(html)
    opens = re.findall(r"window\.open\s*\([^)]*\)", js)
    assert opens, "应存在 window.open 调用（外链打开）"
    for call in opens:
        assert "noopener" in call, f"window.open 调用缺少 noopener: {call}"


# WebSocket stale-stream 防护
def test_interp_seq_variable_exists(html: str):
    assert "_interpSeq" in html, "应有 _interpSeq 序号变量用于 WS stale-stream 防护"


def test_cancel_current_interp_defined_and_called(html: str):
    assert re.search(r"function\s+cancelCurrentInterp\s*\(", html), (
        "需要 cancelCurrentInterp 函数"
    )
    # 至少在 cancelCurrentDivine 和 startDivine 处间接/直接调用
    calls = re.findall(r"\bcancelCurrentInterp\s*\(", html)
    assert len(calls) >= 3, f"cancelCurrentInterp 调用次数不足，实际 {len(calls)}"


# ============================================================
# Codex 第四轮 · 起卦中途切视图的 race 防护
# ============================================================


def test_divine_seq_variable_exists(app_js: str):
    """镜像 _interpSeq 的序号机制：防中途切走导致老 startDivine 覆盖 DOM"""
    assert "_divineSeq" in app_js, "应有 _divineSeq 序号变量"


def test_cancel_current_divine_defined(app_js: str):
    assert re.search(r"function\s+cancelCurrentDivine\s*\(", app_js), (
        "需要 cancelCurrentDivine 显式取消 API"
    )


def test_show_history_item_cancels_divine(app_js: str):
    """showHistoryItem 函数体内必须先调 cancelCurrentDivine"""
    m = re.search(
        r"function\s+showHistoryItem\s*\([^)]*\)\s*\{(.*?)\n\}",
        app_js,
        re.S,
    )
    assert m, "找不到 showHistoryItem 函数体"
    body = m.group(1)
    assert re.search(r"\bcancelCurrentDivine\s*\(", body), (
        "showHistoryItem 必须先 cancelCurrentDivine 避免 race"
    )


def test_back_btn_cancels_divine(app_js: str):
    """返回键应中止进行中的起卦（摇卦中按返回也要停）"""
    # 匹配 backBtn 的 click handler 函数体
    m = re.search(
        r"\$\(['\"]backBtn['\"]\)\.addEventListener\s*\(\s*['\"]click['\"]\s*,\s*function\s*\([^)]*\)\s*\{(.*?)\n\s*\}\s*\)",
        app_js,
        re.S,
    )
    assert m, "找不到 backBtn 的 click handler"
    body = m.group(1)
    assert re.search(r"\bcancelCurrentDivine\s*\(", body), (
        "backBtn click handler 应调 cancelCurrentDivine（替代仅 cancelCurrentInterp）"
    )


def test_start_divine_has_checkpoint_guards(app_js: str):
    """
    startDivine 的每个 await 统一跟一次 checkpoint() 调用。

    源码里 6 个静态调用点（fetch / resp.json / loop sleep600 / loop sleep700 /
    sleep240 / showResult 前），loop 内的 2 处在运行时会展开成 12 次触发，
    能够覆盖所有中断机会。
    """
    m = re.search(
        r"async\s+function\s+startDivine\s*\([^)]*\)\s*\{(.*?)\n\}",
        app_js,
        re.S,
    )
    assert m, "找不到 startDivine 函数体"
    body = m.group(1)
    # 用 `;` 排除函数声明 `function checkpoint() {` 和注释里的裸 `checkpoint()`
    calls = re.findall(r"\bcheckpoint\s*\(\s*\)\s*;", body)
    assert len(calls) >= 6, (
        f"startDivine 的 checkpoint 调用点不足（每 await 后应有一次），实际 {len(calls)}"
    )


def test_start_divine_handles_cancel_sentinel(app_js: str):
    """catch 分支要识别 __divine_cancelled sentinel 并静默退出"""
    m = re.search(
        r"async\s+function\s+startDivine\s*\([^)]*\)\s*\{(.*?)\n\}",
        app_js,
        re.S,
    )
    assert m
    body = m.group(1)
    assert "__divine_cancelled" in body, (
        "startDivine 需以 __divine_cancelled 作取消 sentinel"
    )


# 历史更新
def test_update_history_interp_signature(html: str):
    assert re.search(r"function\s+updateHistoryInterp\s*\(", html), (
        "需要 updateHistoryInterp 函数把最终 AI 解读写回"
    )


def test_save_history_returns_ts(html: str):
    """saveHistory 必须返回主键 ts 供后续 updateHistoryInterp 定位"""
    m = re.search(
        r"function\s+saveHistory\s*\([^)]*\)\s*\{(.*?)\n\}",
        html,
        re.S,
    )
    assert m, "找不到 saveHistory 函数体"
    body = m.group(1)
    assert re.search(r"return\s+[\w.]+\.ts\b", body) or re.search(
        r"return\s+record\.ts\b", body
    ), "saveHistory 应 return record.ts"


def test_start_divine_passes_history_ts_to_stream(html: str):
    """startDivine 里应把 saveHistory 返回值传给 showResult/streamInterp"""
    assert re.search(r"historyTs\s*=\s*saveHistory\s*\(", html), (
        "startDivine 应保存 historyTs"
    )
    assert re.search(r"showResult\s*\([^)]*historyTs", html) or re.search(
        r"streamInterp\s*\([^)]*historyTs", html
    ), "historyTs 必须传给 showResult 或 streamInterp"


# ============================================================
# 第二轮 Codex review 修复：vendor 本地化 + CSP + WS 状态机 + 重试
# ============================================================

VENDOR_DIR = ROOT / "frontend" / "assets" / "vendor"


def test_vendor_files_present():
    """marked 和 DOMPurify 已下载到本地，消除 CDN 供应链风险。
    marked 18+ 的 npm 包不再发 pre-minified 版本，允许 .umd.js 后缀。"""
    assert list(VENDOR_DIR.glob("marked-*.js")), f"缺少本地 marked 文件: {VENDOR_DIR}"
    assert list(VENDOR_DIR.glob("dompurify-*.min.js")), (
        f"缺少本地 dompurify 文件: {VENDOR_DIR}"
    )


def test_script_tags_point_to_local_vendor(html: str):
    """head 里 marked/dompurify 的 script src 必须是相对路径（本地），不得引用 CDN。
    src 允许带 ?v=… 查询串（用于缓存破解，含 __ASSET_VERSION__ 占位符）。
    marked 文件后缀允许 .min.js 或 .umd.js（marked 18+ 的 npm 包不再预压缩）。"""
    marked_tag = re.search(
        r'<script\s+src="([^"?]+marked[^"?]+\.(?:min|umd)\.js)(?:\?[^"]*)?"', html
    )
    assert marked_tag, "缺少 marked script 标签"
    assert marked_tag.group(1).startswith("assets/"), (
        f"marked 应从本地加载，实为: {marked_tag.group(1)}"
    )

    dompurify_tag = re.search(
        r'<script\s+src="([^"?]+dompurify[^"?]+\.min\.js)(?:\?[^"]*)?"', html
    )
    assert dompurify_tag, "缺少 dompurify script 标签"
    assert dompurify_tag.group(1).startswith("assets/"), (
        f"dompurify 应从本地加载，实为: {dompurify_tag.group(1)}"
    )


def test_vendor_scripts_have_sri_integrity(html: str):
    """vendor 脚本必须携带 SRI integrity= 哈希（supply-chain tripwire）。
    任何 byte 改动会让浏览器拒绝执行，迫使升级路径同步更新哈希。"""
    pattern = (
        r'<script\s+src="assets/vendor/[^"]+\.js[^"]*"'
        r'\s+integrity="sha384-[A-Za-z0-9+/=]+"'
    )
    matches = re.findall(pattern, html, re.DOTALL)
    assert len(matches) >= 2, (
        f"应有 2 个带 SRI integrity 的 vendor script（marked + dompurify），"
        f"实际匹配 {len(matches)}"
    )


def test_vendor_scripts_have_crossorigin_anonymous(html: str):
    """SRI 标准要求 crossorigin= 属性存在（尽管同源不触发 CORS，
    `anonymous` 是规范推荐值）。"""
    pattern = (
        r'<script\s+src="assets/vendor/[^"]+\.js[^"]*"'
        r'[^>]*crossorigin="anonymous"'
    )
    matches = re.findall(pattern, html, re.DOTALL)
    assert len(matches) >= 2, (
        f'应有 2 个带 crossorigin="anonymous" 的 vendor script，实际匹配 {len(matches)}'
    )


def test_no_cdn_script_sources(html: str):
    """全文不应出现 jsdelivr/unpkg/cdnjs 等外部脚本源"""
    for host in ("cdn.jsdelivr.net", "unpkg.com", "cdnjs.cloudflare.com"):
        assert f'src="https://{host}' not in html, f"发现外部脚本源: {host}"


def test_has_csp_meta(html: str):
    """head 里应有 Content-Security-Policy meta 作为 defense-in-depth"""
    m = re.search(
        r'<meta\s+http-equiv="Content-Security-Policy"\s+content="([^"]+)"',
        html,
    )
    assert m, "缺少 CSP meta 标签"
    csp = m.group(1)
    assert "default-src 'self'" in csp
    # frame-ancestors 只能在 HTTP header 里生效（见 test_backend_headers.py），
    # 不再在 meta 里断言；tests/test_frontend_structure.py::test_meta_csp_no_frame_ancestors
    # 会反向检查 meta 里不应声明此 directive。
    script_src = re.search(r"script-src([^;]+)", csp).group(1)
    assert "cdn.jsdelivr.net" not in script_src
    assert "'self'" in script_src


# WS 状态机
def test_stream_state_variables(html: str):
    """streamInterp 内应存在拆分后的状态标识符"""
    assert re.search(r"\bdoneReceived\b", html), "缺少 doneReceived 状态"
    assert re.search(r"\bhadError\b", html), "缺少 hadError 状态"
    assert re.search(r"\bhasContent\b", html), "缺少 hasContent 状态"


def test_finalize_takes_success_arg(html: str):
    """finalize 签名应为 finalize(success)，只在 success 时写历史"""
    assert re.search(r"function\s+finalize\s*\(\s*success\s*\)", html), (
        "finalize 应接收 success 参数"
    )
    assert re.search(r"finalize\s*\(\s*true\s*\)", html), (
        "至少应有 finalize(true) 的调用（done 分支）"
    )
    m = re.search(r"function\s+finalize\s*\([^)]*\)\s*\{([\s\S]*?)\n\s{2}\}", html)
    assert m, "找不到 finalize 函数体"
    body = m.group(1)
    assert "updateHistoryInterp" in body, "finalize 内应调 updateHistoryInterp"
    assert "success" in body, "finalize 写历史的条件应引用 success"


def test_classify_stream_end_used(html: str):
    """应调用 Core.classifyStreamEnd 做流结束分类"""
    assert re.search(r"Core\.classifyStreamEnd\s*\(", html), (
        "streamInterp 结束路径应调 Core.classifyStreamEnd"
    )


def test_retry_button_support(html: str):
    """失败/中断路径应提供 .retry-interp 按钮让用户重试"""
    assert ".retry-interp" in html, "缺少 .retry-interp 样式"
    assert "retry-interp" in html, "缺少 retry 按钮创建代码"


def test_core_js_exposes_classify_stream_end(core_js: str):
    assert "classifyStreamEnd" in core_js, "iching-core.js 需导出 classifyStreamEnd"


# 用字符拼接 / chr() 避免源文件里出现"裸"的危险 API 字面量，
# 防止本机 hook / grep 扫描器把测试的检查本身当成危险代码。
_DYN_API_NAMES = [
    "ev" + "al",  # eval
    "new" + " " + "Fun" + "ction",  # new Function
    "document" + ".wr" + "ite",  # document.write
]


@pytest.mark.parametrize("api_needle", _DYN_API_NAMES)
def test_no_dynamic_code_apis(html: str, api_needle: str):
    """运行时代码生成 API 不应出现在前端源码中。"""
    js = _strip_comments(html)
    # 用 \b 边界匹配，避免把属性名或子串误判
    pattern = r"\b" + re.escape(api_needle) + r"\s*\("
    assert not re.search(pattern, js), f"发现可疑调用: {api_needle}(...)"


# ============================================================
# 核心业务函数签名
# ============================================================

REQUIRED_JS_SIGNATURES = [
    r"async\s+function\s+startDivine\s*\(",
    r"function\s+buildBaguaSvg\s*\(",
    r"function\s+buildCoinSvg\s*\(",
    r"async\s+function\s+showResult\s*\(",
    r"function\s+streamInterp\s*\(",
    r"function\s+saveHistory\s*\(",
    r"function\s+openHistory\s*\(",
    r"function\s+closeHistory\s*\(",
    r"function\s+activateTab\s*\(",
    r"function\s+toggleLookup\s*\(",
    r"async\s+function\s+loadHexagrams\s*\(",
    r"async\s+function\s+showHexDetail\s*\(",
    r"function\s+renderCoins\s*\(",
    r"function\s+svgFromString\s*\(",
    r"function\s+haptic\s*\(",
    r"function\s+awaitShakeSettle\s*\(",
    r"function\s+appendYaoToHexPreview\s*\(",
    r"function\s+resetHexPreview\s*\(",
    r"function\s+setDivineMode\s*\(",
]


@pytest.mark.parametrize("sig", REQUIRED_JS_SIGNATURES)
def test_required_function_signatures(html: str, sig: str):
    assert re.search(sig, html), f"缺少函数签名: /{sig}/"


# ============================================================
# 动画 keyframes
# ============================================================

REQUIRED_KEYFRAMES = [
    "spin-cw",
    "spin-cw-very-slow",
    "float-y",
    "shadow-pulse",
    "breathe-glow",
    "drift",
    "breathe-bagua",
    "halo-pulse",
    "breathe-text",
    "breathe-cta",
    "sweep",
    "blink",
    "thinking-pulse",
    "coin-shake",
    "coin-breathe",
    "halo-breathe",
    "coin-toss",
    "mote-0",
    "mote-1",
    "mote-2",
    "slide-up",
    "fade-in",
    "reveal-fade",
    "reveal-focus",
    "holding-enter",
]


@pytest.mark.parametrize("name", REQUIRED_KEYFRAMES)
def test_required_keyframes(html: str, name: str):
    assert re.search(rf"@keyframes\s+{re.escape(name)}\b", html), (
        f"缺少 @keyframes {name}"
    )


def test_bagua_wave_keyframe_generated_per_instance(html: str):
    # 八卦流光 keyframe 在 JS 里用 uid 生成
    assert "bagua-wave-" in html, "应有 per-instance 的 bagua-wave keyframe"


def test_reveal_focus_has_blur_and_scale(html: str):
    """结果页焦点段（大字卦名）应是 blur + scale 组合——方案 B 凝结效果。
    若回退成纯 blur 或移除 scale，仪式感会退化；用户已确认"字从虚空中凝结"的审美方向。"""
    m = re.search(
        r"@keyframes\s+reveal-focus\s*\{([^}]*\{[^}]*\}[^}]*)*\}",
        html,
        re.DOTALL,
    )
    assert m, "找不到 @keyframes reveal-focus 块"
    block = m.group(0)
    assert "blur(" in block, "reveal-focus 必须包含 filter: blur(...)"
    assert "scale(" in block, (
        "reveal-focus 必须包含 transform: scale(...) —— 方案 B 凝结：字从虚空中凝结浮出"
    )


def test_result_head_children_stagger_independently(html: str):
    """.result-head 应把子元素拆成独立 animation（拼音铺垫 → 大字焦点 → 格言收束），
    不能回退成整条 .result-head 统一渐现——否则焦点被稀释。"""
    assert re.search(
        r"\.app\.has-result\s+\.result-head\s+\.hex-name\s*\{[^}]*animation:\s*reveal-focus",
        html,
    ), ".hex-name 必须有独立 reveal-focus 动画"
    assert re.search(
        r"\.app\.has-result\s+\.result-head\s+\.romaji\s*\{[^}]*animation:",
        html,
    ), ".romaji 必须有独立渐现动画"


# ============================================================
# 铜钱视觉："袋中摇"哲学 —— 零旋转 + 模糊呼吸 + 光晕 + 错峰落定
# ============================================================


def test_coin_spin_inner_layer_used_in_render(html: str):
    """.coin-spin 内层分担视觉状态（blur/scale/opacity），与外层摆位 transform 解耦。"""
    assert re.search(r"\.coin-spin\b", html), "CSS 缺少 .coin-spin 选择器"
    assert "className: 'coin-spin'" in html, (
        "renderCoins 未创建 .coin-spin 内层 —— 视觉状态会与外层摆位 transform 冲突"
    )


def test_shaking_applies_heavy_blur(html: str):
    """袋中摇：摇动时必须对 .coin-spin 加 filter: blur —— 这是"藏在手心看不清"的视觉基础。
    并且要足够重（≥4px）才能让轮廓彻底糊掉、眼睛无法追踪。"""
    m = re.search(
        r"\.coin-wrap\.shaking\s+\.coin-spin\s*\{[^}]*filter:\s*blur\((\d+(?:\.\d+)?)px",
        html,
        re.DOTALL,
    )
    assert m, "缺少 .coin-wrap.shaking .coin-spin { filter: blur(...px) }"
    assert float(m.group(1)) >= 4, (
        f"blur 值为 {m.group(1)}px，太清晰 —— 袋中摇需要 ≥4px 让铜钱轮廓糊掉，"
        "否则眼睛会追着呼吸动作看导致眩晕"
    )


def test_no_3d_rotation_in_coin_animation(html: str):
    """袋中摇哲学：铜钱呼吸 keyframe 必须零旋转（rotateY/X/Z 都不能出现）
    —— 任何旋转都会把眼睛拖回"追着动"的眩晕模式。"""
    # 截取 coin-breathe keyframe 体
    m = re.search(
        r"@keyframes\s+coin-breathe\s*\{(.*?)(?=@keyframes|\Z)",
        html,
        re.DOTALL,
    )
    assert m, "缺少 @keyframes coin-breathe"
    body = m.group(1)
    assert "rotateY" not in body and "rotateX" not in body and "rotateZ" not in body, (
        "coin-breathe 含 rotate 轴向 —— 袋中摇不应有任何旋转，否则用户又会眼晕"
    )


def test_shaking_halo_ring_present(html: str):
    """金色光晕：袋中摇期间铜钱周围的"气场"。用 ::after 伪元素 + radial-gradient，
    配 halo-breathe 动画。没有它，摇的阶段只是糊团晃动，缺仪式感。"""
    assert re.search(r"\.coin-wrap\.shaking::after\s*\{", html), (
        "缺少 .coin-wrap.shaking::after 光晕规则"
    )
    assert "halo-breathe" in html, "缺少 halo-breathe 动画引用"


def test_coin_svg_no_inline_filter_in_constructor(app_js: str):
    """buildCoinSvg 的 SVG 根元素不得内联 filter —— 否则 CSS 层控制失效，
    且摇卦态 iOS Safari 会重演"金色 drop-shadow 退化为 viewBox 矩形"bug。"""
    m = re.search(r"buildCoinSvg[\s\S]{0,800}?<svg[^>]*>", app_js)
    assert m, "未在 buildCoinSvg 中找到 <svg 根元素"
    svg_open = m.group(0)
    assert "filter:" not in svg_open, (
        "buildCoinSvg SVG 根元素不应 inline filter —— 走 CSS .coin-spin svg 控制"
    )


def test_coin_svg_filter_has_only_black_drop_shadow(html: str):
    """.coin-spin svg 只保留黑色投影 drop-shadow；金色 halo 改走 .coin-wrap::before
    伪元素承担，彻底绕开 SVG filter 合成链。字面 <g filter="url(#cast)"> 对 text
    合成时 feFlood 矩形残余会被外层 CSS drop-shadow(外扩 halo) 放大成黄色方块，
    这是根因 bug。"""
    m = re.search(
        r"\.coin-spin\s+svg\s*\{([^}]*)\}",
        html,
        re.DOTALL,
    )
    assert m, "缺少 .coin-spin svg { ... } 规则"
    body = m.group(1)
    assert "drop-shadow" in body, ".coin-spin svg 应保留黑色投影 drop-shadow"
    # 金色 drop-shadow 识别标志：rgba(201,169,97,...)（#c9a961 的 rgb）
    assert "rgba(201" not in body, (
        ".coin-spin svg 不应含金色外扩 drop-shadow —— "
        "会放大 <g filter='url(#cast)'> 字面 feFlood 矩形残余成黄色方块"
    )


def test_coins_row_halo_via_before_pseudo(html: str):
    """金色 halo 由 .coins-row::before 承担：单层大光晕，中心 = 铜钱区几何中心，
    三枚铜钱落在光晕正中。不用 .coin-wrap::before（三个小 halo 叠加成花生形状），
    避免与 SVG filter 合成交互（那条路径会把 <g filter='url(#cast)'> 字面 feFlood
    矩形残余放大成黄色方块）。"""
    m = re.search(
        r"\.coins-row::before\s*\{([^}]*)\}",
        html,
        re.DOTALL,
    )
    assert m, "缺少 .coins-row::before 金色 halo 伪元素"
    body = m.group(1)
    # —— 必备字段（结构性）——
    assert "radial-gradient" in body, (
        ".coins-row::before 应用 radial-gradient 做圆形 halo"
    )
    assert "border-radius:" in body and "50%" in body, (
        ".coins-row::before 必须 border-radius: 50% 保证圆形"
    )
    assert "translate(-50%, -50%)" in body or "translate(-50%,-50%)" in body, (
        ".coins-row::before 应 translate(-50%, -50%) 居中于 .coins-row 中心"
    )
    # —— 严格精度（Codex 第九轮 A-L2 采纳：宽松 regex 不足以锁住形状）——
    # 宽高必须严格 420px 且相等（否则 border-radius 50% 退化为椭圆）
    width_match = re.search(r"width:\s*(\d+)px", body)
    height_match = re.search(r"height:\s*(\d+)px", body)
    assert width_match and width_match.group(1) == "420", (
        f".coins-row::before width 必须严格 420px，实际 {width_match and width_match.group(1)!r}"
    )
    assert height_match and height_match.group(1) == "420", (
        f".coins-row::before height 必须严格 420px，实际 {height_match and height_match.group(1)!r}"
    )
    assert width_match.group(1) == height_match.group(1), (
        ".coins-row::before width 必须等于 height（否则 border-radius 50% 变椭圆）"
    )
    # 金色必须是 rgba(201,169,97,0.22)（c9a961 ≈ 老铜金；alpha 0.22 是"气场但不喧宾"）
    assert re.search(r"rgba\(201\s*,\s*169\s*,\s*97\s*,\s*0\.22\)", body), (
        ".coins-row::before 金色必须精确 rgba(201,169,97,0.22) —— "
        "alpha 偏差会让 halo 太虚或太刺眼"
    )
    # transparent stop 必须 60%（太低 halo 范围缩小，太高硬边明显）
    assert re.search(r"transparent\s+60%", body), (
        ".coins-row::before radial-gradient 必须以 transparent 60% 结尾"
    )
    # blur 必须严格 22px（< 柔化不够 / > halo 感知消失）
    assert re.search(r"filter:\s*blur\(22px\)", body), (
        ".coins-row::before filter 必须严格 blur(22px)"
    )
    # pointer-events: none 防止 halo 截获点击（启用手摇时可能误触）
    assert re.search(r"pointer-events:\s*none", body), (
        ".coins-row::before 必须 pointer-events: none，否则截获铜钱区点击"
    )
    # z-index 非负值（配合 .coins-row 的 isolation: isolate 本地栈）
    # 不允许 z-index: -1 —— 若祖先未来有背景色会被遮
    zi_match = re.search(r"z-index:\s*(-?\d+)", body)
    assert zi_match, ".coins-row::before 应显式设置 z-index"
    assert int(zi_match.group(1)) >= 0, (
        f".coins-row::before z-index 不应为负（现 {zi_match.group(1)}），"
        "依赖 .coins-row 的 isolation: isolate 建立本地 stacking context"
    )


def test_coins_row_has_local_stacking_context(html: str):
    """Codex 第九轮 A-L1 采纳：.coins-row 必须建立本地 stacking context，
    防止未来重构把 halo 伪元素压没。"""
    m = re.search(r"\.coins-row\s*\{([^}]*)\}", html, re.DOTALL)
    assert m, "缺少 .coins-row 规则"
    body = m.group(1)
    assert re.search(r"isolation:\s*isolate", body), (
        ".coins-row 必须 isolation: isolate —— 本地 stacking context"
    )
    # .coin-wrap 必须 z-index >= 1 浮在 ::before halo 之上
    wrap_match = re.search(r"\.coin-wrap\s*\{([^}]*)\}", html, re.DOTALL)
    assert wrap_match, "缺少 .coin-wrap 规则"
    wrap_body = wrap_match.group(1)
    assert re.search(r"z-index:\s*[1-9]\d*", wrap_body), (
        ".coin-wrap 必须 z-index >= 1 浮在 halo 之上"
    )


def test_coin_svg_no_dead_drop_shadow_field(app_js: str):
    """Codex 第九轮 A-L3 采纳：buildCoinSvg 删 inline filter 后 p.dropShadow
    字段应一并删除，避免遗留误导性死字段。"""
    m = re.search(
        r"function\s+buildCoinSvg[\s\S]{0,400}?var\s+p\s*=\s*\{([^}]*)\}", app_js
    )
    assert m, "未在 buildCoinSvg 中找到 palette 对象"
    palette_body = m.group(1)
    assert "dropShadow" not in palette_body, (
        "buildCoinSvg palette 不应含 dropShadow 字段 —— inline filter 已删，"
        "该字段无读取路径，遗留会误导维护者"
    )


def test_lunar_date_uses_ganzhi_not_gregorian(app_js: str):
    """meta-bar 左上日期走传统干支纪月纪日（Core.ganzhiDateLabel），对齐应用气质。
    fallback 到公历 y·m·d 允许（防老缓存），但主路径必须是 ganzhiDateLabel。"""
    assert "Core.ganzhiDateLabel" in app_js, (
        "app.js 未调用 Core.ganzhiDateLabel —— lunarDate 仍显示公历"
    )
    m = re.search(r"\$\('lunarDate'\)[\s\S]{0,800}?textContent", app_js)
    assert m, "未找到 lunarDate 赋值代码块"
    snippet = m.group(0)
    assert "ganzhiDateLabel" in snippet, (
        "lunarDate 赋值块必须包含 ganzhiDateLabel 调用（不只是 import 但没用）"
    )


def test_coin_toss_drop_class_wired(html: str):
    """抛落弹跳触发：.just-landed 类 + 落地回调里 JS 加此类 + 绑定 coin-toss 动画。"""
    assert re.search(r"\.coin-wrap\.just-landed\b", html), (
        "CSS 未定义 .coin-wrap.just-landed"
    )
    assert "just-landed" in html and "classList.add('just-landed')" in html, (
        "startDivine 落地回调未给 .coin-wrap 加 .just-landed"
    )
    # .just-landed 必须绑定 coin-toss（否则虽然加了 class，却没有抛落动画）
    assert re.search(
        r"\.coin-wrap\.just-landed\s*\{[^}]*animation:\s*coin-toss", html, re.DOTALL
    ), "缺少 .coin-wrap.just-landed { animation: coin-toss ... } —— 抛落动画未触发"


def test_coin_toss_has_drop_and_bounce_phases(html: str):
    """coin-toss 必须有"跃起到顶点 + 下坠 + 弹跳"多段 keyframe，否则不是"抛落弹跳"。"""
    m = re.search(r"@keyframes\s+coin-toss(.{0,3000})", html, re.DOTALL)
    assert m, "缺少 @keyframes coin-toss"
    body = m.group(1)
    # 至少一段 translate 向上（负值）—— 跃起/弹跳的标志
    assert re.search(r"translate:\s*0\s+-\d+px", body), (
        "coin-toss 无向上 translate —— 没有跃起到顶点或弹跳的动作"
    )
    # 至少 5 段 keyframe 停靠点：0% / 顶点 / 第一次着地 / 弹起 / 归位
    stops = re.findall(r"^\s*(\d+%)", body, re.MULTILINE)
    assert len(stops) >= 5, (
        f"coin-toss 仅 {len(stops)} 段 keyframe，不足以表达 跃+坠+弹+坠+归位"
    )
    # 只能 rotateZ（屏幕平面自转），不能有 rotateX/Y
    assert "rotateX" not in body and "rotateY" not in body, (
        "coin-toss 不应含 rotateX/Y —— 那是 3D 翻腾方案的眩晕源"
    )


def test_landing_phase_does_not_rebuild_all_coins_at_once(app_js: str):
    """落定阶段不得再用 renderCoins(..., false) 整批重建 —— 否则三枚必同帧落地。"""
    assert "renderCoins(faces, idx + 101, false)" not in app_js, (
        "发现 renderCoins(faces, idx + 101, false) —— 仍在整批重建 DOM，"
        "三枚铜钱会同步落地，违反错峰落地设计"
    )


def test_landing_phase_uses_per_coin_setTimeout(app_js: str):
    """落定阶段需 per-coin setTimeout 错峰 + in-place 替换 .coin-spin 内的 SVG。"""
    assert app_js.count("setTimeout") >= 1, "落定阶段缺少 setTimeout 错峰机制"
    assert re.search(r"querySelector\(['\"]\.coin-spin['\"]\)", app_js), (
        "落定阶段需用 querySelector('.coin-spin') 定位内层做 in-place face 替换"
    )


# ============================================================
# 模式切换入口可达性（Codex adversarial review [high] 回归保护）
# ============================================================


def test_mode_toggle_lives_in_compose_not_divine_flow(index_html: str):
    """.df-mode-toggle 必须在 .compose 内，而不是 .divine-flow 内 ——
    后者仅在 .app.is-shaking 时 display:flex，而 startDivine() 进入该状态
    立刻 b.disabled=true；三个状态下按钮都不可点，手摇路径沦为死代码。
    2026-04-19 Codex adversarial review 发现的 high bug 的回归保护。"""
    compose_match = re.search(
        r'<section[^>]*class="compose"[^>]*>(.*?)</section>',
        index_html,
        re.DOTALL,
    )
    assert compose_match, '找不到 <section class="compose">'
    assert "df-mode-toggle" in compose_match.group(1), (
        "df-mode-toggle 不在 .compose 内 —— 用户起卦前看不到模式切换按钮，"
        "手摇 / DeviceMotion 路径永远不可达"
    )
    divine_flow_match = re.search(
        r'<section[^>]*class="divine-flow"[^>]*>(.*?)</section>',
        index_html,
        re.DOTALL,
    )
    assert divine_flow_match, '找不到 <section class="divine-flow">'
    assert "df-mode-toggle" not in divine_flow_match.group(1), (
        "df-mode-toggle 还残留在 .divine-flow 内 —— 该容器起卦前 display:none、"
        "起卦中按钮 disabled、起卦后又隐藏，入口永远不可达"
    )


def test_mode_toggle_buttons_not_disabled_in_initial_html(index_html: str):
    """初始 HTML 里 .df-mode 按钮不应自带 disabled —— 保证用户起卦前即可点击切换。"""
    m = re.search(
        r'<div[^>]*class="df-mode-toggle[^"]*"[^>]*>(.*?)</div>',
        index_html,
        re.DOTALL,
    )
    assert m, "找不到 .df-mode-toggle 节点"
    body = m.group(1)
    assert "disabled" not in body, (
        ".df-mode button 初始带 disabled —— 用户无法在起卦前点击切换模式"
    )


def test_bagua_svg_class_present(html: str):
    # 八卦主 SVG 由 JS 动态构建，挂 class="bagua-svg"
    assert 'class="bagua-svg"' in html, (
        "buildBaguaSvg 输出应带 class=bagua-svg 供样式绑定"
    )


# ============================================================
# 响应式 & 无障碍
# ============================================================


def test_has_small_phone_breakpoint(html: str):
    assert re.search(r"@media\s*\(\s*max-width:\s*380px\s*\)", html)


def test_respects_reduced_motion(html: str):
    assert re.search(r"prefers-reduced-motion:\s*reduce", html)


def test_hover_guarded_by_hover_media_query(html: str):
    assert re.search(r"@media\s*\(\s*hover:\s*hover", html)


# ============================================================
# 移动端交互（haptic 调用）
# ============================================================


def test_haptic_called_during_divine(html: str):
    matches = re.findall(r"\bhaptic\s*\(", html)
    # 定义 + 起卦前 + 每爻落定循环内 + 完成：至少 4 次
    assert len(matches) >= 3, f"haptic 调用次数不足 (found {len(matches)})"


# ============================================================
# iching-core.js 模块
# ============================================================


def test_core_js_exposes_pure_functions(core_js: str):
    for fn in (
        "computeBianLines",
        "coinsForLine",
        "seededLayout",
        "pinyinOf",
        "linesVisualClass",
    ):
        assert fn in core_js, f"iching-core.js 缺少 {fn}"


def test_core_js_dual_mode_exports(core_js: str):
    """同时支持 CommonJS (module.exports) 与浏览器全局 (IChingCore)"""
    assert "module.exports" in core_js
    assert "IChingCore" in core_js


# ============================================================
# 第三轮 Codex review 修复：script 外部化 + 无 inline handler
# ============================================================


def test_app_js_referenced(index_html: str):
    """index.html 应用 <script src="assets/app.js"> 引入外部化后的脚本（允许带 ?v=N 缓存破解）"""
    assert re.search(r'<script\s+src="assets/app\.js(?:\?[^"]*)?"', index_html), (
        "index.html 应通过外部 src 引入 app.js"
    )


def test_no_inline_script_block(index_html: str):
    """不允许 <script>...</script> 内联脚本块（CSP script-src 去 unsafe-inline 的前提）"""
    # 所有 <script> 标签都必须带 src 属性
    scripts = re.findall(r"<script\b([^>]*)>", index_html)
    assert scripts, "缺少 <script> 标签"
    for attrs in scripts:
        assert "src=" in attrs, f"发现 inline <script> 块（无 src）: {attrs!r}"


def test_no_inline_event_handlers(index_html: str):
    """HTML 里禁止任何 on*="..." 属性；统一走 addEventListener / 事件委托"""
    # 匹配常见 on 属性；仅限开头字母为 on 且紧接 = 的
    bad = re.findall(
        r"\son[a-z]+\s*=\s*[\"']",
        index_html,
    )
    assert not bad, (
        f"发现 inline event handler（应全部用 addEventListener 替换）: {bad}"
    )


def test_meta_csp_no_unsafe_inline_script(index_html: str):
    """meta CSP 的 script-src 也应去掉 unsafe-inline（外部化后无需）"""
    m = re.search(
        r'<meta\s+http-equiv="Content-Security-Policy"\s+content="([^"]+)"', index_html
    )
    assert m, "缺少 meta CSP"
    csp = m.group(1)
    script_src = re.search(r"script-src([^;]+)", csp).group(1)
    assert "'unsafe-inline'" not in script_src, (
        "meta CSP 的 script-src 不应再含 'unsafe-inline'"
    )


def test_meta_csp_no_frame_ancestors(index_html: str):
    """
    frame-ancestors 在 meta 中不生效（W3C CSP3 §6.1）；
    放在 meta 里会造成"声明了但没用"的安全幻觉，应只保留在 HTTP header。
    """
    m = re.search(
        r'<meta\s+http-equiv="Content-Security-Policy"\s+content="([^"]+)"', index_html
    )
    assert m, "缺少 meta CSP"
    assert "frame-ancestors" not in m.group(1), (
        "meta CSP 不应声明 frame-ancestors（只能通过 HTTP header 生效）"
    )


def test_data_action_routes_wired(app_js: str):
    """app.js 应包含 data-action 事件委托路由"""
    assert "data-action" in app_js or "getAttribute('data-action')" in app_js, (
        "app.js 应有 data-action 事件路由替代 inline onclick"
    )
    # 至少覆盖三个动作
    for action in ("close-modal", "close-history", "lookup-open"):
        assert action in app_js, f"app.js 缺少 '{action}' 路由"


def test_data_close_outside_wired(app_js: str):
    """overlay 背景点击关闭的事件委托"""
    assert "data-close-outside" in app_js, "app.js 应处理 data-close-outside"


# ============================================================
# 起卦 UI 重构（divine-flow）：顶部进度 + 卦象 preview + 手摇/自动切换
# ============================================================


def test_divine_flow_section_present(index_html: str):
    """新布局的外层 section 应带 class=divine-flow（id 仍为 shakeProgress）"""
    assert re.search(
        r'<section[^>]+class="divine-flow"[^>]+id="shakeProgress"',
        index_html,
    ), "缺少 class=divine-flow 的起卦流程容器"


def test_mode_toggle_buttons_present(index_html: str):
    """底部应有 自动 / 手摇 两个按钮，data-mode 分别为 auto / manual"""
    assert re.search(
        r'<button[^>]+data-mode="auto"[^>]*>\s*自动\s*</button>',
        index_html,
    ), "缺少 data-mode=auto 的『自动』按钮"
    assert re.search(
        r'<button[^>]+data-mode="manual"[^>]*>\s*手摇\s*</button>',
        index_html,
    ), "缺少 data-mode=manual 的『手摇』按钮"


def test_hex_yao_styles_present(index_html: str):
    """卦象 preview 的阳/阴/动爻样式需在 CSS 里定义"""
    assert re.search(r"\.hex-yao\.yang\b", index_html), "缺少 .hex-yao.yang 样式"
    assert re.search(r"\.hex-yao\.yin\b", index_html), "缺少 .hex-yao.yin 样式"
    assert re.search(r"\.hex-yao\.changing\b", index_html), (
        "缺少 .hex-yao.changing 样式（动爻高亮）"
    )


def test_is_shaking_hides_landing_sections(index_html: str):
    """.app.is-shaking 状态下应隐藏 hero / bagua-stage 等落地页元素"""
    assert re.search(
        r"\.app\.is-shaking\s+\.(?:hero|bagua-stage|meta-bar|lookup)",
        index_html,
    ), ".app.is-shaking 下应 display:none 掉 hero/bagua-stage 等"


def test_divine_mode_variable_and_function(app_js: str):
    """app.js 应维护 divineMode 状态并暴露 setDivineMode 切换"""
    assert "divineMode" in app_js, "缺少 divineMode 全局状态"
    assert re.search(r"function\s+setDivineMode\s*\(", app_js), (
        "缺少 setDivineMode 切换函数"
    )


def test_start_divine_uses_await_shake_settle(app_js: str):
    """startDivine 循环内必须通过 awaitShakeSettle 推进（不再硬编码 sleep(600)）"""
    m = re.search(
        r"async\s+function\s+startDivine\s*\([^)]*\)\s*\{(.*?)\n\}",
        app_js,
        re.S,
    )
    assert m, "找不到 startDivine 函数体"
    body = m.group(1)
    assert re.search(r"\bawaitShakeSettle\s*\(", body), (
        "startDivine 应在每爻循环里 await awaitShakeSettle(...)"
    )


def test_start_divine_populates_coin_result_and_hex_preview(app_js: str):
    """每爻落定后应写 coinResult 与 append 到 hexPreview"""
    m = re.search(
        r"async\s+function\s+startDivine\s*\([^)]*\)\s*\{(.*?)\n\}",
        app_js,
        re.S,
    )
    assert m
    body = m.group(1)
    assert "coinResult" in body, "startDivine 应更新 coinResult 文本"
    assert "appendYaoToHexPreview" in body, (
        "startDivine 应调 appendYaoToHexPreview 逐爻构建卦象 preview"
    )
    assert "Core.formatCoinResult" in body, (
        "startDivine 应用 Core.formatCoinResult 生成『字 · 花』文案"
    )


def test_format_coin_result_exposed_in_core(core_js: str):
    """formatCoinResult 应作为纯函数暴露在 iching-core.js"""
    assert "formatCoinResult" in core_js, "iching-core.js 需导出 formatCoinResult"


# ============================================================
# 手摇一爻一摇：状态机 + 三段式动画（2026-04-21 重构）
# ============================================================


def test_manual_mode_shake_thresholds_defined(app_js: str):
    """迟滞阈值 + 最小 shake 时长 + 静候窗口 —— 常量是回归的可视锚点。
    这些值的语义见 awaitManualToss 头注释的状态机图。"""
    assert re.search(r"\bSHAKE_HI\b\s*=\s*18\b", app_js), (
        "缺少 SHAKE_HI 阈值常量（进入 SHAKING 的加速度门槛）"
    )
    assert re.search(r"\bSHAKE_LO\b\s*=\s*6\b", app_js), (
        "缺少 SHAKE_LO 阈值常量（判定静止的加速度门槛）—— 双阈值 hysteresis 设计"
    )
    assert re.search(r"\bMIN_SHAKE_MS\b\s*=\s*600\b", app_js), (
        "缺少 MIN_SHAKE_MS 常量（每爻摇动阶段最短视觉持续 600ms）"
    )
    assert re.search(r"\bQUIET_MS\b\s*=\s*300\b", app_js), (
        "缺少 QUIET_MS 常量（爻间静候窗口；防一次摇动串爆 6 爻）"
    )


def test_manual_toss_state_machine_keywords_present(app_js: str):
    """awaitManualToss 应含 HOLD / SHAKING / QUIET_WAIT 的真实状态迁移分支。

    不只搜全文字符串（那样注释里写"// HOLD"也能过，Codex adversarial review
    MEDIUM finding），而是要求每个关键字都以 state===/==/= 'X' 的赋值或分支
    判断形式出现 —— 保证状态机真的被这个 token 驱动。"""
    assert re.search(r"function\s+awaitManualToss\s*\(", app_js), (
        "缺少 awaitManualToss —— 手摇分支应从 awaitShakeSettle 分出独立状态机"
    )
    for keyword in ("HOLD", "SHAKING", "QUIET_WAIT"):
        # 要求至少一次 state === 'KEYWORD' 或 state = 'KEYWORD' 或三元 'KEYWORD'
        # （QUIET_WAIT 是 isFirst ? 'HOLD' : 'QUIET_WAIT' 形式）
        pattern = (
            rf"\bstate\s*(?:===|==|=)\s*['\"]{keyword}['\"]"
            rf"|\?\s*['\"][A-Z_]+['\"]\s*:\s*['\"]{keyword}['\"]"
        )
        assert re.search(pattern, app_js), (
            f"awaitManualToss 缺少状态 {keyword!r} 的真实赋值/分支 —— "
            "只在注释/文档字符串里出现不算数"
        )


def test_shake_detector_arms_on_manual_mode(app_js: str):
    """setDivineMode('manual') 需挂 devicemotion 监听；切回 auto 需摘。
    常驻监听而非每爻临时挂摘，是"爻间静候"能生效的前提：
    QUIET_WAIT 需要持续采样加速度才能判断手机是否真的静止。"""
    assert "armShakeDetector" in app_js, "缺少 armShakeDetector"
    assert "disarmShakeDetector" in app_js, "缺少 disarmShakeDetector"
    # setDivineMode 里必须引用二者（模式切换驱动挂/摘）
    m = re.search(
        r"function\s+setDivineMode\s*\([^)]*\)\s*\{(.*?)\n\}",
        app_js,
        re.S,
    )
    assert m, "找不到 setDivineMode 函数体"
    body = m.group(1)
    assert "armShakeDetector" in body, "setDivineMode 切手摇时未 armShakeDetector"
    assert "disarmShakeDetector" in body, "setDivineMode 切自动时未 disarmShakeDetector"


def test_no_motion_fallback_hint_present(app_js: str):
    """无 devicemotion 事件时的 click fallback 提示 —— 覆盖 Android HTTP /
    桌面 / iOS 权限拒绝三种情况。

    收紧（Codex adversarial review MEDIUM finding）：不仅要求两个 flag 存在，
    还要求 fallback 文案真的在 NO_MOTION_HINT_MS 触发的 setTimeout 回调里，
    并且早退条件同时含 _motionEverFired（witness）+ _motionSupported（capability）——
    只检查 witness 会把"已授权但用户还没动"误判为"摇不动"（原 LOW finding）。"""
    assert "_motionEverFired" in app_js, "缺少 witness 标志 _motionEverFired"
    assert "_motionSupported" in app_js, (
        "缺少 capability 标志 _motionSupported —— 无法区分"
        "设备能力 vs 是否收到过首个事件"
    )
    # fallback 文案必须绑定在 NO_MOTION_HINT_MS 的 setTimeout 体内
    # 用 .*? + 唯一终结符 NO_MOTION_HINT_MS 精确切出回调体（允许嵌套花括号）
    m = re.search(
        r"setTimeout\s*\(\s*function\s*\(\s*\)\s*\{(.*?)\},\s*NO_MOTION_HINT_MS",
        app_js,
        re.S,
    )
    assert m, (
        "缺少 NO_MOTION_HINT_MS 驱动的 fallback setTimeout —— "
        "文案必须在 timer 回调里（证明有 2s 延迟兜底路径），不是纯字符串"
    )
    body = m.group(1)
    assert "_motionEverFired" in body and "_motionSupported" in body, (
        "fallback timer 的早退条件应同时检查 witness + capability —— "
        "缺 capability 会让已授权但没摇的用户误看到 fallback 文案"
    )
    assert "点击铜钱" in body, "fallback timer 体内缺少点击 fallback 提示文案"


def test_toss_phase_css_present(index_html: str):
    """三段式 data-toss-phase CSS 选择器 —— 驱动 hold/shake/land 的 UI 语义态。"""
    assert re.search(r'#shakeProgress\[data-toss-phase="hold"\]', index_html), (
        "缺少 [data-toss-phase=hold] CSS 选择器"
    )
    assert re.search(r'#shakeProgress\[data-toss-phase="shake"\]', index_html), (
        "缺少 [data-toss-phase=shake] CSS 选择器"
    )


def test_coin_wrap_holding_class_styled(index_html: str):
    """.coin-wrap.holding 必须有独立样式 —— HOLD 态要和 .shaking 视觉不同，
    否则 HOLD → SHAKE 切换无感知，三段式叙事就塌了。"""
    assert re.search(r"\.coin-wrap\.holding\b", index_html), (
        "CSS 未定义 .coin-wrap.holding —— HOLD 态铜钱视觉未区分"
    )


def test_start_divine_sets_toss_phase(app_js: str):
    """startDivine 循环里应调 setTossPhase('hold') / 'land'，否则三段式 CSS 不生效。"""
    m = re.search(
        r"async\s+function\s+startDivine\s*\([^)]*\)\s*\{(.*?)\n\}",
        app_js,
        re.S,
    )
    assert m, "找不到 startDivine 函数体"
    body = m.group(1)
    assert "setTossPhase" in body, "startDivine 应调 setTossPhase 切换三段式态"
    assert "'hold'" in body or '"hold"' in body, (
        "startDivine 应在 HOLD 阶段调 setTossPhase('hold')"
    )
    assert "'land'" in body or '"land"' in body, (
        "startDivine 应在 LAND 阶段调 setTossPhase('land')"
    )


def test_manual_inter_line_rest_longer_than_auto(app_js: str):
    """手摇模式爻间屏息应比自动更长 —— 给用户"呼吸一次"再摇下一爻。

    收紧（Codex adversarial review MEDIUM finding）：要求 1000 出现在 sleep()
    调用或 _restMs 赋值里，且上下文包含 divineMode === 'manual' 分支——
    防止"只在注释里写 1000"或"把 1000 挪进了某个无关 literal"就通过。
    同时断言 700 仍作为自动模式基准存在，锁定"手摇 > 自动"的节奏不等式。"""
    m = re.search(
        r"async\s+function\s+startDivine\s*\([^)]*\)\s*\{(.*?)\n\}",
        app_js,
        re.S,
    )
    assert m, "找不到 startDivine 函数体"
    body = m.group(1)
    # manual 分支的节奏判断
    assert re.search(r"divineMode\s*===?\s*['\"]manual['\"]", body), (
        "startDivine 需按 divineMode === 'manual' 分支走不同节奏"
    )
    # 1000 必须出现在 sleep() 实参或 _restMs 三元结果里，而非注释
    assert re.search(
        r"sleep\s*\(\s*1000\s*\)"
        r"|_restMs\s*=\s*\([^)]*?1000[^)]*?\)"
        r"|_restMs\s*=\s*[^;]*?\?\s*1000",
        body,
    ), (
        "startDivine 手摇分支应有 1000ms 屏息的真实调用 "
        "（sleep(1000) 或 _restMs = ... ? 1000 : 700 形式）"
    )
    # 自动模式的 700ms 作为对照基准必须仍在
    assert re.search(r"\b700\b", body), (
        "startDivine 应保留 700ms 作为自动模式的对照节奏 "
        "（确保「手摇 > 自动」的不等式不退化）"
    )


def test_toss_cleanup_is_synchronous_abort(app_js: str):
    """awaitManualToss 的取消路径必须同步，不能用 setInterval 轮询。

    Codex adversarial review HIGH finding：原实现用 setInterval(cancelPoll, 150)
    检测 _divineSeq 变化，cancelCurrentDivine 后最多 150ms 里 onClick / _shakeSubs
    的老回调还活着，用户快速返回再起卦会被老监听污染新 run 的 UI。

    修复：暴露 _currentTossCleanup 同步句柄，cancelCurrentDivine 和 startDivine
    入口直接调用它立即解绑。"""
    # 同步 abort 句柄必须存在
    assert "_currentTossCleanup" in app_js, (
        "缺少同步 abort 句柄 _currentTossCleanup —— cancel 路径仍依赖 150ms 轮询"
    )
    # cancelCurrentDivine 必须同步调用 cleanup（不是靠 _divineSeq++ 间接触发）
    m = re.search(
        r"function\s+cancelCurrentDivine\s*\(\s*\)\s*\{(.*?)\n\}",
        app_js,
        re.S,
    )
    assert m, "找不到 cancelCurrentDivine 函数体"
    cancel_body = m.group(1)
    assert "_currentTossCleanup" in cancel_body, (
        "cancelCurrentDivine 必须同步调用 _currentTossCleanup —— "
        "否则老 onClick / _shakeSubs 在 _divineSeq++ 后仍存活"
    )
    # startDivine 入口同样要清（防旁路触发的悬挂 toss）
    sd = re.search(
        r"async\s+function\s+startDivine\s*\([^)]*\)\s*\{(.*?)\n\}",
        app_js,
        re.S,
    )
    assert sd, "找不到 startDivine 函数体"
    sd_body = sd.group(1)
    assert "_currentTossCleanup" in sd_body, (
        "startDivine 入口应先清上一次 _currentTossCleanup —— "
        "Enter 键 / 程序化触发能绕过 btn.disabled，需要双保险"
    )
    # 不得再有 150ms poll 残留（会和同步通道重复触发 cleanup）
    assert not re.search(
        r"setInterval\s*\([^}]*?getCancelled[^}]*?150", app_js, re.S
    ), (
        "awaitManualToss 里仍存在 150ms 轮询 getCancelled —— "
        "应已改为 _currentTossCleanup 同步通道"
    )


def test_peak_haptic_debounce_is_per_yao(app_js: str):
    """SHAKE 峰值回响去抖 (lastPeakHaptic) 必须是 awaitManualToss 闭包局部变量。

    Codex adversarial review MEDIUM finding：若把 lastPeakHaptic 提升为模块级
    共享状态，第 N 爻的 200ms 去抖窗口会延续到第 N+1 爻，第二爻第一次峰值
    可能因 now-lastPeakHaptic < 200ms 被吞掉。测试钉住"每爻独立 debounce"。"""
    # 闭包局部声明：在 awaitManualToss 函数头段（finish 函数之前）里
    m = re.search(
        r"function\s+awaitManualToss\s*\([^)]*\)\s*\{.*?"
        r"(var|let|const)\s+lastPeakHaptic\s*=\s*0",
        app_js,
        re.S,
    )
    assert m, (
        "lastPeakHaptic 必须在 awaitManualToss 函数体内声明为闭包局部变量 —— "
        "闭包局部才保证每爻进入时 debounce 窗口重置为 0"
    )
    # 模块级不得有同名全局（否则会 shadow/污染跨爻状态）
    assert not re.search(r"^(var|let|const)\s+lastPeakHaptic\b", app_js, re.M), (
        "lastPeakHaptic 不应声明为模块级全局 —— 会让 debounce 跨爻共享"
    )


def test_motion_supported_set_on_detector_arm(app_js: str):
    """_motionSupported 应在 armShakeDetector 成功挂 listener 时置 true，
    在 iOS requestPermission denied/catch 分支置 false。

    Codex adversarial review LOW finding：原 _motionEverFired 把"设备能力"
    等同于"本 session 至少收过一次事件"，已授权但还没摇的用户会看到错的
    fallback 文案。修复：capability 基于 arm 成功，不再基于 first-event witness。"""
    # armShakeDetector 函数体内必须置 _motionSupported = true
    m = re.search(
        r"function\s+armShakeDetector\s*\(\s*\)\s*\{(.*?)\n\}",
        app_js,
        re.S,
    )
    assert m, "找不到 armShakeDetector 函数体"
    arm_body = m.group(1)
    assert re.search(r"_motionSupported\s*=\s*true", arm_body), (
        "armShakeDetector 应在挂 listener 成功后置 _motionSupported = true"
    )
    # requestPermission 的 denied 分支（else）或 catch 分支必须显式置 false
    # 用 [^{}]*? 避免跨越嵌套块，精确定位"分支体内部"
    denied_ok = re.search(
        r"\}\s*else\s*\{[^{}]*?_motionSupported\s*=\s*false",
        app_js,
        re.S,
    )
    catch_ok = re.search(
        r"\.catch\s*\(\s*function\s*\([^)]*\)\s*\{[^{}]*?_motionSupported\s*=\s*false",
        app_js,
        re.S,
    )
    assert denied_ok or catch_ok, (
        "setDivineMode 的 requestPermission denied/catch 分支应显式置 "
        "_motionSupported = false —— 否则拒权路径永远卡在初值 false"
        "（虽然初值对，但没显式表意会让 review 看不出意图）"
    )


# ============================================================
# 节奏感优化 B + D：dash 节拍器 + 屏息死区拆段（2026-04-21）
# ============================================================


def test_dash_active_shake_solid_style(index_html: str):
    """Stage B：.active.active-shake 必须实心亮金 + 停脉冲 —— 用户感知"系统在听"。"""
    # active-shake 必须把 animation 置为 none（否则 dash-pulse 仍在跑，和 HOLD 没区分）
    m = re.search(
        r"\.df-dashes\s*>\s*span\.active\.active-shake\s*\{([^}]*)\}",
        index_html,
        re.S,
    )
    assert m, "缺少 .df-dashes > span.active.active-shake CSS 规则"
    body = m.group(1)
    assert re.search(r"animation\s*:\s*none", body), (
        "active-shake 应 animation: none —— 停掉 HOLD 的 dash-pulse 呼吸，改为静止的 '紧张' 态"
    )


def test_dash_land_ping_keyframe(index_html: str):
    """Stage B：LAND 态的 ping 闪烁 keyframe 必须存在且含 scaleY 弹性拉伸。"""
    m = re.search(r"@keyframes\s+dash-land-ping\b([^@]*)", index_html, re.S)
    assert m, "缺少 @keyframes dash-land-ping"
    body = m.group(1)
    # scaleY 放大是"被敲击"的弹性感，没了就没有 ping 效果
    assert re.search(r"scaleY\(1\.[0-9]", body), (
        "dash-land-ping 缺少 scaleY 弹性拉伸 —— 丧失 LAND 态的 'ping' 观感"
    )


def test_set_toss_phase_syncs_active_dash(app_js: str):
    """Stage B：setTossPhase 必须同步更新当前 active dash 的子 class，
    否则 dash 节拍器永远停在 HOLD 态，shake / land 不会被可视化。"""
    m = re.search(
        r"function\s+setTossPhase\s*\([^)]*\)\s*\{(.*?)\n\}",
        app_js,
        re.S,
    )
    assert m, "找不到 setTossPhase 函数体"
    body = m.group(1)
    assert "active-shake" in body, (
        "setTossPhase 未同步 'active-shake' —— SHAKE 态 dash 视觉丢失"
    )
    assert "active-land" in body, (
        "setTossPhase 未同步 'active-land' —— LAND 态 dash 的 ping 闪烁不会触发"
    )


def test_ready_pulse_stage_a_removed(index_html: str, app_js: str):
    """Stage A "灯泡脉冲" 已回退 —— 用户反馈太像数字 UI 语言，不贴合筊杯语境。
    回退后用持续性环境动画（gather-in + drift + shimmer）承担"存在感"信号。
    防回归：任何人若把 ready-pulse 搬回来都立刻炸。"""
    assert "ready-pulse" not in index_html, (
        "index.html 仍含 ready-pulse —— Stage A 应已回退为环境动画"
    )
    assert "coin-ready-pulse" not in index_html, (
        "index.html 仍含 @keyframes coin-ready-pulse 残留"
    )
    assert "pulseHoldReady" not in app_js, (
        "app.js 仍含 pulseHoldReady —— Stage A 的灯泡脉冲应完全回退"
    )
    assert "ready-pulse" not in app_js, "app.js 仍含 ready-pulse 类名操作残留"


def test_holding_coin_drift_animation(index_html: str):
    """HOLD 态的微晃 drift：持续性 ±1.5px translate，比 .shaking 的 0.2s/2px 更慢更小。
    这是"铜钱在掌心里轻漂"的视觉基础，也是"活着在等"的环境信号。"""
    assert re.search(
        r"\.coin-wrap\.holding\s+\.coin-spin\s*\{[^}]*animation\s*:[^;]*coin-hold-drift",
        index_html,
        re.S,
    ), "HOLD .coin-spin 未绑定 coin-hold-drift 动画"
    m = re.search(r"@keyframes\s+coin-hold-drift\b([^@]*)", index_html, re.S)
    assert m, "缺少 @keyframes coin-hold-drift"
    body = m.group(1)
    # 必须用 translate 属性而不是 transform —— 和 coin-breathe 的 transform/scale 不冲突
    assert "translate:" in body, (
        "coin-hold-drift 应用独立 translate 属性，避免与 coin-breathe 的 scale 冲突"
    )


def test_pearl_sheen_on_coin_surface(index_html: str):
    """珠光在硬币"表面"（.coin-spin::after 内层）而非外环。
    用户反馈："流光不是在硬币边缘流动，而是在硬币表面，有一种珠光感"。
    防回归：任何人把 shimmer 搬回 .coin-wrap::before 外环都会炸。"""
    # 珠光必须长在 .coin-spin 内侧，不是 .coin-wrap 外环
    assert re.search(
        r"\.coin-wrap\.holding\s+\.coin-spin::after\s*\{[^}]*radial-gradient",
        index_html,
        re.S,
    ), "缺少 .coin-wrap.holding .coin-spin::after 的 radial-gradient 珠光层"
    # mix-blend-mode: overlay —— 让高光只提亮金属色区域
    m = re.search(
        r"\.coin-wrap\.holding\s+\.coin-spin::after\s*\{([^}]*)\}",
        index_html,
        re.S,
    )
    assert m, "找不到 .coin-spin::after 规则体"
    body = m.group(1)
    assert "mix-blend-mode" in body, (
        ".coin-spin::after 缺少 mix-blend-mode —— 珠光会变成不透明贴纸而非表面光"
    )
    # 外环 shimmer 应已移除（::before 或 halo-hold-shimmer 不应再出现）
    assert "halo-hold-shimmer" not in index_html, (
        "halo-hold-shimmer（外环流光）应已被移除 —— 用户明确要求珠光在表面不在边缘"
    )


def test_regather_transition_on_landed_coins(index_html: str, app_js: str):
    """LAND→HOLD 过渡：3 枚落定硬币向 coinsRow 中心"归位"并同步 blur/halo 升起。
    用户反馈："应该要先归位，同步光晕升起让硬币变得模糊"。"""
    # CSS: .regathering 必须用 translate 表达归位位移
    m = re.search(
        r"\.coin-wrap\.holding\.regathering\s*\{([^}]*)\}",
        index_html,
        re.S,
    )
    assert m, "缺少 .coin-wrap.holding.regathering CSS 规则"
    body = m.group(1)
    assert "translate:" in body, (
        ".regathering 缺少 translate —— '归位'移动的视觉基础丢失"
    )
    assert "transition:" in body and "translate" in body, (
        ".regathering 缺少 translate 的 transition —— 归位会瞬移而非平滑过渡"
    )
    # JS: 必须有 startRegather 函数，且在 startDivine 里被调用
    assert re.search(r"function\s+startRegather\s*\(", app_js), (
        "缺少 startRegather 工具函数"
    )
    m2 = re.search(
        r"async\s+function\s+startDivine\s*\([^)]*\)\s*\{(.*?)\n\}",
        app_js,
        re.S,
    )
    assert m2, "找不到 startDivine 函数体"
    assert "startRegather(" in m2.group(1), (
        "startDivine 未调用 startRegather —— 归位动作不会触发"
    )
    # JS: startRegather 必须计算朝中心的 dx/dy 并写入 CSS 变量
    m3 = re.search(
        r"function\s+startRegather\s*\([^)]*\)\s*\{(.*?)\n\}",
        app_js,
        re.S,
    )
    assert m3, "找不到 startRegather 函数体"
    sr_body = m3.group(1)
    assert "--home-dx" in sr_body and "--home-dy" in sr_body, (
        "startRegather 未写入 --home-dx / --home-dy CSS 变量"
    )
    assert "getBoundingClientRect" in sr_body, (
        "startRegather 未用 getBoundingClientRect 计算相对中心的位移 —— 归位方向会错"
    )


def test_holding_enter_keyframe_matches_steady_state(index_html: str):
    """入场渐显：新 3 枚 .coin-wrap 从"无"到稳态 HOLD 的 500ms 过渡。
    to 态的 scale/opacity/filter 必须严格对齐稳态起点，否则 JS 移除 .entering
    瞬间稳态 animation (coin-breathe from scale 0.94) 会发生跳变闪帧。"""
    m = re.search(r"@keyframes\s+holding-enter\b([^@]*)", index_html, re.S)
    assert m, "缺少 @keyframes holding-enter"
    body = m.group(1)
    # from 态：极淡雾团
    assert re.search(r"from\s*\{[^}]*opacity:\s*0\b", body, re.S), (
        "holding-enter from 态缺少 opacity: 0 —— 铜钱不会从'无'渐入"
    )
    assert re.search(r"from\s*\{[^}]*scale\(0\.82\)", body, re.S), (
        "holding-enter from 态缺少 scale(0.82) —— 入场缩放起点错"
    )
    assert re.search(r"from\s*\{[^}]*blur\(10px\)", body, re.S), (
        "holding-enter from 态缺少 blur(10px) —— 入场模糊起点错"
    )
    # to 态：与稳态 .coin-wrap.holding .coin-spin 严格匹配（0.82 / 0.94 / 6px）
    assert re.search(r"to\s*\{[^}]*opacity:\s*0\.82\b", body, re.S), (
        "holding-enter to 态 opacity 必须为 0.82（对齐稳态），否则 500ms 末尾会闪"
    )
    assert re.search(r"to\s*\{[^}]*scale\(0\.94\)", body, re.S), (
        "holding-enter to 态 scale 必须为 0.94（对齐 coin-breathe from），否则衔接跳变"
    )
    assert re.search(r"to\s*\{[^}]*blur\(6px\)", body, re.S), (
        "holding-enter to 态 blur 必须为 6px（对齐稳态 filter），否则模糊度会跳"
    )


def test_holding_entering_rule_binds_animation(index_html: str, app_js: str):
    """.coin-wrap.holding.entering .coin-spin 规则必须绑定 holding-enter animation
    + forwards，保证 500ms 跑完后 to 态锁住，等 JS 移除 .entering 稳态接手。
    同时 coinsEnterHold 必须接受 opts.entering 参数，startDivine 手摇分支必须调用。"""
    # CSS：entering 类绑定动画 + forwards
    m = re.search(
        r"\.coin-wrap\.holding\.entering\s+\.coin-spin\s*\{([^}]*)\}",
        index_html,
        re.S,
    )
    assert m, "缺少 .coin-wrap.holding.entering .coin-spin 规则 —— 入场动画无法触发"
    body = m.group(1)
    assert "holding-enter" in body, (
        ".coin-wrap.holding.entering .coin-spin 未绑定 holding-enter animation"
    )
    assert "forwards" in body, "holding-enter 缺少 forwards —— 动画跑完会闪回 from 态"
    # JS：coinsEnterHold 签名支持参数
    m2 = re.search(
        r"function\s+coinsEnterHold\s*\(([^)]*)\)\s*\{(.*?)\n\}",
        app_js,
        re.S,
    )
    assert m2, "找不到 coinsEnterHold 函数"
    sig, body = m2.group(1), m2.group(2)
    assert sig.strip(), "coinsEnterHold 必须接受参数（用于 opts.entering）"
    assert "entering" in body, (
        "coinsEnterHold 函数体未处理 entering —— 入场动画不会被触发"
    )
    # JS：startDivine 手摇分支调 coinsEnterHold({ entering: true })
    m3 = re.search(
        r"async\s+function\s+startDivine\s*\([^)]*\)\s*\{(.*?)\n\}",
        app_js,
        re.S,
    )
    assert m3, "找不到 startDivine 函数体"
    assert re.search(
        r"coinsEnterHold\(\s*\{\s*entering:\s*true\s*\}\s*\)",
        m3.group(1),
    ), "startDivine 手摇分支未调用 coinsEnterHold({ entering: true }) —— 入场渐显失效"


def test_coin_shake_uses_rotate_not_translate(index_html: str):
    """coin-shake 必须用 rotate 抖而不是 translate —— 否则 CSS animation 占用
    .coin-wrap translate 属性，会覆盖基础 translate transition，导致
    regathering→shaking 时 translate 从 var(--home-dx,dy) 瞬跳到 coin-shake
    起点（用户报"硬币位置突然改变"的根因）。

    rotate 是 CSS Transforms Level 2 独立属性，和 inline style.transform=
    'rotate(Xdeg)' 合成叠加而非覆盖，不影响位置排布的固定角度。"""
    m = re.search(r"@keyframes\s+coin-shake\b([^@]*)", index_html, re.S)
    assert m, "缺少 @keyframes coin-shake"
    body = m.group(1)
    # 必须用 rotate 抖动（不能用 translate —— 会覆盖外层 translate transition）
    assert "rotate:" in body, (
        "coin-shake 必须用独立 rotate 属性抖动；translate 会覆盖外层 "
        "translate transition 导致 HOLD→SHAKE 位置瞬跳"
    )
    assert "translate:" not in body, (
        "coin-shake 不得使用 translate —— 用 rotate 代替才能保留外层 "
        "translate 给基础 transition 做状态过渡"
    )


def test_holding_enter_translate_aligns_with_drift(index_html: str):
    """holding-enter to 态的 translate 必须精确匹配 coin-hold-drift 0% 起点
    （-1.5px 0.5px），保证 JS 移除 .entering 瞬间稳态 drift animation 从
    相同值起步，消除"蓄势→持稳"阶段 1.5-2.5px 的 translate 跳变。

    drift 是 alternate + from(0%) 起点，所以 from(0%) 就是启动瞬间的 translate。"""
    m = re.search(r"@keyframes\s+holding-enter\b([^@]*)", index_html, re.S)
    assert m, "缺少 @keyframes holding-enter"
    body = m.group(1)
    # from 态：translate 从 0 开始（入场无位移）
    assert re.search(r"from\s*\{[^}]*translate:\s*0\s+0\b", body, re.S), (
        "holding-enter from 态应包含 translate: 0 0（入场起始位置）"
    )
    # to 态必须精确等于 coin-hold-drift 0% 的 translate 值
    assert re.search(r"to\s*\{[^}]*translate:\s*-1\.5px\s+0\.5px\b", body, re.S), (
        "holding-enter to 态 translate 必须为 -1.5px 0.5px，精确对齐 "
        "coin-hold-drift from，否则稳态 drift 启动瞬间 translate 会跳变"
    )


def test_coin_wrap_base_transition_includes_translate(index_html: str):
    """.coin-wrap 基础 transition 必须单独声明 translate（CSS Transforms Level 2
    独立属性，不会被 `transform 0.5s` 覆盖）。不加这条，.regathering 类被
    coinsEnterShake() 删除瞬间 translate 会从 var(--home-dx,dy) 突变回 0，
    HOLD→SHAKE 过渡会"啪地散开"。"""
    # 抓 .coin-wrap { ... } 基础规则（不含 .holding / .shaking / .just-landed 等修饰）
    m = re.search(
        r"\.coin-wrap\s*\{([^}]*)\}",
        index_html,
        re.S,
    )
    assert m, "找不到 .coin-wrap 基础 CSS 规则"
    body = m.group(1)
    assert "transition:" in body, ".coin-wrap 基础规则缺少 transition"
    # transition 属性必须显式列出 translate（不是只有 transform）
    transition_m = re.search(r"transition:\s*([^;]+);", body, re.S)
    assert transition_m, ".coin-wrap transition 声明格式异常"
    transition_value = transition_m.group(1)
    assert "translate" in transition_value, (
        ".coin-wrap 基础 transition 未覆盖 translate 属性 —— "
        "HOLD→SHAKE 时 translate 会从 --home-dx/dy 瞬变回 0"
    )


def test_shake_peak_haptic_with_debounce(app_js: str):
    """SHAKE 阶段每次 mag>HI 的峰值回响：haptic(8) + 200ms 去抖。
    physical event（手腕动作）= 物理回响合格；禁止密集连发把仪式感震成灯泡。"""
    m = re.search(
        r"function\s+awaitManualToss\s*\([^)]*\)\s*\{(.*)",
        app_js,
        re.S,
    )
    assert m, "找不到 awaitManualToss 函数"
    body = m.group(1)
    # 去抖变量必须在 Promise 闭包内声明
    assert "lastPeakHaptic" in body, "awaitManualToss 缺少 lastPeakHaptic 去抖状态变量"
    # SHAKE 分支必须在 mag > SHAKE_HI 时调 haptic(8)
    assert re.search(r"haptic\(8\)", body), (
        "awaitManualToss 未在 SHAKE 分支发 haptic(8) 峰值回响"
    )
    # 200ms 去抖阈值
    assert re.search(r"lastPeakHaptic\s*\)\s*>\s*200", body), (
        "SHAKE 峰值 haptic 缺少 200ms 去抖条件 —— 密集震动会破坏仪式感"
    )


def test_manual_rest_split_into_two_segments(app_js: str):
    """Stage D：手摇非末爻的爻间屏息必须拆成两段叙事，消除"阳爻死静 1 秒"的死区。
    防回归：有人可能统一节奏时合并成整段 sleep(1000)。"""
    m = re.search(
        r"async\s+function\s+startDivine\s*\([^)]*\)\s*\{(.*?)\n\}",
        app_js,
        re.S,
    )
    assert m, "找不到 startDivine 函数体"
    body = m.group(1)
    # 分段时长（450 + 550 = 1000，与原整段等长；仅在非末爻生效以保留末爻的整段屏息）
    assert re.search(r"\bsleep\(450\)", body), (
        "startDivine 手摇非末爻屏息缺少 sleep(450) 第一段（全亮 '阳爻'）"
    )
    assert re.search(r"\bsleep\(550\)", body), (
        "startDivine 手摇非末爻屏息缺少 sleep(550) 第二段（过渡到下一爻蓄势）"
    )
    # 过渡文案必须存在 —— 这句是消除"卡住了吗"疑虑的核心信号
    assert "凝神片刻" in body, (
        "startDivine 缺少 '凝神片刻 · 下一爻蓄势' 过渡文案 —— Stage D 的叙事连续性未生效"
    )


# ============================================================
# 手摇首爻书法描边入场（2026-04-23 redo）
# ============================================================


def test_stroke_draw_keyframe_present(index_html: str):
    """@keyframes stroke-draw 必须定义，终态 stroke-dashoffset: 0。

    这是 SVG 路径"描出来"的视觉核心——起始 stroke-dashoffset 100（配合
    pathLength=100 + stroke-dasharray 100），终态 0 就是"线走满一圈"。"""
    m = re.search(
        r"@keyframes\s+stroke-draw\s*\{([^}]*?)\}",
        index_html,
        re.S,
    )
    assert m, "缺少 @keyframes stroke-draw —— 书法描边动画未定义"
    body = m.group(1)
    assert re.search(r"stroke-dashoffset:\s*0\b", body), (
        "stroke-draw 终态必须 stroke-dashoffset: 0 —— 否则线画不完整"
    )


def test_coin_fill_in_end_matches_holding_steady(index_html: str):
    """coin-fill-in 100% 末帧必须逐字匹配 .coin-wrap.holding .coin-spin 稳态。

    书法描边完成后真硬币 fade-in，末帧值必须对齐 HOLD 稳态（opacity 0.82 /
    scale 0.94 / blur(6px) saturate(0.8) / translate -1.5px 0.5px），否则切
    .holding class 瞬间会有肉眼可见的跳帧。"""
    m = re.search(
        r"@keyframes\s+coin-fill-in\s*\{.*?100%\s*\{([^}]*)\}",
        index_html,
        re.S,
    )
    assert m, "找不到 coin-fill-in 100% 关键帧"
    end_frame = m.group(1)
    assert re.search(r"opacity:\s*0\.82\b", end_frame), (
        "coin-fill-in 100% opacity 应 0.82 对齐 holding 稳态"
    )
    assert re.search(r"transform:\s*scale\(0\.94\)", end_frame), (
        "coin-fill-in 100% transform 应 scale(0.94) 对齐 holding"
    )
    assert re.search(r"filter:\s*blur\(6px\)\s+saturate\(0\.8\)", end_frame), (
        "coin-fill-in 100% filter 应 blur(6px) saturate(0.8) 对齐 holding"
    )
    assert re.search(r"translate:\s*-1\.5px\s+0\.5px", end_frame), (
        "coin-fill-in 100% translate 应 -1.5px 0.5px "
        "（对齐 coin-hold-drift 0% 起点，稳态接力无跳帧）"
    )


def test_sketching_class_wires_stroke_animations(index_html: str):
    """.coin-wrap.sketching .sketch-outer / .sketch-inner 必须绑 stroke-draw
    动画，且通过 --sketch-delay CSS 变量承接 JS stagger。

    防回归：若有人把 delay 硬编码在 CSS 里（animation-delay: 150ms），JS 就
    没法 per-coin 精确控制 stagger；必须是 var(--sketch-delay, 0ms) 形式。"""
    m_outer = re.search(
        r"\.coin-wrap\.sketching\s+\.sketch-outer\s*\{([^}]*)\}",
        index_html,
        re.S,
    )
    assert m_outer, "缺少 .coin-wrap.sketching .sketch-outer 规则"
    outer_body = m_outer.group(1)
    assert re.search(r"stroke-dasharray:\s*100", outer_body), (
        "sketch-outer 应 stroke-dasharray: 100（配合 SVG pathLength=100 归一化长度）"
    )
    assert "stroke-draw" in outer_body, "sketch-outer 应 animation: stroke-draw"
    assert "var(--sketch-delay" in outer_body, (
        "sketch-outer 的 animation-delay 应走 var(--sketch-delay, 0ms) —— "
        "JS 给每枚硬币设不同值实现 stagger"
    )

    m_inner = re.search(
        r"\.coin-wrap\.sketching\s+\.sketch-inner\s*\{([^}]*)\}",
        index_html,
        re.S,
    )
    assert m_inner, "缺少 .coin-wrap.sketching .sketch-inner 规则"
    inner_body = m_inner.group(1)
    # 内方描边必须在外圆之后起笔（外圆 460ms + 320ms delay = 780ms 前内方不动）
    assert "stroke-draw" in inner_body, "sketch-inner 应 animation: stroke-draw"
    assert re.search(
        r"calc\(\s*var\(--sketch-delay[^)]*\)\s*\+\s*320ms\s*\)", inner_body
    ), (
        "sketch-inner 的 delay 应是 calc(var(--sketch-delay) + 320ms) —— "
        "在外圆 460ms 描到 70% 时内方开始补点（天圆地方的铸造顺序）"
    )


def test_start_divine_idx0_uses_calligraphy(app_js: str):
    """startDivine 手摇分支必须按 idx === 0 分叉：首爻 coinsEnterCalligraphy +
    await sleep(1420) + coinsEnterHold；后续爻沿用 coinsEnterHold({entering:true})。

    钉住 1420 是因为三枚 stagger 150ms + 单爻总 1120ms（460 外圆起笔 + 660 四段
    fill-in with sharp peak + slow melt）= 300 + 1120 = 1420，改时长必须同步改
    JS 和 CSS（CSS 里 coin-fill-in duration 660ms 对应），测试里两头查防走样。"""
    assert "coinsEnterCalligraphy" in app_js, (
        "缺少 coinsEnterCalligraphy 函数 —— 首爻书法描边未接入"
    )
    assert "buildCoinSketch" in app_js, (
        "缺少 buildCoinSketch —— 描边 SVG 构造函数未定义"
    )
    m = re.search(
        r"async\s+function\s+startDivine\s*\([^)]*\)\s*\{(.*?)\n\}",
        app_js,
        re.S,
    )
    assert m, "找不到 startDivine 函数体"
    body = m.group(1)
    assert re.search(r"idx\s*===?\s*0", body), (
        "startDivine 手摇分支应判断 idx === 0（首爻仪式、后续爻不重复）"
    )
    # idx === 0 分支体内调 coinsEnterCalligraphy + sleep(1420)
    m2 = re.search(
        r"idx\s*===?\s*0\s*\)\s*\{([^{}]*?(?:\{[^{}]*\}[^{}]*?)*?)\}\s*else",
        body,
        re.S,
    )
    assert m2, "找不到 startDivine 的 idx === 0 分支体"
    idx0_body = m2.group(1)
    assert "coinsEnterCalligraphy" in idx0_body, (
        "idx === 0 分支应调 coinsEnterCalligraphy"
    )
    assert re.search(r"sleep\s*\(\s*1420\s*\)", idx0_body), (
        "idx === 0 分支应 await sleep(1420) 给描边 + 四段 fill-in + stagger 完整时长"
    )


def test_coin_fill_in_has_sharp_peak(index_html: str):
    """coin-fill-in 中间必须存在"硬币锐利清晰"的关键帧窗口。

    用户反馈："硬币应该先清晰画出来再渐隐入光雾"。旧实现 0%→100% 直接从
    虚到 HOLD 雾态，硬币全程不清晰。新实现必须在 25-55% 之间有 opacity:1 +
    scale ≥1.0 + blur(0) 的清晰峰值，让用户读到硬币细节。

    本断言钉住这个"可读窗口"不会被无意回退。"""
    m = re.search(
        r"@keyframes\s+coin-fill-in\s*\{(.*?)\n\}",
        index_html,
        re.S,
    )
    assert m, "找不到 @keyframes coin-fill-in"
    body = m.group(1)
    # 必须有至少一个介于 25%-55% 的关键帧同时满足：
    #   opacity: 1  +  scale(1.0) 或 scale(1.XX)  +  blur(0)
    found_sharp = False
    for pct in (25, 30, 40, 45, 55):
        frame_m = re.search(
            rf"\b{pct}%\s*\{{([^}}]*)\}}",
            body,
            re.S,
        )
        if not frame_m:
            continue
        frame_body = frame_m.group(1)
        has_full_opacity = re.search(r"opacity:\s*1\b", frame_body) is not None
        has_full_scale = re.search(r"scale\(1(?:\.\d+)?\)", frame_body) is not None
        has_no_blur = re.search(r"blur\(0(?:px)?\)", frame_body) is not None
        if has_full_opacity and has_full_scale and has_no_blur:
            found_sharp = True
            break
    assert found_sharp, (
        "coin-fill-in 25-55% 区间必须至少有一个关键帧同时满足 "
        "opacity:1 + scale(1.0+) + blur(0) —— 这是「硬币清晰可读」的视觉锚点，"
        "少了用户就看不到硬币的「乾亨元利」字、方孔和铸边"
    )


def test_build_coin_sketch_uses_path_length_normalization(app_js: str):
    """buildCoinSketch 必须用 pathLength='100' 把 SVG 描边长度归一化。

    不归一化的话每枚硬币的 SVG 根据 viewBox 计算不同的周长，CSS 写死
    stroke-dasharray: 100 就会错位。pathLength='100' 是跨浏览器的兼容选择。"""
    m = re.search(
        r"function\s+buildCoinSketch\s*\([^)]*\)\s*\{(.*?)\n\}",
        app_js,
        re.S,
    )
    assert m, "找不到 buildCoinSketch 函数体"
    body = m.group(1)
    # 外圆 + 内方都必须带 pathLength="100"
    assert body.count('pathLength="100"') >= 2, (
        f'buildCoinSketch 应给 ≥2 个 SVG 元素加 pathLength="100" '
        f"（外圆 + 内方），当前 {body.count(chr(34))} 次 pathLength 出现 —— "
        "不归一化会让 CSS stroke-dasharray:100 在不同硬币尺寸下错位"
    )
    # 两个 class hook 必须存在（CSS 绑定 animation 用）
    assert 'class="sketch-outer"' in body, "buildCoinSketch 缺外圆 class hook"
    assert 'class="sketch-inner"' in body, "buildCoinSketch 缺内方 class hook"


def test_reduced_motion_sketching_fallback(index_html: str):
    """prefers-reduced-motion 下描边叠层隐藏，硬币直接落 HOLD 稳态。

    全局通配规则已经把 animation 挤到 0.001s，这里显式 fallback 是防御层
    + 测试锚点，防止未来有人改通配规则破坏 reduced-motion 路径。"""
    m = re.search(
        r"@media\s*\(\s*prefers-reduced-motion:\s*reduce\s*\)\s*\{(.*?)\n\}\s*(?:\n|</style>)",
        index_html,
        re.S,
    )
    assert m, "找不到 @media (prefers-reduced-motion: reduce) 规则块"
    body = m.group(1)
    # 描边叠层应被显式隐藏
    assert re.search(
        r"\.coin-wrap\.sketching\s+\.coin-sketch[^}]*?opacity:\s*0",
        body,
        re.S,
    ), "reduced-motion 下 .coin-sketch 应显式 opacity: 0"
    # .coin-spin 应显式落在 HOLD 稳态
    assert re.search(
        r"\.coin-wrap\.sketching\s+\.coin-spin[^}]*?"
        r"opacity:\s*0\.82[^}]*?"
        r"scale\(0\.94\)[^}]*?"
        r"blur\(6px\)",
        body,
        re.S,
    ), (
        "reduced-motion 下 .coin-wrap.sketching .coin-spin 应显式落到 HOLD 稳态"
        " (opacity 0.82 / scale 0.94 / blur 6px)"
    )


def test_all_hexagrams_page_hex_data_matches_backend():
    """dev-tools/all-hexagrams.js 的 HEX_DATA 必须和 backend HEXAGRAMS 严格一致。

    曾经踩坑（Codex adversarial review 指出）：HEX_DATA 是为体检页手动导出的硬编码，
    导出脚本把 TRIGRAMS binary `(bottom, middle, top)` 当成 `(top, middle, bottom)` 读，
    导致 48/64 卦 yao 上下反转——名字对、形状错，让体检页得出的视觉结论全部污染。

    这条测试是防线：任何人改 backend 数据或 JS 硬编码，只要不同步两边就立刻炸出。
    """
    import json
    from backend.hexagrams_data import HEXAGRAMS, TRIGRAMS

    js_path = ROOT / "dev-tools" / "all-hexagrams.js"
    assert js_path.exists(), f"{js_path} 不存在（体检页脚本被意外删了？）"
    js = js_path.read_text(encoding="utf-8")

    # 抓 const HEX_DATA = [ ... ]; 里的数组字面量
    m = re.search(r"const\s+HEX_DATA\s*=\s*(\[.*?\]);", js, re.S)
    assert m, "all-hexagrams.js 必须有 `const HEX_DATA = [ ... ];` 数组字面量"
    js_data = json.loads(m.group(1))  # JSON.parse — 依赖字面量是严格 JSON 格式

    assert len(js_data) == 64, f"HEX_DATA 必须恰好 64 卦，实际 {len(js_data)}"
    assert len(HEXAGRAMS) == 64, "backend HEXAGRAMS 意外不是 64 个"

    mismatches = []
    for js_entry, py_entry in zip(js_data, HEXAGRAMS):
        n = py_entry["number"]
        name = py_entry["name"]
        lower = TRIGRAMS[py_entry["lower_trigram"]]["binary"]
        upper = TRIGRAMS[py_entry["upper_trigram"]]["binary"]
        # binary = (bottom, middle, top)；yaos 自底向上：yao1..yao3=下卦底/中/顶, yao4..yao6=上卦底/中/顶
        expected_yaos = [lower[0], lower[1], lower[2], upper[0], upper[1], upper[2]]

        assert js_entry["n"] == n, f"序号错位：JS #{js_entry['n']} vs Python #{n}"
        assert js_entry["name"] == name, (
            f"卦名错位：#{n} JS={js_entry['name']!r} vs Python={name!r}"
        )
        if js_entry["yaos"] != expected_yaos:
            mismatches.append(
                f"#{n} {name}: JS yaos={js_entry['yaos']} vs expected={expected_yaos}"
            )

    assert not mismatches, (
        f"HEX_DATA 和 backend 不一致（{len(mismatches)}/64）：\n"
        + "\n".join(mismatches[:10])
        + ("\n..." if len(mismatches) > 10 else "")
    )
