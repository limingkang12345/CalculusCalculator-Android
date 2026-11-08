import re
from sympy import sympify as sympify_sympy
from sympy import Symbol, simplify, radsimp, Basic as SympyBasic
from sympy.core.sympify import SympifyError

# latex2sympy2_extended 为可选依赖：仅在处理 $LaTeX$ 输入时需要。
# 改为延迟导入，避免在无该包的环境（或离线精简场景）下整个模块无法加载；
# 仅当表达式以 $ 开头、真正需要 LaTeX 解析时才尝试导入。
_latex2sympy = None
def _get_latex2sympy():
    global _latex2sympy
    if _latex2sympy is None:
        from latex2sympy2_extended import latex2sympy as _l2s
        _latex2sympy = _l2s
    return _latex2sympy

def _preprocess_func_calls(expr_str, fs):
    """预处理函数调用表达式，将 f(arg) 形式替换为函数体表达式
    例如 fs={"f":["f","x**2","Reals","x"]} 时，"f(3)" 被替换为 "(3**2)"
    支持嵌套调用如 f(g(2)) 和同时使用 f(2)+f(3)
    """
    if not fs:
        return expr_str

    # 按函数名长度降序排列，避免短名称优先于长名称匹配
    func_names = sorted(fs.keys(), key=len, reverse=True)
    result = expr_str

    while True:
        # 查找最左侧的函数调用（使用 \b 避免 sqrt( 中的 t( 被误匹配）
        best_pos = len(result)
        best_func = None
        for func_name in func_names:
            match = re.search(r'\b' + re.escape(func_name) + r'\(', result)
            pos = match.start() if match else -1
            if pos != -1 and pos < best_pos:
                best_pos = pos
                best_func = func_name

        if best_func is None:
            break

        # 查找匹配的右括号（支持嵌套括号）
        start_arg = best_pos + len(best_func) + 1
        depth = 1
        end_arg = start_arg
        while depth > 0 and end_arg < len(result):
            if result[end_arg] == '(':
                depth += 1
            elif result[end_arg] == ')':
                depth -= 1
            end_arg += 1

        if depth != 0:
            break  # 括号不匹配，跳过

        arg_str = result[start_arg:end_arg - 1]
        var_name = fs[best_func][3]
        body_str = fs[best_func][1]

        # 在函数体中将自变量替换为参数值，带 \b 避免部分匹配（如 x0 被误替换）
        expanded_body = re.sub(r'\b' + re.escape(var_name) + r'\b', f'({arg_str})', body_str)
        replacement = f'({expanded_body})'
        result = result[:best_pos] + replacement + result[end_arg:]

    return result


def sympify(expr, fs, locals = None, is_simplify = False, is_rationalize = False):
    # 用于处理输入的表达式
    # expr(str):符合Python和Sympy规范的表达式或Latex代码
    # fs(dict):函数字典
    # locals(dict):自变量映射
    # is_simplify(bool):是否自动化简
    # is_rationalize(bool):是否对结果执行分母有理化
    # return:处理后的表达式

    # 处理 expr 已经是 sympy 表达式对象的情况（例如 _py_func_value 在 arg 为空
    # 时直接返回 sympy 表达式）。对其做下标访问或字符串解析都会出错，
    # 因此这里直接按需求后处理后返回。
    if isinstance(expr, SympyBasic):
        result = radsimp(expr) if is_rationalize else expr
        return result
    # 积木生成代码可能把定积分上下限等作为 int/float 传入，
    # 原逻辑的 expr[0] 下标访问会报错，这里统一转成字符串再解析。
    # 仅扩展输入类型，不改变字符串表达式的既有处理流程。
    if not isinstance(expr, str):
        expr = str(expr)
    if expr == "":  return Symbol("", latex="")
    if expr[0]=="$":
        try:
            expr = _get_latex2sympy()(expr[1:])
        except Exception as e:
            try:
                expr = _preprocess_func_calls(expr, fs)
                expr = sympify_sympy(expr)
            except:
                return "不规范的表达式输入"
    else:
        expr = _preprocess_func_calls(expr, fs)
    try:
        origin_expr = sympify_sympy(expr, locals = locals)
    except SympifyError:
        return "不规范的表达式输入"
    for f in fs.keys():
        if Symbol(f) in origin_expr.free_symbols:
            try:  origin_expr = origin_expr.subs(f, sympify_sympy(fs[f][1], locals = locals))
            except SympifyError:  return "错误的函数定义"
    result = sympify_sympy(simplify(origin_expr), locals = locals) if is_simplify else sympify_sympy(origin_expr, locals = locals)
    if is_rationalize:
        result = radsimp(result)

    return result


def ordered_expr_text(expr, split_eq=False):
    """按表达式的构造顺序（即输入顺序）转成文本。

    SymPy 的 str() 会按 as_ordered_terms() 重新排列 Add 的项，例如把
    x**2/a**2 + y**2/b**2 显示成 y**2/b**2 + x**2/a**2；sstr(order="none")
    沿用 .args 的构造顺序，能保住 MathLive 中用户书写的先后次序。
    split_eq=True 时把等式写成 "lhs = rhs"，供解几页 parse_sympy 保序解析；
    计算器页保持 Eq(...) 形式，避免影响 _safe_sympify 的单表达式解析。
    """
    from sympy import sstr, Eq
    try:
        if split_eq and isinstance(expr, Eq):
            return (sstr(expr.lhs, order="none") + " = "
                    + sstr(expr.rhs, order="none"))
        return sstr(expr, order="none")
    except TypeError:
        return str(expr)