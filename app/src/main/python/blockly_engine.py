# 积木（Blockly）模式执行引擎。
#
# 移植自原项目的 ui/blockly.py（PythonBridge），去掉 PySide6 / QWebChannel 等 GUI
# 依赖，改为在 Chaquopy 环境下执行 Blockly 生成的 Python 代码，并把输出以结构化
# JSON 回传给 WebView 前端。计算内核（derivative / integral / solvers / 等）仍复用
# 原项目的纯计算模块，功能逻辑保持不变。

import io
import json
import sys

# --------------------------------------------------------------------------- #
# 全局状态（整个积木模式会话内共享，与原项目 fs 行为一致）
# --------------------------------------------------------------------------- #
fs = {}            # 函数字典：name -> [name, body, domain, var]
_inputs = {}       # 输入表格：name -> value
_outputs = []      # 本次运行收集的输出：[{"name", "text", "latex"}, ...]


def set_inputs(json_text):
    """由前端同步输入表格（JSON 字符串）。"""
    global _inputs
    try:
        _inputs = json.loads(json_text) or {}
    except Exception:
        _inputs = {}


def get_functions_json():
    """返回已定义函数名列表的 JSON 字符串。"""
    return json.dumps(list(fs.keys()))


def set_function_names(json_text):
    """同步"定义函数"积木中的函数名到 fs（占位），供"调用函数"下拉使用。
    已存在的完整定义保留，新名字加占位，不再出现的名字移除（移植自 ui/blockly.py）。"""
    global fs
    try:
        names = json.loads(json_text) or []
    except Exception:
        return
    new_fs = {}
    for name in names:
        if name in fs:
            new_fs[name] = fs[name]
        else:
            new_fs[name] = [name, '', '', '']
    fs = new_fs


_state = ''


def set_state(json_text):
    """保存积木工作区序列化状态（供存档使用）。"""
    global _state
    _state = json_text or ''


def get_state():
    """返回积木工作区序列化状态。"""
    return _state


def get_input(name):
    return _inputs.get(name, '')


def py_output(name, value):
    """把输出追加到结果列表（前端以结构化方式渲染）。"""
    text, is_latex = _format_value(value)
    _outputs.append({"name": name, "text": text, "latex": is_latex})
    return value


@staticmethod
def _format_value(value):
    """将任意值转为 (显示文本, 是否为 LaTeX) 二元组（移植自 ui/blockly.py）。"""
    if value is None:
        return ('', False)
    try:
        from sympy import latex as _latex, sympify as _sympify
    except Exception:
        _latex = None
        _sympify = None
    if isinstance(value, dict):
        items = [(k, _format_value(v)) for k, v in value.items()]
        parts = ['{}={}'.format(k, t) for k, (t, _) in items]
        return (r',\ '.join(parts), any(f for _, f in items))
    if isinstance(value, (list, tuple, set)):
        items = [_format_value(v) for v in value]
        parts = [t for t, _ in items]
        return (r'\ \ \ '.join(parts), any(f for _, f in items))
    if isinstance(value, str):
        if _sympify is not None and _latex is not None and value.strip():
            try:
                return (_latex(_sympify(value)), True)
            except Exception:
                pass
        return (value, False)
    if _latex is not None:
        try:
            return (_latex(value), True)
        except Exception:
            pass
    return (str(value), False)


def define_func(name, expr, domain, var):
    """定义函数：fs[name] = [名称, 表达式, 定义域, 变量]"""
    from core.sympify import sympify
    if not name or not expr:
        return '错误：函数名称和表达式不能为空'
    try:
        body = str(sympify(expr, fs))
    except Exception as err:
        return '错误：函数表达式无效 - {}'.format(err)
    fs[name] = [name, body, domain or 'Reals', var or 'x']
    return '已定义函数 {}({}) = {}'.format(name, var or 'x', body)


