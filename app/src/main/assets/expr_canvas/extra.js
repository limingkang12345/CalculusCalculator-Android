/* 表达式画布（解几计算器）安卓端：工具栏、对话框与 Python 回帖处理。
   原桌面版的 QLineEdit / QPushButton / QPlainTextEdit / QDialog 在此以等价 HTML 实现，
   QWebChannel 桥接由 index.html 内的 setupBridge() 代理到 AndroidBridge.canvas(json)。 */

var $ = function (id) { return document.getElementById(id); };
var DLG_SVG_NS = 'http://www.w3.org/2000/svg';

MathKeyboard.send = function (payload) {
  if (window.AndroidBridge && window.AndroidBridge.canvas) {
    window.AndroidBridge.canvas(JSON.stringify({ action: 'latexToExpr', latex: payload.latex }));
  } else MathKeyboard.close();
};

var TRANSFORM_METHODS = [
  ['simplify', '化简 simplify'],
  ['expand', '展开 expand'],
  ['factor', '因式分解 factor'],
  ['cancel', '约分 cancel'],
  ['together', '通分 together'],
  ['apart', '部分分式 apart'],
  ['trigsimp', '三角化简 trigsimp'],
  ['expand_trig', '三角展开 expand_trig'],
  ['powsimp', '幂化简 powsimp'],
  ['expand_power_exp', '指数展开 expand_power_exp'],
  ['expand_log', '对数展开 expand_log'],
  ['logcombine', '对数合并 logcombine'],
  ['radsimp', '有理化 radsimp'],
  ['op_replace', '替换为输入表达式'],
  ['op_add', '加上输入表达式'],
  ['op_mul', '乘以输入表达式'],
  ['op_div', '除以输入表达式'],
  ['op_pow', '乘方（指数为输入）'],
  ['op_recip', '取倒数'],
  ['op_square', '平方'],
  ['op_sqrt', '算术平方根'],
  ['op_subs', '换元（输入符号 + 换元式）']
];

/* 对齐桌面版 expr_viewer.ExpressionDialog：BASE_OPERATIONS + DIV_OPERATIONS，
   另保留安卓原有的三个单目运算。group: base / div / unary */
var DLG_OPS = [
  ['replace', '替换', 'base'],
  ['add', '加', 'base'],
  ['sub', '减', 'base'],
  ['mul', '乘', 'base'],
  ['div', '除', 'base'],
  ['pow', '乘方', 'base'],
  ['div_mul', '上下同乘', 'div'],
  ['div_div', '上下同除', 'div'],
  ['op_recip', '取倒数', 'unary'],
  ['op_square', '平方', 'unary'],
  ['op_sqrt', '算术平方根', 'unary']
];
var DLG_OP_GROUPS = [
  ['base', '可用操作'],
  ['div', 'Div 专用（选中分式节点时可用）'],
  ['unary', '单目运算（不依赖拖拽节点）']
];

function esc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function optionsHtml(list, selected) {
  return list.map(function (p) {
    return '<option value="' + esc(p[0]) + '"' +
      (p[0] === selected ? ' selected' : '') + '>' + esc(p[1]) + '</option>';
  }).join('');
}

/* ---------- 拖拽节点对话框（桌面版「重叠的表达式」） ---------- */
var pendingDialog = null;
var dlgMeta = {};
var dlgSelectedId = null;
var dlgSelectedOp = null;
var dlgState = {};

function opGroupHtml(group, title) {
  var buttons = DLG_OPS.filter(function (o) { return o[2] === group; }).map(function (o) {
    return '<button type="button" class="dlg-op" data-op="' + esc(o[0]) + '"' +
      ' data-group="' + esc(o[2]) + '" disabled>' + esc(o[1]) + '</button>';
  }).join('');
  return '<div class="dlg-ops-group"><div class="dlg-ops-title">' + esc(title) +
    '</div><div class="dlg-ops">' + buttons + '</div></div>';
}

