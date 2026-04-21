/* 64 卦体检页脚本 —— 外部化以通过 CSP script-src 'self'。
 * 页面：frontend/all-hexagrams.html
 * 用途：dev 时把 64 卦静态铺一张大表，配合顶部 panel 对照 halo/背景/gap 变量。 */

const HEX_DATA = [
  {"n":1,"name":"乾","yaos":[1,1,1,1,1,1]},{"n":2,"name":"坤","yaos":[0,0,0,0,0,0]},
  {"n":3,"name":"屯","yaos":[0,0,1,0,1,0]},{"n":4,"name":"蒙","yaos":[0,1,0,1,0,0]},
  {"n":5,"name":"需","yaos":[1,1,1,0,1,0]},{"n":6,"name":"讼","yaos":[0,1,0,1,1,1]},
  {"n":7,"name":"师","yaos":[0,1,0,0,0,0]},{"n":8,"name":"比","yaos":[0,0,0,0,1,0]},
  {"n":9,"name":"小畜","yaos":[1,1,1,1,1,0]},{"n":10,"name":"履","yaos":[0,1,1,1,1,1]},
  {"n":11,"name":"泰","yaos":[1,1,1,0,0,0]},{"n":12,"name":"否","yaos":[0,0,0,1,1,1]},
  {"n":13,"name":"同人","yaos":[1,0,1,1,1,1]},{"n":14,"name":"大有","yaos":[1,1,1,1,0,1]},
  {"n":15,"name":"谦","yaos":[1,0,0,0,0,0]},{"n":16,"name":"豫","yaos":[0,0,0,0,0,1]},
  {"n":17,"name":"随","yaos":[0,0,1,0,1,1]},{"n":18,"name":"蛊","yaos":[1,1,0,1,0,0]},
  {"n":19,"name":"临","yaos":[0,1,1,0,0,0]},{"n":20,"name":"观","yaos":[0,0,0,1,1,0]},
  {"n":21,"name":"噬嗑","yaos":[0,0,1,1,0,1]},{"n":22,"name":"贲","yaos":[1,0,1,1,0,0]},
  {"n":23,"name":"剥","yaos":[0,0,0,1,0,0]},{"n":24,"name":"复","yaos":[0,0,1,0,0,0]},
  {"n":25,"name":"无妄","yaos":[0,0,1,1,1,1]},{"n":26,"name":"大畜","yaos":[1,1,1,1,0,0]},
  {"n":27,"name":"颐","yaos":[0,0,1,1,0,0]},{"n":28,"name":"大过","yaos":[1,1,0,0,1,1]},
  {"n":29,"name":"坎","yaos":[0,1,0,0,1,0]},{"n":30,"name":"离","yaos":[1,0,1,1,0,1]},
  {"n":31,"name":"咸","yaos":[1,0,0,0,1,1]},{"n":32,"name":"恒","yaos":[1,1,0,0,0,1]},
  {"n":33,"name":"遁","yaos":[1,0,0,1,1,1]},{"n":34,"name":"大壮","yaos":[1,1,1,0,0,1]},
  {"n":35,"name":"晋","yaos":[0,0,0,1,0,1]},{"n":36,"name":"明夷","yaos":[1,0,1,0,0,0]},
  {"n":37,"name":"家人","yaos":[1,0,1,1,1,0]},{"n":38,"name":"睽","yaos":[0,1,1,1,0,1]},
  {"n":39,"name":"蹇","yaos":[1,0,0,0,1,0]},{"n":40,"name":"解","yaos":[0,1,0,0,0,1]},
  {"n":41,"name":"损","yaos":[0,1,1,1,0,0]},{"n":42,"name":"益","yaos":[0,0,1,1,1,0]},
  {"n":43,"name":"夬","yaos":[1,1,1,0,1,1]},{"n":44,"name":"姤","yaos":[1,1,0,1,1,1]},
  {"n":45,"name":"萃","yaos":[0,0,0,0,1,1]},{"n":46,"name":"升","yaos":[1,1,0,0,0,0]},
  {"n":47,"name":"困","yaos":[0,1,0,0,1,1]},{"n":48,"name":"井","yaos":[1,1,0,0,1,0]},
  {"n":49,"name":"革","yaos":[1,0,1,0,1,1]},{"n":50,"name":"鼎","yaos":[1,1,0,1,0,1]},
  {"n":51,"name":"震","yaos":[0,0,1,0,0,1]},{"n":52,"name":"艮","yaos":[1,0,0,1,0,0]},
  {"n":53,"name":"渐","yaos":[1,0,0,1,1,0]},{"n":54,"name":"归妹","yaos":[0,1,1,0,0,1]},
  {"n":55,"name":"丰","yaos":[1,0,1,0,0,1]},{"n":56,"name":"旅","yaos":[1,0,0,1,0,1]},
  {"n":57,"name":"巽","yaos":[1,1,0,1,1,0]},{"n":58,"name":"兑","yaos":[0,1,1,0,1,1]},
  {"n":59,"name":"涣","yaos":[0,1,0,1,1,0]},{"n":60,"name":"节","yaos":[0,1,1,0,1,0]},
  {"n":61,"name":"中孚","yaos":[0,1,1,1,1,0]},{"n":62,"name":"小过","yaos":[1,0,0,0,0,1]},
  {"n":63,"name":"既济","yaos":[1,0,1,0,1,0]},{"n":64,"name":"未济","yaos":[0,1,0,1,0,1]}
];

