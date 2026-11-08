# -*- coding: utf-8 -*-
"""CalculusCalculator 安卓端计算引擎（Chaquopy / 离线）。

本模块在 APK 内嵌的 Python 运行时中执行，复用原项目的纯计算模块：
    core.sympify.sympify        —— 表达式解析（支持 Python/SymPy 语法与 $LaTeX$）
    functions.derivative        —— 显/隐函数求导
    functions.integral          —— 不定/定积分
    functions.simplification     —— 13 种表达式变形
    functions.solvers           —— 方程/不等式/方程组/微分方程/解三角形
    functions.functions         —— 函数值域/单调/奇偶/周期/最值
    functions.paint2D           —— 函数绘图（matplotlib Agg 出图）
    functions.planes            —— 平面几何（30 类运算）
    functions.solids            —— 立体几何（37 类运算）
    functions.paint3D           —— 三维几何对象绘图
    expr_calculator.expr_tree   —— 表达式树与分层着色 LaTeX

对外只暴露一个函数：
    compute(request_json: str) -> str   # 返回 JSON 字符串
由 Java 侧通过 Chaquopy 调用，结果以 LaTeX + PNG（base64）形式回传 WebView。
"""

import json
import io
import base64
import re

import matplotlib
matplotlib.use("Agg")  # 非交互式后端，离线出图
import matplotlib.pyplot as plt
from matplotlib import rc_context

import sympy
from sympy import (
    sympify as sp_sympify, Eq, Symbol, latex as sp_latex,
    Reals, Interval, oo, S, Function,
)

from core.sympify import sympify, ordered_expr_text
from functions.derivative import derivative, yinhanshu_derivative
from functions.integral import integral
from functions.simplification import simplifies
from functions.solvers import (
    solve_fangcheng, solve_weifenfangcheng, solve_fangchengzu,
    solve_budengshi, solve_budengshizu, solve_sanjiaoxing,
)

# 会话级「定义区」：与原项目 fs 一致，格式为 {name: [name, body, domain, var]}。
# 定义后可在其它运算里直接写 f(3) / f(g(2))。
_FS = {}
from functions.functions import get_function_attr
from functions.paint2D import draw_functions
from functions import planes as planes_mod
from functions import solids as solids_mod
from functions.paint3D import draw3d


# ---------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------
def _is_err(obj):
    """core.sympify 在解析失败时返回错误字符串。"""
    return isinstance(obj, str)


def _safe_sympify(s, fs, locals=None):
    """解析单条表达式为 sympy 对象；失败抛 ValueError。

    自动识别 LaTeX：若字符串含反斜杠命令（如 \\frac）且未以 $ 开头，
    则自动包成 $...$ 交给 latex2sympy 解析，从而同时支持 SymPy 语法与 LaTeX。
    """
    if s is None:
        s = ""
    s = str(s).strip()
    if s and not s.startswith("$") and "\\" in s:
        s = "$" + s + "$"
    r = sympify(s, fs, locals=locals)
    if _is_err(r):
        raise ValueError(r if r else "空表达式")
    return r


def _parse_relation(s, fs, locals=None):
    """把 'lhs = rhs' / 'lhs < rhs' / ... 解析为 sympy Eq / Rel。

    兼容整段以 $...$ 包裹的 LaTeX 等式（如 $x^2 = 2$）。
    """
    s = str(s).strip()
    if s.startswith("$") and s.endswith("$"):
        s = s[1:-1]
    m = re.split(r"(<=|>=|!=|==|=|<|>)", s, maxsplit=1)
    if len(m) < 3:
        raise ValueError("需要等式或不等式，例如 x**2 = 1")
    lhs = _safe_sympify(m[0], fs, locals)
    rhs = _safe_sympify(m[2], fs, locals)
    op = m[1]
    if op in ("=", "=="):
        return Eq(lhs, rhs)
    if op == "<":
        return lhs < rhs
    if op == ">":
        return lhs > rhs
    if op == "<=":
        return lhs <= rhs
    if op == ">=":
        return lhs >= rhs
    if op == "!=":
        return lhs != rhs
    raise ValueError("无法识别的关系运算符")


