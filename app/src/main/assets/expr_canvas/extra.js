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
  ['op_sqrt', '算术平方根']
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

function opGroupHtml(group, title) {
  var buttons = DLG_OPS.filter(function (o) { return o[2] === group; }).map(function (o) {
    return '<button type="button" class="dlg-op" data-op="' + esc(o[0]) + '"' +
      ' data-group="' + esc(o[2]) + '" disabled>' + esc(o[1]) + '</button>';
  }).join('');
  return '<div class="dlg-ops-group"><div class="dlg-ops-title">' + esc(title) +
    '</div><div class="dlg-ops">' + buttons + '</div></div>';
}

function buildDialogBody(d) {
  if (d.kind === 'transform') {
    return '<div class="dlg-node">选中节点：<b>' + esc(d.nodeText) + '</b><br>' +
      esc(d.nodeType) + ' · 第 ' + esc(d.depth) + ' 层</div>' +
      '<label>变形 / 节点操作</label>' +
      '<select id="dlg-method">' + optionsHtml(TRANSFORM_METHODS, 'simplify') + '</select>' +
      '<label>输入表达式（op_* 操作需要，如 x+1 或 2）</label>' +
      '<div class="kbd-field-row"><input id="dlg-input" type="text" placeholder="例如 x+1">' +
      '<button type="button" class="kbd-open" data-kbd="dlg-input" title="数学键盘">∑</button></div>' +
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
      '<div class="dlg-note">韦达定理：只填一个未知量（如 x）时，会用另一张方程消去两式共有的其它变量，得到关于 x 的一元二次方程，再给出两根之和与两根之积；也可用「直接求解方程组」。</div>';
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
}

function collectDialog(d) {
  var p = { action: d.action, args: d.args || [] };
  if (d.kind === 'transform') {
    p.method = $('dlg-method').value;
    p.input = $('dlg-input').value.trim();
  } else if (d.kind === 'solve') {
    p['var'] = $('dlg-var').value.trim() || 'x';
    p.domain = $('dlg-domain').value;
  } else if (d.kind === 'system') {
    p.mode = $('dlg-mode').value;
    p.vars = $('dlg-vars').value.trim() || 'x,y';
  } else if (d.kind === 'nodeOp') {
    p.op = dlgSelectedOp || 'add';
    p.target_node_id = dlgSelectedId || '';
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
  if (r.dialog) openDialog(r.dialog);
};

/* 页面就绪后清空详情区，等待用户添加表达式 */
$('detail').textContent = '点击画布中的节点，查看其自定义结构与 SymPy 表达式';
