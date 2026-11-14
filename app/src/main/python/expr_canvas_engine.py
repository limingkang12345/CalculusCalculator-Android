# -*- coding: utf-8 -*-
"""解几计算器（表达式画布）安卓端引擎。

复用原项目 expr_calculator/expr_tree.py 的表达式树与 LatexPrinter（分层着色 LaTeX），
把 ui/expr.py -> expr_viewer.MainWindow 的 QWebChannel/Qt 交互改写为 JSON 桥接：
    handle(request_json) -> json
返回的 actions 数组由前端 window.applyCanvasResult 逐条执行（addItem / updateItem /
removeItem / setCanvas / clearSelection）。Qt 对话框以页内 HTML 对话框替代。
"""

import json
import html as html_lib
import traceback

import sympy

from expr_calculator.expr_tree import (
    Add, Div, Eq, Expr, Integer, LatexPrinter, Mul, Point, Pow, Rational,
    Relational, Symbol, from_sympy, parse_sympy,
)


COMMON_EQUATIONS = (
    (
        "圆",
        (
            ("标准方程 (x−a)²+(y−b)²=r²", "(x-({a}))**2+(y-({b}))**2=({r})**2", ("a", "b", "r"), "a、b 为圆心坐标，r 为半径"),
        ),
    ),
    (
        "直线",
        (
            ("一般式 Ax+By+C=0", "({A})*x+({B})*y+({C})=0", ("A", "B", "C"), "A、B 不同时为 0"),
            ("斜截式 y=kx+m", "y=({k})*x+({m})", ("k", "m"), "k 为斜率，m 为纵截距"),
        ),
    ),
    (
        "椭圆",
        (
            ("标准方程 x²/a²+y²/b²=1", "x**2/({a})**2+y**2/({b})**2=1", ("a", "b"), "a 为长半轴，b 为短半轴"),
        ),
    ),
    (
        "双曲线",
        (
            ("横轴 x²/a²−y²/b²=1", "x**2/({a})**2-y**2/({b})**2=1", ("a", "b"), "a 为实半轴，b 为虚半轴"),
            ("纵轴 y²/a²−x²/b²=1", "y**2/({a})**2-x**2/({b})**2=1", ("a", "b"), "a 为实半轴，b 为虚半轴"),
        ),
    ),
    (
        "抛物线",
        (
            ("开口向右 y²=2px", "y**2=2*({p})*x", ("p",), "p 为焦点参数"),
            ("开口向左 y²=−2px", "y**2=-2*({p})*x", ("p",), "p 为焦点参数"),
            ("开口向上 x²=2py", "x**2=2*({p})*y", ("p",), "p 为焦点参数"),
            ("开口向下 x²=−2py", "x**2=-2*({p})*y", ("p",), "p 为焦点参数"),
            ("顶点式 y=a(x−h)²+k", "y=({a})*(x-({h}))**2+({k})", ("a", "h", "k"), "a 为开口系数，顶点为 (h, k)"),
        ),
    ),
)


GENERAL_CONDITIONS = (
    ("通过点", (("x0", "横坐标", "例如 2"), ("y0", "纵坐标", "例如 3")), "曲线经过该点", "通过点 ({x0}, {y0})"),
    ("参数关系", (("relation", "方程", "例如 a=2b"),), "参数之间的关系式", "参数关系 {relation}"),
)

TYPE_CONDITIONS = {
    "直线": (
        ("斜率", (("k", "数值", "例如 2"),), "留空即保留参数 k", "斜率 = {k}"),
        ("截距", (("m", "数值", "例如 -1"),), "在 y 轴上的截距", "截距 = {m}"),
    ),
    "圆": (
        ("圆心所在直线", (("line", "方程", "例如 x=1"),), "圆心 (a, b) 在这条直线上", "圆心在 {line}"),
        ("半径", (("r", "数值", "例如 3"),), "留空即保留参数 r", "半径 = {r}"),
    ),
    "椭圆": (
        ("离心率", (("e", "数值", "例如 1/2"),), "0 < e < 1", "离心率 = {e}"),
        ("长轴长", (("L", "数值", "例如 6"),), "等于 2a", "长轴长 = {L}"),
        ("短轴长", (("S", "数值", "例如 4"),), "等于 2b", "短轴长 = {S}"),
        ("焦距", (("F", "数值", "例如 4"),), "等于 2c，且 c² = a² − b²", "焦距 = {F}"),
    ),
    "双曲线": (
        ("离心率", (("e", "数值", "例如 2"),), "e > 1", "离心率 = {e}"),
        ("实轴长", (("L", "数值", "例如 4"),), "等于 2a", "实轴长 = {L}"),
        ("虚轴长", (("S", "数值", "例如 4"),), "等于 2b", "虚轴长 = {S}"),
        ("焦距", (("F", "数值", "例如 4"),), "等于 2c，且 c² = a² + b²", "焦距 = {F}"),
    ),
    "抛物线": (
        ("准线", (("d", "方程或数值", "例如 x=-2"),), "标准形式下使用", "准线 {d}"),
        ("焦点坐标", (("f", "坐标", "例如 (1, 0)"),), "标准形式下使用", "焦点 {f}"),
    ),
}

STANDARD_PARABOLA_VARIANTS = (0, 1, 2, 3)

def _numeric_value(text: str):
    value = parse_sympy(text.strip())
    if not isinstance(value, sympy.Expr) or value.free_symbols:
        raise ValueError("“" + text.strip() + "”不是有效数值")
    if value.is_real is False:
        raise ValueError("“" + text.strip() + "”不是实数")
    return value


def _coordinate_value(text: str, horizontal: bool):
    cleaned = text.strip().strip("()（）").replace("，", ",")
    parts = [part for part in cleaned.split(",") if part.strip()]
    if not parts:
        raise ValueError("请填写坐标，例如 (1, 0)")
    values = [_numeric_value(part) for part in parts]
    if len(values) == 1:
        return values[0]
    return values[0] if horizontal else values[1]


def _directrix_value(text: str):
    expression = parse_sympy(text.strip())
    if isinstance(expression, sympy.Eq):
        left, right = expression.lhs, expression.rhs
        if left.free_symbols:
            left, right = right, left
        expression = left
    if expression.free_symbols:
        raise ValueError("准线应写成 x=-2 或 y=1 这样的形式")
    return expression


def _normalize_line(expression):
    x, y = sympy.Symbol("x"), sympy.Symbol("y")
    for _round in range(2):
        try:
            polynomial = sympy.Poly(expression, x, y)
        except sympy.PolynomialError:
            return expression
        if polynomial.total_degree() > 1:
            return expression
        coefficients = [item for item in polynomial.coeffs() if item != 0]
        if not coefficients:
            return expression
        factor = coefficients[0]
        for item in coefficients[1:]:
            factor = sympy.gcd(factor, item)
        if factor in (0, 1):
            return expression
        expression = sympy.expand(expression / factor)
    return expression


def _solution_is_real(solution, left, right, protected) -> bool:
    """过滤复参数解与退化解：半轴必须是实数且非零。"""
    for symbol, value in solution.items():
        if value.is_real is False:
            return False
        if symbol.name in protected and value.is_zero is True:
            return False
    for expression in (left, right):
        if expression.has(sympy.I) or expression.has(sympy.zoo) or expression.has(sympy.nan):
            return False
    return True