def _latex_png(latex_str, fontsize=18, dpi=170, theme="light"):
    """用 matplotlib mathtext 把 LaTeX 渲染成 PNG（base64），失败返回 None。"""
    if not latex_str:
        return None
    fg = "black" if theme == "light" else "#e8eaed"
    try:
        fig = plt.figure(figsize=(0.1, 0.1))
        with rc_context({"text.color": fg, "mathtext.fontset": "cm",
                         "font.family": "DejaVu Sans"}):
            fig.text(0.5, 0.5, "$" + latex_str + "$", fontsize=fontsize,
                     color=fg, ha="center", va="center")
        buf = io.BytesIO()
        fig.savefig(buf, dpi=dpi, format="png", transparent=True,
                    bbox_inches="tight", pad_inches=0.12)
        plt.close(fig)
        return base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        return None


def _render(obj, theme="light"):
    """把 sympy 结果转成 (latex, png_b64, text)。字符串原样返回。"""
    if isinstance(obj, str):
        return None, None, obj
    try:
        ltx = sp_latex(obj)
    except Exception:
        return None, None, str(obj)
    return ltx, _latex_png(ltx, theme=theme), str(obj)


def _fig_png(fig, dpi=120):
    """把 matplotlib Figure 转 PNG（base64）。"""
    buf = io.BytesIO()
    fig.savefig(buf, dpi=dpi, format="png", bbox_inches="tight",
                transparent=True, pad_inches=0.15)
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _ok(op, obj=None, theme="light", extra=None):
    ltx, png, text = _render(obj, theme) if obj is not None else (None, None, "")
    out = {"ok": True, "op": op, "latex": ltx, "png": png,
           "text": text, "plot_png": None, "error": None}
    if extra:
        out.update(extra)
    return out


def _fail(op, msg):
    return {"ok": False, "op": op, "latex": None, "png": None,
            "text": "", "plot_png": None, "error": str(msg)}


# ---------------------------------------------------------------
# 几何结果渲染（处理 sympy 几何对象 / 元组 / 字典 / 布尔）
# ---------------------------------------------------------------
def _geo_latex(obj):
    if isinstance(obj, str):
        return None
    if isinstance(obj, bool):
        return r"\text{%s}" % ("是" if obj else "否")
    if isinstance(obj, dict):
        parts = []
        for k, v in obj.items():
            l = _geo_latex(v)
            if l is None:
                l = r"\text{%s}" % str(v)
            parts.append(r"\textbf{%s}:& %s" % (k, l))
        return r"\begin{aligned}%s\end{aligned}" % r"\\".join(parts)
    if isinstance(obj, (tuple, list)):
        items = []
        for x in obj:
            l = _geo_latex(x)
            items.append(l if l is not None else r"\text{%s}" % str(x))
        return "(" + ", ".join(items) + ")"
    try:
        return sp_latex(obj)
    except Exception:
        return None


def _geo_text(obj):
    if isinstance(obj, str):
        return obj
    if isinstance(obj, bool):
        return "是" if obj else "否"
    if isinstance(obj, dict):
        return "\n".join("%s: %s" % (k, _geo_text(v)) for k, v in obj.items())
    if isinstance(obj, (tuple, list)):
        return "(" + ", ".join(_geo_text(x) for x in obj) + ")"
    return str(obj)


def _ok_geo(op, obj, theme="light"):
    ltx = _geo_latex(obj)
    text = _geo_text(obj)
    png = _latex_png(ltx, theme=theme) if ltx else None
    return {"ok": True, "op": op, "latex": ltx, "png": png,
            "text": text, "plot_png": None, "error": None}


# ---------------------------------------------------------------
# 各操作分发（微积分）
# ---------------------------------------------------------------
def _op_simplify(req, fs):
    op = req.get("op")
    method_map = {
        "simplify": 0, "expand": 1, "factor": 2, "collect": 3,
        "cancel": 4, "apart": 5, "trigsimp": 6, "expand_trig": 7,
        "powsimp": 8, "expand_power_exp": 9, "expand_log": 10,
        "logcombine": 11, "substitute": 12,
    }
    method = method_map[op]
    expr = _safe_sympify(req.get("expr", ""), fs)
    zhuyuan = req.get("var", "x") or "x"
    huanyuan = req.get("sub_var", "t") or "t"
    huanyuanshi = req.get("sub_expr", "") or "x"
    r = simplifies(str(expr), method, zhuyuan, huanyuan, huanyuanshi, fs)
    return _ok(op, r)


