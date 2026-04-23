/* ==============================================================
   marked 配置 — 禁 HTML 防 XSS
   ============================================================== */
marked.setOptions({ renderer: new marked.Renderer(), breaks: true });
(function() {
  var t = new marked.Tokenizer();
  t.html = function() { return false; };   // 禁用 HTML tokenizer
  marked.use({ tokenizer: t });
})();

/* ==============================================================
   Markdown 安全渲染 — marked → DOMPurify sanitize
   防御层：
     1) tokenizer.html=false  禁用原始 HTML token
     2) DOMPurify allow-list  仅保留安全的排版标签
     3) ALLOWED_ATTR 仅 href  + URI_REGEXP 仅 http(s)
     4) 点击时 #linkConfirm 二次确认（见下方 click 拦截）
   ============================================================== */
var SAFE_MD_CONFIG = {
  ALLOWED_TAGS: ['p', 'br', 'strong', 'em', 'h1', 'h2', 'h3',
                 'ul', 'ol', 'li', 'code', 'blockquote', 'hr', 'a'],
  ALLOWED_ATTR: ['href'],
  ALLOWED_URI_REGEXP: /^https?:\/\//i,
};
function renderMarkdownSafely(raw) {
  if (!raw) return '';
  var html = marked.parse(raw);
  return DOMPurify.sanitize(html, SAFE_MD_CONFIG);
}

/* ==============================================================
   全局状态
   ============================================================== */
var API_BASE = window.location.origin;
var Core = window.IChingCore;
var isDivining = false;
var divineMode = 'auto';           // 'auto' | 'manual' — 见 setDivineMode / awaitShakeSettle
var _motionPermissionRequested = false; // iOS 的 DeviceMotionEvent.requestPermission 只请求一次
var hexagramsCache = null;

/* 手摇模式状态机阈值 —— 详见 awaitManualToss 头注释。
 * HI/LO 双阈值是迟滞（hysteresis）设计：防止加速度在阈值线上方的小抖动反复触发；
 * MIN_SHAKE_MS 与用户的生理手势时长解耦，给每一次"摇"至少 600ms 的视觉演出。 */
var SHAKE_HI = 18;            // 进入 SHAKING 的加速度阈值 (m/s²)
var SHAKE_LO = 6;             // 判定 "静止" 的加速度阈值
var MIN_SHAKE_MS = 600;       // 每爻摇动阶段最短视觉持续时间
var QUIET_MS = 300;           // 爻间静候：连续 mag<LO 达到此时长才允许下一爻
var NO_MOTION_HINT_MS = 2000; // 进入手摇模式 N ms 内无 devicemotion 事件则提示 fallback

/* 手摇检测器：setDivineMode('manual') 挂 / setDivineMode('auto') 摘；
 * awaitManualToss 通过 subscribeShake 订阅加速度采样做状态机。
 *
 * 两个状态语义刻意分开 —— Codex adversarial review 指出旧实现把能力等同见证：
 *   _motionSupported：capability，listener 挂上 + 权限 granted 即置 true
 *   _motionEverFired：witness，至少收到过一次真实事件
 * 文案选择：只要 _motionSupported === true 就显示"轻摇可得一爻"，
 * 即便用户还没动（以前会错报为"摇不动？点击铜钱"）。
 *
 * _currentTossCleanup：awaitManualToss 的同步 abort 句柄。cancelCurrentDivine
 * 或 startDivine 入口调用它，立即解绑 click / _shakeSubs 监听，避免 old run
 * 的监听器在 _divineSeq++ 之后仍然响应事件污染 new run 的共享 UI（原 150ms
 * poll 方案在此窗口内会漏掉快速返回 → 重新起卦的竞态）。 */
var _motionEverFired = false;
var _motionSupported = false;
var _shakeSubs = [];
var _motionListenerActive = false;
var _currentTossCleanup = null;
var _currentInterpWs = null;
var _interpSeq = 0;
var _divineSeq = 0;   // 镜像 _interpSeq：中途切换视图时丢弃老 startDivine 的回调
var _divineAbort = null;   // AbortController 句柄：让慢网/冷启动下的 fetch('/api/divine') 真正中断，而非仅"结果被丢弃"
var __uid = 0;
function uid(prefix) { __uid++; return (prefix || 'u') + __uid; }

/* ==============================================================
   工具函数
   ============================================================== */
function $(id) { return document.getElementById(id); }
function el(tag, attrs, text) {
  var e = document.createElement(tag);
  if (attrs) Object.keys(attrs).forEach(function(k) {
    if (k === 'className') e.className = attrs[k];
    else if (k === 'style') e.style.cssText = attrs[k];
    else e.setAttribute(k, attrs[k]);
  });
  if (text !== undefined) e.textContent = text;
  return e;
}
function clearChildren(parent) { while (parent.firstChild) parent.removeChild(parent.firstChild); }
function sleep(ms) { return new Promise(function(r) { setTimeout(r, ms); }); }
function showError(msg) {
  var box = $('errorMsg');
  box.textContent = msg;
  box.classList.add('active');
  setTimeout(function() { box.classList.remove('active'); }, 5000);
}

/* SVG 装配 — DOMParser 避免 innerHTML */
var SVG_NS = 'http://www.w3.org/2000/svg';
function svgFromString(str) {
  var doc = new DOMParser().parseFromString(str, 'image/svg+xml');
  var err = doc.getElementsByTagName('parsererror')[0];
  if (err) throw new Error('SVG parse error');
  return doc.documentElement;
}
function moveChildren(from, to) {
  while (from.firstChild) {
    to.appendChild(document.adoptNode(from.firstChild));
  }
}

/* 把"带声调、空格分隔音节"的 pinyin 原串格式化为设计稿样式
 * "SHAN · TIAN · DA · XU" —— 剥声调、全大写、中点分隔。 */
function _formatPinyinRaw(raw) {
  if (!raw) return '';
  var plain = raw.normalize('NFD').replace(/[\u0300-\u036f]/g, '');
  return plain.toUpperCase().split(/\s+/).filter(Boolean).join(' · ');
}
/* 结果页顶部小字金色拼音：优先展示全卦名四音节（山天大畜 → SHAN · TIAN · DA · XU），
 * 数据不全时降级为本卦名短拼音（大畜 → DA · XU）。 */
function formatHexPinyin(hex) {
  if (!hex) return '';
  var raw = '';
  if (typeof Core !== 'undefined') {
    if (Core.fullHexPinyin) raw = Core.fullHexPinyin(hex) || '';
    if (!raw && Core.pinyinOf) raw = Core.pinyinOf(hex.name || '') || '';
  }
  return _formatPinyinRaw(raw);
}

/* 触感反馈 — 移动设备短震 */
function haptic(pattern) {
  try {
    if (navigator.vibrate) navigator.vibrate(pattern);
  } catch (e) { /* no-op */ }
}

/* 干支纪月纪日 —— 传统中国编年，对齐墨玉鎏金整体气质。
 * 算法在 iching-core.js（ganzhiDateLabel）；若 Core 未挂载（老缓存）fallback 公历。 */
(function() {
  var el = $('lunarDate');
  if (!el) return;
  var d = new Date();
  var label = (typeof Core !== 'undefined' && Core.ganzhiDateLabel)
    ? Core.ganzhiDateLabel(d)
    : '';
  if (!label) {
    var y = d.getFullYear();
    var m = String(d.getMonth() + 1).padStart(2, '0');
    var dt = String(d.getDate()).padStart(2, '0');
    label = y + '·' + m + '·' + dt;
  }
  el.textContent = label;
})();

/* ==============================================================
   星空背景 — 伪随机填充（使用 createElementNS）
   ============================================================== */
function fillStarfield(svg, count, seed, color) {
  var x = seed;
  function rand() { x = (x * 9301 + 49297) % 233280; return x / 233280; }
  for (var i = 0; i < count; i++) {
    var c = document.createElementNS(SVG_NS, 'circle');
    c.setAttribute('cx', (rand() * 100).toFixed(2));
    c.setAttribute('cy', (rand() * 100).toFixed(2));
    c.setAttribute('r', (rand() * 0.22 + 0.05).toFixed(3));
    c.setAttribute('fill', color);
    c.setAttribute('opacity', (rand() * 0.7 + 0.3).toFixed(2));
    svg.appendChild(c);
  }
}
fillStarfield($('starfield-gold'), 120, 17, '#c9a961');
fillStarfield($('starfield-white'), 60, 88, '#ffffff');

/* 金尘 */
(function() {
  var box = $('motes');
  for (var i = 0; i < 9; i++) {
    var m = el('div', { className: 'mote' });
    var s = 2 + (i % 3);
    m.style.cssText =
      'left:' + ((i * 37) % 100) + '%;' +
      'top:' + ((i * 53) % 100) + '%;' +
      'width:' + s + 'px;height:' + s + 'px;' +
      'opacity:' + (0.25 + (i % 3) * 0.1) + ';' +
      'animation: mote-' + (i % 3) + ' ' + (8 + i) + 's ease-in-out ' + (i * 0.7) + 's infinite;';
    box.appendChild(m);
  }
})();

/* ==============================================================
   八卦 SVG 构建 — DOMParser 装配
   ============================================================== */