def _term_degree(term) -> int:
    try:
        return sympy.Poly(term, sympy.Symbol("x"), sympy.Symbol("y")).total_degree()
    except sympy.PolynomialError:
        return 1


def _order_terms(expression):
    """把负项排到后面、高次项排到前面，让解出的方程更接近书写习惯。"""
    if isinstance(expression, sympy.Add):
        terms = [_order_terms(child) for child in expression.args]
        indexed = list(enumerate(terms))
        indexed.sort(key=lambda pair: (
            -_term_degree(pair[1]),
            1 if pair[1].could_extract_minus_sign() else 0,
            0 if sympy.Symbol("x") in pair[1].free_symbols else 1,
            pair[0],
        ))
        return sympy.Add(*[term for _index, term in indexed], evaluate=False)
    if isinstance(expression, sympy.Mul):
        return sympy.Mul(*[_order_terms(child) for child in expression.args], evaluate=False)
    if isinstance(expression, sympy.Pow):
        return sympy.Pow(_order_terms(expression.base), _order_terms(expression.exp), evaluate=False)
    return expression


def _condition_equations(type_name, name, variant, param_names, base_expression, values):
    x, y = sympy.Symbol("x"), sympy.Symbol("y")
    params = {key: sympy.Symbol(key) for key in param_names}
    if name == "通过点":
        point = {x: _numeric_value(values["x0"]), y: _numeric_value(values["y0"])}
        return [base_expression.subs(point)]
    if name == "参数关系":
        expression = parse_sympy(values["relation"].strip())
        if isinstance(expression, sympy.Eq):
            expression = expression.lhs - expression.rhs
        if not isinstance(expression, sympy.Expr):
            raise ValueError("关系式无法解析")
        extra = expression.free_symbols - set(params.values())
        if extra:
            raise ValueError("关系式只能包含参数：" + "、".join(param_names))
        return [expression]
    if name == "斜率":
        value = _numeric_value(values["k"])
        if "k" in params:
            return [params["k"] - value]
        return [-params["A"] - value * params["B"]]
    if name == "截距":
        value = _numeric_value(values["m"])
        if "m" in params:
            return [params["m"] - value]
        return [-params["C"] - value * params["B"]]
    if name == "圆心所在直线":
        line = parse_sympy(values["line"].strip())
        if isinstance(line, sympy.Eq):
            line = line.lhs - line.rhs
        if not isinstance(line, sympy.Expr):
            raise ValueError("直线方程无法解析")
        return [line.subs({x: params["a"], y: params["b"]})]
    if name == "半径":
        value = _numeric_value(values["r"])
        if not value > 0:
            raise ValueError("半径必须是正数")
        return [params["r"] - value]
    if name == "离心率":
        value = _numeric_value(values["e"])
        if type_name == "椭圆":
            if not 0 < value < 1:
                raise ValueError("椭圆的离心率需满足 0 < e < 1")
            return [params["a"] ** 2 * (1 - value ** 2) - params["b"] ** 2]
        if not value > 1:
            raise ValueError("双曲线的离心率需大于 1")
        return [params["a"] ** 2 * (value ** 2 - 1) - params["b"] ** 2]
    if name in ("长轴长", "实轴长"):
        value = _numeric_value(values["L"])
        if not value > 0:
            raise ValueError("轴长必须是正数")
        return [2 * params["a"] - value]
    if name in ("短轴长", "虚轴长"):
        value = _numeric_value(values["S"])
        if not value > 0:
            raise ValueError("轴长必须是正数")
        return [2 * params["b"] - value]
    if name == "焦距":
        value = _numeric_value(values["F"])
        if not value > 0:
            raise ValueError("焦距必须是正数")
        if type_name == "椭圆":
            return [params["a"] ** 2 - params["b"] ** 2 - (value / 2) ** 2]
        return [params["a"] ** 2 + params["b"] ** 2 - (value / 2) ** 2]
    if name == "准线":
        distance = _directrix_value(values["d"])
        sign = -2 if variant in (0, 2) else 2
        return [params["p"] - sign * distance]
    if name == "焦点坐标":
        horizontal = variant in (0, 1)
        value = _coordinate_value(values["f"], horizontal)
        sign = 2 if variant in (0, 2) else -2
        return [params["p"] - sign * value]
    raise ValueError("未知条件：" + name)


def _tidy_expression(expression):
    """把模板解析出的数值项折叠：去掉 0 项、1 系数，并算出数值幂。"""
    if isinstance(expression, sympy.Eq):
        return sympy.Eq(
            _tidy_expression(expression.lhs),
            _tidy_expression(expression.rhs),
            evaluate=False,
        )
    if isinstance(expression, sympy.Add):
        terms = []
        for child in expression.args:
            child = _tidy_expression(child)
            if child.is_number and child == 0:
                continue
            terms.append(child)
        if not terms:
            return sympy.Integer(0)
        if len(terms) == 1:
            return terms[0]
        return sympy.Add(*terms, evaluate=False)
    if isinstance(expression, sympy.Mul):
        coefficient = sympy.Integer(1)
        factors = []
        for child in expression.args:
            child = _tidy_expression(child)
            if child.is_number and child.is_rational:
                coefficient = coefficient * child
                continue
            factors.append(child)
        if coefficient == 0:
            return sympy.Integer(0)
        if coefficient != 1:
            factors.insert(0, coefficient)
        if not factors:
            return sympy.Integer(1)
        if len(factors) == 1:
            return factors[0]
        return sympy.Mul(*factors, evaluate=False)
    if isinstance(expression, sympy.Pow):
        base = _tidy_expression(expression.base)
        exponent = _tidy_expression(expression.exp)
        if base.is_number and exponent.is_number:
            return base ** exponent
        return sympy.Pow(base, exponent, evaluate=False)
    return expression



GEOMETRY_TYPES = (
    (
        "distance",
        "点到直线距离",
        "点 P 到直线的距离",
        (("点 P", "point", "p"), ("直线", "line", "line")),
    ),
    (
        "intersection",
        "两直线交点",
        "两条直线的交点坐标",
        (("直线 1", "line", "line1"), ("直线 2", "line", "line2")),
    ),
    (
        "midpoint",
        "交点线段中点",
        "直线与二次曲线的两个交点为端点的线段中点",
        (("直线", "line", "line"), ("二次曲线", "curve", "curve")),
    ),
    (
        "area3",
        "三角形面积（三点）",
        "三个点围成的三角形面积",
        (("点 P1", "point", "p1"), ("点 P2", "point", "p2"), ("点 P3", "point", "p3")),
    ),
    (
        "area_lc",
        "三角形面积（直线+曲线+点）",
        "直线与曲线的两个交点，再与给定点围成三角形",
        (("直线", "line", "line"), ("二次曲线", "curve", "curve"), ("点 P", "point", "p")),
    ),
)


def _line_expression(text: str):
    expression = parse_sympy(text.strip())
    if isinstance(expression, sympy.Eq):
        expression = expression.lhs - expression.rhs
    if not isinstance(expression, sympy.Expr):
        raise ValueError("直线方程无法解析")
    expression = sympy.expand(expression)
    x, y = sympy.Symbol("x"), sympy.Symbol("y")
    try:
        polynomial = sympy.Poly(expression, x, y)
    except sympy.PolynomialError:
        raise ValueError("直线方程必须是 x、y 的一次式") from None
    if polynomial.total_degree() > 1:
        raise ValueError("直线方程必须是 x、y 的一次式")
    if polynomial.total_degree() == 0:
        raise ValueError("直线方程不能是常数")
    return expression


