/**
 * scroll-debug.js — 安卓滚动诊断 HUD
 *
 * 仅在 URL 带 ?debug=scroll 时由 index.html 动态注入。
 * 展示实时视口 / 滚动 / 容器高度指标，支持一键 A/B 切换可疑 CSS，
 * 并记录最近 20 条 scroll 事件供根因定位。
 *
 * 正常用户不加载、不执行，对生产无影响。
 */
(function () {
  if (location.search.indexOf('debug=scroll') === -1) return;

  var app = document.getElementById('app');
  var LOG_MAX = 20;
  var scrollLog = [];
  var lastY = 0;

  function mk(tag, attrs, children) {
    var n = document.createElement(tag);
    if (attrs) for (var k in attrs) {
      if (k === 'style') n.style.cssText = attrs[k];
      else if (k === 'data') for (var d in attrs.data) n.setAttribute('data-' + d, attrs.data[d]);
      else if (k === 'text') n.textContent = attrs[k];
      else n.setAttribute(k, attrs[k]);
    }
    if (children) children.forEach(function (c) { n.appendChild(c); });
    return n;
  }

  // 1vh / 1svh / 1dvh 实际解析值（浏览器对这些单位的私下算账）
  function measureVhUnits() {
    var probe = document.createElement('div');
    probe.style.cssText = 'position:fixed;left:-9999px;top:0;height:100vh;width:1px;';
    document.body.appendChild(probe);
    var vh = probe.getBoundingClientRect().height;
    probe.style.height = '100svh';
    var svh = probe.getBoundingClientRect().height;
    probe.style.height = '100dvh';
    var dvh = probe.getBoundingClientRect().height;
    probe.remove();
    return { vh: vh, svh: svh, dvh: dvh };
  }

  function fmt(n) { return (Math.round(n * 10) / 10).toFixed(1); }

  function snapshot() {
    var docEl = document.documentElement;
    var body = document.body;
    var vv = window.visualViewport;
    var vh = measureVhUnits();
    var maxY = Math.max(0, docEl.scrollHeight - window.innerHeight);
    var bodyStyle = getComputedStyle(body);
    return {
      innerWH: window.innerWidth + '×' + window.innerHeight,
      visualVP: vv ? (fmt(vv.width) + '×' + fmt(vv.height) + '@top' + fmt(vv.offsetTop)) : 'n/a',
      'vh/svh/dvh': fmt(vh.vh) + ' / ' + fmt(vh.svh) + ' / ' + fmt(vh.dvh),
      scrollY: window.scrollY + ' / ' + maxY + ' (gap=' + (maxY - window.scrollY) + ')',
      body_sH: body.scrollHeight,
      html_sH: docEl.scrollHeight,
      app_sH_cH: app ? (app.scrollHeight + ' / ' + app.clientHeight) : 'n/a',
      overflow_y: getComputedStyle(docEl).overflowY + ' | ' + bodyStyle.overflowY,
      osb_y: bodyStyle.overscrollBehaviorY,
      appClass: app ? app.className : 'n/a',
    };
  }

  // ---- HUD 骨架 ----
  var btnStyle = 'padding:3px 6px;font:10px ui-monospace,monospace;' +
    'background:#1a1208;color:#c9a961;border:1px solid rgba(201,169,97,0.4);' +
    'border-radius:3px;cursor:pointer;';

  var btnCopy = mk('button', { style: btnStyle + 'flex:1;', data: { sd: 'copy' }, text: 'copy' });
  var btnToggle = mk('button', { style: btnStyle + 'flex:1;', data: { sd: 'toggle' }, text: 'hide' });
  var topRow = mk('div', { style: 'display:flex;gap:6px;margin-bottom:6px;' }, [btnCopy, btnToggle]);

  var metricsEl = mk('pre', {
    style: 'margin:0 0 6px;white-space:pre-wrap;color:#ead29a;',
    data: { sd: 'metrics' }
  });

  var btnOsb  = mk('button', { style: btnStyle, data: { sd: 'osb' },  text: 'osb:none→auto' });
  var btnDvh  = mk('button', { style: btnStyle, data: { sd: 'dvh' },  text: '+dvh on .app' });
  var btnOvfx = mk('button', { style: btnStyle, data: { sd: 'ovfx' }, text: 'overflow-x:hidden→visible' });
  var toggleRow = mk('div',
    { style: 'display:flex;flex-wrap:wrap;gap:4px;margin-bottom:6px;' },
    [btnOsb, btnDvh, btnOvfx]);

  var logEl = mk('div', {
    style: 'max-height:120px;overflow:auto;font:10px ui-monospace,monospace;' +
      'color:#9a8f6a;border-top:1px dashed rgba(201,169,97,0.3);padding-top:4px;' +
      'white-space:pre;',
    data: { sd: 'log' }
  });

  var hud = mk('div', {
    id: 'scroll-debug-hud',
    style:
      'position:fixed;right:8px;bottom:8px;z-index:999999;' +
      'max-width:280px;padding:8px 10px;border-radius:6px;' +
      'background:rgba(0,0,0,0.82);color:#c9a961;' +
      'font:11px/1.4 ui-monospace,Menlo,Consolas,monospace;' +
      'border:1px solid rgba(201,169,97,0.35);box-shadow:0 4px 20px rgba(0,0,0,0.5);' +
      'pointer-events:auto;'
  }, [topRow, metricsEl, toggleRow, logEl]);
  document.body.appendChild(hud);

  function renderMetrics() {
    var s = snapshot();
    var lines = [];
    for (var k in s) {
      var label = k;
      while (label.length < 11) label += ' ';
      lines.push(label + ': ' + s[k]);
    }
    metricsEl.textContent = lines.join('\n');
  }

  function pushLog(ev) {
    var maxY = Math.max(0, document.documentElement.scrollHeight - window.innerHeight);
    var y = window.scrollY;
    scrollLog.push({
      t: (performance.now() / 1000).toFixed(2),
      ev: ev,
      y: y,
      d: y - lastY,
      gap: maxY - y,
    });
    lastY = y;
    if (scrollLog.length > LOG_MAX) scrollLog.shift();
    logEl.textContent = scrollLog.map(function (r) {
      return r.t + 's ' + r.ev + ' y=' + r.y + ' Δ=' + r.d + ' gap=' + r.gap;
    }).join('\n');
    logEl.scrollTop = logEl.scrollHeight;
  }

  var raf = 0;
  function requestRefresh() {
    if (raf) return;
    raf = requestAnimationFrame(function () { raf = 0; renderMetrics(); });
  }

  window.addEventListener('scroll', function () { pushLog('scroll'); requestRefresh(); }, { passive: true });
  window.addEventListener('resize', function () { pushLog('resize'); requestRefresh(); });
  if (window.visualViewport) {
    window.visualViewport.addEventListener('resize', function () { pushLog('vv-resize'); requestRefresh(); });
    window.visualViewport.addEventListener('scroll', function () { pushLog('vv-scroll'); requestRefresh(); });
  }
  setInterval(requestRefresh, 500);

  // ---- A/B 切换 ----
  var state = { osb: false, dvh: false, ovfx: false, hidden: false };

  function applyToggles() {
    document.body.style.overscrollBehavior = state.osb ? 'auto' : '';
    if (app) app.style.minHeight = state.dvh ? '100dvh' : '';
    document.documentElement.style.overflowX = state.ovfx ? 'visible' : '';
    document.body.style.overflowX = state.ovfx ? 'visible' : '';
    btnOsb.textContent  = state.osb  ? 'osb:[auto]'       : 'osb:none→auto';
    btnDvh.textContent  = state.dvh  ? '[+dvh on]'        : '+dvh on .app';
    btnOvfx.textContent = state.ovfx ? 'overflow-x:[visible]' : 'overflow-x:hidden→visible';
    requestRefresh();
  }

  hud.addEventListener('click', function (e) {
    var t = e.target.getAttribute && e.target.getAttribute('data-sd');
    if (!t) return;
    if (t === 'copy') {
      var payload = { snapshot: snapshot(), toggles: state, log: scrollLog };
      var txt = JSON.stringify(payload, null, 2);
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(txt).then(
          function () { e.target.textContent = 'copied!'; setTimeout(function () { e.target.textContent = 'copy'; }, 1200); },
          function () { prompt('复制失败，手动复制：', txt); }
        );
      } else {
        prompt('手动复制：', txt);
      }
    } else if (t === 'toggle') {
      state.hidden = !state.hidden;
      for (var i = 1; i < hud.children.length; i++) {
        hud.children[i].style.display = state.hidden ? 'none' : '';
      }
      e.target.textContent = state.hidden ? 'show' : 'hide';
    } else if (state.hasOwnProperty(t)) {
      state[t] = !state[t];
      applyToggles();
      pushLog('toggle:' + t + '=' + state[t]);
    }
  });

  renderMetrics();
  pushLog('init');
})();