function buildBaguaSvg() {
  var size = 260, cx = size/2, cy = size/2;
  var ringR = size * 0.38;
  var trigSpan = size * 0.17;
  var lineH = size * 0.018;
  var lineGap = size * 0.012;
  var mid = '#c9a961', tip = '#f4e0a8', deep = '#140a02';
  var u = uid('bg');
  var trigrams = [
    [1,1,1],[1,1,0],[1,0,1],[1,0,0],
    [0,1,1],[0,1,0],[0,0,1],[0,0,0]
  ];

  var parts = [];
  parts.push('<svg xmlns="' + SVG_NS + '" class="bagua-svg" viewBox="0 0 ' + size + ' ' + size + '" aria-hidden="true">');
  parts.push('<defs>');
  parts.push('<style>' +
    '@keyframes bagua-wave-' + u + ' {' +
      '0%,100% { filter: brightness(0.85); transform: scale(1); opacity: 0.65; }' +
      '12%,25% { filter: brightness(1.5); transform: scale(1.08); opacity: 1; }' +
      '45%     { filter: brightness(0.85); transform: scale(1); opacity: 0.65; }' +
    '}' +
    '</style>');
  parts.push('<filter id="cast-' + u + '" x="-30%" y="-30%" width="160%" height="160%">' +
    '<feGaussianBlur in="SourceAlpha" stdDeviation="' + (size*0.004) + '" result="blur"/>' +
    '<feSpecularLighting in="blur" surfaceScale="' + (size*0.022) + '" specularConstant="1.3" specularExponent="15" lighting-color="' + tip + '" result="spec">' +
      '<feDistantLight azimuth="135" elevation="58"/>' +
    '</feSpecularLighting>' +
    '<feComposite in="spec" in2="SourceAlpha" operator="in" result="specClipped"/>' +
    '<feOffset in="SourceAlpha" dx="' + (size*0.012) + '" dy="' + (size*0.014) + '" result="sOff"/>' +
    '<feGaussianBlur in="sOff" stdDeviation="' + (size*0.008) + '" result="sBlur"/>' +
    '<feFlood flood-color="' + deep + '" flood-opacity="0.9" result="sColor"/>' +
    '<feComposite in="sColor" in2="sBlur" operator="in" result="sCast"/>' +
    '<feFlood flood-color="' + mid + '" flood-opacity="0.95" result="charColor"/>' +
    '<feComposite in="charColor" in2="SourceAlpha" operator="in" result="charFilled"/>' +
    '<feGaussianBlur in="SourceAlpha" stdDeviation="' + (size*0.01) + '" result="aoBlur"/>' +
    '<feComposite in="aoBlur" in2="SourceAlpha" operator="out" result="ao"/>' +
    '<feFlood flood-color="' + deep + '" flood-opacity="0.6" result="aoColor"/>' +
    '<feComposite in="aoColor" in2="ao" operator="in" result="aoFinal"/>' +
    '<feMerge>' +
      '<feMergeNode in="sCast"/>' +
      '<feMergeNode in="aoFinal"/>' +
      '<feMergeNode in="charFilled"/>' +
      '<feMergeNode in="specClipped"/>' +
    '</feMerge>' +
    '</filter>');
  parts.push('</defs>');

  // 分隔环
  parts.push('<circle cx="' + cx + '" cy="' + cy + '" r="' + (ringR - trigSpan*0.55) + '" fill="none" stroke="' + mid + '" stroke-width="0.6" opacity="0.3"/>');

  // 8 卦象
  for (var i = 0; i < 8; i++) {
    var tri = trigrams[i];
    var angle = (i * 45 - 90) * Math.PI / 180;
    var tx = cx + Math.cos(angle) * ringR;
    var ty = cy + Math.sin(angle) * ringR;
    var rot = i * 45;
    var delay = -(7 - i) * 1.5;
    parts.push('<g filter="url(#cast-' + u + ')" transform="translate(' + tx + ' ' + ty + ') rotate(' + rot + ')">');
    parts.push('<g style="animation: bagua-wave-' + u + ' 12s ease-in-out ' + delay + 's infinite; transform-origin: 0 0;">');
    for (var j = 0; j < 3; j++) {
      var yOffset = (j - 1) * (lineH + lineGap);
      if (tri[j]) {
        parts.push('<rect x="' + (-trigSpan/2) + '" y="' + (yOffset - lineH/2) + '" width="' + trigSpan + '" height="' + lineH + '" fill="' + mid + '" rx="' + (lineH * 0.3) + '"/>');
      } else {
        var half = trigSpan * 0.38;
        parts.push('<rect x="' + (-trigSpan/2) + '" y="' + (yOffset - lineH/2) + '" width="' + half + '" height="' + lineH + '" fill="' + mid + '" rx="' + (lineH * 0.3) + '"/>');
        parts.push('<rect x="' + (trigSpan/2 - half) + '" y="' + (yOffset - lineH/2) + '" width="' + half + '" height="' + lineH + '" fill="' + mid + '" rx="' + (lineH * 0.3) + '"/>');
      }
    }
    parts.push('</g></g>');
  }

  // 太极
  var taiji = size * 0.22, tr = taiji / 2;
  parts.push('<g filter="url(#cast-' + u + ')" transform="translate(' + cx + ' ' + cy + ')">');
  parts.push('<circle cx="0" cy="0" r="' + tr + '" fill="none" stroke="' + mid + '" stroke-width="' + (taiji*0.03) + '"/>');
  parts.push('<path d="M 0 ' + (-tr) + ' A ' + tr + ' ' + tr + ' 0 0 1 0 ' + tr + ' A ' + (tr/2) + ' ' + (tr/2) + ' 0 0 1 0 0 A ' + (tr/2) + ' ' + (tr/2) + ' 0 0 0 0 ' + (-tr) + ' Z" fill="' + mid + '"/>');
  parts.push('<circle cx="0" cy="' + (-tr/2) + '" r="' + (taiji*0.09) + '" fill="' + mid + '"/>');
  parts.push('</g>');
  // 阳鱼暗点（在 cast 外）
  parts.push('<circle cx="' + cx + '" cy="' + (cy + taiji/4) + '" r="' + (taiji*0.09) + '" fill="' + deep + '"/>');

  parts.push('</svg>');
  return svgFromString(parts.join(''));
}

$('baguaRotate').appendChild(buildBaguaSvg());

/* ==============================================================
   铜钱 SVG — DOMParser 装配
   ============================================================== */
function buildCoinSvg(size, face) {
  face = face || '字';
  size = size || 82;
  var u = uid('coin');
  var p = {
    base:'#8a6220', highlight:'#d9a94a', tip:'#f0d080',
    shadow:'#3a2208', deep:'#1a0c02',
    charFill:'#6a4818', charTip:'#e8c878', charShadow:'#1a0c02',
  };
  var r = size / 2;
  var hole = size * 0.2;
  var holeRim = size * 0.28;
  var outerRim = size * 0.48;
  var chars = ['乾','亨','元','利'];
  var charPos = [
    { x: r,             y: r - size*0.3 },
    { x: r,             y: r + size*0.3 },
    { x: r + size*0.3,  y: r },
    { x: r - size*0.3,  y: r },
  ];
  var yang = (face === '字');

  var parts = [];
  // drop-shadow 走 CSS（.coin-spin svg），摇卦态覆盖为只剩黑投影；避免 iOS Safari
  // 外层 blur 嵌套内层金色 drop-shadow 时退化为 viewBox 矩形的合成 bug。
  parts.push('<svg xmlns="' + SVG_NS + '" width="' + size + '" height="' + size + '" viewBox="0 0 ' + size + ' ' + size + '">');

  parts.push('<defs>');
  parts.push('<radialGradient id="face-' + u + '" cx="35%" cy="28%" r="85%">' +
    '<stop offset="0%" stop-color="' + p.highlight + '" stop-opacity="0.9"/>' +
    '<stop offset="30%" stop-color="' + p.base + '"/>' +
    '<stop offset="70%" stop-color="' + p.base + '"/>' +
    '<stop offset="100%" stop-color="' + p.shadow + '"/>' +
    '</radialGradient>');
  parts.push('<linearGradient id="outerRim-' + u + '" x1="25%" y1="20%" x2="80%" y2="85%">' +
    '<stop offset="0%" stop-color="' + p.tip + '"/>' +
    '<stop offset="40%" stop-color="' + p.highlight + '"/>' +
    '<stop offset="100%" stop-color="' + p.shadow + '"/>' +
    '</linearGradient>');
  parts.push('<linearGradient id="holeRim-' + u + '" x1="25%" y1="20%" x2="80%" y2="85%">' +
    '<stop offset="0%" stop-color="' + p.tip + '"/>' +
    '<stop offset="50%" stop-color="' + p.highlight + '"/>' +
    '<stop offset="100%" stop-color="' + p.shadow + '"/>' +
    '</linearGradient>');
  parts.push('<filter id="patina-' + u + '">' +
    '<feTurbulence type="fractalNoise" baseFrequency="2.5" numOctaves="3" seed="3"/>' +
    '<feColorMatrix values="0 0 0 0 0.1   0 0 0 0 0.15   0 0 0 0 0.05   0 0 0 0.4 0"/>' +
    '<feComposite in2="SourceGraphic" operator="in"/>' +
    '</filter>');
  parts.push('<filter id="scratch-' + u + '">' +
    '<feTurbulence type="turbulence" baseFrequency="0.8 0.05" numOctaves="2" seed="5"/>' +
    '<feColorMatrix values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 0.25 0"/>' +
    '<feComposite in2="SourceGraphic" operator="in"/>' +
    '</filter>');
  parts.push('<filter id="cast-' + u + '" x="-40%" y="-40%" width="180%" height="180%">' +
    '<feGaussianBlur in="SourceAlpha" stdDeviation="' + (size*0.006) + '" result="blur"/>' +
    '<feSpecularLighting in="blur" surfaceScale="' + (size*0.02) + '" specularConstant="1.2" specularExponent="18" lighting-color="' + p.charTip + '" result="spec">' +
      '<feDistantLight azimuth="135" elevation="55"/>' +
    '</feSpecularLighting>' +
    '<feComposite in="spec" in2="SourceAlpha" operator="in" result="specClipped"/>' +
    '<feOffset in="SourceAlpha" dx="' + (size*0.015) + '" dy="' + (size*0.02) + '" result="sOff"/>' +
    '<feGaussianBlur in="sOff" stdDeviation="' + (size*0.01) + '" result="sBlur"/>' +
    '<feFlood flood-color="' + p.charShadow + '" flood-opacity="0.85" result="sColor"/>' +
    '<feComposite in="sColor" in2="sBlur" operator="in" result="sCast"/>' +
    '<feFlood flood-color="' + p.charFill + '" result="charColor"/>' +
    '<feComposite in="charColor" in2="SourceAlpha" operator="in" result="charFilled"/>' +
    '<feGaussianBlur in="SourceAlpha" stdDeviation="' + (size*0.012) + '" result="aoBlur"/>' +
    '<feComposite in="aoBlur" in2="SourceAlpha" operator="out" result="ao"/>' +
    '<feFlood flood-color="' + p.deep + '" flood-opacity="0.5" result="aoColor"/>' +
    '<feComposite in="aoColor" in2="ao" operator="in" result="aoFinal"/>' +
    '<feMerge>' +
      '<feMergeNode in="sCast"/>' +
      '<feMergeNode in="aoFinal"/>' +
      '<feMergeNode in="charFilled"/>' +
      '<feMergeNode in="specClipped"/>' +
    '</feMerge>' +
    '</filter>');
  parts.push('<mask id="faceMask-' + u + '">' +
    '<rect width="' + size + '" height="' + size + '" fill="black"/>' +
    '<circle cx="' + r + '" cy="' + r + '" r="' + outerRim + '" fill="white"/>' +
    '<rect x="' + (r-hole/2) + '" y="' + (r-hole/2) + '" width="' + hole + '" height="' + hole + '" fill="black"/>' +
    '</mask>');
  parts.push('</defs>');

  parts.push('<circle cx="' + r + '" cy="' + r + '" r="' + (r - 0.5) + '" fill="url(#face-' + u + ')"/>');
  parts.push('<circle cx="' + r + '" cy="' + r + '" r="' + (r - size*0.04) + '" fill="none" stroke="url(#outerRim-' + u + ')" stroke-width="' + (size*0.08) + '"/>');
  parts.push('<circle cx="' + r + '" cy="' + r + '" r="' + outerRim + '" fill="none" stroke="' + p.deep + '" stroke-width="' + (size*0.012) + '" opacity="0.7"/>');
  parts.push('<circle cx="' + r + '" cy="' + r + '" r="' + (r - 0.5) + '" fill="none" stroke="' + p.deep + '" stroke-width="1" opacity="0.85"/>');
  parts.push('<g mask="url(#faceMask-' + u + ')">');
  parts.push('<rect width="' + size + '" height="' + size + '" filter="url(#patina-' + u + ')"/>');
  parts.push('<rect width="' + size + '" height="' + size + '" filter="url(#scratch-' + u + ')" opacity="0.6"/>');
  parts.push('</g>');
  if (yang) {
    parts.push('<g filter="url(#cast-' + u + ')">');
    for (var i = 0; i < 4; i++) {
      parts.push('<text x="' + charPos[i].x + '" y="' + charPos[i].y + '" font-size="' + (size*0.2) + '" font-weight="900" fill="' + p.charFill + '" text-anchor="middle" dominant-baseline="central" font-family="STKaiti,Kaiti SC,Kaiti TC,楷体,KaiTi,Noto Serif SC,serif">' + chars[i] + '</text>');
    }
    parts.push('</g>');
  } else {
    parts.push('<g filter="url(#cast-' + u + ')">');
    for (var k = 0; k < 4; k++) {
      parts.push('<g transform="rotate(' + (k*90) + ' ' + r + ' ' + r + ')">' +
        '<ellipse cx="' + r + '" cy="' + (r*0.45) + '" rx="' + (size*0.04) + '" ry="' + (size*0.09) + '" fill="' + p.charFill + '"/>' +
        '</g>');
    }
    parts.push('<circle cx="' + r + '" cy="' + r + '" r="' + (size*0.05) + '" fill="' + p.charFill + '"/>');
    parts.push('</g>');
  }
  parts.push('<rect x="' + (r-holeRim/2) + '" y="' + (r-holeRim/2) + '" width="' + holeRim + '" height="' + holeRim + '" fill="none" stroke="url(#holeRim-' + u + ')" stroke-width="' + (size*0.035) + '" rx="' + (size*0.003) + '"/>');
  parts.push('<rect x="' + (r-holeRim/2) + '" y="' + (r-holeRim/2) + '" width="' + holeRim + '" height="' + holeRim + '" fill="none" stroke="' + p.deep + '" stroke-width="0.6" opacity="0.7" rx="' + (size*0.003) + '"/>');
  parts.push('<rect x="' + (r-hole/2) + '" y="' + (r-hole/2) + '" width="' + hole + '" height="' + hole + '" fill="#000" rx="0.3"/>');
  var edgeW = Math.max(0.5, size*0.006);
  parts.push('<path d="M ' + (r-hole/2+0.5) + ' ' + (r-hole/2+0.5) + ' L ' + (r+hole/2-0.5) + ' ' + (r-hole/2+0.5) + '" stroke="' + p.tip + '" stroke-width="' + edgeW + '" opacity="0.55"/>');
  parts.push('<path d="M ' + (r-hole/2+0.5) + ' ' + (r-hole/2+0.5) + ' L ' + (r-hole/2+0.5) + ' ' + (r+hole/2-0.5) + '" stroke="' + p.tip + '" stroke-width="' + Math.max(0.4, size*0.005) + '" opacity="0.35"/>');
  parts.push('<path d="M ' + (r-hole/2+0.5) + ' ' + (r+hole/2-0.5) + ' L ' + (r+hole/2-0.5) + ' ' + (r+hole/2-0.5) + ' L ' + (r+hole/2-0.5) + ' ' + (r-hole/2+0.5) + '" stroke="#000" stroke-width="' + Math.max(0.6, size*0.008) + '" opacity="0.9" fill="none"/>');

  parts.push('</svg>');
  return svgFromString(parts.join(''));
}

