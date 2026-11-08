(function () {
  var BS = String.fromCharCode(92);
  function L(s) { return BS + s; }

  var ONE_ARG = ('sqrt overline underline vec hat bar tilde dot ddot acute grave ' +
    'breve check mathring mathrm mathbf mathbb mathcal mathfrak mathit mathsf ' +
    'mathtt mathscr boldsymbol pmb text textbf textit operatorname').split(' ').map(L);
  var TWO_ARG = ('frac dfrac tfrac cfrac binom dbinom tbinom overset underset').split(' ').map(L);
  var LEGACY = {};
  LEGACY[L('mathbbR')] = L('mathbb') + '{R}';
  LEGACY[L('mathbbC')] = L('mathbb') + '{C}';
  LEGACY[L('mathbbN')] = L('mathbb') + '{N}';
  LEGACY[L('mathbbQ')] = L('mathbb') + '{Q}';
  LEGACY[L('mathbbZ')] = L('mathbb') + '{Z}';
  var CMD_RE = new RegExp('^' + BS + BS + '[a-zA-Z]+');

  function isSpace(ch) {
    var c = ch.charCodeAt(0);
    return c === 32 || c === 9 || c === 13 || c === 10;
  }

  function readGroup(t, p) {
    if (p >= t.length) return ['', p];
    if (t[p] === '{') {
      var d = 0;
      for (var k = p; k < t.length; k++) {
        if (t[k] === '{') d++;
        else if (t[k] === '}') { d--; if (d === 0) return [t.slice(p, k + 1), k + 1]; }
      }
      return [t.slice(p), t.length];
    }
    var e = p + 1;
    if (t[p] === BS) while (e < t.length && /[a-zA-Z]/.test(t[e])) e++;
    return ['{' + t.slice(p, e) + '}', e];
  }

  function normalizeLatex(src) {
    if (!src) return '';
    var t = src, k;
    for (k in LEGACY) {
      if (Object.prototype.hasOwnProperty.call(LEGACY, k)) t = t.split(k).join(LEGACY[k]);
    }
    var out = [], p = 0;
    while (p < t.length) {
      if (t[p] !== BS) { out.push(t[p]); p++; continue; }
      var m = CMD_RE.exec(t.slice(p));
      if (!m) { out.push(t[p]); p++; continue; }
      var cmd = m[0];
      p += cmd.length;
      out.push(cmd);
      var c = TWO_ARG.indexOf(cmd) >= 0 ? 2 : (ONE_ARG.indexOf(cmd) >= 0 ? 1 : 0);
      if (c === 0) continue;
      if (cmd === L('sqrt') && t[p] === '[') {
        var cl = t.indexOf(']', p);
        if (cl > 0) { out.push(t.slice(p, cl + 1)); p = cl + 1; }
      }
      for (var j = 0; j < c; j++) {
        while (p < t.length && isSpace(t[p])) { out.push(t[p]); p++; }
        var g = readGroup(t, p);
        out.push(g[0]); p = g[1];
      }
    }
    return out.join('');
  }

  var get = function (id) { return document.getElementById(id); };
  var mask = null, useMathLive = false, target = null, showTimer = null;
  var allowHide = false, restoreCount = 0, guardTarget = null;

  function field() { return get(useMathLive ? 'kbd-mf' : 'kbd-raw'); }

  function isOpen() { return !!mask && !mask.classList.contains('hidden'); }

  function getLatex() {
    var f = field();
    return f ? (f.value || '') : '';
  }

  function keyboard() { return window.mathVirtualKeyboard || null; }

  function hideVirtualKeyboard() {
    var k = keyboard();
    if (!k || !k.hide) return;
    allowHide = true;
    restoreCount = 0;
    try { k.hide({ animate: false }); }
    catch (err) { try { k.hide(); } catch (e2) {} }
    finally { allowHide = false; }
  }

  function showVirtualKeyboard() {
    bindKeyboardGuard();
    var k = keyboard();
    if (!k || !k.show) return;
    try { k.show({ animate: false }); }
    catch (err) { try { k.show(); } catch (e2) {} }
  }

  function setPolicy() {
    if (!useMathLive) return;
    var f = field();
    if (!f) return;
    try { f.setAttribute('math-virtual-keyboard-policy', 'manual'); } catch (err) {}
    try { f.mathVirtualKeyboardPolicy = 'manual'; } catch (err) {}
  }

  function connected(node) {
    if (!node) return false;
    if (node.isConnected !== undefined) return node.isConnected;
    return document.contains ? document.contains(node) : true;
  }

  function bindKeyboardGuard(attempt) {
    var k = keyboard();
    if (!k || !k.addEventListener || k === guardTarget) {
      if ((attempt || 0) < 10 && (!k || k !== guardTarget)) {
        setTimeout(function () { bindKeyboardGuard((attempt || 0) + 1); }, 100);
      }
      return;
    }
    guardTarget = k;
    k.addEventListener('before-virtual-keyboard-toggle', function (e) {
      if (!allowHide && isOpen() && e && e.detail && e.detail.visible === false && e.preventDefault) {
        e.preventDefault();
      }
    });
    k.addEventListener('virtual-keyboard-toggle', function () {
      var cur = keyboard();
      if (!allowHide && isOpen() && cur && cur.visible === false && restoreCount < 3) {
        restoreCount++;
        showVirtualKeyboard();
      }
    });
  }

  function close() {
    if (showTimer) { clearTimeout(showTimer); showTimer = null; }
    hideVirtualKeyboard();
    if (mask) mask.classList.add('hidden');
    target = null;
  }

  function commit() {
    var latex = getLatex().trim();
    if (!latex) { close(); return; }
    if (typeof API.send === 'function') API.send({ action: 'latexToExpr', latex: normalizeLatex(latex) });
    else close();
  }

  function build() {
    useMathLive = (typeof MathfieldElement !== 'undefined');
    var fieldHtml = useMathLive
      ? '<math-field id="kbd-mf" math-virtual-keyboard-policy="manual" inputmode="none" locale="zh-CN" ' +
        'placeholder="点击键盘输入公式"></math-field>'
      : '<textarea id="kbd-raw" rows="2" placeholder="输入 LaTeX 公式"></textarea>';
    var m = document.createElement('div');
    m.id = 'kbd-mask';
    m.className = 'hidden';
    m.innerHTML =
      '<div id="kbd-bar">' +
        fieldHtml +
        '<button type="button" class="btn" id="kbd-cancel">取消</button>' +
        '<button type="button" class="btn primary" id="kbd-ok">确定</button>' +
      '</div>';
    document.body.appendChild(m);
    mask = m;

    get('kbd-cancel').addEventListener('click', close);
    get('kbd-ok').addEventListener('click', commit);
    ['click', 'pointerdown', 'pointerup', 'pointermove', 'mousedown', 'mouseup',
      'mousemove', 'touchstart', 'touchend'].forEach(function (t) {
      m.addEventListener(t, function (e) { e.stopPropagation(); }, false);
    });
    if (useMathLive && MathfieldElement.locale !== undefined) MathfieldElement.locale = 'zh-CN';
    setPolicy();
    if (useMathLive) bindKeyboardGuard();
    if (useMathLive && window.customElements && customElements.whenDefined) {
      try {
        customElements.whenDefined('math-field').then(setPolicy).catch(function () {});
      } catch (err) {}
    }

    document.addEventListener('click', function (e) {
      var b = e.target && e.target.closest ? e.target.closest('[data-kbd]') : null;
      if (!b) return;
      e.preventDefault();
      var t = get(b.getAttribute('data-kbd'));
      if (t) open(t);
    }, true);

    document.addEventListener('visibilitychange', function () {
      if (!document.hidden) return;
      setTimeout(function () {
        if (document.hidden && isOpen()) close();
      }, 400);
    });
    window.addEventListener('pagehide', close);
    window.addEventListener('resize', function () {
      if (isOpen() && !connected(target)) close();
    });
  }

  function open(inp) {
    if (!inp) return;
    if (!mask) build();
    close();
    target = inp;
    var f = field();
    if (f) {
      if (useMathLive && typeof f.setValue === 'function') {
        try { f.setValue(''); } catch (err) { f.value = ''; }
      } else f.value = '';
    }
    setPolicy();
    mask.classList.remove('hidden');
    if (useMathLive) {
      try { f.focus({ preventScroll: true }); } catch (err) { try { f.focus(); } catch (e2) {} }
      showTimer = setTimeout(function () {
        showTimer = null;
        if (!connected(target)) { close(); return; }
        setPolicy();
        try { field().focus({ preventScroll: true }); } catch (err) {}
        showVirtualKeyboard();
      }, 120);
    }
  }

  var API = {
    send: null,
    open: open,
    close: close,
    isOpen: isOpen,
    normalizeLatex: normalizeLatex,
    applyExpr: function (r) {
      var t = target;
      if (!connected(t) && t && t.id) t = get(t.id);
      if (connected(t) && r && r.expr !== undefined) {
        t.value = r.expr;
        try {
          var ev = document.createEvent('HTMLEvents');
          ev.initEvent('change', true, false);
          t.dispatchEvent(ev);
        } catch (err) {}
      }
      close();
      if (r && r.error && typeof console !== 'undefined' && console.warn) console.warn(r.error);
    }
  };
  window.MathKeyboard = API;
  build();
})();