def _line_coefficients(text: str):
    x, y = sympy.Symbol("x"), sympy.Symbol("y")
    expression = _line_expression(text)
    polynomial = sympy.Poly(expression, x, y)
    return (
        polynomial.coeff_monomial(x),
        polynomial.coeff_monomial(y),
        polynomial.coeff_monomial(1),
    )


def _curve_expression(text: str):
    expression = parse_sympy(text.strip())
    if isinstance(expression, sympy.Eq):
        expression = expression.lhs - expression.rhs
    if not isinstance(expression, sympy.Expr):
        raise ValueError("曲线方程无法解析")
    return sympy.expand(expression)


def _intersections(first, second, x, y):
    try:
        solutions = sympy.solve([first, second], [x, y], dict=True)
    except Exception as exc:
        raise ValueError("求解交点失败：" + str(exc)) from None
    points = []
    seen = set()
    for solution in solutions:
        if x not in solution or y not in solution:
            continue
        key = (sympy.srepr(solution[x]), sympy.srepr(solution[y]))
        if key in seen:
            continue
        seen.add(key)
        points.append((sympy.simplify(solution[x]), sympy.simplify(solution[y])))
    return points


def _point_line_distance(point, line_text: str):
    a, b, c = _line_coefficients(line_text)
    x0, y0 = point
    return sympy.simplify(sympy.Abs(a * x0 + b * y0 + c) / sympy.sqrt(a ** 2 + b ** 2))


def _triangle_area(first, second, third):
    value = (
        first[0] * (second[1] - third[1])
        + second[0] * (third[1] - first[1])
        + third[0] * (first[1] - second[1])
    ) / 2
    return sympy.simplify(sympy.Abs(value))



def _parse_point_text(text: str):
    """把 "(a, b)" 解析成 (x 树, y 树)，不是点则返回 None。"""
    text = text.strip()
    if not (text.startswith("(") and text.endswith(")")):
        return None
    inner = text[1:-1]
    depth = 0
    for index, char in enumerate(inner):
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        elif char == "," and depth == 0:
            left = inner[:index].strip()
            right = inner[index + 1:].strip()
            if not left or not right:
                return None
            try:
                return (
                    from_sympy(parse_sympy(left), ordered=False),
                    from_sympy(parse_sympy(right), ordered=False),
                )
            except Exception:
                return None
    return None


def _format_number(value) -> str:
    if value is sympy.oo:
        return "∞"
    if value is -sympy.oo:
        return "-∞"
    return str(value)


def _format_range(value) -> str:
    if isinstance(value, sympy.Interval):
        left = "(" if value.left_open else "["
        right = ")" if value.right_open else "]"
        return left + _format_number(value.start) + ", " + _format_number(value.end) + right
    if isinstance(value, sympy.Union):
        return " ∪ ".join(_format_range(argument) for argument in value.args)
    if isinstance(value, sympy.FiniteSet):
        if not value.args:
            return "∅"
        return "{" + ", ".join(_format_number(item) for item in value.args) + "}"
    return str(value)


def _finite_solution_roots(solutions):
    """从 solveset 的结果中提取有限个根；无限解集返回 None。"""
    if solutions is sympy.S.EmptySet or solutions == sympy.EmptySet:
        return []
    if getattr(solutions, "is_FiniteSet", False):
        return list(solutions)
    if isinstance(solutions, sympy.Intersection):
        roots = []
        for part in solutions.args:
            if getattr(part, "is_FiniteSet", False):
                roots.extend(list(part))
        return roots
    if isinstance(solutions, sympy.Union):
        roots = []
        for part in solutions.args:
            subset = _finite_solution_roots(part)
            if subset is None:
                return None
            roots.extend(subset)
        return roots
    return None




VARIABLE_PRIORITY = ("x", "y", "z", "t", "u", "v", "w")


def _polynomial(equation):
    value = equation.to_sympy() if hasattr(equation, "to_sympy") else equation
    if isinstance(value, sympy.Equality):
        value = value.lhs - value.rhs
    return sympy.expand(sympy.fraction(sympy.together(value))[0])


def _poly_in(expression, variable):
    try:
        numerator = sympy.fraction(sympy.together(expression))[0]
        return sympy.Poly(sympy.expand(numerator), variable, extension=True)
    except Exception:
        return None


def _factor_candidates(expression, variable):
    candidates = [expression]
    try:
        _coefficient, factors = sympy.factor_list(expression, variable)
        candidates.extend(factor for factor, _power in factors)
    except Exception:
        try:
            _coefficient, factors = sympy.factor_list(expression)
            candidates.extend(factor for factor, _power in factors)
        except Exception:
            pass
    return candidates


def _quadratic_candidates(expressions, variable, other_symbols):
    found, diagnostics = [], []

    def collect(expression, label):
        for candidate in _factor_candidates(expression, variable):
            polynomial = _poly_in(candidate, variable)
            if polynomial is None or polynomial.degree() != 2:
                continue
            coefficients = polynomial.all_coeffs()
            if len(coefficients) != 3 or sympy.simplify(coefficients[0]) == 0:
                continue
            found.append(polynomial)
            return True
        diagnostics.append(label + ": " + str(expression))
        return False

    def collect_resultants(symbols):
        for other in symbols:
            for first in range(len(expressions)):
                for second in range(first + 1, len(expressions)):
                    try:
                        resultant = sympy.simplify(
                            sympy.resultant(expressions[first], expressions[second], other))
                    except Exception:
                        continue
                    if resultant == 0:
                        continue
                    collect(resultant, "消去 " + str(other))

    eliminable = [s for s in other_symbols if s.name in VARIABLE_PRIORITY]
    parameters = [s for s in other_symbols if s.name not in VARIABLE_PRIORITY]
    collect_resultants(eliminable)
    for index, expression in enumerate(expressions, 1):
        collect(expression, "方程 " + str(index))
    collect_resultants(parameters)
    return found, diagnostics


def _build_pair_tree(text, covered, dragged):
    text = str(text or "").strip()
    if not text:
        raise ValueError("请输入含 A、B 的表达式或方程")
    local = {"A": sympy.Symbol("A"), "B": sympy.Symbol("B")}
    try:
        template = from_sympy(parse_sympy(text, local, evaluate=False), ordered=False)
    except Exception:
        raise ValueError("表达式无法解析：只能使用 A、B 和常数")
    names = {node.name for node in template.free_symbols}
    extra = names - {"A", "B"}
    if extra:
        raise ValueError("只能使用 A、B 和常数，不能出现：" + "、".join(sorted(extra)))
    if not names:
        raise ValueError("请输入含 A、B 的表达式或方程")
    result = template.subs(Symbol("A"), covered.copy())
    return result.subs(Symbol("B"), dragged.copy())


def _compute_range_text(tree):
    try:
        expression = tree.to_sympy()
    except Exception:
        return "无法计算"
    if isinstance(expression, sympy.Equality):
        return "方程暂无取值范围"
    symbols = sorted(expression.free_symbols, key=lambda s: s.name)
    if not symbols:
        return str(expression)
    if len(symbols) > 1:
        return "含多个变量，暂不支持"
    if sympy.count_ops(expression) > 60:
        return "表达式较复杂，暂不计算"
    try:
        from sympy.calculus.util import function_range
        value = function_range(expression, symbols[0], sympy.S.Reals)
    except Exception:
        return "无法计算"
    return _format_range(value)