/* 设备加速度全局监听 —— setDivineMode 控制挂/摘。
 * 原始 mag 采样分发给所有 subscribeShake 回调（awaitManualToss 通过它做状态机）。 */
function _onDeviceMotion(e) {
  _motionEverFired = true;
  var a = e.acceleration || e.accelerationIncludingGravity;
  if (!a) return;
  var mag = Math.hypot(a.x || 0, a.y || 0, a.z || 0);
  for (var i = _shakeSubs.length - 1; i >= 0; i--) {
    try { _shakeSubs[i](mag); } catch (_) { /* no-op */ }
  }
}

function armShakeDetector() {
  if (_motionListenerActive) return;
  if (typeof window.DeviceMotionEvent === 'undefined') return;
  window.addEventListener('devicemotion', _onDeviceMotion);
  _motionListenerActive = true;
  // listener 成功挂上即视为设备支持；权限拒绝走不到这里（requestPermission
  // 的 denied 分支会显式置 _motionSupported = false）
  _motionSupported = true;
}

function disarmShakeDetector() {
  if (!_motionListenerActive) return;
  window.removeEventListener('devicemotion', _onDeviceMotion);
  _motionListenerActive = false;
}

function subscribeShake(fn) {
  _shakeSubs.push(fn);
  return function () {
    var i = _shakeSubs.indexOf(fn);
    if (i >= 0) _shakeSubs.splice(i, 1);
  };
}

/* 统一切换"握/摇/落"三段视觉状态 —— CSS 通过
 * `#shakeProgress[data-toss-phase="..."]` 选择器驱动铜钱区样式变化。
 *
 * 同时同步顶部 active dash 的子 class，使 6 段 dash 进度条变成节拍器：
 *   hold/null → 纯 .active（呼吸脉冲）
 *   shake     → .active.active-shake（实心亮金，脉冲停）
 *   land      → .active.active-land（一次 ping 闪烁）
 * 用户扫顶部一眼就知道当前爻在哪个阶段，不用读文字。 */
function setTossPhase(phase) {
  var sp = $('shakeProgress');
  if (!sp) return;
  if (phase) sp.setAttribute('data-toss-phase', phase);
  else sp.removeAttribute('data-toss-phase');

  var bars = $('tossBars');
  if (!bars) return;
  var active = bars.querySelector('span.active');
  if (!active) return;
  active.classList.remove('active-shake', 'active-land');
  if (phase === 'shake') active.classList.add('active-shake');
  else if (phase === 'land') active.classList.add('active-land');
}

/* 归位动作：LAND 态（各枚硬币在 seededLayout 给出的随机位置）→ HOLD 态。
 * 每枚硬币向 coinsRow 中心方向收拢 35%，同步 halo 升起 + blur 加深，
 * 500ms 内完成。用户反馈核心："应该要先归位，同步光晕升起让硬币变得模糊"。
 *
 * 实现要点：
 *   - 不重建 DOM，直接在当前 .just-landed 的 wrap 上做 class 切换
 *   - 每枚 wrap 各自算 (dx, dy) 相对 coinsRow 中心的"收拢向量"，
 *     写入 CSS 变量 --home-dx / --home-dy
 *   - CSS 的 .coin-wrap.holding.regathering 通过 translate: var(--home-dx, 0)...
 *     + transition: translate 500ms 把"归位移动"表达成 compositor-friendly 的
 *     translate 过渡（GPU 路径，不触发 layout reflow）
 *   - .holding 同时被加上：halo-hold-fade-in 500ms 自动跑，coin-spin 的
 *     filter blur/opacity 通过 transition 同步过渡 */
function startRegather() {
  var wraps = $('coinsRow').querySelectorAll('.coin-wrap.just-landed');
  if (!wraps.length) return;
  var row = $('coinsRow');
  var rowRect = row.getBoundingClientRect();
  var cx = rowRect.width / 2;
  var cy = rowRect.height / 2;
  for (var i = 0; i < wraps.length; i++) {
    var w = wraps[i];
    var wRect = w.getBoundingClientRect();
    var wx = wRect.left + wRect.width / 2 - rowRect.left;
    var wy = wRect.top + wRect.height / 2 - rowRect.top;
    // 收拢 35% —— 三枚向中心靠但仍能分辨是三枚（太近视觉重叠，太远感觉不到"归位"）
    var dx = (cx - wx) * 0.35;
    var dy = (cy - wy) * 0.35;
    w.style.setProperty('--home-dx', dx + 'px');
    w.style.setProperty('--home-dy', dy + 'px');
    w.classList.remove('just-landed');
    w.classList.add('holding', 'regathering');
  }
}

/* 把当前 .coin-wrap 从"握"态切到"摇"态（或反向）。
 * 不重建 DOM，只换 class —— 避免 SVG 重新构建导致的一帧闪烁。 */
function coinsEnterShake() {
  var wraps = $('coinsRow').querySelectorAll('.coin-wrap');
  for (var i = 0; i < wraps.length; i++) {
    wraps[i].classList.remove('holding');
    wraps[i].classList.add('shaking');
  }
}
/* coinsEnterHold(opts)
 *   opts.entering=true → 同时加 .entering 瞬态类，CSS 里 @keyframes holding-enter
 *     跑一次 500ms 把铜钱从"无"（opacity 0 / scale 0.82 / blur 10px）渐显到
 *     HOLD 稳态（0.82 / 0.94 / 6px）。520ms 后清除 .entering 让稳态 animation
 *     (coin-breathe + coin-hold-drift) 接手。用于后续爻（idx > 0）入场。
 *   不传参数 → 只做 shaking/just-landed/gathering → holding 的 class 切换
 *     （coinsEnterSandGather 跑完 800ms 后调此函数不传 entering，把 .gathering
 *      换成 .holding 交棒到稳态 animation）。 */