def py_simplifies(expr, method, zhuyuan='', huanyuan='', huanyuanshi=''):
    from functions.simplification import simplifies
    return simplifies(expr, int(method), zhuyuan or None,
                      huanyuan or None, huanyuanshi or None, fs)


def py_solve_fangchengzu(eqs, vars_text):
    from functions.solvers import solve_fangchengzu
    from core.sympify import sympify
    from sympy import Eq, Symbol
    eq_list = [Eq(sympify(e, fs), 0) for e in eqs]
    var_list = [Symbol(s.strip()) for s in vars_text.split(',') if s.strip()]
    return solve_fangchengzu(eq_list, var_list, fs)


def py_solve_budengshi(lhs, op, rhs, var, domain='Reals'):
    from functions.solvers import solve_budengshi
    from core.sympify import sympify
    from sympy import Rel
    rel = Rel(sympify(lhs, fs), sympify(rhs, fs), op)
    return solve_budengshi(rel, var, domain or 'Reals', fs)


def py_solve_budengshizu(items, var):
    from functions.solvers import solve_budengshizu
    from core.sympify import sympify
    from sympy import Rel, Symbol
    rels = [Rel(sympify(l, fs), sympify(r, fs), o) for (l, o, r) in items]
    return solve_budengshizu(rels, Symbol(var), fs)


def py_solve_triangle(*conds):
    from functions.solvers import solve_sanjiaoxing
    from core.sympify import sympify
    angles = {}
    sides = {}
    mapping = {'A': ('A', angles), 'B': ('B', angles), 'C': ('C', angles),
               'a': ('a', sides), 'b': ('b', sides), 'c': ('c', sides)}
    for kind, val in conds:
        key = (kind or '').strip()
        if not key or key not in mapping or not val:
            continue
        target_key, target = mapping[key]
        target[target_key] = sympify(val, fs)
    return solve_sanjiaoxing(angles, sides, fs)


def py_calc(expr):
    from core.sympify import sympify
    from sympy import radsimp
    return radsimp(sympify(expr, fs, is_simplify=True))


def py_func_value(name, arg=''):
    """计算已定义函数的值；arg 为空时返回函数表达式本身。"""
    from core.sympify import sympify
    from sympy import symbols
    if not name or name not in fs:
        return '未定义函数: {}'.format(name or '?')
    body = fs[name][1]
    var = fs[name][3]
    expr = sympify(body, fs)
    if not arg:
        return expr
    return expr.subs(symbols(var), sympify(arg, fs))


def execute_blockly(code):
    """执行 Blockly 生成的 Python 代码，返回 JSON：
    {"outputs": [...], "stdout": str, "error": str|null, "functions": [...]}
    """
    global _outputs
    _outputs = []
    error_text = None
    out_buffer = io.StringIO()
    old_stdout = sys.stdout
    env = {
        'fs': fs,
        'get_input': get_input,
        'py_output': py_output,
        'define_func': define_func,
        'py_simplifies': py_simplifies,
        'py_solve_fangchengzu': py_solve_fangchengzu,
        'py_solve_budengshi': py_solve_budengshi,
        'py_solve_budengshizu': py_solve_budengshizu,
        'py_solve_triangle': py_solve_triangle,
        'py_calc': py_calc,
        'py_func_value': py_func_value,
    }
    try:
        try:
            eval(compile(code, '<blockly>', 'eval'), env)
        except SyntaxError:
            sys.stdout = out_buffer
            try:
                exec(code, env)
            except Exception as err:
                error_text = '执行错误: {}'.format(err)
            finally:
                sys.stdout = old_stdout
        except Exception as err:
            error_text = '执行错误: {}'.format(err)
    except Exception as err:
        error_text = '执行错误: {}'.format(err)

    return json.dumps({
        "outputs": _outputs,
        "stdout": out_buffer.getvalue(),
        "error": error_text,
        "functions": list(fs.keys()),
    })