function ceTypes(d) { return (d && d.spec && d.spec.types) || []; }
function ceConditions(d, typeName) {
  return ((d && d.spec && d.spec.conditions) || {})[typeName] || [];
}
function ceCurrent() {
  var d = pendingDialog;
  var typeSel = $('dlg-ce-type'), varSel = $('dlg-ce-variant'), methodSel = $('dlg-ce-method');
  if (!d || !typeSel || !varSel || !methodSel) return null;
  var types = ceTypes(d);
  var t = types[Number(typeSel.value)] || types[0];
  if (!t) return null;
  var variants = t.variants || [];
  var v = variants[Number(varSel.value)] || variants[0] || { names: [], hint: '' };
  return { d: d, t: t, v: v, method: Number(methodSel.value) || 0,
           variantIndex: Number(varSel.value) || 0 };
}

function renderCeParams() {
  var c = ceCurrent();
  var box = $('dlg-ce-params');
  if (!c || !box) return;
  var values = dlgState.params || {};
  box.innerHTML = '<div class="dlg-note">' + esc(c.v.hint || '') +
    '；留空表示保留该参数符号。</div>' +
    (c.v.names || []).map(function (n) {
      var id = 'ce-p-' + n;
      return '<label>' + esc(n) + ' =</label>' +
        '<div class="kbd-field-row"><input id="' + esc(id) + '" type="text" data-ce-param="' + esc(n) +
        '" value="' + esc(values[n] || '') + '" placeholder="留空保留 ' + esc(n) + '">' +
        '<button type="button" class="kbd-open" data-kbd="' + esc(id) + '" title="数学键盘">∑</button></div>';
    }).join('');
}

function ceAvailableConditions(c) {
  var list = ceConditions(c.d, c.t.name);
  var std = (c.d.spec && c.d.spec.standardParabolaVariants) || [];
  if (c.t.name === '抛物线' && std.indexOf(c.variantIndex) < 0) {
    list = list.filter(function (e) { return e.name !== '准线' && e.name !== '焦点坐标'; });
  }
  return list;
}

function renderCeCondFields() {
  var c = ceCurrent();
  var sel = $('dlg-ce-cond-name'), box = $('dlg-ce-cond-fields');
  if (!c || !sel || !box) return;
  var entry = null;
  ceAvailableConditions(c).forEach(function (e) { if (e.name === sel.value) entry = e; });
  if (!entry) { box.innerHTML = ''; return; }
  box.innerHTML = '<div class="dlg-note">' + esc(entry.hint || '') + '</div>' +
    (entry.fields || []).map(function (f) {
      var id = 'ce-c-' + f[0];
      return '<label>' + esc(f[1]) + '</label>' +
        '<div class="kbd-field-row"><input id="' + esc(id) + '" type="text" data-ce-cond="' + esc(f[0]) +
        '" placeholder="' + esc(f[2]) + '">' +
        '<button type="button" class="kbd-open" data-kbd="' + esc(id) + '" title="数学键盘">∑</button></div>';
    }).join('');
}

function renderCeConditions() {
  var c = ceCurrent();
  var box = $('dlg-ce-conds');
  if (!c || !box) return;
  var entries = ceAvailableConditions(c);
  var list = dlgState.conditions || [];
  box.innerHTML = '<label>条件类型</label><select id="dlg-ce-cond-name">' +
    entries.map(function (e) { return '<option value="' + esc(e.name) + '">' + esc(e.name) + '</option>'; }).join('') +
    '</select><div id="dlg-ce-cond-fields"></div>' +
    '<div class="dlg-row"><button type="button" id="dlg-ce-cond-add" class="btn">添加条件</button></div>' +
    '<div class="dlg-cond-list">' + list.map(function (item, i) {
      var summary = Object.keys(item.values || {}).map(function (k) {
        return k + '=' + item.values[k];
      }).join('，');
      return '<div class="dlg-cond"><span>' + esc(item.name) + '（' + esc(summary) + '）</span>' +
        '<button type="button" class="btn small" data-ce-cond-del="' + i + '">删除</button></div>';
    }).join('') + '</div>';
  renderCeCondFields();
}

function renderCeVariants() {
  var d = pendingDialog;
  var typeSel = $('dlg-ce-type'), varSel = $('dlg-ce-variant');
  if (!d || !typeSel || !varSel) return;
  var types = ceTypes(d);
  var t = types[Number(typeSel.value)] || types[0] || { variants: [] };
  varSel.innerHTML = (t.variants || []).map(function (v, i) {
    return '<option value="' + i + '">' + esc(v.label) + '</option>';
  }).join('');
  varSel.value = '0';
}

