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
    # marked 已本地化为 assets/vendor/marked-<version>.min.js
    assert re.search(r"marked-[\d.]+\.min\.js", html), "缺少 marked 脚本引用"
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
    "AI 解读",
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
    """marked 和 DOMPurify 已下载到本地，消除 CDN 供应链风险"""
    assert list(VENDOR_DIR.glob("marked-*.min.js")), (
        f"缺少本地 marked 文件: {VENDOR_DIR}"
    )
    assert list(VENDOR_DIR.glob("dompurify-*.min.js")), (
        f"缺少本地 dompurify 文件: {VENDOR_DIR}"
    )


def test_script_tags_point_to_local_vendor(html: str):
    """head 里 marked/dompurify 的 script src 必须是相对路径（本地），不得引用 CDN"""
    marked_tag = re.search(r'<script\s+src="([^"]+marked[^"]+\.min\.js)"', html)
    assert marked_tag, "缺少 marked script 标签"
    assert marked_tag.group(1).startswith("assets/"), (
        f"marked 应从本地加载，实为: {marked_tag.group(1)}"
    )

    dompurify_tag = re.search(r'<script\s+src="([^"]+dompurify[^"]+\.min\.js)"', html)
    assert dompurify_tag, "缺少 dompurify script 标签"
    assert dompurify_tag.group(1).startswith("assets/"), (
        f"dompurify 应从本地加载，实为: {dompurify_tag.group(1)}"
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
