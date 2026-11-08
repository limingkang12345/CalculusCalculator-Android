// CalculusCalculator 前端逻辑：功能集成页（定义区 / 计算区 / 绘图区）。
// 与 Java 的桥接：AndroidBridge.compute(json)，Java 回帖 window.Calc.onResult(json)。

const $ = id => document.getElementById(id);

// 共享可视化数学键盘的后端通道：LaTeX -> SymPy 表达式回填输入框。
MathKeyboard.send = function (payload) {
  if (typeof AndroidBridge !== 'undefined' && AndroidBridge.compute)
    AndroidBridge.compute(JSON.stringify({ op: 'latexToExpr', latex: payload.latex }));
  else MathKeyboard.close();
};

function sendFp(payload) {
  const req = Object.assign({ op: 'fp' }, payload);
  if (typeof AndroidBridge !== 'undefined' && AndroidBridge.compute)
    AndroidBridge.compute(JSON.stringify(req));
}

function readRows(box) {
  return Array.from(box.querySelectorAll('input, select')).map(e => e.value);
}

function expandParams(params, values, offset) {
  let count = 3;
  for (let i = 0; i < params.length; i++) {
    const row = offset + i;
    if (params[i][2] === 'quantity' && values && values.length > row)
      count = Math.max(3, parseInt(values[row], 10) || 3);
  }
  const rows = [];
  for (const f of params) {
    if (f[0].indexOf('{}') >= 0) {
      for (let i = 0; i < count; i++) rows.push([f[0].replace('{}', i + 1), f[1], f[2]]);
    } else rows.push(f);
  }
  return rows;
}

function groupRows(fixed, member, values) {
  const count = Math.max(1, parseInt(values[0], 10) || 2);
  const rows = fixed.map(r => r.slice());
  for (let i = 0; i < count; i++)
    for (const f of member) rows.push([f[0].replace('{}', i + 1), f[1], f[2]]);
  return rows;
}