function renderCeAll() {
  var c = ceCurrent();
  if (!c) return;
  $('dlg-ce-params').classList.toggle('hidden', c.method !== 0);
  $('dlg-ce-conds').classList.toggle('hidden', c.method !== 1);
  renderCeParams();
  renderCeConditions();
}

function renderGeoFields() {
  var d = pendingDialog;
  var sel = $('dlg-geo-type'), box = $('dlg-geo-fields'), hint = $('dlg-geo-hint');
  if (!d || !sel || !box) return;
  var types = (d.spec && d.spec.types) || [];
  var g = types[Number(sel.value)] || types[0];
  if (!g) return;
  if (hint) hint.textContent = g.hint || '';
  var spec = d.spec || {};
  var lists = {
    point: spec.points || [],
    line: spec.equations || [],
    curve: (spec.equations || []).concat((spec.expressions || []).filter(function (x) {
      return (spec.equations || []).indexOf(x) < 0;
    }))
  };
  box.innerHTML = (g.fields || []).map(function (f) {
    var id = 'geo-f-' + f[2];
    var listId = 'geo-list-' + f[2];
    var items = lists[f[1]] || [];
    return '<label>' + esc(f[0]) + '</label>' +
      '<datalist id="' + esc(listId) + '">' + items.map(function (x) {
        return '<option value="' + esc(x) + '"></option>';
      }).join('') + '</datalist>' +
      '<div class="kbd-field-row"><input id="' + esc(id) + '" type="text" data-geo-field="' + esc(f[2]) +
      '" list="' + esc(listId) + '" placeholder="' + esc(f[1] === 'point' ? '(a, b)' : '方程') + '">' +
      '<button type="button" class="kbd-open" data-kbd="' + esc(id) + '" title="数学键盘">∑</button></div>';
  }).join('');
}

