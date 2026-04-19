/**
 * iching-core.js — 周易算卦前端核心纯函数
 *
 * 这些函数无 DOM 副作用、纯输入→输出，便于在 Node 子进程中单元测试。
 * 浏览器环境通过 <script> 载入后挂到 window.IChingCore；Node 环境通过
 * require 直接拿到 module.exports。
 */

(function (root, factory) {
  var api = factory();
  if (typeof module === 'object' && module.exports) {
    module.exports = api;
  } else {
    root.IChingCore = api;
  }
}(typeof self !== 'undefined' ? self : this, function () {

  // 爻值语义：
  // 6 = 老阴（变爻，→ 少阳 7）
  // 7 = 少阳（不变）
  // 8 = 少阴（不变）
  // 9 = 老阳（变爻，→ 少阴 8）
  function computeBianLines(lines) {
    return lines.map(function (v) {
      if (v === 9) return 8;
      if (v === 6) return 7;
      return v;
    });
  }

  // 爻值 → 3 枚铜钱正反面（true = 字/正面, false = 花/反面）
  // 字=3, 花=2；三枚之和 = 爻值
  //   6 → 0 字 3 花 → [F,F,F]
  //   7 → 1 字 2 花
  //   8 → 2 字 1 花
  //   9 → 3 字 0 花 → [T,T,T]
  // 返回的是"正反数量对"，调用方可自行洗牌。
  function coinsForLine(lineVal) {
    var heads = lineVal - 6;
    var faces = [false, false, false];
    for (var i = 0; i < heads; i++) faces[i] = true;
    return faces;
  }

  // 给定种子返回三枚铜钱的扰动布局 (x, y, rotate)
  // 基点在 260×170 的舞台内保留少量交叠感；扰动幅度约 ±18px / ±13°
  function seededLayout(seed) {
    var s = seed * 9301 + 49297;
    function rnd() {
      s = (s * 16807 + 12345) % 2147483647;
      return (s % 1000) / 1000;
    }
    var base = [
      { x: 20,  y: 45 },
      { x: 90,  y: 25 },
      { x: 160, y: 50 },
    ];
    return base.map(function (p) {
      return {
        x:   p.x + (rnd() - 0.5) * 18,
        y:   p.y + (rnd() - 0.5) * 18,
        rot: (rnd() - 0.5) * 26,
      };
    });
  }

  // 简化的卦名拼音表（尾 1-2 字查表，未命中返回空串）
  var PINYIN_MAP = {
    '乾': 'qián', '坤': 'kūn', '屯': 'zhūn', '蒙': 'méng', '需': 'xū',
    '讼': 'sòng', '师': 'shī', '比': 'bǐ', '小畜': 'xiǎo xù', '履': 'lǚ',
    '泰': 'tài', '否': 'pǐ', '同人': 'tóng rén', '大有': 'dà yǒu',
    '谦': 'qiān', '豫': 'yù', '随': 'suí', '蛊': 'gǔ', '临': 'lín',
    '观': 'guān', '噬嗑': 'shì hé', '贲': 'bì', '剥': 'bō', '复': 'fù',
    '无妄': 'wú wàng', '大畜': 'dà xù', '颐': 'yí', '大过': 'dà guò',
    '坎': 'kǎn', '离': 'lí', '咸': 'xián', '恒': 'héng', '遁': 'dùn',
    '大壮': 'dà zhuàng', '晋': 'jìn', '明夷': 'míng yí', '家人': 'jiā rén',
    '睽': 'kuí', '蹇': 'jiǎn', '解': 'xiè', '损': 'sǔn', '益': 'yì',
    '夬': 'guài', '姤': 'gòu', '萃': 'cuì', '升': 'shēng', '困': 'kùn',
    '井': 'jǐng', '革': 'gé', '鼎': 'dǐng', '震': 'zhèn', '艮': 'gèn',
    '渐': 'jiàn', '归妹': 'guī mèi', '丰': 'fēng', '旅': 'lǚ', '巽': 'xùn',
    '兑': 'duì', '涣': 'huàn', '节': 'jié', '中孚': 'zhōng fú',
    '小过': 'xiǎo guò', '既济': 'jì jì', '未济': 'wèi jì',
  };
  function pinyinOf(name) {
    if (!name) return '';
    var last2 = name.length >= 2 ? name.slice(-2) : '';
    var last1 = name.slice(-1);
    if (last2 && PINYIN_MAP[last2]) return PINYIN_MAP[last2];
    if (PINYIN_MAP[last1]) return PINYIN_MAP[last1];
    return '';
  }

  // 三爻 → 自然象：用于把 hex.upper_trigram/lower_trigram 的"卦名字符"
  // (艮/乾/坎/离…) 映射成日常自然象 (山/天/水/火…)，组成传统四字卦名。
  var TRIGRAM_NATURAL = {
    '乾': '天', '坤': '地', '震': '雷', '巽': '风',
    '坎': '水', '离': '火', '艮': '山', '兑': '泽',
  };
  // 自然象字 + 纯卦 "为" 字的拼音 —— PINYIN_MAP 里没有这些单字条目。
  var EXTRA_PINYIN = {
    '天': 'tiān', '地': 'dì',   '雷': 'léi', '风': 'fēng',
    '水': 'shuǐ', '火': 'huǒ',  '山': 'shān', '泽': 'zé',
    '为': 'wéi',
  };

  // 完整卦名：
  //   - 八纯卦（上下同象）→ "乾为天"/"坤为地"/… 传统写法
  //   - 其它 56 卦 → 自然象(上) + 自然象(下) + 本卦名，如 艮上+乾下+大畜 → 山天大畜
  //   - 数据缺失时降级为 hex.name，保证不崩。
  function fullHexName(hex) {
    if (!hex) return '';
    var u = TRIGRAM_NATURAL[hex.upper_trigram];
    var l = TRIGRAM_NATURAL[hex.lower_trigram];
    if (!u || !l) return hex.name || '';
    if (hex.upper_trigram === hex.lower_trigram) {
      return hex.upper_trigram + '为' + u;
    }
    return u + l + (hex.name || '');
  }

  // 对应 fullHexName 的完整拼音（带声调，空格分隔音节），
  // 供上层剥声调/大写/加中点装饰成 "SHAN · TIAN · DA · XU"。
  function fullHexPinyin(hex) {
    if (!hex) return '';
    var u = TRIGRAM_NATURAL[hex.upper_trigram];
    var l = TRIGRAM_NATURAL[hex.lower_trigram];
    if (!u || !l) return pinyinOf(hex.name || '');
    var parts;
    if (hex.upper_trigram === hex.lower_trigram) {
      parts = [PINYIN_MAP[hex.upper_trigram] || '', EXTRA_PINYIN['为'], EXTRA_PINYIN[u]];
    } else {
      parts = [EXTRA_PINYIN[u], EXTRA_PINYIN[l], pinyinOf(hex.name || '')];
    }
    return parts.filter(Boolean).join(' ');
  }

  // 爻视觉类名
  function linesVisualClass(val, changing) {
    var yang = (val === 7 || val === 9);
    var cls = 'h-line';
    if (!yang)    cls += ' yin';
    if (changing) cls += ' changing';
    return cls;
  }

  // 3 枚铜钱结果 → "字 · 花 · 花" 展示文案
  // 输入 faces: true=字(正面) / false=花(反面)；非数组或空数组返回 ''
  function formatCoinResult(faces) {
    if (!Array.isArray(faces) || faces.length === 0) return '';
    return faces.map(function (f) { return f ? '字' : '花'; }).join(' · ');
  }

  // AI 解读 WebSocket 状态机分类 —— streamInterp 在 close/error 时据此决定
  // UI 文案、是否写历史、是否显示重试按钮。
  //
  // 输入语义：
  //   doneReceived — 服务端是否发过 {type:"done"}（流结束信号）
  //   hadError     — 服务端是否发过 {type:"error"}（此时 UI 已显示错误文案，不能被覆盖）
  //   hasContent   — 是否收到过任何实质 {type:"content"} 文本（空 text 不计入）
  //
  // 输出取值：
  //   'success'     — done && hasContent，写历史、清 typing、无重试
  //   'error'       — 收到 error，保留错误文案、不写历史、提供重试
  //   'no-content'  — 无实质 content（含 done-without-content：LLM 整段只走 reasoning
  //                   或空响应、未开始就断），显示 fallback、提供重试
  //   'interrupted' — 有 content 但未 done（中途断网/服务崩），保留已显示内容 + 中断提示 + 重试
  //
  // 为什么 'success' 必须同时看 doneReceived 和 hasContent：某些 OpenAI 兼容 LLM
  // 开启 reasoning_split 后整段 delta 只填 reasoning 字段不填 content，后端
  // `if delta.content:` 过滤后前端 content event 一次都收不到——仅凭 done 判成功
  // 会停在"沉思中..."永不揭示，是 2026-04-19 Codex 第八轮发现的 high。
  function classifyStreamEnd(state) {
    state = state || {};
    if (state.doneReceived && state.hasContent) return 'success';
    if (state.hadError)                          return 'error';
    if (!state.hasContent)                       return 'no-content';
    return 'interrupted';
  }

  return {
    computeBianLines:  computeBianLines,
    coinsForLine:      coinsForLine,
    seededLayout:      seededLayout,
    pinyinOf:          pinyinOf,
    fullHexName:       fullHexName,
    fullHexPinyin:     fullHexPinyin,
    linesVisualClass:  linesVisualClass,
    formatCoinResult:  formatCoinResult,
    classifyStreamEnd: classifyStreamEnd,
  };
}));