const Fp = {
  spec: null,
  defType: 0,
  calcFunc: 0,
  selected: null,

  boot() { sendFp({ action: 'spec' }); },

  init() {
    const S = this.spec;
    const fill = (id, items) => {
      const el = $(id); el.innerHTML = '';
      items.forEach((n, i) => {
        const o = document.createElement('option'); o.value = i; o.textContent = n; el.appendChild(o);
      });
    };
    fill('fpDefType', S.def_types);
    fill('fpCalcFunc', S.calc_functions);
    fill('fpDrawMode', S.draw_modes);

    $('fpDefType').addEventListener('change', () => {
      this.defType = parseInt($('fpDefType').value, 10); this.rebuild('def', true);
    });
    $('fpCalcFunc').addEventListener('change', () => {
      this.calcFunc = parseInt($('fpCalcFunc').value, 10); this.rebuild('calc', true);
    });
    $('fpDrawMode').addEventListener('change', () => this.refreshDrawObjs());
    $('fpDefSave').addEventListener('click', () => sendFp({ action: 'def_save', type: this.defType, values: this.values('def') }));
    $('fpDefClear').addEventListener('click', () => this.rebuild('def', true));
    $('fpDefPreview').addEventListener('click', () => sendFp({ action: 'def_preview', type: this.defType, values: this.values('def'), mode: parseInt($('fpDefMode').value, 10), text: this.lastDefText() }));
    $('fpDefEdit').addEventListener('click', () => {
      if (!this.selected) return this.showResult({ ok: false, error: '请先选择要编辑的对象' });
      sendFp({ action: 'def_edit', name: this.selected });
    });
    $('fpDefDel').addEventListener('click', () => {
      if (!this.selected) return this.showResult({ ok: false, error: '请先选择要删除的对象' });
      sendFp({ action: 'def_del', name: this.selected });
    });
    $('fpCalcGo').addEventListener('click', () => sendFp({ action: 'calc', index: this.calcFunc, values: this.values('calc') }));
    $('fpCalcClear').addEventListener('click', () => this.rebuild('calc', true));
    $('fpDrawGo').addEventListener('click', () => sendFp({ action: 'draw', mode: parseInt($('fpDrawMode').value, 10), names: this.drawNames() }));

    this.rebuild('def', true);
    this.rebuild('calc', true);
    this.refreshDrawObjs();
    sendFp({ action: 'def_list' });
  },

  values(kind) { return readRows($(kind === 'def' ? 'fpDefRows' : 'fpCalcRows')); },

  lastDefText() { const v = this.values('def'); return v.length ? v[v.length - 1] : ''; },

  freeName(dim, objType) {
    const S = this.spec, prefix = S.name_prefix[objType];
    if (!prefix) return '';
    const used = (S.objects[dim] && S.objects[dim][objType]) || [];
    let n = 1;
    while (used.indexOf(prefix + n) >= 0) n++;
    return prefix + n;
  },

  defRows(values) {
    const S = this.spec;
    if (this.defType < 3) return S.def_fixed[this.defType].map(r => r.slice());
    const dim = this.defType === 3 ? 'plane' : 'solid';
    const table = S.geometry[dim], types = Object.keys(table);
    const objType = (values[1] && table[values[1]]) ? values[1] : types[0];
    const methods = table[objType], titles = methods.map(m => m.name);
    const mt = (values[2] && titles.indexOf(values[2]) >= 0) ? values[2] : titles[0];
    const params = methods.find(m => m.name === mt).params;
    return [['名称', this.freeName(dim, objType), 'value'],
            ['几何对象类型', types, 'select'],
            ['创建方式', titles, 'select']].concat(expandParams(params, values, 3));
  },

  calcRows(values) {
    const S = this.spec, i = this.calcFunc;
    if (i === 0) {
      const rows = [['计算引擎', S.calc_engines, 'select'], ['表达式', '', 'value']];
      if ((values[0] || S.calc_engines[0]) === S.calc_engines[1]) rows.push(['精度', '16', 'value']);
      return rows;
    }
    if (i === 1) return [['表达式', '', 'value'], ['求导变量', 'x', 'value'], ['求导次数', '1', 'value']];
    if (i === 2) return [['表达式', '', 'value'], ['积分变量', 'x', 'value']];
    if (i === 3) return [['左式', '', 'value'], ['右式', '0', 'value'], ['求解变量', 'x', 'value'], ['求解定义域', 'Reals', 'value']];
    if (i === 4) return [['左式', '', 'value'], ['不等号', ['!=', '>', '>=', '<', '<='], 'select'], ['右式', '0', 'value'], ['求解变量', 'x', 'value'], ['求解定义域', 'Reals', 'value']];
    if (i === 5) return groupRows([['方程数量', 2, 'quantity'], ['求解变量', 'x,y', 'value']],
      [['方程{}左式', '', 'value'], ['方程{}右式', '0', 'value']], values);
    if (i === 6) return groupRows([['不等式数量', 2, 'quantity'], ['求解变量', 'x', 'value']],
      [['不等式{}左式', '', 'value'], ['不等式{}不等号', ['!=', '>', '>=', '<', '<='], 'select'], ['不等式{}右式', '0', 'value']], values);
    if (i === 7 || i === 8) {
      const table = S.ops[i === 7 ? 'plane' : 'solid'], types = Object.keys(table);
      const objType = (values[0] && table[values[0]]) ? values[0] : types[0];
      const ops = table[objType], titles = ops.map(o => o.name);
      const ot = (values[1] && titles.indexOf(values[1]) >= 0) ? values[1] : titles[0];
      const params = ops.find(o => o.name === ot).params;
      return [['几何对象类型', types, 'select'], ['计算方式', titles, 'select']]
        .concat(expandParams(params, values, 2));
    }
    if (i === 9) {
      const rows = [['变形方法', S.transform_names, 'select'], ['表达式', '', 'value']];
      const m = values[0] || S.transform_names[0];
      if (m === S.transform_names[3]) rows.push(['主元符号', 'x', 'value']);
      else if (m === S.transform_names[12]) rows.push(['主元符号', 'x', 'value'], ['换元符号', 't', 'value'], ['换元表达式', 'x+1', 'value']);
      return rows;
    }
    if (i === 10) {
      const rows = [];
      for (let k = 1; k <= 3; k++) rows.push(['条件' + k + '类型', S.triangle_parts, 'select'], ['条件' + k + '值', '', 'value']);
      return rows;
    }
    return [];
  },

  rebuild(kind, reset) {
    const box = $(kind === 'def' ? 'fpDefRows' : 'fpCalcRows');
    const old = reset ? [] : readRows(box);
    const dim = kind === 'def'
      ? (this.defType === 4 ? 'solid' : 'plane')
      : (this.calcFunc === 8 ? 'solid' : 'plane');
    const rows = kind === 'def' ? this.defRows(old) : this.calcRows(old);
    this.renderRows(box, rows, old, dim, () => this.rebuild(kind, false));
  },

  renderRows(box, rows, values, dim, onChange) {
    if (window.MathKeyboard && MathKeyboard.isOpen && MathKeyboard.isOpen()) MathKeyboard.close();
    const S = this.spec;
    box.innerHTML = '';
    let seq = 0;
    const idPrefix = 'kbd-' + box.id + '-';
    rows.forEach((r, i) => {
      const title = r[0], def = r[1], role = r[2];
      const wrap = document.createElement('div'); wrap.className = 'p';
      const lab = document.createElement('label'); lab.textContent = title;
      let inp, isText = false;
      if (role === 'select') {
        inp = document.createElement('select');
        (Array.isArray(def) ? def : []).forEach(o => {
          const p = document.createElement('option'); p.value = o; p.textContent = o; inp.appendChild(p);
        });
        if (values[i] !== undefined && (Array.isArray(def) ? def : []).indexOf(values[i]) >= 0) inp.value = values[i];
      } else if (S.role_category[role]) {
        inp = document.createElement('select');
        const cat = S.role_category[role];
        const names = (S.objects[dim] && S.objects[dim][cat]) || [];
        if (!names.length) {
          const p = document.createElement('option'); p.value = ''; p.textContent = '（请先定义' + cat + '）'; inp.appendChild(p);
        }
        names.forEach(n => { const p = document.createElement('option'); p.value = n; p.textContent = n; inp.appendChild(p); });
        if (values[i] !== undefined) inp.value = values[i];
      } else {
        inp = document.createElement('input');
        isText = true;
        if (role === 'integer' || role === 'quantity') inp.type = 'number';
        inp.placeholder = Array.isArray(def) ? '' : String(def);
        inp.value = values[i] !== undefined ? values[i] : (Array.isArray(def) ? def[0] : def);
      }
      inp.id = idPrefix + (++seq);
      inp.addEventListener('change', onChange);
      wrap.appendChild(lab);
      if (isText) {
        const row = document.createElement('div'); row.className = 'kbd-field-row';
        row.appendChild(inp);
        const kb = document.createElement('button');
        kb.type = 'button'; kb.className = 'kbd-open'; kb.textContent = '∑';
        kb.title = '数学键盘';
        kb.setAttribute('data-kbd', inp.id);
        row.appendChild(kb);
        wrap.appendChild(row);
      } else {
        wrap.appendChild(inp);
      }
      box.appendChild(wrap);
    });
  },

  refreshObjectSelects() { this.rebuild('def', false); this.rebuild('calc', false); },

  renderTree(groups) {
    const box = $('fpDefTree'); box.innerHTML = '';
    const keys = Object.keys(groups || {});
    keys.forEach(label => {
      const h = document.createElement('div'); h.className = 'fp-tree-group'; h.textContent = label; box.appendChild(h);
      (groups[label] || []).forEach(item => {
        const d = document.createElement('div'); d.className = 'fp-tree-item';
        d.textContent = item.name + ' : ' + (item.values || []).slice(1, 4).join(', ');
        d.addEventListener('click', () => {
          box.querySelectorAll('.fp-tree-item').forEach(x => x.classList.remove('sel'));
          d.classList.add('sel'); this.selected = item.name;
        });
        box.appendChild(d);
      });
    });
    if (!keys.length) box.textContent = '（暂无定义）';
  },

  refreshDrawObjs() {
    if (!this.spec) return;
    const mode = parseInt($('fpDrawMode').value, 10) || 0;
    const box = $('fpDrawObjs'); box.innerHTML = '';
    let entries = [];
    if (mode === 2) {
      entries = (this.spec.objects['函数'] || []).map(n => [n, null]);
    } else {
      const dim = mode === 0 ? 'plane' : 'solid';
      const objs = this.spec.objects[dim] || {};
      Object.keys(objs).forEach(cat => objs[cat].forEach(n => entries.push([n, cat])));
    }
    entries.forEach(pair => {
      const lab = document.createElement('label'); lab.className = 'fp-check';
      const cb = document.createElement('input'); cb.type = 'checkbox'; cb.checked = true; cb.value = pair[0];
      lab.appendChild(cb); lab.appendChild(document.createTextNode(pair[1] ? '[' + pair[1] + '] ' + pair[0] : pair[0]));
      box.appendChild(lab);
    });
    if (!entries.length) box.textContent = '（暂无可绘制对象，请先在定义区创建）';
  },

  drawNames() {
    return Array.from($('fpDrawObjs').querySelectorAll('input:checked')).map(c => c.value);
  },

  showResult(res) {
    const r = $('fpResult'); r.classList.remove('hidden');
    $('fpError').textContent = ''; $('fpError').classList.add('hidden');
    $('fpLatex').textContent = ''; $('fpText').textContent = '';
    $('fpImgWrap').classList.add('hidden');
    if (!res || res.ok === false) {
      $('fpError').textContent = '⚠ ' + ((res && res.error) || '操作失败');
      $('fpError').classList.remove('hidden');
      return;
    }
    if (res.png) { $('fpResImg').src = 'data:image/png;base64,' + res.png; $('fpImgWrap').classList.remove('hidden'); }
    if (res.latex) $('fpLatex').textContent = res.latex;
    if (res.text) $('fpText').textContent = res.text;
  },

  showDefPreview(res) {
    $('fpDefOutput').textContent = res.error ? ('⚠ ' + res.error) : (res.text || '');
    this.showResult(res);
  },

  showDraw(res) {
    $('fpDrawWrap').classList.add('hidden');
    if (res.ok && res.plot_png) {
      $('fpDrawImg').src = 'data:image/png;base64,' + res.plot_png;
      $('fpDrawWrap').classList.remove('hidden');
    }
    this.showResult(res);
  },

  applyEdit(res) {
    this.defType = res.type;
    $('fpDefType').value = String(res.type);
    const box = $('fpDefRows');
    const values = res.values || [];
    const dim = this.defType === 4 ? 'solid' : 'plane';
    this.renderRows(box, this.defRows(values), values, dim, () => this.rebuild('def', false));
  },

  onResult(res) {
    $('loading').classList.add('hidden');
    if (!this.spec) {
      if (res.ok && res.action === 'spec') { this.spec = res.spec; this.init(); }
      else this.showResult(res);
      return;
    }
    const a = res.action;
    if (a === 'spec') { this.spec = res.spec; this.init(); return; }
    if (a === 'objects') {
      this.spec.objects = res.objects; this.refreshObjectSelects(); this.refreshDrawObjs(); return;
    }
    if (a === 'def_list') {
      this.renderTree(res.groups);
      if (res.objects) this.spec.objects = res.objects;
      this.refreshObjectSelects(); this.refreshDrawObjs(); return;
    }
    if (a === 'def_save' || a === 'def_del' || a === 'save_result') {
      if (res.objects) this.spec.objects = res.objects;
      if (res.ok) {
        if (a === 'def_save') this.rebuild('def', true);
        if (a === 'save_result') $('fpSaveAs').value = '';
        this.refreshObjectSelects(); this.refreshDrawObjs();
        sendFp({ action: 'def_list' });
      }
      this.showResult(res);
      return;
    }
    if (a === 'def_edit') { if (res.ok) this.applyEdit(res); this.showResult(res); return; }
    if (a === 'def_preview') { this.showDefPreview(res); return; }
    if (a === 'draw') { this.showDraw(res); return; }
    this.showResult(res);
    if (a === 'calc' && res.ok) {
      $('fpCalcOutput').textContent = res.text || '';
      const name = ($('fpSaveAs').value || '').trim();
      if (name) sendFp({ action: 'save_result', name });
    }
  }
};