function buildDialogBody(d) {
  if (d.kind === 'transform') {
    return '<div class="dlg-node">选中节点：<b>' + esc(d.nodeText) + '</b><br>' +
      esc(d.nodeType) + ' · 第 ' + esc(d.depth) + ' 层</div>' +
      '<label>变形 / 节点操作</label>' +
      '<select id="dlg-method">' + optionsHtml(TRANSFORM_METHODS, 'simplify') + '</select>' +
      '<label>输入表达式（op_* 操作需要；换元时填新符号如 t）</label>' +
      '<div class="kbd-field-row"><input id="dlg-input" type="text" placeholder="例如 x+1 或 t">' +
      '<button type="button" class="kbd-open" data-kbd="dlg-input" title="数学键盘">∑</button></div>' +
      '<label>换元式（仅「换元」需要，例如 x+1 表示令 t = x+1）</label>' +
      '<div class="kbd-field-row"><input id="dlg-replace" type="text" placeholder="例如 x+1">' +
      '<button type="button" class="kbd-open" data-kbd="dlg-replace" title="数学键盘">∑</button></div>' +
      '<label class="dlg-check"><input id="dlg-ascopy" type="checkbox"> 保存为副本（不覆盖原卡片）</label>' +
      '<div class="dlg-note">SymPy 变形直接作用于选中节点；节点操作会用输入表达式与选中节点构造新子树。</div>';
  }
  if (d.kind === 'solve') {
    return '<div class="dlg-node">方程：<b>' + esc(d.nodeText) + '</b></div>' +
      '<label>求解变量</label>' +
      '<div class="kbd-field-row"><input id="dlg-var" type="text" value="' + esc(d.var || 'x') + '">' +
      '<button type="button" class="kbd-open" data-kbd="dlg-var" title="数学键盘">∑</button></div>' +
      '<label>求解范围</label><select id="dlg-domain">' +
      optionsHtml([['Reals', '实数 Reals'], ['Complexes', '复数 Complexes'], ['Integers', '整数 Integers']], 'Reals') +
      '</select>' +
      '<div class="dlg-note">每个根会生成一张独立卡片。</div>';
  }
  if (d.kind === 'system') {
    return '<div class="dlg-node">' + esc(d.text || '两张方程卡片联立') + '</div>' +
      '<label>联立方式</label><select id="dlg-mode">' +
      optionsHtml([['solve', '直接求解方程组'], ['vieta', '韦达定理（根与系数关系）']], 'solve') +
      '</select>' +
      '<label>未知量（逗号分隔）</label>' +
      '<div class="kbd-field-row"><input id="dlg-vars" type="text" value="' + esc(d.vars || 'x,y') + '">' +
      '<button type="button" class="kbd-open" data-kbd="dlg-vars" title="数学键盘">∑</button></div>' +
      '<label>韦达定理生成项（仅韦达模式生效）</label>' +
      '<div class="dlg-checks">' +
      '<label class="dlg-check"><input type="checkbox" data-sys-out="sum" checked> 两根之和 x₁+x₂</label>' +
      '<label class="dlg-check"><input type="checkbox" data-sys-out="product" checked> 两根之积 x₁·x₂</label>' +
      '<label class="dlg-check"><input type="checkbox" data-sys-out="abs"> |x₁ − x₂|</label>' +
      '<label class="dlg-check"><input type="checkbox" data-sys-out="delta"> 判别式 Δ</label>' +
      '</div>' +
      '<div class="dlg-note">韦达定理：只填一个未知量（如 x）时，会用结式消去 x/y/z 等其它变量，a/b/c 等符号作为参数保留在系数中；也可用「直接求解方程组」。</div>';
  }
  if (d.kind === 'nodeOp') {
    var ops = DLG_OP_GROUPS.map(function (g) { return opGroupHtml(g[0], g[1]); }).join('');
    return '<div class="dlg-formula-box"><div id="dlg-formula">公式渲染中…</div></div>' +
      '<div id="dlg-sel-box"></div>' +
      '<div class="dlg-src">目标卡片：<b>' + esc(d.targetText) + '</b></div>' +
      '<div class="dlg-src">拖拽节点：<b>' + esc(d.nodeType) + '</b><br>' + esc(d.nodeText) + '</div>' +
      '<div id="dlg-selinfo" class="dlg-selinfo">在上方公式中点击选择目标节点</div>' +
      '<div class="dlg-hint">运算顺序：选中节点 运算 拖拽节点' +
        (d.nodeZero ? '（拖拽节点为零，不能作为除数或乘数）' : '') + '</div>' +
      ops +
      '<div class="dlg-note">结果会替换目标卡片中的选中节点，可撤销；未选择节点与操作时「确定」不可用。</div>';
  }
  if (d.kind === 'commonEquation') {
    var types = ceTypes(d);
    return '<label>生成方式</label><select id="dlg-ce-method">' +
      optionsHtml([['0', '直接填写参数'], ['1', '用条件反推参数']], '0') + '</select>' +
      '<label>方程类型</label><select id="dlg-ce-type">' +
      types.map(function (t, i) { return '<option value="' + i + '">' + esc(t.name) + '</option>'; }).join('') +
      '</select>' +
      '<label>方程形式</label><select id="dlg-ce-variant"></select>' +
      '<div id="dlg-ce-params"></div>' +
      '<div id="dlg-ce-conds" class="hidden"></div>' +
      '<div class="dlg-note">直接填写参数时留空即保留参数符号；用条件反推时会联立求解参数并生成方程卡片。</div>';
  }
  if (d.kind === 'geometry') {
    var geoTypes = (d.spec && d.spec.types) || [];
    return '<label>几何量</label><select id="dlg-geo-type">' +
      geoTypes.map(function (g, i) { return '<option value="' + i + '">' + esc(g.label) + '</option>'; }).join('') +
      '</select><div id="dlg-geo-fields"></div>' +
      '<div id="dlg-geo-hint" class="dlg-note"></div>' +
      '<div class="dlg-note">可从下拉选择画布中已有的点 / 方程卡片，也可直接输入；结果会生成新卡片（点用 Point 节点）。</div>';
  }
  if (d.kind === 'expressionPair') {
    return '<div class="dlg-node">A（被覆盖）：<b>' + esc(d.textA || '') + '</b></div>' +
      '<div class="dlg-node">B（拖拽）：<b>' + esc(d.textB || '') + '</b></div>' +
      '<label>组合模板（用 A、B 与常数）</label>' +
      '<div class="kbd-field-row"><input id="dlg-pair" type="text" value="A+B" placeholder="例如 A+B 或 A*B">' +
      '<button type="button" class="kbd-open" data-kbd="dlg-pair" title="数学键盘">∑</button></div>' +
      '<div class="dlg-note">A 表示被覆盖的表达式，B 表示拖拽的表达式；例如 A*B、A=B。</div>';
  }
  return '<div class="dlg-node">' + esc(d.text || '') + '</div>';
}