def _common_spec():
    types = []
    for type_name, variants in COMMON_EQUATIONS:
        types.append({
            "name": type_name,
            "variants": [{"label": v[0], "names": list(v[2]), "hint": v[3]} for v in variants],
        })
    conditions = {}
    for type_name, _variants in COMMON_EQUATIONS:
        entries = list(GENERAL_CONDITIONS) + list(TYPE_CONDITIONS.get(type_name, ()))
        conditions[type_name] = [
            {"name": e[0], "fields": [[f[0], f[1], f[2]] for f in e[1]], "hint": e[2]}
            for e in entries
        ]
    return {
        "types": types, "conditions": conditions,
        "standardParabolaVariants": list(STANDARD_PARABOLA_VARIANTS),
    }


def _build_common_equation_trees(type_name, variant_index, method, params, conditions):
    variants = dict((t[0], t[1]) for t in COMMON_EQUATIONS)[type_name]
    _label, template, names, _hint = variants[int(variant_index)]
    if int(method) == 0:
        mapping = {}
        for name in names:
            value = str(params.get(name) or "").strip()
            mapping[name] = value or name
        equation = parse_sympy(template.format(**mapping), evaluate=False)
        if not isinstance(equation, sympy.Eq):
            raise ValueError("生成的不是方程，请检查参数")
        return [from_sympy(_tidy_expression(equation), ordered=False)]
    if not conditions:
        raise ValueError("请至少添加一个条件")
    base = parse_sympy(template.format(**{key: key for key in names}), evaluate=False)
    if not isinstance(base, sympy.Eq):
        raise ValueError("方程形式无法解析")
    equations = []
    for cond in conditions:
        equations.extend(_condition_equations(
            type_name, cond.get("name", ""), int(variant_index), names,
            base.lhs - base.rhs, cond.get("values") or {}))
    unknowns = [sympy.Symbol(key) for key in names]
    try:
        solutions = sympy.solve(equations, unknowns, dict=True)
    except Exception as exc:
        raise ValueError("联立求解失败：" + str(exc))
    if not solutions:
        raise ValueError("这些条件互相矛盾，或不足以确定参数")
    is_general_line = type_name == "直线" and int(variant_index) == 0
    protected = {"a", "b", "r", "p"}
    trees, seen, rejected = [], set(), 0
    for solution in solutions:
        squares = {}
        for symbol, value in solution.items():
            if symbol.name in ("a", "b", "r"):
                squares[sympy.Pow(symbol, 2)] = sympy.simplify(value ** 2)
        left = base.lhs.subs(squares).subs(solution)
        right = base.rhs.subs(squares).subs(solution)
        if not _solution_is_real(solution, left, right, protected):
            rejected += 1
            continue
        if is_general_line:
            left = _normalize_line(left)
        left = _order_terms(left)
        right = _order_terms(right)
        key = sympy.srepr(left) + "|" + sympy.srepr(right)
        if key in seen:
            continue
        seen.add(key)
        equation = _tidy_expression(sympy.Eq(left, right, evaluate=False))
        trees.append(from_sympy(equation, ordered=False))
    if not trees:
        if rejected:
            raise ValueError("这些条件在实数范围内无解：解出的半轴为虚数或为零。")
        raise ValueError("条件没有产生新的方程")
    return trees


def _compute_geometry_tree(kind, fields):
    x, y = sympy.Symbol("x"), sympy.Symbol("y")

    def point(name):
        parsed = _parse_point_text(str(fields.get(name) or ""))
        if parsed is None:
            raise ValueError("点坐标应写成 (a, b)")
        return parsed[0].to_sympy(), parsed[1].to_sympy()

    if kind == "distance":
        return from_sympy(_point_line_distance(point("p"), str(fields.get("line") or "")), ordered=True)
    if kind == "intersection":
        first = _line_expression(str(fields.get("line1") or ""))
        second = _line_expression(str(fields.get("line2") or ""))
        points = _intersections(first, second, x, y)
        if not points:
            raise ValueError("两条直线没有交点（可能平行）")
        return Point(from_sympy(points[0][0], ordered=True), from_sympy(points[0][1], ordered=True))
    if kind == "midpoint":
        line = _line_expression(str(fields.get("line") or ""))
        curve = _curve_expression(str(fields.get("curve") or ""))
        points = _intersections(line, curve, x, y)
        if len(points) != 2:
            raise ValueError("直线与二次曲线应有 2 个交点，实际得到 " + str(len(points)) + " 个")
        middle_x = sympy.simplify((points[0][0] + points[1][0]) / 2)
        middle_y = sympy.simplify((points[0][1] + points[1][1]) / 2)
        return Point(from_sympy(middle_x, ordered=True), from_sympy(middle_y, ordered=True))
    if kind == "area3":
        return from_sympy(_triangle_area(point("p1"), point("p2"), point("p3")), ordered=True)
    if kind == "area_lc":
        line = _line_expression(str(fields.get("line") or ""))
        curve = _curve_expression(str(fields.get("curve") or ""))
        points = _intersections(line, curve, x, y)
        if len(points) != 2:
            raise ValueError("直线与二次曲线应有 2 个交点，实际得到 " + str(len(points)) + " 个")
        return from_sympy(_triangle_area(points[0], points[1], point("p")), ordered=True)
    raise ValueError("未知几何量")


def _geometry_spec(points, equations, expressions):
    return {
        "types": [
            {"key": g[0], "label": g[1], "hint": g[2],
             "fields": [[f[0], f[1], f[2]] for f in g[3]]}
            for g in GEOMETRY_TYPES
        ],
        "points": points, "equations": equations, "expressions": expressions,
    }


class CanvasItem:
    def __init__(self, item_id, tree, x=0.0, y=0.0, note="", collapsed=False, title=""):
        self.item_id = item_id
        self.tree = tree
        self.x = float(x)
        self.y = float(y)
        self.note = note or ""
        self.collapsed = bool(collapsed)
        self.title = title or ""