function coinsEnterHold(opts) {
  var entering = !!(opts && opts.entering);
  var wraps = $('coinsRow').querySelectorAll('.coin-wrap');
  for (var i = 0; i < wraps.length; i++) {
    wraps[i].classList.remove('shaking', 'just-landed', 'gathering');
    wraps[i].classList.add('holding');
    if (entering) wraps[i].classList.add('entering');
  }
  if (entering) {
    setTimeout(function () {
      var ws = $('coinsRow').querySelectorAll('.coin-wrap.entering');
      for (var j = 0; j < ws.length; j++) ws[j].classList.remove('entering');
    }, 520);
  }
}

/* 手摇模式首爻（idx === 0）入场仪式 —— 金砂聚合 800ms。
 * 走独立 .gathering 类而非复用 .entering：沙聚合叙事（多层 radial-gradient
 * 云从分散汇聚到中心）和 holding-enter 的 blur/scale fade-in 视觉语言不同，
 * 独立类让 CSS 规则清晰、测试可断言、将来要改动互不串扰。
 *
 * 调用后 800ms 内 sand-converge + coin-crystallize 两组 keyframes 并行跑完，
 * coin-crystallize 末帧（opacity 0.82 / scale 0.94 / blur 6px / translate
 * -1.5px 0.5px）逐字对齐 .coin-wrap.holding 稳态，保证切 .holding 时无跳帧。
 *
 * 不用 animationend 监听 —— sleep(800) 简单稳定，兜底 timeout 不会比 css
 * 动画更晚（浏览器不跑满 animation-duration 是 spec 允许的，监听器反而可能
 * 漏事件）。 */
function coinsEnterSandGather() {
  var wraps = $('coinsRow').querySelectorAll('.coin-wrap');
  for (var i = 0; i < wraps.length; i++) {
    wraps[i].classList.remove('shaking', 'just-landed', 'holding', 'entering');
    wraps[i].classList.add('gathering');
  }
}

/* 等待一爻"落定"触发 —— startDivine 每爻循环内调用。
 * divineMode 分发：auto 走固定 600ms timer，manual 走手势状态机。
 * 返回 Promise<{peakMag}> —— peakMag 留给未来可能的"强度映射"特性消费。
 *
 * isFirst 仅对 manual 生效：第一爻跳过"静候门槛"（此时用户才刚按下起卦）。 */
function awaitShakeSettle(getCancelled, isFirst) {
  if (divineMode === 'auto') {
    return sleep(600).then(function () { return { peakMag: 0 }; });
  }
  return awaitManualToss(getCancelled, isFirst);
}

/* 手摇模式单爻状态机：
 *
 *   QUIET_WAIT ──(mag<LO 持续 QUIET_MS)──▶ HOLD ──(mag>HI)──▶ SHAKING ──┐
 *        ▲                                                               │
 *        └───────── mag≥LO 重置 quiet 计时（UI 提示"请持稳手机"）         │
 *                                                                        │
 *        SHAKING ──(经过 MIN_SHAKE_MS 且 mag<LO)──▶ resolve              │
 *        SHAKING ──────────────────────────────────────────────────────┘
 *
 * isFirst=true 跳过 QUIET_WAIT 直接进 HOLD（第一爻用户刚按下起卦，谈不上"上一爻余震"）。
 *
 * 兜底：coinStage 点击任意阶段都强制推进；即使走点击 bypass 也强制最小
 * MIN_SHAKE_MS 的视觉演出（否则仪式感塌）。覆盖桌面 / Android HTTP / 权限拒绝。
 */
function awaitManualToss(getCancelled, isFirst) {
  // 防御：若上一次 awaitManualToss 的 cleanup 尚未触发（startDivine 或
  // cancelCurrentDivine 的入口正常会先调掉，这里是双保险），立即执行。
  if (_currentTossCleanup) {
    try { _currentTossCleanup(); } catch (_) { /* no-op */ }
  }
  return new Promise(function (resolve) {
    var state = isFirst ? 'HOLD' : 'QUIET_WAIT';
    var quietSince = Date.now();
    var riseStartMs = 0;
    var peakMag = 0;
    var lastPeakHaptic = 0;  // SHAKE 峰值回响去抖：闭包局部，每爻独立窗口
    var settled = false;
    var coinStage = $('coinStage');

    function holdHintText() {
      // 基于 capability（_motionSupported）而非 witness（_motionEverFired）：
      // 已授权 iOS / Android HTTPS 即便用户还没动也显示"轻摇可得一爻"，
      // 不再把"没收到首个事件"误报为"设备摇不动"。
      return _motionSupported
        ? '持铜钱 · 轻摇可得一爻'
        : '持铜钱 · 摇手机或点击铜钱';
    }

    $('tossHint').textContent = (state === 'HOLD') ? holdHintText() : '请持稳手机';

    // 2s fallback 兜底：设备不支持 / 拒权才切"点击铜钱"文案。
    // 支持的设备即使 2s 内未收到事件也不切 —— 避免对"还没动的用户"误报。
    var noMotionHintTimer = setTimeout(function () {
      if (settled || _motionEverFired || _motionSupported) return;
      if (state !== 'SHAKING') {
        $('tossHint').textContent = '摇不动？点击铜钱区也可定爻';
      }
    }, NO_MOTION_HINT_MS);

    function enterShaking(initialMag) {
      if (state === 'SHAKING') return;
      state = 'SHAKING';
      riseStartMs = Date.now();
      peakMag = initialMag || 0;
      setTossPhase('shake');
      coinsEnterShake();
      $('tossHint').textContent = '凝神摇卦…';
      haptic(30);
    }

    function finish() {
      if (settled) return;
      settled = true;
      if (_currentTossCleanup === finish) _currentTossCleanup = null;
      unsub();
      coinStage.removeEventListener('click', onClick);
      clearTimeout(noMotionHintTimer);
      resolve({ peakMag: peakMag });
    }
    // 暴露同步 abort 句柄：cancelCurrentDivine / 下一轮 startDivine 入口直接
    // 调 finish 立即解绑监听，避免"_divineSeq 改了但 listener 还活 150ms"的
    // stale handler 污染新 run（Codex adversarial review HIGH finding）。
    _currentTossCleanup = finish;

    // 点击 bypass：任何阶段点击铜钱都强制走完 SHAKE 最小视觉再 resolve
    function onClick() {
      if (settled) return;
      if (state !== 'SHAKING') enterShaking(0);
      var elapsed = Date.now() - riseStartMs;
      var remaining = Math.max(0, MIN_SHAKE_MS - elapsed);
      setTimeout(finish, remaining);
    }
    coinStage.addEventListener('click', onClick);

    var unsub = subscribeShake(function (mag) {
      if (settled) return;
      var now = Date.now();

      if (state === 'QUIET_WAIT') {
        if (mag < SHAKE_LO) {
          if (now - quietSince >= QUIET_MS) {
            state = 'HOLD';
            $('tossHint').textContent = holdHintText();
          }
        } else {
          quietSince = now;
          $('tossHint').textContent = '请持稳手机';
        }
        return;
      }

      if (state === 'HOLD') {
        if (mag > SHAKE_HI) enterShaking(mag);
        return;
      }

      if (state === 'SHAKING') {
        if (mag > peakMag) peakMag = mag;
        // 峰值回响：每次越过 HI 阈值给一次 haptic(8) 轻震，200ms 去抖避免密集。
        // 表达"铜钱感知到腕部动作"的物理回响，不是 UI 状态信号。
        // 与落定阶段的 haptic(18) 幅度错开，用户能听出"摇→落"的分层。
        if (mag > SHAKE_HI && (now - lastPeakHaptic) > 200) {
          haptic(8);
          lastPeakHaptic = now;
        }
        if ((now - riseStartMs) >= MIN_SHAKE_MS && mag < SHAKE_LO) finish();
        return;
      }
    });
    // 此处不再 setInterval 轮询 getCancelled：取消走 _currentTossCleanup 同步通道
    // （Codex adversarial review HIGH finding）。getCancelled 参数保留做签名兼容
    // 与 awaitShakeSettle 对齐，目前未被内部读取。
  });
}

/* 卦象 progressive preview — 每摇一爻在顶部追加一行（初爻在底，传统周易方向） */
function resetHexPreview() {
  clearChildren($('hexPreview'));
}

function appendYaoToHexPreview(lineVal) {
  var box = $('hexPreview');
  var isYang = (lineVal === 7 || lineVal === 9);
  var isChanging = (lineVal === 6 || lineVal === 9);
  var cls = 'hex-yao ' + (isYang ? 'yang' : 'yin');
  if (isChanging) cls += ' changing';
  var row = el('div', { className: cls });
  // 初爻在底 → 新 yao 插到现有第一个 child 之前，DOM 里保持 [最新, ..., 最早]
  // 配合 CSS flex-direction: column + justify-content: flex-end 形成自底向上生长
  if (box.firstChild) box.insertBefore(row, box.firstChild);
  else box.appendChild(row);
  // 下一帧加 .shown 触发滑入过渡
  requestAnimationFrame(function () { row.classList.add('shown'); });
}

function renderCoins(faces, seedNum, shaking) {
  var row = $('coinsRow');
  clearChildren(row);
  var layout = Core.seededLayout(seedNum);
  for (var i = 0; i < 3; i++) {
    var wrap = el('div', { className: 'coin-wrap' + (shaking ? ' shaking' : '') });
    wrap.style.left = layout[i].x + 'px';
    wrap.style.top = layout[i].y + 'px';
    // 外层 .coin-wrap 的 transform 只承担静态 rotate（摆位）+ 被 coin-shake 动画覆盖时
    // 的抖动；coin-shake 已改用独立 translate/rotate 属性，两者不冲突
    wrap.style.transform = 'rotate(' + layout[i].rot + 'deg)';
    // 外层微抖相位错位，三枚不同步
    wrap.style.animationDelay = (i * 0.03) + 's';

    // 内层 .coin-spin 承担视觉状态（blur/scale/opacity 切换）；袋中摇哲学下
    // 零旋转，只有呼吸起伏。三枚动画相位错开一点，让"气息"看起来更活。
    var spin = el('div', { className: 'coin-spin' });
    spin.style.animationDelay = (i * 0.15 + Math.random() * 0.1).toFixed(2) + 's';
    spin.appendChild(buildCoinSvg(82, faces[i] ? '字' : '花'));
    wrap.appendChild(spin);
    row.appendChild(wrap);
  }
}

/* ==============================================================
   起卦主流程
   ============================================================== */