function installDlgHitAreas(host) {
  var svg = host.querySelector('svg');
  if (!svg) return;
  var viewBox = svg.viewBox && svg.viewBox.baseVal;
  var svgRect = svg.getBoundingClientRect();
  var unitsPerPx = (viewBox && svgRect.width) ? viewBox.width / svgRect.width : 1;
  var pad = 5 * unitsPerPx;
  Array.prototype.forEach.call(host.querySelectorAll('g[id]'), function (group) {
    if (group.id.indexOf('__l') < 0) return;
    var box = null;
    try { box = group.getBBox(); } catch (err) { box = null; }
    if (!box || !isFinite(box.width) || !isFinite(box.height)) return;
    if (box.width <= 0 || box.height <= 0) return;
    var rect = document.createElementNS(DLG_SVG_NS, 'rect');
    rect.setAttribute('class', 'dlg-hit-area');
    rect.setAttribute('x', box.x - pad);
    rect.setAttribute('y', box.y - pad);
    rect.setAttribute('width', box.width + 2 * pad);
    rect.setAttribute('height', box.height + 2 * pad);
    rect.setAttribute('fill', 'transparent');
    rect.setAttribute('pointer-events', 'all');
    group.insertBefore(rect, group.firstChild);
  });
}

function renderDlgFormula(latex) {
  var host = $('dlg-formula');
  if (!host) return;
  host.classList.remove('error');
  host.textContent = '$$' + (latex || '') + '$$';
  if (typeof MathJax === 'undefined' || !MathJax.startup) return;
  MathJax.startup.promise.then(function () {
    return MathJax.typesetPromise([host]);
  }).then(function () {
    installDlgHitAreas(host);
  }).catch(function (err) {
    host.classList.add('error');
    host.textContent = String(err);
  });
}

function updateDlgOk() {
  $('dlg-ok').disabled = !(dlgSelectedId && dlgSelectedOp);
}

function selectDlgNode(group) {
  var id = group.id;
  var meta = dlgMeta[id] || {};
  dlgSelectedId = id;
  var box = $('dlg-sel-box');
  if (box) {
    var raw = group.getBoundingClientRect();
    box.style.display = 'block';
    box.style.left = (raw.left - 4) + 'px';
    box.style.top = (raw.top - 4) + 'px';
    box.style.width = (raw.width + 8) + 'px';
    box.style.height = (raw.height + 8) + 'px';
    try { box.style.borderColor = getComputedStyle(group).color || '#0969da'; } catch (err) {}
  }
  var text = meta.text || '';
  if (text.length > 60) text = text.slice(0, 57) + '...';
  $('dlg-selinfo').innerHTML = '已选中：<b>' + esc(meta.type || '节点') + '</b> · 第 ' +
    (meta.depth === undefined ? '?' : meta.depth) + ' 层<br>' + esc(text);
  var isDiv = meta.type === 'Div';
  Array.prototype.forEach.call($('dlg-body').querySelectorAll('.dlg-op'), function (b) {
    var disabled = b.getAttribute('data-group') === 'div' ? !isDiv : false;
    b.disabled = disabled;
    if (disabled && b.getAttribute('data-op') === dlgSelectedOp) {
      b.classList.remove('active');
      dlgSelectedOp = null;
    }
  });
  updateDlgOk();
}