def _op_derivative(req, fs):
    f = req.get("expr", "")
    v = req.get("var", "x") or "x"
    n = int(req.get("order", 1) or 1)
    x = req.get("value", "")  # 代入值，可空
    if req.get("implicit"):
        r = yinhanshu_derivative(f, req.get("var1", "x"),
                                 req.get("var2", "y"), n, x, fs)
    else:
        r = derivative(f, v, n, x, fs)
    if _is_err(r):
        raise ValueError(r)
    return _ok(req.get("op"), r)


def _op_integral(req, fs):
    f = req.get("expr", "")
    v = req.get("var", "x") or "x"
    a = req.get("a", "")
    b = req.get("b", "")
    r = integral(f, v, fs, a, b)
    if _is_err(r):
        raise ValueError(r)
    return _ok(req.get("op"), r)


def _op_solve_eq(req, fs):
    rel = _parse_relation(req.get("expr", ""), fs)
    zhuyuan = req.get("var", "x") or "x"
    domain = req.get("domain", "Reals") or "Reals"
    r = solve_fangcheng(rel, zhuyuan, domain, fs)
    return _ok(req.get("op"), r)


def _op_solve_ineq(req, fs):
    rel = _parse_relation(req.get("expr", ""), fs)
    zhuyuan = req.get("var", "x") or "x"
    domain = req.get("domain", "Reals") or "Reals"
    r = solve_budengshi(rel, zhuyuan, domain, fs)
    return _ok(req.get("op"), r)


def _op_solve_system(req, fs):
    lines = [s for s in req.get("expr", "").split("\n") if s.strip()]
    eqs = [_parse_relation(s, fs) for s in lines]
    vars_ = [v.strip() for v in (req.get("vars", "x,y").split(",")) if v.strip()]
    zhuyuan = [Symbol(v) for v in vars_]
    r = solve_fangchengzu(eqs, zhuyuan, fs)
    return _ok(req.get("op"), r)


def _op_solve_ineq_system(req, fs):
    lines = [s for s in req.get("expr", "").split("\n") if s.strip()]
    if not lines:
        raise ValueError("请每行输入一个不等式")
    rels = [_parse_relation(s, fs) for s in lines]
    zhuyuan = Symbol(req.get("var", "x") or "x")
    r = solve_budengshizu(rels, zhuyuan, fs)
    return _ok(req.get("op"), r)


def _op_ode(req, fs):
    # 微分方程以 f(x) 为主元，输入示例： Derivative(f(x), x) = f(x)
    locals_d = {"f": Function("f")}
    rel = _parse_relation(req.get("expr", ""), fs, locals=locals_d)
    r = solve_weifenfangcheng(rel, "f", fs)
    return _ok(req.get("op"), r)


def _op_function_attr(req, fs):
    attr_map = {
        "frange": 1, "fmono_inc": 2, "fmono_dec": 3, "fparity": 4,
        "fperiod": 5, "fmax": 6, "fmin": 7,
    }
    attr = attr_map[req.get("op")]
    f = req.get("expr", "")
    s = req.get("var", "x") or "x"
    d = req.get("domain", "Reals") or "Reals"
    r = get_function_attr(f, s, d, attr, fs)
    return _ok(req.get("op"), r)


def _op_triangle(req, fs):
    angles, sides = {}, {}
    for part in (req.get("angles", "") or "").split(","):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            val = v.strip()
            if val.endswith("°") or val.lower().endswith("deg"):
                val = str(sp_sympify(val.rstrip("°deg DEM").strip()) * sympy.pi / 180)
            angles[k.strip()] = _safe_sympify(val, fs)
    for part in (req.get("sides", "") or "").split(","):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            sides[k.strip()] = _safe_sympify(v.strip(), fs)
    if not angles and not sides:
        raise ValueError("请填写已知条件，例如 angles='A=30°,B=60' sides='a=5'")
    r = solve_sanjiaoxing(angles, sides, fs)
    return _ok(req.get("op"), r)