async function startDivine() {
  if (isDivining) return;
  isDivining = true;

  // 若上一卦的 AI 解读还在流，先关掉避免把新卦的 DOM 覆盖
  cancelCurrentInterp();

  var btn = $('btnDivine');
  var app = $('app');
  var question = $('question').value.trim();

  // 序号守卫：中途切到历史/首页会调 cancelCurrentDivine 递增 _divineSeq，
  // 任何 await 醒来后 checkpoint() 发现 mySeq 失效即抛 sentinel 静默退出。
  // 递增前先拆掉上一次 awaitManualToss 的监听（正常路径下 btn.disabled 让这里
  // 不该有悬挂，但键盘 Enter / 程序化触发等旁路能绕过 disable，双保险）。
  if (_currentTossCleanup) { try { _currentTossCleanup(); } catch (_) {} }
  var mySeq = ++_divineSeq;
  function checkpoint() {
    if (mySeq !== _divineSeq) throw new Error('__divine_cancelled');
  }

  resetResultCards();
  resetHexPreview();
  $('coinResult').textContent = '';
  app.classList.remove('has-result');
  app.classList.add('is-shaking');
  app.setAttribute('data-mode', divineMode);
  $('baguaStage').classList.add('mode-shake');
  $('coinStage').setAttribute('aria-hidden', 'false');
  $('shakeProgress').setAttribute('aria-hidden', 'false');

  // 起卦进行中禁用模式切换（避免状态机中途被扰）
  document.querySelectorAll('.df-mode').forEach(function (b) { b.disabled = true; });

  btn.disabled = true;
  haptic([60, 40, 60]);

  // AbortController：让 fetch 可被 backBtn 点击真正中断，并设置 10s 兜底超时。
  // 不声明在 try 外——异常路径靠下面的 catch AbortError 统一处理 + finally 清 timeout。
  _divineAbort = new AbortController();
  var _divineTimeoutId = setTimeout(function () { _divineAbort.abort(); }, 10000);

  try {
    var resp = await fetch(API_BASE + '/api/divine', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: question || undefined }),
      signal: _divineAbort.signal,
    });
    clearTimeout(_divineTimeoutId);
    checkpoint();
    if (!resp.ok) throw new Error('请求失败 (' + resp.status + ')');
    var data = await resp.json();
    checkpoint();
    var lines = data.hexagram.lines;

    var barsBox = $('tossBars');
    clearChildren(barsBox);
    for (var i = 0; i < 6; i++) barsBox.appendChild(el('span'));

    var tossNames = ['壹','贰','叁','肆','伍','陆'];
    for (var idx = 0; idx < 6; idx++) {
      $('tossLabel').textContent = '第 ' + tossNames[idx] + ' 爻';
      $('tossCount').textContent = (idx + 1) + ' / 6';
      $('tossInstr').textContent = '凝神静候';
      $('coinResult').textContent = '';

      var bars = barsBox.children;
      for (var j = 0; j < 6; j++) {
        bars[j].className = j < idx ? 'done' : (j === idx ? 'active' : '');
      }

      // 手摇 vs 自动：初始视觉态不同
      //   手摇 = HOLD 态（铜钱聚拢静置，等用户摇）
      //   自动 = 直接进 SHAKE 态（铜钱持续随机翻转 600ms 后落定）
      var shakingFaces = [Math.random() > 0.5, Math.random() > 0.5, Math.random() > 0.5];
      if (divineMode === 'manual') {
        setTossPhase('hold');
        renderCoins(shakingFaces, Date.now() + idx, false);
        if (idx === 0) {
          // 首爻仪式感：金砂聚合 800ms —— 沙云从分散汇聚到中心凝结成硬币
          // 本体，完成后硬币稳态数值（scale 0.94 / opacity 0.82 / blur 6px /
          // translate -1.5px 0.5px）由 coin-crystallize keyframes 100% 末帧
          // 精确对齐 .coin-wrap.holding .coin-spin，切稳态无跳帧。
          coinsEnterSandGather();
          $('tossHint').textContent = '金砂成形…';
          await sleep(800);
          checkpoint();
          coinsEnterHold();  // 不带 entering：移除 .gathering 加 .holding，走稳态
        } else {
          // 后续爻：continue with 500ms holding-enter fade-in（与之前一致，
          // 沙聚合只是首爻的仪式入场，不在每爻重跑以免拖慢节奏）。
          coinsEnterHold({ entering: true });
        }
        $('tossHint').textContent = _motionSupported
          ? '持铜钱 · 轻摇可得一爻'
          : '持铜钱 · 摇手机或点击铜钱';
      } else {
        setTossPhase('shake');
        renderCoins(shakingFaces, Date.now() + idx, true);
        $('tossHint').textContent = '铜钱自行翻转中…';
      }

      await awaitShakeSettle(function () { return mySeq !== _divineSeq; }, idx === 0);
      checkpoint();

      // 落定阶段 — 按真实爻值
      setTossPhase('land');
      var lineVal = lines[idx];
      var faces = Core.coinsForLine(lineVal);
      // 洗牌使视觉上位置不固定
      for (var m = faces.length - 1; m > 0; m--) {
        var n = Math.floor(Math.random() * (m + 1));
        var tmp = faces[m]; faces[m] = faces[n]; faces[n] = tmp;
      }
      // 三枚铜钱错峰落地 —— 不再一次 renderCoins 重建 DOM（那样三枚会同帧落地，
      // 视觉上很假）。而是在既有 .coin-wrap 上 in-place 替换 .coin-spin 的 SVG，
      // 用独立 setTimeout 让每枚铜钱走自己的时间线。
      //
      // 位置洗牌已在上面做过；这里再独立洗"落地先后顺序"，两者解耦，避免
      // 出现"position 2 永远最后落"这种可识别的假模式。
      var _order = [0, 1, 2];
      for (var _p = _order.length - 1; _p > 0; _p--) {
        var _q = Math.floor(Math.random() * (_p + 1));
        var _t = _order[_p]; _order[_p] = _order[_q]; _order[_q] = _t;
      }
      // 三枚铜钱抛出时刻错开 ~80ms —— 像三个手指先后弹出，看起来是
      // "先后抛出"的自然不齐；再小眼睛读不出差别，再大显得刻意
      var _baseDelays = [0, 80, 160];  // ms
      var _landSched = [0, 0, 0];
      for (var _s = 0; _s < 3; _s++) {
        _landSched[_order[_s]] = _baseDelays[_s] + Math.floor(Math.random() * 80 - 40);
      }

      var _wraps = $('coinsRow').querySelectorAll('.coin-wrap');
      (function (mySeqLocal) {
        for (var _c = 0; _c < 3; _c++) {
          (function (coinIdx) {
            setTimeout(function () {
              if (mySeqLocal !== _divineSeq) return;
              var w = _wraps[coinIdx];
              if (!w) return;
              var spin = w.querySelector('.coin-spin');
              if (spin) {
                clearChildren(spin);
                spin.appendChild(buildCoinSvg(82, faces[coinIdx] ? '字' : '花'));
              }
              w.classList.remove('shaking');
              w.classList.add('just-landed');
              haptic(18);
            }, Math.max(0, _landSched[coinIdx]));
          })(_c);
        }
      })(mySeq);

      // 等最后一枚完成全程抛落弹跳动画（coin-toss 时长 550ms）
      // 然后再刷新文案/Progressive 预览，避免"字还没落铜钱还在弹"的割裂
      var _maxDelay = Math.max(_landSched[0], _landSched[1], _landSched[2]);
      await sleep(Math.max(0, _maxDelay) + 560);
      checkpoint();

      var lineType = lineVal === 6 ? '老阴（变）' : lineVal === 7 ? '少阳'
                   : lineVal === 8 ? '少阴' : '老阳（变）';
      var yinYang = (lineVal === 7 || lineVal === 9) ? '阳爻' : '阴爻';
      $('tossInstr').textContent = lineType;
      $('tossHint').textContent = yinYang;
      $('coinResult').textContent = Core.formatCoinResult(faces);
      appendYaoToHexPreview(lineVal);

      // 爻间屏息：
      //   手摇 + 非末爻：拆 1000ms 为 450ms 全亮 "阳爻" + 550ms 过渡文案，
      //                   消除"这爻结束了吗"的不确定感，配合顶部 dash
      //                   .active-land → .done 的过渡双通道表达"正在推进"。
      //   手摇末爻 / 自动：保持整段 sleep —— 末爻后接 sleep(520) 进结果页，
      //                   已经是叙事过渡；自动连续节奏不需要中间叙事。
      // 无论哪条路径，awaitManualToss 的 QUIET_WAIT 仍能兜住用户持续晃动的情况。
      if (divineMode === 'manual' && idx < 5) {
        await sleep(450);
        checkpoint();
        // 启动"归位"动作 —— 3 枚落定硬币向中心收拢，同步 halo 升起 + blur 加深。
        // 450ms 已经让用户充分读到"阳爻"，现在进入过渡态。
        startRegather();
        $('tossHint').textContent = '凝神片刻 · 下一爻蓄势';
        await sleep(550);
        checkpoint();
      } else {
        var _restMs = (divineMode === 'manual') ? 1000 : 700;
        await sleep(_restMs);
        checkpoint();
      }
    }

    var barsAll = $('tossBars').children;
    for (var k = 0; k < 6; k++) barsAll[k].className = 'done';
    haptic([40, 30, 80]);

    // 六爻全部 done → 切到结果页前的"屏息停顿"。
    // 240ms 过短，用户反馈缺少仪式感；520ms 让最后一爻完成态在视网膜上多停一拍，
    // 模拟"铜钱落定 → 师者凝神 → 天机现前"的递进节奏。与分层渐现的第一段
    // (.result-top delay 0s) 首尾相接，形成完整的"吸气 → 揭示"弧线。
    await sleep(520);
    checkpoint();
    app.classList.remove('is-shaking');
    app.removeAttribute('data-mode');
    $('baguaStage').classList.remove('mode-shake');
    $('coinStage').setAttribute('aria-hidden', 'true');
    $('shakeProgress').setAttribute('aria-hidden', 'true');
    setTossPhase(null);

    app.classList.add('has-result');
    // 先占位保存（此时 interpretation 还是后端象辞）；AI 流式完成后再回写真实解读
    var historyTs = saveHistory(data, question);
    checkpoint();
    await showResult(data, question, historyTs);
  } catch (e) {
    // 取消路径：cancelCurrentDivine 已复位 UI，这里静默退出即可
    if (e && e.message === '__divine_cancelled') return;
    // AbortError：来自用户按 backBtn 触发的 _divineAbort.abort()（被 cancelCurrentDivine 接管状态）
    // 或 10s 超时后的 abort（此时视作网络/服务失败，显示友好提示）
    if (e && e.name === 'AbortError') {
      if (mySeq !== _divineSeq) return;  // 用户主动取消，已复位
      app.classList.remove('is-shaking');
      app.removeAttribute('data-mode');
      $('baguaStage').classList.remove('mode-shake');
      setTossPhase(null);
      showError('算卦请求超时（10 秒）。请检查网络或稍后重试。');
      return;
    }
    app.classList.remove('is-shaking');
    app.removeAttribute('data-mode');
    $('baguaStage').classList.remove('mode-shake');
    setTossPhase(null);
    showError('算卦失败：' + e.message + '。请检查后端服务是否启动。');
  } finally {
    // 清理 timeout 防泄漏（正常路径已 clearTimeout，这里是异常路径保险）
    clearTimeout(_divineTimeoutId);
    // 仅在本次仍是"当前"起卦时才做收尾；被取消则让 cancelCurrentDivine 接管状态
    if (mySeq === _divineSeq) {
      btn.disabled = false;
      isDivining = false;
      document.querySelectorAll('.df-mode').forEach(function (b) { b.disabled = false; });
      _divineAbort = null;
    }
  }
}