window.Calc = {
  onResult(res) {
    if (res && res.op === 'latexToExpr') { MathKeyboard.applyExpr(res); return; }
    if (res && res.page === 'fp') { Fp.onResult(res); return; }
    $('loading').classList.add('hidden');
    $('result').classList.remove('hidden');
    const plotWrap = $('plotWrap'), imgWrap = $('imgWrap');
    plotWrap.classList.add('hidden'); imgWrap.classList.add('hidden');
    $('latex').textContent = ''; $('text').textContent = ''; $('error').textContent = '';
    $('error').classList.add('hidden');
    if (!res || res.ok === false) {
      $('error').textContent = '⚠ ' + (res && res.error ? res.error : '计算失败');
      $('error').classList.remove('hidden');
      return;
    }
    if (res.plot_png) {
      $('plotImg').src = 'data:image/png;base64,' + res.plot_png;
      plotWrap.classList.remove('hidden');
    }
    if (res.png) {
      $('resImg').src = 'data:image/png;base64,' + res.png;
      imgWrap.classList.remove('hidden');
    }
    if (res.latex) $('latex').textContent = res.latex;
    if (res.text && res.text !== res.latex) $('text').textContent = res.text;
    if (res.defined && res.defined.length)
      $('text').textContent += '\n已定义：' + res.defined.join('，');
  }
};

Fp.boot();