def _op_plot(req, fs):
    var = req.get("var", "x") or "x"
    lines = [s.strip() for s in req.get("expr", "").split("\n") if s.strip()]
    if not lines:
        raise ValueError("请至少输入一个函数，例如 x**2")
    entries = []
    for i, line in enumerate(lines):
        expr = _safe_sympify(line, fs)
        entries.append(("f%d" % (i + 1), expr, var))
    xmin = float(req.get("xmin", -10))
    xmax = float(req.get("xmax", 10))
    fig = draw_functions(entries, xlim=(xmin, xmax), theme="light")
    png = _fig_png(fig)
    return _ok(req.get("op"), None, extra={"plot_png": png})


# ---------------------------------------------------------------
# 平面几何 / 立体几何 / 3D 绘图
# ---------------------------------------------------------------
def _op_planes(req, fs):
    sub = int(req.get("sub", 0))
    params = req.get("params", []) or []
    r = planes_mod.get_planes_result(sub, list(params), fs)
    return _ok_geo("planes", r)


def _op_solids(req, fs):
    sub = int(req.get("sub", 0))
    params = req.get("params", []) or []
    r = solids_mod.get_solids_result(sub, list(params), fs)
    return _ok_geo("solids", r)


def _op_plot3d(req, fs):
    """解析三维几何对象描述并绘制。

    每行一种对象，格式：
        point   x,y,z
        line    x1,y1,z1; x2,y2,z2
        segment x1,y1,z1; x2,y2,z2
        ray     x1,y1,z1; x2,y2,z2
        plane   x1,y1,z1; x2,y2,z2; x3,y3,z3
    空行与以 # 开头的注释忽略。
    """
    spec = req.get("expr", "") or req.get("spec", "")
    lines = [s.strip() for s in spec.split("\n") if s.strip() and not s.strip().startswith("#")]
    objects = []
    try:
        for line in lines:
            kind, _, rest = line.partition(" ")
            rest = rest.strip()
            if kind == "point":
                p = solids_mod._parse_point3d(rest, fs)
                objects.append((p, None))
            elif kind in ("line", "segment", "ray"):
                a, _, b = rest.partition(";")
                l = solids_mod._build_line_from_strs(a.strip(), b.strip(), fs)
                objects.append((l, None))
            elif kind == "plane":
                parts = [x.strip() for x in rest.split(";")]
                if len(parts) != 3:
                    raise ValueError("plane 需要 3 个点，用 ; 分隔")
                pl = solids_mod._build_plane_from_strs(
                    parts[0], parts[1], parts[2], fs)
                objects.append((pl, None))
            else:
                raise ValueError("未知对象类型: %s（支持 point/line/segment/ray/plane）" % kind)
    except Exception as e:
        return _fail("plot3d", e)
    if not objects:
        return _fail("plot3d", "请至少输入一个三维对象，例如：\npoint 0,0,0\nline 0,0,0; 1,1,1")
    fig = draw3d(objects, theme="light")
    png = _fig_png(fig, dpi=110)
    return _ok("plot3d", None, extra={"plot_png": png})


def _op_exprtree(req, fs):
    """基于表达式树对表达式做结构化变形。"""
    from expr_calculator.expr_tree import from_string, from_sympy
    from sympy import simplify, expand, factor, cancel, together, apart, trigsimp, radsimp
    kind = req.get("kind", "simplify")
    inp = req.get("expr", "")
    method = {
        "simplify": simplify, "expand": expand, "factor": factor,
        "cancel": cancel, "together": together, "apart": apart,
        "trigsimp": trigsimp, "radsimp": radsimp,
    }.get(kind, simplify)
    tree = from_string(inp)
    result = from_sympy(method(tree.to_sympy()), ordered=True)
    return _ok("exprtree", result.to_sympy())