function resetResultCards() {
  $('paneJudgment').textContent = '';
  clearChildren($('paneLines'));
  $('paneInterp').textContent = '';
  $('paneInterp').className = 'interp';
  clearChildren($('hexes'));
  $('judgmentBox').textContent = '';
  $('resultRomaji').textContent = '';
  $('resultName').textContent = '';
  $('resultSymbol').textContent = '';
  $('resultEpithet').textContent = '';
  $('resultNum').textContent = '';
  activateTab('judgment');
}

function buildLineEl(val, isChanging, isBian) {
  return el('div', { className: Core.linesVisualClass(val, isChanging) });
}

function buildHexCol(labelTxt, hex, linesArr, changingPos, isBian) {
  var col = el('div', { className: 'col' + (isBian ? ' bian' : '') });
  col.appendChild(el('div', { className: 'label' }, labelTxt));
  var lines = el('div', { className: 'lines' });
  for (var i = 0; i < 6; i++) {
    var isChanging = changingPos && changingPos.indexOf(i + 1) !== -1;
    lines.appendChild(buildLineEl(linesArr[i], isChanging, isBian));
  }
  col.appendChild(lines);
  // 本卦下方只显示短名（顶部大字已展示四字全名，避免重复）；
  // 变卦下方显示四字全名（对齐设计稿 Image #6：如"山泽损"），便于识别。
  // Core.fullHexName 不可用时降级为 hex.name，兼容旧缓存的 iching-core.js。
  var displayName = hex.name;
  if (isBian && Core && Core.fullHexName) displayName = Core.fullHexName(hex) || hex.name;
  col.appendChild(el('div', { className: 'name' }, displayName));
  return col;
}

function buildArrowSvg() {
  var svg = document.createElementNS(SVG_NS, 'svg');
  svg.setAttribute('width', '28');
  svg.setAttribute('height', '60');
  svg.setAttribute('viewBox', '0 0 28 60');
  svg.setAttribute('fill', 'none');
  var path = document.createElementNS(SVG_NS, 'path');
  path.setAttribute('d', 'M4 30h20M18 22l6 8-6 8');
  path.setAttribute('stroke', 'currentColor');
  path.setAttribute('stroke-width', '1');
  path.setAttribute('stroke-linecap', 'round');
  path.setAttribute('stroke-linejoin', 'round');
  svg.appendChild(path);
  return svg;
}

async function showResult(data, question, historyTs) {
  var hex = data.hexagram;
  $('resultRomaji').textContent = formatHexPinyin(hex);
  // Core.fullHexName 在旧缓存的 iching-core.js 里不存在，这里做防御：拿不到就回退到 hex.name
  $('resultName').textContent = (Core && Core.fullHexName ? Core.fullHexName(hex) : '') || hex.name;
  $('resultSymbol').textContent = hex.symbol || '';  // 节点保留但 CSS 隐藏，保证前端结构测试不破
  $('resultEpithet').textContent = (hex.upper_trigram || '') + ' 上 · ' + (hex.lower_trigram || '') + ' 下';
  $('resultNum').textContent = '第 ' + hex.number + ' 卦';

  var hexesBox = $('hexes');
  clearChildren(hexesBox);
  hexesBox.appendChild(buildHexCol('本 卦', hex, hex.lines, data.changing_lines, false));

  if (data.changed_hexagram) {
    var mid = el('div', { className: 'arrow-col' });
    mid.appendChild(el('div', { className: 'bian-char' }, '变'));
    mid.appendChild(buildArrowSvg());
    hexesBox.appendChild(mid);
    var bianLines = Core.computeBianLines(hex.lines);
    hexesBox.appendChild(buildHexCol('变 卦', data.changed_hexagram, bianLines, [], true));
  } else {
    var mid2 = el('div', { className: 'arrow-col' });
    mid2.appendChild(el('div', { className: 'bian-char' }, '静'));
    hexesBox.appendChild(mid2);
    var col = el('div', { className: 'col bian' });
    col.appendChild(el('div', { className: 'label' }, '无变爻'));
    col.appendChild(el('div', { style: 'font-family: var(--font-serif); font-size: 13px; color: var(--text-dim); padding: 20px 0;' }, '本卦自现'));
    hexesBox.appendChild(col);
  }

  $('judgmentBox').textContent = data.judgment || '';
  $('paneJudgment').textContent = data.judgment || '';

  var linesUl = $('paneLines');
  clearChildren(linesUl);
  (data.lines_text || []).forEach(function(t, i) {
    var li = el('li', null, t);
    if (data.changing_lines && data.changing_lines.indexOf(i + 1) !== -1) li.classList.add('changing-line');
    linesUl.appendChild(li);
  });

  $('resultSection').scrollIntoView({ behavior: 'instant', block: 'start' });
  streamInterp(data, question, historyTs);
}

/**
 * 流式 AI 解读。
 * @param {Object} data       - /api/divine 返回数据
 * @param {string} question   - 用户的问题
 * @param {number|null} historyTs - 历史条目主键（saveHistory 返回的 ts），
 *                                  用于在流结束后把最终 Markdown 写回 localStorage。
 *
 * stale-stream 防护：每次进入 startDivine 都会递增 _interpSeq 并 close 旧 WS；
 * streamInterp 捕获自己的 mySeq，所有 handler 入口先校验当前 seq，过期立即丢弃。
 */
function streamInterp(data, question, historyTs) {
  var interp = $('paneInterp');
  interp.textContent = '正在请大师解卦...';
  interp.className = 'interp thinking';

  var wsUrl = API_BASE.replace(/^http/, 'ws') + '/ws/interpret';
  var ws;
  try { ws = new WebSocket(wsUrl); }
  catch (e) {
    interp.textContent = data.interpretation || '解读服务暂不可用';
    interp.className = 'interp';
    return;
  }
  _currentInterpWs = ws;
  var mySeq = _interpSeq;
  var isCurrent = function () { return mySeq === _interpSeq; };

  // 状态机：拆开语义不同的三个信号，避免"first"同时承担多个职责
  var hasContent   = false;   // 是否收到过 content
  var doneReceived = false;   // 是否收到 done（唯一的成功信号）
  var hadError     = false;   // 是否收到 error（UI 已显示错误文案，不得覆盖）
  var raw          = '';
  var finalized    = false;

  function finalize(success) {
    if (finalized) return;
    finalized = true;
    interp.classList.remove('typing', 'thinking');
    // 只有在显式成功时才写历史；失败/中断路径保留占位象辞作 fallback
    if (success && historyTs && raw) updateHistoryInterp(historyTs, raw);
  }

  ws.onopen = function() {
    if (!isCurrent()) return;
    ws.send(JSON.stringify({
      question: question || '',
      hexagram_name: data.hexagram.name,
      hexagram_number: data.hexagram.number,
      judgment: data.judgment,
      image: data.interpretation,
      lines_text: data.lines_text,
      changing_lines: data.changing_lines || [],
      changed_hexagram_name: data.changed_hexagram ? data.changed_hexagram.name : null,
    }));
  };
  ws.onmessage = function(ev) {
    if (!isCurrent()) return;
    var msg = JSON.parse(ev.data);
    if (msg.type === 'thinking') {
      interp.textContent = '大师正在沉思中...';
      interp.className = 'interp thinking';
    } else if (msg.type === 'content') {
      // 空 text 不算"实质 content"——防 LLM 发多个空 content event 绕过 no-content 判定
      if (!msg.text) return;
      if (!hasContent) { raw = ''; interp.className = 'interp typing'; hasContent = true; }
      raw += msg.text;
      // 经 marked + DOMPurify 双层清洗后再注入，允许的标签/属性/URL 方案见 SAFE_MD_CONFIG
      interp.innerHTML = renderMarkdownSafely(raw);
    } else if (msg.type === 'done') {
      doneReceived = true;
      // 不在此处 finalize—onclose 会调 handleStreamEnd → classifyStreamEnd，
      // 结合 hasContent 判断真实成败。done 但无 content（LLM 整段只出 reasoning）
      // 现在会正确走 'no-content' 分支显示 fallback + 重试按钮。
    } else if (msg.type === 'error') {
      hadError = true;
      interp.classList.remove('typing', 'thinking');
      // 后端限流 / LLM 异常会走这里；清空占位内容保证错误消息独占
      interp.textContent = '解读出错：' + (msg.text || '未知错误');
      appendRetry();
    }
  };
  ws.onclose = function() {
    if (!isCurrent()) return;
    handleStreamEnd(data, question, historyTs, interp, {
      doneReceived: doneReceived, hadError: hadError, hasContent: hasContent, raw: raw,
    }, finalize);
  };
  ws.onerror = function() {
    // 仅标记 hadError 并让后续 onclose 做统一收尾（浏览器保证 onerror 后会触发 onclose）
    if (!isCurrent()) return;
    // 不覆盖业务层的 error 消息；纯网络错误由 onclose 的 interrupted/no-content 分支处理
  };

  // 把 data/question/historyTs 存到 interp 上，供重试按钮闭包访问
  interp._lastStreamCtx = { data: data, question: question, historyTs: historyTs };

  function appendRetry() {
    if (interp.querySelector('.retry-interp')) return;
    var btn = el('button', { className: 'retry-interp', type: 'button' }, '重新解读');
    btn.addEventListener('click', function() {
      var ctx = interp._lastStreamCtx;
      if (ctx) streamInterp(ctx.data, ctx.question, ctx.historyTs);
    });
    interp.appendChild(btn);
  }
  // 把 appendRetry 暴露给 handleStreamEnd 用
  interp._appendRetry = appendRetry;
}