function openDialog(d) {
  pendingDialog = d;
  dlgState = { params: {}, conditions: [] };
  $('dlg-title').textContent = d.title || '对话框';
  $('dlg-body').innerHTML = buildDialogBody(d);
  dlgMeta = {}; dlgSelectedId = null; dlgSelectedOp = null;
  var box = $('dlg-sel-box');
  if (box) box.style.display = 'none';
  if (d.kind === 'nodeOp') {
    dlgMeta = d.info || {};
    $('dlg-ok').disabled = true;
    renderDlgFormula(d.latex);
  } else {
    $('dlg-ok').disabled = false;
    if (d.kind === 'commonEquation') {
      renderCeVariants();
      renderCeAll();
    }
    if (d.kind === 'geometry') renderGeoFields();
  }
  $('dlg-mask').classList.remove('hidden');
}

function closeDialog() {
  $('dlg-mask').classList.add('hidden');
  $('dlg-ok').disabled = false;
  var box = $('dlg-sel-box');
  if (box) box.style.display = 'none';
  dlgSelectedId = null; dlgSelectedOp = null; dlgMeta = {};
  pendingDialog = null;
  dlgState = {};
}

function collectDialog(d) {
  var p = { action: d.action, args: d.args || [] };
  if (d.kind === 'transform') {
    p.method = $('dlg-method').value;
    p.input = $('dlg-input').value.trim();
    p.replace = $('dlg-replace').value.trim();
    p.as_copy = $('dlg-ascopy').checked;
  } else if (d.kind === 'solve') {
    p['var'] = $('dlg-var').value.trim() || 'x';
    p.domain = $('dlg-domain').value;
  } else if (d.kind === 'system') {
    p.mode = $('dlg-mode').value;
    p.vars = $('dlg-vars').value.trim() || 'x,y';
    p.outputs = [];
    Array.prototype.forEach.call($('dlg-body').querySelectorAll('[data-sys-out]'), function (i) {
      if (i.checked) p.outputs.push(i.getAttribute('data-sys-out'));
    });
    if (!p.outputs.length) p.outputs = ['sum', 'product'];
  } else if (d.kind === 'nodeOp') {
    p.op = dlgSelectedOp || 'add';
    p.target_node_id = dlgSelectedId || '';
  } else if (d.kind === 'commonEquation') {
    var c = ceCurrent();
    p.type = c ? c.t.name : '圆';
    p.variant = c ? c.variantIndex : 0;
    p.method = c ? c.method : 0;
    p.params = {};
    Array.prototype.forEach.call($('dlg-body').querySelectorAll('[data-ce-param]'), function (i) {
      p.params[i.getAttribute('data-ce-param')] = i.value.trim();
    });
    p.conditions = dlgState.conditions || [];
  } else if (d.kind === 'geometry') {
    var types = (d.spec && d.spec.types) || [];
    var idx = Number($('dlg-geo-type').value) || 0;
    p.type = (types[idx] || {}).key || 'distance';
    p.fields = {};
    Array.prototype.forEach.call($('dlg-body').querySelectorAll('[data-geo-field]'), function (i) {
      p.fields[i.getAttribute('data-geo-field')] = i.value.trim();
    });
  } else if (d.kind === 'expressionPair') {
    p.template = $('dlg-pair').value.trim();
  }
  return p;
}

$('dlg-body').addEventListener('click', function (e) {
  var target = e.target;
  var group = target && target.closest ? target.closest('g[id*="__l"]') : null;
  if (group && group.closest('#dlg-formula')) { selectDlgNode(group); return; }
  var b = target && target.closest ? target.closest('.dlg-op') : null;
  if (b && !b.disabled) {
    dlgSelectedOp = b.getAttribute('data-op');
    Array.prototype.forEach.call($('dlg-body').querySelectorAll('.dlg-op'), function (x) {
      x.classList.toggle('active', x === b);
    });
    updateDlgOk();
    return;
  }
  if (target && target.id === 'dlg-ce-cond-add') {
    var sel = $('dlg-ce-cond-name');
    if (!sel || !sel.value) return;
    var values = {};
    Array.prototype.forEach.call($('dlg-body').querySelectorAll('[data-ce-cond]'), function (i) {
      values[i.getAttribute('data-ce-cond')] = i.value.trim();
    });
    dlgState.conditions = (dlgState.conditions || []).concat([{ name: sel.value, values: values }]);
    renderCeConditions();
    return;
  }
  var del = target && target.closest ? target.closest('[data-ce-cond-del]') : null;
  if (del) {
    var index = Number(del.getAttribute('data-ce-cond-del'));
    dlgState.conditions = (dlgState.conditions || []).filter(function (_x, i) { return i !== index; });
    renderCeConditions();
  }
});