class CanvasEngine:
    def __init__(self):
        self.items = {}
        self.order = []
        self.infos = {}
        self.maps = {}
        self.next_id = 0
        self.history = []
        self.hist_index = -1
        self.dlg_map = {}
        self.dlg_info = {}
        self.dlg_target = None
        self.dlg_tree = None
        self._push_history()

    def _find(self, item_id):
        return self.items.get(item_id)

    def _node(self, item_id, node_id):
        return self.maps.get(item_id, {}).get(node_id)

    def _new_item(self, tree, note="", x=0.0, y=0.0):
        item_id = "c%d" % self.next_id
        self.next_id += 1
        item = CanvasItem(item_id, tree, x=x, y=y, note=note)
        self.items[item_id] = item
        self.order.append(item_id)
        return item

    def _kind(self, item):
        if isinstance(item.tree, Point):
            return "point"
        if isinstance(item.tree, (Eq, Relational)):
            return "equation"
        return "expression"

    def _item_payload(self, item):
        printer = LatexPrinter(colorize=True, id_prefix=item.item_id + "__")
        colored = printer.doprint(item.tree)
        return colored, printer.node_info, printer.node_map

    def _data(self, item, with_pos=False):
        colored, info, node_map = self._item_payload(item)
        self.infos[item.item_id] = info
        self.maps[item.item_id] = node_map
        data = {
            "id": item.item_id,
            "latex": colored,
            "meta": info,
            "kind": self._kind(item),
            "note": item.note,
            "collapsed": item.collapsed,
            "title": item.title,
        }
        if with_pos:
            data["x"] = item.x
            data["y"] = item.y
        return data

    def _act_add(self, item):
        return {"fn": "addItem", "args": [self._data(item)]}

    def _act_update(self, item, select=None):
        colored, info, node_map = self._item_payload(item)
        self.infos[item.item_id] = info
        self.maps[item.item_id] = node_map
        select_id = None
        if select is not None:
            for key, value in node_map.items():
                if value is select:
                    select_id = key
                    break
        return {
            "fn": "updateItem",
            "args": [item.item_id, colored, info, select_id,
                     self._kind(item), item.note],
        }

    def _act_set_canvas(self):
        payload = [self._data(self.items[i], with_pos=True) for i in self.order]
        return {"fn": "setCanvas", "args": [payload]}

    def _snapshot(self):
        return [
            (i, self.items[i].tree.copy(), self.items[i].x,
             self.items[i].y, self.items[i].note,
             self.items[i].collapsed, self.items[i].title)
            for i in self.order
        ]

    def _push_history(self):
        self.history = self.history[:self.hist_index + 1]
        self.history.append(self._snapshot())
        self.hist_index = len(self.history) - 1

    def _restore_history(self):
        snap = self.history[self.hist_index]
        self.items = {}
        self.order = []
        self.infos = {}
        self.maps = {}
        for entry in snap:
            item_id, tree, x, y, note = entry[:5]
            collapsed = entry[5] if len(entry) > 5 else False
            title = entry[6] if len(entry) > 6 else ""
            self.items[item_id] = CanvasItem(item_id, tree, x, y, note, collapsed, title)
            self.order.append(item_id)

    def _flags(self):
        return {
            "undo": self.hist_index > 0,
            "redo": 0 <= self.hist_index < len(self.history) - 1,
        }

    def _detail(self, item_id, node_id):
        info = self.infos.get(item_id, {}).get(node_id) if node_id else None
        node = self.maps.get(item_id, {}).get(node_id) if node_id else None
        if info is None or node is None:
            return ("未选中节点",
                    "点击画布中的节点，查看其自定义结构与 SymPy 表达式")
        text = info["text"]
        if len(text) > 80:
            text = text[:77] + "..."
        selection = (
            "已选中：<b>" + html_lib.escape(info["type"]) + "</b> · 第 "
            + str(info["depth"]) + " 层 · <span style='color:"
            + info["color"] + "'>" + html_lib.escape(text) + "</span>"
        )
        detail = "节点结构：" + repr(node) + "\nSymPy：" + str(node.to_sympy())
        return selection, detail

    def _node_operation(self, node, method, input_tree):
        if method == "op_replace":
            return input_tree.copy() if input_tree is not None else None
        if method == "op_add":
            return Add(node.copy(), input_tree.copy()) if input_tree is not None else None
        if method == "op_mul":
            return Mul(node.copy(), input_tree.copy()) if input_tree is not None else None
        if method == "op_div":
            return Div(node.copy(), input_tree.copy()) if input_tree is not None else None
        if method == "op_pow":
            return Pow(node.copy(), input_tree.copy()) if input_tree is not None else None
        if method == "op_recip":
            return Div(Integer(1), node.copy())
        if method == "op_square":
            return Pow(node.copy(), Integer(2))
        if method == "op_sqrt":
            return Pow(node.copy(), Rational(1, 2))
        return None

    def _replace_node(self, item, node, new):
        parent = node.parent
        if parent is None:
            item.tree = new
            return new
        index = next((i for i, child in enumerate(parent.args) if child is node), None)
        if index is None:
            return None
        if isinstance(parent, Add) and isinstance(new, Add):
            parent.remove(index)
            for offset, term in enumerate(new.args):
                parent.insert(index + offset, term)
            item.tree = parent.root
            return parent
        if isinstance(parent, Mul) and isinstance(new, Mul):
            parent.remove(index)
            for offset, factor in enumerate(new.args):
                parent.insert(index + offset, factor)
            item.tree = parent.root
            return parent
        target = node.replace_with(new)
        item.tree = target.root
        return target

    def _is_zero(self, expr):
        try:
            value = getattr(expr, "is_zero", False)
            return bool(value) if not callable(value) else False
        except Exception:
            return False

    def _dialog_operation(self, node, op, dragged, raw_source):
        if op in ("div", "op_div", "div_mul", "div_div") and self._is_zero(raw_source):
            raise ZeroDivisionError("zero")
        if op in ("replace", "op_replace"):
            return dragged
        if op in ("add", "op_add"):
            return Add(node.copy(), dragged)
        if op == "sub":
            return Add(node.copy(), Mul(Integer(-1), dragged))
        if op in ("mul", "op_mul"):
            return Mul(node.copy(), dragged)
        if op in ("div", "op_div"):
            return Div(node.copy(), dragged)
        if op in ("pow", "op_pow"):
            return Pow(node.copy(), dragged)
        if op == "div_mul":
            if not isinstance(node, Div):
                return None
            return Div(Mul(node.numerator.copy(), dragged),
                       Mul(node.denominator.copy(), raw_source.copy()))
        if op == "div_div":
            if not isinstance(node, Div):
                return None
            return Div(Div(node.numerator.copy(), dragged),
                       Div(node.denominator.copy(), raw_source.copy()))
        if op == "op_recip":
            return Div(Integer(1), node.copy())
        if op == "op_square":
            return Pow(node.copy(), Integer(2))
        if op == "op_sqrt":
            return Pow(node.copy(), Rational(1, 2))
        return None

    def _finite_roots(self, sol):
        if isinstance(sol, sympy.FiniteSet):
            return list(sol)
        if getattr(sol, "is_EmptySet", False) or sol == sympy.S.EmptySet:
            return []
        roots = []
        try:
            for part in getattr(sol, "args", []):
                if isinstance(part, sympy.FiniteSet):
                    roots.extend(list(part))
        except Exception:
            pass
        return roots

    def _eq_to_expr(self, tree):
        try:
            expr = tree.to_sympy() if hasattr(tree, "to_sympy") else tree
        except Exception:
            return None
        if isinstance(expr, sympy.Equality):
            expr = expr.lhs - expr.rhs
        if not isinstance(expr, sympy.Basic):
            return None
        try:
            return sympy.expand(expr)
        except Exception:
            return None

    def _poly_degree(self, expr, var):
        try:
            return sympy.Poly(expr, var).degree()
        except Exception:
            return -1

    def _vieta_cards(self, eq1, eq2, variables, outputs=None):
        variable = sympy.Symbol(variables[0] if variables else "x")
        names = set()
        for eq in (eq1, eq2):
            try:
                names.update(s.name for s in eq.to_sympy().free_symbols)
            except Exception:
                pass
        names.discard(variable.name)
        other_symbols = [sympy.Symbol(n) for n in sorted(names)]
        try:
            expressions = [_polynomial(eq) for eq in (eq1, eq2)]
            polynomials, diagnostics = _quadratic_candidates(
                expressions, variable, other_symbols)
        except Exception as exc:
            self._vieta_diagnostics = ["消元失败：" + str(exc)]
            return []
        self._vieta_diagnostics = diagnostics
        if not polynomials:
            return []
        coefficients = polynomials[0].all_coeffs()
        if len(coefficients) != 3:
            return []
        a, b, c = coefficients
        try:
            sum_value = sympy.simplify(-b / a)
            product_value = sympy.simplify(c / a)
        except Exception:
            return []
        try:
            discriminant = sympy.simplify(b ** 2 - 4 * a * c)
        except Exception:
            discriminant = b ** 2 - 4 * a * c
        wanted = outputs or ["sum", "product"]
        cards = []
        if "sum" in wanted:
            cards.append((from_sympy(sum_value, ordered=True), "韦达定理：两根之和 = -b/a"))
        if "product" in wanted:
            cards.append((from_sympy(product_value, ordered=True), "韦达定理：两根之积 = c/a"))
        if "abs" in wanted:
            distance = sympy.simplify(sympy.sqrt(discriminant) / sympy.Abs(a))
            cards.append((from_sympy(distance, ordered=True), "韦达定理：|x₁ − x₂|"))
        if "delta" in wanted:
            cards.append((from_sympy(discriminant, ordered=True), "韦达定理：判别式 Δ"))
        return cards

    def _geometry_sources(self):
        points, equations, expressions = [], [], []
        for item_id in self.order:
            item = self.items[item_id]
            if isinstance(item.tree, Point):
                text = "(" + str(item.tree.x) + ", " + str(item.tree.y) + ")"
                if text not in points:
                    points.append(text)
                continue
            text = str(item.tree)
            if isinstance(item.tree, (Eq, Relational)):
                if text not in equations:
                    equations.append(text)
            elif text not in expressions:
                expressions.append(text)
        return points, equations, expressions

    def _node_path(self, node):
        path = []
        current = node
        while current.parent is not None:
            path.append(current.index_in_parent)
            current = current.parent
        path.reverse()
        return path

    def _node_at(self, tree, path):
        current = tree
        for index in path:
            current = current.args[index]
        return current

    def _apply_substitution(self, item, input_tree, replace_tree, as_copy, out):
        if not isinstance(input_tree, Symbol):
            return "请只输入一个换元符号，例如 t"
        if replace_tree is None:
            return "请填写换元式，例如 x+1"
        name = input_tree.name
        card_names = {s.name for s in item.tree.free_symbols}
        candidates = sorted({s.name for s in replace_tree.free_symbols} & card_names)
        if not candidates:
            return "换元式里的变量没有出现在表达式中"
        if len(candidates) > 1:
            return "换元式只能包含一个变量，例如 x+1"
        variable_name = candidates[0]
        if name in card_names - {variable_name}:
            return "符号 " + name + " 已在表达式中使用，请换一个符号"
        variable = sympy.Symbol(variable_name)
        try:
            solutions = sympy.solve(
                sympy.Eq(sympy.Symbol(name), replace_tree.to_sympy()), variable, dict=True)
        except Exception as exc:
            return "解换元式失败：" + str(exc)
        if not solutions:
            return "无法从换元式解出 " + variable_name
        if len(solutions) > 1:
            return "换元式对 " + variable_name + " 有多组解（如平方），暂不支持"
        replacement = from_sympy(solutions[0][variable], ordered=True)
        base_tree = item.tree.copy() if as_copy else item.tree
        substituted = base_tree.subs(Symbol(variable_name), replacement)
        try:
            substituted = from_sympy(sympy.expand(substituted.to_sympy()), ordered=True)
        except Exception:
            pass
        definition = name + " = " + str(replace_tree)
        if len(definition) > 34:
            definition = definition[:32] + "…"
        note = (item.note + "；" + definition) if item.note else definition
        if as_copy:
            new = self._new_item(substituted, note=note)
            new.title = item.title
            out["actions"].append(self._act_add(new))
            self._push_history()
            out["status"] = "已换元并保存副本：" + definition
            return None
        item.tree = substituted
        item.note = note
        out["actions"].append(self._act_update(item))
        self._push_history()
        out["status"] = "已换元：" + definition
        return None

    def handle(self, request_json):
        out = {"actions": []}
        try:
            req = json.loads(request_json)
            action = req.get("action", "")
            args = req.get("args", []) or []
            self._run(action, req, args, out)
        except Exception as exc:
            out["error"] = "%s\n%s" % (exc, traceback.format_exc()[-400:])
        out["count"] = "%d 个表达式" % len(self.order)
        out.update(self._flags())
        return json.dumps(out, ensure_ascii=False)

    def _run(self, action, req, args, out):
        if action == "commonEquationSpec":
            out["dialog"] = {
                "kind": "commonEquation", "title": "常用方程",
                "action": "applyCommonEquation", "args": [], "spec": _common_spec(),
            }
            return
        if action == "applyCommonEquation":
            try:
                trees = _build_common_equation_trees(
                    req.get("type") or "圆", req.get("variant", 0),
                    req.get("method", 0), req.get("params") or {},
                    req.get("conditions") or [])
            except Exception as exc:
                out["error"] = "无法生成方程：" + str(exc)
                return
            for tree in trees:
                item = self._new_item(tree)
                out["actions"].append(self._act_add(item))
            self._push_history()
            out["status"] = "已添加 %d 张常用方程卡片" % len(trees)
            return
        if action == "geometrySpec":
            points, equations, expressions = self._geometry_sources()
            out["dialog"] = {
                "kind": "geometry", "title": "几何计算",
                "action": "applyGeometry", "args": [],
                "spec": _geometry_spec(points, equations, expressions),
            }
            return
        if action == "applyGeometry":
            try:
                tree = _compute_geometry_tree(
                    req.get("type") or req.get("geometryType") or "distance",
                    req.get("fields") or {})
            except Exception as exc:
                out["error"] = "无法计算：" + str(exc)
                return
            item = self._new_item(tree)
            out["actions"].append(self._act_add(item))
            self._push_history()
            out["status"] = "已添加" + ("点" if isinstance(tree, Point) else "几何表达式")
            return
        if action == "openExpressionPair":
            first, second = self._find(args[0]), self._find(args[1])
            if first is None or second is None:
                out["error"] = "卡片已失效"
                return
            if isinstance(first.tree, (Eq, Point, Relational)) or isinstance(second.tree, (Eq, Point, Relational)):
                out["error"] = "组合表达式需要两张非方程、非点的卡片"
                return
            out["dialog"] = {
                "kind": "expressionPair", "title": "组合表达式",
                "action": "applyExpressionPair", "args": [args[0], args[1]],
                "textA": str(second.tree), "textB": str(first.tree),
            }
            return
        if action == "applyExpressionPair":
            first, second = self._find(args[0]), self._find(args[1])
            if first is None or second is None:
                out["error"] = "卡片已失效"
                return
            try:
                tree = _build_pair_tree(req.get("template") or "", second.tree, first.tree)
            except Exception as exc:
                out["error"] = str(exc)
                return
            item = self._new_item(tree)
            out["actions"].append(self._act_add(item))
            self._push_history()
            out["status"] = "已用 A、B 组合生成新卡片"
            return
        if action == "setCollapsed":
            item = self._find(args[0]) if args else None
            if item:
                item.collapsed = bool(req.get("collapsed"))
            return
        if action == "setTitle":
            item = self._find(args[0]) if args else None
            if item:
                item.title = str(req.get("title") or "")
            return
        if action == "selectCard":
            item = self._find(args[0]) if args else None
            if item:
                out["properties"] = {
                    "id": item.item_id, "kind": self._kind(item),
                    "text": str(item.tree), "note": item.note,
                    "title": item.title, "range": _compute_range_text(item.tree),
                }
            return
        if action == "dropNodeOnCanvas":
            source = self._node(args[0], args[1]) if len(args) > 1 else None
            if source is None:
                out["error"] = "节点已失效"
                return
            x = float(args[2]) if len(args) > 2 else 0.0
            y = float(args[3]) if len(args) > 3 else 0.0
            item = self._new_item(source.copy(), x=x, y=y)
            out["actions"].append({"fn": "addItem", "args": [self._data(item, with_pos=True)]})
            self._push_history()
            out["status"] = "已用选中部分生成新卡片"
            return
        if action == "latexToExpr":
            latex = (req.get("latex") or "").strip()
            if not latex:
                out["expr"] = ""
                out["status"] = "公式为空"
                return
            try:
                from core.sympify import sympify, ordered_expr_text
                expr = sympify("$" + latex, {})
                if isinstance(expr, sympy.Basic):
                    out["expr"] = ordered_expr_text(expr, split_eq=True)
                    out["status"] = "公式已转换为表达式"
                else:
                    out["error"] = "公式无法解析：%s" % expr
                    out["expr"] = latex
            except Exception as exc:
                out["error"] = "公式转换失败：%s" % exc
                out["expr"] = latex
            return
        if action == "add":
            text = (req.get("expr") or (args[0] if args else "") or "").strip()
            if not text:
                out["error"] = "请输入表达式"
                return
            tree = from_sympy(parse_sympy(text), ordered=False)
            item = self._new_item(tree)
            out["actions"].append(self._act_add(item))
            self._push_history()
            out["status"] = "已添加：" + text

        elif action == "select":
            item_id = args[0] if len(args) > 0 else ""
            node_id = args[1] if len(args) > 1 else ""
            out["selection"], out["detail"] = self._detail(item_id, node_id)

        elif action == "clear":
            out["selection"] = "未选中节点"
            out["detail"] = "点击画布中的节点，查看其自定义结构与 SymPy 表达式"

        elif action in ("placeItem", "moveItem"):
            item = self._find(args[0]) if len(args) > 0 else None
            if item and len(args) > 2:
                item.x = float(args[1])
                item.y = float(args[2])
            if action == "moveItem":
                self._push_history()

        elif action == "swap":
            item = self._find(args[0])
            node = self._node(args[0], args[1])
            index = int(args[2])
            if item is None or not isinstance(node, Add):
                return
            if index < 0 or index + 1 >= len(node.args):
                return
            node.swap(index, index + 1)
            item.tree = node.root
            out["actions"].append(self._act_update(item, select=node))
            self._push_history()
            out["status"] = "已交换相邻项"

        elif action == "expand":
            item = self._find(args[0])
            node = self._node(args[0], args[1])
            if item is None or not isinstance(node, Add):
                return
            parent = node.parent
            if isinstance(parent, Mul):
                index = next((i for i, child in enumerate(parent.args) if child is node), None)
                if index is None:
                    return
                expanded = parent.expand(index)
            elif isinstance(parent, Pow):
                expanded = parent.expand()
            else:
                return
            grand = parent.parent
            if isinstance(grand, Add) and isinstance(expanded, Add):
                position = next((i for i, child in enumerate(grand.args) if child is parent), None)
                if position is None:
                    return
                grand.remove(position)
                for offset, term in enumerate(expanded.args):
                    grand.insert(position + offset, term)
                item.tree = grand.root
                out["actions"].append(self._act_update(item, select=grand))
            elif grand is None:
                item.tree = expanded
                out["actions"].append(self._act_update(item, select=expanded))
            else:
                target = parent.replace_with(expanded)
                item.tree = target.root
                out["actions"].append(self._act_update(item, select=target))
            self._push_history()
            out["status"] = "已展开括号"

        elif action == "copyItem":
            item = self._find(args[0])
            if item is None:
                return
            new = self._new_item(item.tree.copy(), note=item.note)
            out["actions"].append(self._act_add(new))
            self._push_history()
            out["status"] = "已复制卡片"

        elif action == "deleteItem":
            item_id = args[0]
            if item_id not in self.items:
                return
            del self.items[item_id]
            self.order = [i for i in self.order if i != item_id]
            self.infos.pop(item_id, None)
            self.maps.pop(item_id, None)
            out["actions"].append({"fn": "removeItem", "args": [item_id]})
            out["actions"].append({"fn": "clearSelection", "args": [False]})
            out["selection"] = "未选中节点"
            out["detail"] = "点击画布中的节点，查看其自定义结构与 SymPy 表达式"
            self._push_history()
            out["status"] = "已删除卡片"

        elif action == "transform":
            item_id, node_id = args[0], args[1]
            node = self._node(item_id, node_id)
            info = self.infos.get(item_id, {}).get(node_id, {})
            if node is None:
                out["error"] = "节点已失效，请重新点击"
                return
            if isinstance(node, Eq):
                free = sorted(str(s) for s in node.to_sympy().free_symbols)
                out["dialog"] = {
                    "kind": "solve", "title": "求解方程", "action": "applySolve",
                    "args": [item_id, node_id], "nodeText": str(node),
                    "var": free[0] if free else "x",
                }
            else:
                out["dialog"] = {
                    "kind": "transform", "title": "变形 / 节点操作",
                    "action": "applyTransform", "args": [item_id, node_id],
                    "nodeText": str(node), "nodeType": info.get("type", ""),
                    "depth": info.get("depth", 0),
                }

        elif action == "applyTransform":
            item_id, node_id = args[0], args[1]
            item = self._find(item_id)
            node = self._node(item_id, node_id)
            method = req.get("method", "simplify")
            text = (req.get("input") or "").strip()
            replace_text = (req.get("replace") or "").strip()
            as_copy = bool(req.get("as_copy"))
            if item is None or node is None:
                out["error"] = "节点已失效，请重新点击"
                return
            if method == "op_subs":
                try:
                    input_tree = from_sympy(parse_sympy(text), ordered=False) if text else None
                    replace_tree = from_sympy(parse_sympy(replace_text), ordered=False) if replace_text else None
                except Exception as exc:
                    out["error"] = "换元输入无法解析：" + str(exc)
                    return
                error = self._apply_substitution(item, input_tree, replace_tree, as_copy, out)
                if error:
                    out["error"] = error
                return
            try:
                if method.startswith("op_"):
                    input_tree = from_sympy(parse_sympy(text), ordered=False) if text else None
                    transformed = self._node_operation(node, method, input_tree)
                else:
                    func = getattr(sympy, method, None)
                    if func is None:
                        raise ValueError("未知变形：" + method)
                    transformed = from_sympy(func(node.to_sympy()), ordered=True)
            except Exception as exc:
                out["error"] = "变形失败：" + str(exc)
                return
            if transformed is None:
                out["error"] = "该操作需要填写输入表达式"
                return
            if as_copy:
                copy_item = CanvasItem(item.item_id, item.tree.copy(), item.x, item.y,
                                       item.note, item.collapsed, item.title)
                try:
                    copy_node = self._node_at(copy_item.tree, self._node_path(node))
                except Exception:
                    copy_node = None
                if copy_node is None or self._replace_node(copy_item, copy_node, transformed) is None:
                    out["error"] = "节点已失效"
                    return
                new = self._new_item(copy_item.tree, note=item.note)
                new.title = item.title
                out["actions"].append(self._act_add(new))
                self._push_history()
                out["status"] = "已保存为副本"
                return
            target = self._replace_node(item, node, transformed)
            if target is None:
                out["error"] = "节点已失效"
                return
            out["actions"].append(self._act_update(item, select=target))
            self._push_history()
            out["status"] = "已变形：" + method

        elif action == "applySolve":
            item_id, node_id = args[0], args[1]
            node = self._node(item_id, node_id)
            if node is None:
                out["error"] = "方程节点已失效"
                return
            variable = (req.get("var") or "x").strip() or "x"
            domain_name = req.get("domain", "Reals")
            domain = {
                "Reals": sympy.S.Reals,
                "Complexes": sympy.S.Complexes,
                "Integers": sympy.S.Integers,
            }.get(domain_name, sympy.S.Reals)
            roots = _finite_solution_roots(
                sympy.solveset(node.to_sympy(), sympy.Symbol(variable), domain))
            if roots is None:
                roots = []
            if not roots:
                out["error"] = "未找到有限个根（或解集为无限集）"
                return
            for root in roots:
                new = self._new_item(from_sympy(root, ordered=True))
                out["actions"].append(self._act_add(new))
            self._push_history()
            out["status"] = "已生成 %d 个根卡片" % len(roots)

        elif action == "openSystem":
            first, second = self._find(args[0]), self._find(args[1])
            if first is None or second is None:
                return
            if not isinstance(first.tree, Eq) or not isinstance(second.tree, Eq):
                out["error"] = "联立需要两张方程卡片"
                return
            free1 = first.tree.to_sympy().free_symbols
            free2 = second.tree.to_sympy().free_symbols

            def var_key(name):
                return (0 if name in ("x", "y", "z") else 1, name)

            shared = sorted((str(s) for s in (free1 & free2)), key=var_key)
            free = sorted((str(s) for s in (free1 | free2)), key=var_key)
            default_vars = ",".join(shared or free) if (shared or free) else "x,y"
            out["dialog"] = {
                "kind": "system", "title": "方程联立", "action": "applySystem",
                "args": [args[0], args[1]],
                "text": str(first.tree) + "  ，  " + str(second.tree),
                "vars": default_vars,
                "varsList": (shared or free) or ["x", "y"],
                "outputs": ["sum", "product"],
            }

        elif action == "applySystem":
            first, second = self._find(args[0]), self._find(args[1])
            if first is None or second is None:
                out["error"] = "卡片已失效"
                return
            variables = [v.strip() for v in (req.get("vars") or "x,y").split(",") if v.strip()]
            mode = req.get("mode", "solve")
            cards = []
            if mode == "vieta":
                cards = self._vieta_cards(
                    first.tree, second.tree, variables,
                    req.get("outputs") or ["sum", "product"])
            else:
                equations = [first.tree.to_sympy(), second.tree.to_sympy()]
                symbols = [sympy.Symbol(v) for v in variables]
                for solution in sympy.solve(equations, symbols, dict=True):
                    for key, value in solution.items():
                        cards.append((
                            from_sympy(sympy.Eq(key, value), ordered=True),
                            "联立解：" + str(key),
                        ))
            if not cards:
                if mode == "vieta":
                    detail = "；".join(getattr(self, "_vieta_diagnostics", [])[:3])
                    out["error"] = ("未得到关于 %s 的一元二次方程：请把未知量只保留一个变量，"
                                    "或改用「直接求解方程组」%s"
                                    % (variables[0] if variables else "x",
                                       ("（" + detail + "）") if detail else ""))
                else:
                    out["error"] = "方程组未得到有限解"
                return
            for tree, note in cards:
                new = self._new_item(tree, note=note)
                out["actions"].append(self._act_add(new))
            self._push_history()
            out["status"] = "已添加 %d 张结果卡片" % len(cards)

        elif action == "dropNode":
            source_id, node_id, target_id = args[0], args[1], args[2]
            source = self._node(source_id, node_id)
            item = self._find(target_id)
            if source is None or item is None:
                out["error"] = "节点或卡片已失效"
                return
            printer = LatexPrinter(colorize=True, id_prefix="dlg__")
            colored = printer.doprint(item.tree)
            self.dlg_map = printer.node_map
            self.dlg_info = printer.node_info
            self.dlg_target = target_id
            self.dlg_tree = item.tree
            src_text = str(source)
            if len(src_text) > 60:
                src_text = src_text[:57] + "..."
            out["dialog"] = {
                "kind": "nodeOp", "title": "重叠的表达式", "action": "applyNodeOp",
                "args": [source_id, node_id, target_id],
                "latex": colored, "info": printer.node_info,
                "nodeText": src_text, "nodeType": type(source).__name__,
                "targetText": str(item.tree), "nodeZero": self._is_zero(source),
            }

        elif action == "applyNodeOp":
            source_id, node_id, target_id = args[0], args[1], args[2]
            source = self._node(source_id, node_id)
            item = self._find(target_id)
            if source is None or item is None:
                out["error"] = "节点或卡片已失效"
                return
            op = req.get("op", "add")
            dialog_node_id = req.get("target_node_id") or ""
            node = None
            if (dialog_node_id and self.dlg_target == target_id
                    and self.dlg_tree is item.tree):
                node = self.dlg_map.get(dialog_node_id)
            if node is None:
                node = item.tree
            dragged = source.copy()
            try:
                new = self._dialog_operation(node, op, dragged, source)
            except ZeroDivisionError:
                out["error"] = "拖拽节点为零，不能作为除数或乘数"
                return
            except Exception as exc:
                out["error"] = "无法执行：%s" % exc
                return
            if new is None:
                out["error"] = "所选节点不支持该操作：%s" % op
                return
            if self._replace_node(item, node, new) is None:
                out["error"] = "节点已失效，请重新拖拽"
                return
            out["actions"].append(self._act_update(item))
            out["actions"].append({"fn": "clearSelection", "args": [False]})
            self._push_history()
            out["status"] = "已应用节点操作"
            self.dlg_map = {}
            self.dlg_info = {}
            self.dlg_target = None
            self.dlg_tree = None

        elif action in ("undo", "redo"):
            if action == "undo" and self.hist_index > 0:
                self.hist_index -= 1
            elif action == "redo" and self.hist_index < len(self.history) - 1:
                self.hist_index += 1
            else:
                return
            self._restore_history()
            out["actions"].append(self._act_set_canvas())
            out["actions"].append({"fn": "clearSelection", "args": [False]})
            out["selection"] = "未选中节点"
            out["detail"] = "点击画布中的节点，查看其自定义结构与 SymPy 表达式"
            out["status"] = "已撤销" if action == "undo" else "已重做"

        else:
            out["error"] = "未知操作：" + action


_engine = CanvasEngine()


def handle(request_json):
    return _engine.handle(request_json)