/**
 * 流结束的统一处理 —— 根据状态分类决定 UI 文案、是否重试、是否写历史。
 * 逻辑集中在 Core.classifyStreamEnd（纯函数，有独立单测）。
 */
function handleStreamEnd(data, question, historyTs, interp, state, finalize) {
  var kind = Core.classifyStreamEnd(state);
  switch (kind) {
    case 'success':
      // 已在 done 分支 finalize(true) 过了，这里只是兜底
      finalize(true);
      return;
    case 'error':
      // 错误文案已显示，重试按钮已挂，不覆盖
      finalize(false);
      return;
    case 'no-content':
      interp.textContent = data.interpretation || '解读服务暂不可用，可点击下方重试';
      if (interp._appendRetry) interp._appendRetry();
      finalize(false);
      return;
    case 'interrupted':
      // 有部分 content，但没收到 done —— 追加"中断"提示而不是覆盖
      var notice = el('div', { className: 'interp-interrupted' }, '（连接中断，解读未完成）');
      interp.appendChild(notice);
      if (interp._appendRetry) interp._appendRetry();
      finalize(false);
      return;
  }
}

/** 取消当前进行中的 AI 解读流（再起卦或返回首页时调用） */
function cancelCurrentInterp() {
  _interpSeq++;
  if (_currentInterpWs) {
    try { _currentInterpWs.close(); } catch (e) { /* no-op */ }
    _currentInterpWs = null;
  }
}

/**
 * 中止进行中的起卦动画 + 解读流，并把 UI 复位到"非起卦中"态。
 * 调用场景：摇卦中途用户点历史条目、按返回键等需要立即切换视图的动作。
 * startDivine 的 await 唤醒后 checkpoint() 会发现 _divineSeq 已变，抛 sentinel 静默退出。
 */
function cancelCurrentDivine() {
  _divineSeq++;
  // 同步拆掉 awaitManualToss 的 click / subscribeShake 监听。原 150ms poll
  // 在这段窗口里老监听还活着，用户快速返回再起卦会被老 onClick / _shakeSubs
  // 污染新 run 的 UI（Codex adversarial review HIGH finding）。
  if (_currentTossCleanup) { try { _currentTossCleanup(); } catch (_) {} }
  // 真正中断正在跑的 fetch（慢网/冷启动时不再白等浏览器默认超时）
  if (_divineAbort) { try { _divineAbort.abort(); } catch (_) {} _divineAbort = null; }
  cancelCurrentInterp();
  isDivining = false;
  $('app').classList.remove('is-shaking');
  $('app').removeAttribute('data-mode');
  $('baguaStage').classList.remove('mode-shake');
  $('coinStage').setAttribute('aria-hidden', 'true');
  $('shakeProgress').setAttribute('aria-hidden', 'true');
  setTossPhase(null);
  $('btnDivine').disabled = false;
  document.querySelectorAll('.df-mode').forEach(function (b) { b.disabled = false; });
}

/* Tabs */
function activateTab(name) {
  document.querySelectorAll('#tabs button').forEach(function(b) {
    b.classList.toggle('active', b.getAttribute('data-tab') === name);
  });
  document.querySelectorAll('#tabBody .pane').forEach(function(p) {
    p.classList.toggle('active', p.getAttribute('data-pane') === name);
  });
}
document.querySelectorAll('#tabs button').forEach(function(b) {
  b.addEventListener('click', function() { activateTab(b.getAttribute('data-tab')); });
});

/* 返回首页 */
$('backBtn').addEventListener('click', function() {
  // 起卦进行中按返回键也要中止（否则老 startDivine 会覆盖首页回到的 DOM）
  cancelCurrentDivine();
  $('app').classList.remove('has-result');
  window.scrollTo({ top: 0, behavior: 'smooth' });
});

/* 分享（退化为复制链接） */
$('shareBtn').addEventListener('click', async function() {
  var text = '周易问卦 — ' + $('resultName').textContent + '\n' + $('judgmentBox').textContent;
  if (navigator.share) {
    try { await navigator.share({ title: '周易问卦', text: text, url: location.href }); return; } catch(e){}
  }
  if (navigator.clipboard) {
    try { await navigator.clipboard.writeText(text + '\n' + location.href); showError('已复制到剪贴板'); return; } catch(e){}
  }
  showError('暂不支持分享');
});

/* 起卦按钮 + Enter 提交 */
$('btnDivine').addEventListener('click', startDivine);
$('question').addEventListener('keydown', function(e) {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); startDivine(); }
});

/* 自动 / 手摇 模式切换 */
function setDivineMode(mode) {
  if (mode !== 'auto' && mode !== 'manual') return;
  divineMode = mode;
  var btns = document.querySelectorAll('.df-mode');
  btns.forEach(function (b) {
    var on = (b.getAttribute('data-mode') === mode);
    b.classList.toggle('active', on);
    b.setAttribute('aria-selected', on ? 'true' : 'false');
  });
  // 便于 CSS 通过 [data-mode] 做视觉提示（如手摇模式下铜钱区显 pointer）
  $('app').setAttribute('data-mode', mode);

  if (mode === 'manual') {
    // iOS 13+ 的 DeviceMotionEvent.requestPermission 必须在用户手势里调一次。
    // Android / iOS<13 没有这个方法，跳过即可 —— 直接 armShakeDetector 开始听。
    if (!_motionPermissionRequested
        && typeof DeviceMotionEvent !== 'undefined'
        && typeof DeviceMotionEvent.requestPermission === 'function') {
      _motionPermissionRequested = true;
      DeviceMotionEvent.requestPermission().then(function (res) {
        if (res === 'granted') {
          armShakeDetector();
        } else {
          // 显式拒权 → 文案立刻切 fallback（不用等 2s 的 NO_MOTION_HINT_MS 兜底）
          _motionSupported = false;
        }
      }).catch(function () {
        _motionSupported = false;
      });
    } else {
      armShakeDetector();
    }
  } else {
    // 切回自动：释放监听节电（再切回手摇时会重挂）
    disarmShakeDetector();
  }
}
document.querySelectorAll('.df-mode').forEach(function (b) {
  b.addEventListener('click', function () {
    if (b.disabled) return;
    setDivineMode(b.getAttribute('data-mode'));
  });
});

/* ==============================================================
   64 卦速查
   ============================================================== */
function toggleLookup(forceOpen) {
  var btn = $('lookupToggle');
  var grid = $('lookupGrid');
  var isOpen = grid.classList.contains('open');
  if (forceOpen && isOpen) {
    grid.scrollIntoView({ behavior: 'smooth' });
    return;
  }
  if (forceOpen || !isOpen) {
    grid.classList.add('open'); btn.classList.add('open');
    if (!hexagramsCache) loadHexagrams();
    setTimeout(function() { grid.scrollIntoView({ behavior: 'smooth', block: 'start' }); }, 100);
  } else {
    grid.classList.remove('open'); btn.classList.remove('open');
  }
}

async function loadHexagrams() {
  var grid = $('lookupGrid');
  clearChildren(grid);
  grid.appendChild(el('div', { style: 'grid-column:1/-1; text-align:center; color:var(--text-dim); padding:18px; font-size:13px;' }, '加载中...'));
  try {
    var resp = await fetch(API_BASE + '/api/hexagrams');
    if (!resp.ok) throw new Error('请求失败 (' + resp.status + ')');
    hexagramsCache = await resp.json();
    renderHexagramGrid(hexagramsCache);
  } catch (e) {
    clearChildren(grid);
    grid.appendChild(el('div', { style: 'grid-column:1/-1; text-align:center; color:#e87a7a; padding:18px; font-size:13px;' }, '加载失败：' + e.message));
  }
}

function renderHexagramGrid(list) {
  var grid = $('lookupGrid');
  clearChildren(grid);
  list.forEach(function(h) {
    var card = el('div', { className: 'hex-card' });
    card.addEventListener('click', function() { showHexDetail(h.number); });
    card.appendChild(el('span', { className: 'card-sym' }, h.symbol || ''));
    card.appendChild(el('span', { className: 'card-name' }, h.name));
    card.appendChild(el('span', { className: 'card-num' }, '第 ' + h.number + ' 卦'));
    grid.appendChild(card);
  });
}

async function showHexDetail(number) {
  var modal = $('modal');
  var body = $('modalBody');
  clearChildren(body);
  body.appendChild(el('div', { style: 'text-align:center; color:var(--text-dim); padding:20px; font-size:13px;' }, '加载中...'));
  modal.classList.add('active');

  try {
    var resp = await fetch(API_BASE + '/api/hexagrams/' + number);
    if (!resp.ok) throw new Error('请求失败 (' + resp.status + ')');
    var h = await resp.json();
    clearChildren(body);
    body.appendChild(el('div', { className: 'm-sym' }, h.symbol || ''));
    body.appendChild(el('div', { className: 'm-title' }, h.name + '卦'));
    body.appendChild(el('div', { className: 'm-meta' }, '第 ' + h.number + ' 卦 · ' + (h.upper_trigram || '') + ' 上 / ' + (h.lower_trigram || '') + ' 下'));
    if (h.judgment) {
      body.appendChild(el('h4', null, '卦辞'));
      body.appendChild(el('p', null, h.judgment));
    }
    if (h.image) {
      body.appendChild(el('h4', null, '象辞'));
      body.appendChild(el('p', null, h.image));
    }
    if (h.lines && h.lines.length) {
      body.appendChild(el('h4', null, '爻辞'));
      var ul = el('ul');
      h.lines.forEach(function(line) { ul.appendChild(el('li', null, line)); });
      body.appendChild(ul);
    }
  } catch (e) {
    clearChildren(body);
    body.appendChild(el('div', { style: 'text-align:center; color:#e87a7a; padding:20px;' }, '加载失败：' + e.message));
  }
}

function closeModal() { $('modal').classList.remove('active'); }

/* 外链二次确认 — 点击 AI 解读里的链接时弹出
   防御层顺序：DOMPurify 已把 href 限制为 http(s)；这里只做"用户知情同意"层 */
var _pendingExternalUrl = null;
function closeLinkConfirm() {
  _pendingExternalUrl = null;
  $('linkConfirm').classList.remove('active');
}

/* ==============================================================
   统一事件委托 — CSP 禁 unsafe-inline 后，所有 on* 属性被移除
   在 DOM 上挂 data-action / data-close-outside，这里集中路由
   ============================================================== */