$('dlg-body').addEventListener('change', function (e) {
  var id = e.target && e.target.id;
  if (id === 'dlg-ce-type') {
    dlgState.conditions = [];
    renderCeVariants();
    renderCeAll();
  } else if (id === 'dlg-ce-variant') {
    dlgState.conditions = [];
    renderCeAll();
  } else if (id === 'dlg-ce-method') {
    renderCeAll();
  } else if (id === 'dlg-ce-cond-name') {
    renderCeCondFields();
  } else if (id === 'dlg-geo-type') {
    renderGeoFields();
  }
});

$('dlg-cancel').addEventListener('click', closeDialog);
$('dlg-mask').addEventListener('click', function (e) {
  if (e.target === $('dlg-mask')) closeDialog();
});
$('dlg-ok').addEventListener('click', function () {
  var d = pendingDialog;
  if (!d) return;
  if (d.kind === 'nodeOp' && (!dlgSelectedId || !dlgSelectedOp)) return;
  var payload = collectDialog(d);
  closeDialog();
  if (window.AndroidBridge && window.AndroidBridge.canvas) {
    window.AndroidBridge.canvas(JSON.stringify(payload));
  }
});

/* ---------- 工具栏 ---------- */
function send(obj) {
  if (window.AndroidBridge && window.AndroidBridge.canvas) {
    window.AndroidBridge.canvas(JSON.stringify(obj));
  }
}

function doAdd() {
  var v = $('expr-input').value.trim();
  if (!v) return;
  send({ action: 'add', args: [], expr: v });
  $('expr-input').value = '';
}

$('add-btn').addEventListener('click', doAdd);
$('expr-input').addEventListener('keydown', function (e) {
  if (e.key === 'Enter') { e.preventDefault(); doAdd(); }
});
$('undo-btn').addEventListener('click', function () { send({ action: 'undo', args: [] }); });
$('redo-btn').addEventListener('click', function () { send({ action: 'redo', args: [] }); });
$('common-btn').addEventListener('click', function () { send({ action: 'commonEquationSpec', args: [] }); });
$('geometry-btn').addEventListener('click', function () { send({ action: 'geometrySpec', args: [] }); });

/* ---------- Python 回帖 ---------- */
window.applyCanvasResult = function (jsonText) {
  var r;
  try { r = JSON.parse(jsonText); } catch (err) { return; }
  (r.actions || []).forEach(function (a) {
    try {
      var fn = window[a.fn];
      if (typeof fn === 'function') fn.apply(null, a.args || []);
    } catch (err) { console.error('canvas action failed', a.fn, err); }
  });
  if (r.status !== undefined) $('status').textContent = r.status;
  if (r.count !== undefined) $('count').textContent = r.count;
  if (r.detail !== undefined) $('detail').textContent = r.detail;
  if (r.selection !== undefined) $('sel-info').innerHTML = r.selection;
  if (r.undo !== undefined) $('undo-btn').disabled = !r.undo;
  if (r.redo !== undefined) $('redo-btn').disabled = !r.redo;
  if (r.error) $('status').textContent = r.error;
  if (r.expr !== undefined) MathKeyboard.applyExpr(r);
  if (r.properties) {
    var p = r.properties;
    canvas.querySelectorAll('.math-item').forEach(function (el) {
      el.classList.toggle('selected', el.dataset.id === p.id);
    });
    $('sel-info').innerHTML = '卡片 ' + esc(p.id) + ' · ' + esc(p.kind) +
      (p.title ? ' · ' + esc(p.title) : '');
    $('detail').textContent = p.text + '\n取值范围：' + p.range + (p.note ? '\n备注：' + p.note : '');
  }
  if (r.dialog) openDialog(r.dialog);
};

/* 页面就绪后清空详情区，等待用户添加表达式 */
$('detail').textContent = '点击画布中的节点，查看其自定义结构与 SymPy 表达式';