# ---------------------------------------------------------------
# 数值计算（对应原项目「计算」的四种引擎）与定义区
# ---------------------------------------------------------------
def _op_calc(req, fs):
    engine = req.get("engine", "python")
    text = (req.get("expr") or "").strip()
    if not text:
        raise ValueError("请输入要计算的表达式")

    if engine == "python":
        import math
        env = {"__builtins__": {}}
        for name in dir(math):
            if not name.startswith("_"):
                env[name] = getattr(math, name)
        env.update({"abs": abs, "round": round, "int": int, "float": float,
                    "pow": pow, "sum": sum, "min": min, "max": max})
        return _ok("calc", eval(text, env, {}))

    if engine == "mpmath":
        import mpmath as mp
        env = {"__builtins__": {}}
        for name in dir(mp):
            if not name.startswith("_"):
                try:
                    env[name] = getattr(mp, name)
                except Exception:
                    pass
        env.update({"abs": abs, "int": int, "float": float, "pow": pow})
        with mp.workdps(int(req.get("dps", 16) or 16)):
            result_text = str(eval(text, env, {}))
        return _ok("calc", result_text)

    if engine == "sympy":
        r = sympify(text, fs, is_simplify=True)
        if _is_err(r):
            raise ValueError(r)
        return _ok("calc", r)

    if engine == "latex":
        r = sympify(text, {}, is_simplify=False)
        ltx = text if _is_err(r) else sp_latex(r)
        return {"ok": True, "op": "calc", "latex": ltx, "png": None,
                "text": ltx, "plot_png": None, "error": None}

    raise ValueError("未知计算引擎：" + engine)


def _op_define(req, fs):
    name = (req.get("name") or "").strip()
    body = (req.get("expr") or "").strip()
    var = (req.get("var") or "x").strip() or "x"
    domain = (req.get("domain") or "Reals").strip() or "Reals"
    if not name or not body:
        raise ValueError("请填写名称与函数体，例如 name=f, expr=x**2+1")
    _FS[name] = [name, body, domain, var]
    return {"ok": True, "op": "define", "latex": None, "png": None,
            "text": "已定义 %s(%s) = %s" % (name, var, body),
            "plot_png": None, "error": None, "defined": list(_FS.keys())}


def _op_fp(req, fs):
    import functions_page
    return functions_page.handle(req, fs)


def _op_latex_to_expr(req, fs):
    latex = (req.get("latex") or "").strip()
    if not latex:
        return {"ok": False, "op": "latexToExpr", "expr": "", "error": "公式为空"}
    try:
        expr = sympify("$" + latex, {})
        if not isinstance(expr, sympy.Basic):
            return {"ok": False, "op": "latexToExpr", "expr": latex,
                    "error": "公式无法解析：%s" % expr}
        return {"ok": True, "op": "latexToExpr",
                "expr": ordered_expr_text(expr), "error": None}
    except Exception as exc:
        return {"ok": False, "op": "latexToExpr", "expr": latex,
                "error": "公式转换失败：%s" % exc}


# ---------------------------------------------------------------
# 入口
# ---------------------------------------------------------------
_DISPATCH = {
    "fp": _op_fp,
    "latexToExpr": _op_latex_to_expr,
    "simplify": _op_simplify, "expand": _op_simplify, "factor": _op_simplify,
    "collect": _op_simplify, "cancel": _op_simplify, "apart": _op_simplify,
    "trigsimp": _op_simplify, "expand_trig": _op_simplify,
    "powsimp": _op_simplify, "expand_power_exp": _op_simplify,
    "expand_log": _op_simplify, "logcombine": _op_simplify,
    "substitute": _op_simplify,
    "derivative": _op_derivative, "integral": _op_integral,
    "solve": _op_solve_eq, "solve_inequality": _op_solve_ineq,
    "solve_system": _op_solve_system, "solve_inequality_system": _op_solve_ineq_system,
    "ode": _op_ode, "calc": _op_calc, "define": _op_define,
    "frange": _op_function_attr, "fmono_inc": _op_function_attr,
    "fmono_dec": _op_function_attr, "fparity": _op_function_attr,
    "fperiod": _op_function_attr, "fmax": _op_function_attr,
    "fmin": _op_function_attr, "triangle": _op_triangle, "plot": _op_plot,
    "planes": _op_planes, "solids": _op_solids,
    "plot3d": _op_plot3d, "exprtree": _op_exprtree,
}


def compute(request_json):
    """由 Java 侧调用：request_json -> JSON 字符串结果。"""
    try:
        req = json.loads(request_json)
        op = req.get("op", "")
        fs = req.get("fs") or _FS
        handler = _DISPATCH.get(op)
        if handler is None:
            return json.dumps(_fail(op, "未知操作: %s" % op), ensure_ascii=False)
        return json.dumps(handler(req, fs), ensure_ascii=False)
    except Exception as e:
        import traceback
        return json.dumps(_fail("?", "%s\n%s" % (e, traceback.format_exc()[:500])),
                          ensure_ascii=False)