function maxYinRun(yaos) {
  let cur = 0, best = 0;
  for (const y of yaos) {
    if (y === 0) { cur++; if (cur > best) best = cur; }
    else cur = 0;
  }
  return best;
}

function renderGrid() {
  const grid = document.getElementById('grid');
  if (!grid) return;
  HEX_DATA.forEach(h => {
    const card = document.createElement('div');
    card.className = 'hex-card';
    if (maxYinRun(h.yaos) >= 4) card.classList.add('dense-yin');

    const lines = document.createElement('div');
    lines.className = 'lines';
    h.yaos.forEach(y => {
      const line = document.createElement('div');
      line.className = 'h-line ' + (y === 1 ? 'yang' : 'yin');
      // 对 yin 额外塞两个 .yin-half —— body.yin-sibling 开关激活时它们会显示，
      // ::before/::after 相应被 content: none 隐藏。默认情况下 .yin-half 是 display: none，
      // 渲染仍走 pseudo-element 路径。
      if (y !== 1) {
        const hL = document.createElement('div');
        hL.className = 'yin-half left';
        const hR = document.createElement('div');
        hR.className = 'yin-half right';
        line.appendChild(hL);
        line.appendChild(hR);
      }
      lines.appendChild(line);
    });
    card.appendChild(lines);

    const name = document.createElement('div');
    name.className = 'name';
    name.textContent = h.name;
    card.appendChild(name);

    const num = document.createElement('div');
    num.className = 'num';
    num.textContent = h.n;
    card.appendChild(num);

    grid.appendChild(card);
  });
}

function bindPanel() {
  document.querySelectorAll('.panel button').forEach(btn => {
    btn.addEventListener('click', () => {
      const group = btn.dataset.group;
      const value = btn.dataset.value;
      // sibling 组是 on/off 单词开关，单独处理；其他组走 prefix+value pattern
      if (group === 'sibling') {
        document.body.classList.toggle('yin-sibling', value === 'on');
      } else {
        const prefix = (group === 'bg') ? 'bg-' :
                       (group === 'cosmos') ? 'cosmos-' :
                       (group === 'coin') ? 'coin-' :
                       (group === 'gap') ? 'gap-' :
                       (group === 'flag') ? 'flag-' : '';
        [...document.body.classList].forEach(cls => {
          if (cls.startsWith(prefix)) document.body.classList.remove(cls);
        });
        if (value !== 'off' && value !== 'black' && value !== 'fill') {
          document.body.classList.add(prefix + value);
        }
      }
      document.querySelectorAll(`.panel button[data-group="${group}"]`).forEach(b => {
        b.classList.toggle('active', b === btn);
      });
    });
  });
}

document.addEventListener('DOMContentLoaded', () => {
  renderGrid();
  bindPanel();
});