document.addEventListener('click', function(e) {
  var el = e.target;
  if (!el || !el.closest) return;

  // data-action: 显式动作路由（button / div 均可）
  var actionEl = el.closest('[data-action]');
  if (actionEl) {
    switch (actionEl.getAttribute('data-action')) {
      case 'close-modal':    closeModal();        return;
      case 'close-history':  closeHistory();      return;
      case 'lookup-open':    toggleLookup(true);  return;
    }
  }

  // data-close-outside: overlay 背景点击关闭（只响应 target === 自身）
  var overlay = el.closest('[data-close-outside]');
  if (overlay && e.target === overlay) {
    if (overlay.id === 'linkConfirm') closeLinkConfirm();
    else overlay.classList.remove('active');
    return;
  }
});

// lookupToggle 之前是 inline onclick，现用 addEventListener
$('lookupToggle').addEventListener('click', function() { toggleLookup(); });
document.addEventListener('click', function(e) {
  var anchor = e.target && e.target.closest && e.target.closest('a[href]');
  if (!anchor) return;
  // 只拦截 AI 解读区域内的外链
  if (!anchor.closest('#paneInterp')) return;
  var href = anchor.getAttribute('href');
  if (!/^https?:\/\//i.test(href)) return;    // 再防一次（DOMPurify 已兜住）
  e.preventDefault();
  _pendingExternalUrl = href;
  $('lcUrl').textContent = href;              // textContent：URL 永不被当 HTML
  $('linkConfirm').classList.add('active');
});
$('lcCancel').addEventListener('click', closeLinkConfirm);
$('lcGo').addEventListener('click', function() {
  var url = _pendingExternalUrl;
  closeLinkConfirm();
  if (url) window.open(url, '_blank', 'noopener,noreferrer');
});

document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') {
    if ($('linkConfirm').classList.contains('active')) closeLinkConfirm();
    else if ($('modal').classList.contains('active')) closeModal();
    else if ($('historyPanel').classList.contains('open')) closeHistory();
  }
});

/* ==============================================================
   历史卦象（localStorage，上限 30）
   ============================================================== */
var HISTORY_KEY = 'iching_history_v1';
function loadHistoryList() {
  try { return JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]'); }
  catch (e) { return []; }
}
function saveHistory(data, question) {
  var record = {
    ts: Date.now(),
    question: question || '',
    hexagram: {
      number: data.hexagram.number, name: data.hexagram.name, symbol: data.hexagram.symbol,
      lines: data.hexagram.lines,
      upper_trigram: data.hexagram.upper_trigram,
      lower_trigram: data.hexagram.lower_trigram,
    },
    changed_hexagram: data.changed_hexagram || null,
    judgment: data.judgment, lines_text: data.lines_text, changing_lines: data.changing_lines,
    // 先用后端象辞占位；AI 流式完成后 updateHistoryInterp 会覆盖为真实 Markdown
    interpretation: data.interpretation,
  };
  try {
    var list = loadHistoryList();
    list.unshift(record);
    list = list.slice(0, 30);
    localStorage.setItem(HISTORY_KEY, JSON.stringify(list));
  } catch (e) { /* 忽略存储错误 */ }
  return record.ts;   // 供 updateHistoryInterp 定位
}

/** AI 解读流式完成后写回真实 Markdown */
function updateHistoryInterp(ts, finalText) {
  try {
    var list = loadHistoryList();
    for (var i = 0; i < list.length; i++) {
      if (list[i].ts === ts) {
        list[i].interpretation = finalText;
        localStorage.setItem(HISTORY_KEY, JSON.stringify(list));
        return;
      }
    }
  } catch (e) { /* 忽略存储错误 */ }
}

function fmtDate(ts) {
  var d = new Date(ts);
  var mm = String(d.getMonth()+1).padStart(2,'0');
  var dd = String(d.getDate()).padStart(2,'0');
  var hh = String(d.getHours()).padStart(2,'0');
  var mi = String(d.getMinutes()).padStart(2,'0');
  return mm + '/' + dd + ' ' + hh + ':' + mi;
}

function renderHistory() {
  var list = loadHistoryList();
  var box = $('historyList');
  clearChildren(box);
  if (!list.length) {
    box.appendChild(el('div', { className: 'h-empty' }, '尚无卦象记录'));
    return;
  }
  list.forEach(function(it, idx) {
    var row = el('div', { className: 'history-item' });
    row.appendChild(el('div', { className: 'h-sym' }, it.hexagram.symbol || ''));
    var main = el('div', { className: 'h-main' });
    main.appendChild(el('div', { className: 'h-name' }, it.hexagram.name + (it.changed_hexagram ? ' → ' + it.changed_hexagram.name : '')));
    if (it.question) main.appendChild(el('div', { className: 'h-q' }, it.question));
    row.appendChild(main);
    row.appendChild(el('div', { className: 'h-date' }, fmtDate(it.ts)));
    var del = el('button', { className: 'h-del', 'aria-label': '删除' }, '×');
    del.addEventListener('click', function(e) {
      e.stopPropagation();
      var arr = loadHistoryList();
      arr.splice(idx, 1);
      localStorage.setItem(HISTORY_KEY, JSON.stringify(arr));
      renderHistory();
    });
    row.addEventListener('click', function() {
      closeHistory();
      showHistoryItem(it);
    });
    row.appendChild(del);
    box.appendChild(row);
  });
}

function showHistoryItem(it) {
  // 防竞态：起卦动画中途点历史条目，必须先停掉 startDivine 的回调链，
  // 否则老 await sleep 醒来后会覆盖刚渲染好的历史 DOM
  cancelCurrentDivine();
  var data = {
    hexagram: {
      number: it.hexagram.number, name: it.hexagram.name, symbol: it.hexagram.symbol,
      lines: it.hexagram.lines,
      upper_trigram: it.hexagram.upper_trigram || '',
      lower_trigram: it.hexagram.lower_trigram || '',
    },
    changed_hexagram: it.changed_hexagram,
    judgment: it.judgment, lines_text: it.lines_text,
    changing_lines: it.changing_lines, interpretation: it.interpretation,
  };
  $('app').classList.add('has-result');
  // 复用 showResult 渲染，但不触发 WebSocket 重解读
  var hex = data.hexagram;
  $('resultRomaji').textContent = formatHexPinyin(hex);
  $('resultName').textContent = (Core && Core.fullHexName ? Core.fullHexName(hex) : '') || hex.name;
  $('resultSymbol').textContent = hex.symbol || '';
  $('resultEpithet').textContent = it.question ? '「' + it.question + '」' : '无具体问题';
  $('resultNum').textContent = '第 ' + hex.number + ' 卦';

  var hexesBox = $('hexes');
  clearChildren(hexesBox);
  hexesBox.appendChild(buildHexCol('本 卦', hex, hex.lines, data.changing_lines, false));
  if (data.changed_hexagram) {
    var mid = el('div', { className: 'arrow-col' });
    mid.appendChild(el('div', { className: 'bian-char' }, '变'));
    mid.appendChild(buildArrowSvg());
    hexesBox.appendChild(mid);
    hexesBox.appendChild(buildHexCol('变 卦', data.changed_hexagram, Core.computeBianLines(hex.lines), [], true));
  } else {
    var mid2 = el('div', { className: 'arrow-col' });
    mid2.appendChild(el('div', { className: 'bian-char' }, '静'));
    hexesBox.appendChild(mid2);
    var col = el('div', { className: 'col bian' });
    col.appendChild(el('div', { className: 'label' }, '无变爻'));
    col.appendChild(el('div', { style: 'font-family: var(--font-serif); font-size: 13px; color: var(--text-dim); padding: 20px 0;' }, '本卦自现'));
    hexesBox.appendChild(col);
  }

  $('judgmentBox').textContent = data.judgment || '';
  $('paneJudgment').textContent = data.judgment || '';
  var linesUl = $('paneLines');
  clearChildren(linesUl);
  (data.lines_text || []).forEach(function(t, i) {
    var li = el('li', null, t);
    if (data.changing_lines && data.changing_lines.indexOf(i + 1) !== -1) li.classList.add('changing-line');
    linesUl.appendChild(li);
  });
  // 历史重放：也要取消正在流的 AI 解读，避免它往当前 DOM 写
  cancelCurrentInterp();
  var interp = $('paneInterp');
  interp.className = 'interp';
  var savedMd = it.interpretation || data.interpretation || '';
  if (/[*#`_\[\]>-]/.test(savedMd)) {
    // 看起来是 Markdown，过 sanitizer 渲染
    interp.innerHTML = renderMarkdownSafely(savedMd);
  } else {
    interp.textContent = savedMd;
  }
  activateTab('judgment');
  $('resultSection').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function openHistory() {
  renderHistory();
  $('historyPanel').classList.add('open');
  $('historyPanel').setAttribute('aria-hidden', 'false');
  $('historyBackdrop').classList.add('active');
}
function closeHistory() {
  $('historyPanel').classList.remove('open');
  $('historyPanel').setAttribute('aria-hidden', 'true');
  $('historyBackdrop').classList.remove('active');
}
$('btnHistory').addEventListener('click', openHistory);

/* 历史抽屉：右滑关闭（touch/pointer） */
(function() {
  var panel = $('historyPanel');
  var startX = null;
  panel.addEventListener('pointerdown', function(e) {
    if (e.pointerType !== 'touch') return;
    startX = e.clientX;
  });
  panel.addEventListener('pointermove', function(e) {
    if (startX === null) return;
    var dx = e.clientX - startX;
    if (dx > 10) panel.style.transform = 'translateX(' + dx + 'px)';
  });
  panel.addEventListener('pointerup', function(e) {
    if (startX === null) return;
    var dx = e.clientX - startX;
    panel.style.transform = '';
    if (dx > 60) closeHistory();
    startX = null;
  });
  panel.addEventListener('pointercancel', function() {
    panel.style.transform = '';
    startX = null;
  });
})();

/* 诊断面板按需加载（?debug=scroll）—— 安卓滚动 bug 排查用，正常用户零影响。
 * 不走 index.html ASSET_VERSION，直接带 Date.now() 保证每次都拿新版，
 * 方便在真机上验证 A/B 切换效果。 */
if (location.search.indexOf('debug=scroll') !== -1) {
  var _sdScript = document.createElement('script');
  _sdScript.src = 'assets/scroll-debug.js?t=' + Date.now();
  document.body.appendChild(_sdScript);
}

