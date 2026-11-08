# -*- coding: utf-8 -*-
"""功能集成页后端：定义区 / 计算区 / 绘图区。"""

import json
import io
import base64

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import rc_context

import sympy
from sympy import Eq, Rel, Symbol, latex, radsimp, simplify

from core.sympify import sympify
from functions import planes as planes_mod
from functions import solids as solids_mod
from functions.derivative import derivative
from functions.integral import integral
from functions.simplification import simplifies
from functions.solvers import (
    solve_fangcheng, solve_budengshi, solve_fangchengzu,
    solve_budengshizu, solve_sanjiaoxing,
)
from functions.paint2D import draw2d, draw_functions
from functions.paint3D import draw3d


CALC_FUNCTION_NAMES = ["计算", "求导", "积分", "解方程", "解不等式", "解方程组",
                       "解不等式组", "平面计算", "立体计算", "变形", "解三角形"]
DEF_TYPE_NAMES = ["函数", "集合", "向量", "平面几何", "立体几何"]
CALC_ENGINE_NAMES = ["Python内置引擎", "Mpmath高精度引擎", "Sympy符号引擎", "Latex代码生成引擎"]
TRANSFORM_NAMES = [
    "通用化简(simplify)", "展开(expand)", "因式分解(factor)", "主元(collect)",
    "通分(cancel)", "分离(apart)", "三角变换(trigsimp)", "三角展开(expand_trig)",
    "指数合并(powsimp)", "指数展开(expand_power_exp)", "对数展开(expand_log)",
    "对数合并(logcombine)", "换元",
]
TRIANGLE_PARTS = ["未选择", "角A", "角B", "角C", "边a", "边b", "边c"]
TRIANGLE_KEYS = ["", "A", "B", "C", "a", "b", "c"]
DRAW_MODE_NAMES = ["平面几何模式", "立体几何模式", "函数模式"]
TRANSFORM_PIVOT = 3
TRANSFORM_SUBST = 12

VALUE = "value"
SELECT = "select"
QUANTITY = "quantity"
POINT = "point"
LINE = "line"
SEGMENT = "segment"
TRIANGLE = "triangle"
CIRCLE = "circle"
PLANE = "plane"
INTEGER = "integer"

ROLE_CATEGORY = {
    POINT: "点", LINE: "直线", SEGMENT: "线段", TRIANGLE: "三角形",
    CIRCLE: "圆", PLANE: "平面",
}
NAME_PREFIX = {
    "点": "p", "直线": "l", "线段": "s", "三角形": "t",
    "圆": "c", "多边形": "poly", "平面": "pl",
}

PLANE_GEOMETRY = {
    "点": [
        ("按坐标创建", [("x坐标", "0", VALUE), ("y坐标", "0", VALUE)], "点", "create_point"),
    ],
    "直线": [
        ("两点创建", [("点1名称", "", POINT), ("点2名称", "", POINT)], "直线", "create_line"),
        ("线段的垂直平分线", [("线段名称", "", SEGMENT)], "直线", "perpendicular_bisector"),
        ("过点作平行线", [("直线名称", "", LINE), ("点名称", "", POINT)], "直线", "line_parallel_through_point"),
        ("过点作垂线", [("直线名称", "", LINE), ("点名称", "", POINT)], "直线", "line_perpendicular_through_point"),
        ("两直线的角平分线", [("直线1名称", "", LINE), ("直线2名称", "", LINE)], "直线", "angle_bisector_line"),
        ("角的平分线", [("点1名称", "", POINT), ("顶点名称", "", POINT), ("点3名称", "", POINT)], "直线", "angle_bisector"),
        ("三角形的高线", [("三角形名称", "", TRIANGLE), ("顶点索引", "0", INTEGER)], "直线", "triangle_altitude"),
    ],
    "线段": [
        ("两点创建", [("点1名称", "", POINT), ("点2名称", "", POINT)], "线段", "segment_from_points"),
        ("三角形的中线", [("三角形名称", "", TRIANGLE), ("顶点索引", "0", INTEGER)], "线段", "triangle_median"),
        ("三角形的中位线", [("三角形名称", "", TRIANGLE)], "线段", "triangle_midsegment"),
    ],
    "三角形": [
        ("三点创建", [("点1名称", "", POINT), ("点2名称", "", POINT), ("点3名称", "", POINT)], "三角形", "create_triangle"),
    ],
    "多边形": [
        ("顶点依次创建", [("顶点数", 3, QUANTITY), ("顶点{}名称", "", POINT)], "多边形", "create_polygon"),
    ],
    "圆": [
        ("圆心与半径", [("圆心名称", "", POINT), ("半径", "1", VALUE)], "圆", "create_circle"),
        ("三点定圆", [("点1名称", "", POINT), ("点2名称", "", POINT), ("点3名称", "", POINT)], "圆", "create_circle_three_points"),
        ("以两点为直径", [("点1名称", "", POINT), ("点2名称", "", POINT)], "圆", "circle_with_diameter"),
        ("圆心与圆上一点", [("圆心名称", "", POINT), ("圆上点名称", "", POINT)], "圆", "circle_by_center_and_point"),
        ("三角形的内切圆", [("三角形名称", "", TRIANGLE)], "圆", "triangle_incircle"),
        ("三角形的旁切圆", [("三角形名称", "", TRIANGLE), ("顶点索引", "0", INTEGER)], "圆", "triangle_excircle"),
    ],
}

SOLID_GEOMETRY = {
    "点": [
        ("按坐标创建", [("x坐标", "0", VALUE), ("y坐标", "0", VALUE), ("z坐标", "0", VALUE)], "点", "create_point3d"),
        ("点到平面的垂足", [("点名称", "", POINT), ("平面名称", "", PLANE)], "点", "perpendicular_foot_to_plane"),
        ("点到直线的垂足", [("点名称", "", POINT), ("直线名称", "", LINE)], "点", "perpendicular_foot_to_line_3d"),
    ],
    "直线": [
        ("两点创建", [("点1名称", "", POINT), ("点2名称", "", POINT)], "直线", "create_line3d"),
        ("过点作平行线", [("直线名称", "", LINE), ("点名称", "", POINT)], "直线", "line_parallel_through_point_3d"),
        ("过点作已知直线的垂线", [("点名称", "", POINT), ("直线名称", "", LINE)], "直线", "perpendicular_line_from_point"),
        ("过点作平面的垂线", [("平面名称", "", PLANE), ("点名称", "", POINT)], "直线", "line_perpendicular_to_plane_through_point"),
    ],
    "平面": [
        ("三点创建", [("点1名称", "", POINT), ("点2名称", "", POINT), ("点3名称", "", POINT)], "平面", "create_plane_three_points"),
        ("一点与法向量", [("点名称", "", POINT), ("法向量x", "1", VALUE), ("法向量y", "1", VALUE), ("法向量z", "1", VALUE)], "平面", "create_plane_point_normal"),
        ("过直线与点", [("直线名称", "", LINE), ("点名称", "", POINT)], "平面", "plane_through_line_and_point"),
        ("过两条直线", [("直线1名称", "", LINE), ("直线2名称", "", LINE)], "平面", "plane_through_two_lines"),
        ("过点作平行平面", [("平面名称", "", PLANE), ("点名称", "", POINT)], "平面", "plane_parallel_through_point"),
        ("过点作垂直于直线的平面", [("直线名称", "", LINE), ("点名称", "", POINT)], "平面", "plane_perpendicular_to_line_through_point"),
    ],
    "线段": [
        ("两点创建", [("点1名称", "", POINT), ("点2名称", "", POINT)], "线段", "segment3d_from_points"),
    ],
}

GEOMETRY = {"plane": PLANE_GEOMETRY, "solid": SOLID_GEOMETRY}
_NEEDS_FS = {"create_point", "create_circle", "create_point3d", "create_plane_point_normal"}

PLANE_OPS = {
    "点": [
        ("两点距离", "point_distance", [("点1名称", "", POINT), ("点2名称", "", POINT)]),
        ("中点坐标", "midpoint", [("点1名称", "", POINT), ("点2名称", "", POINT)]),
        ("共线判断", "collinear_check", [("点数", 3, QUANTITY), ("点{}名称", "", POINT)]),
        ("平移点", "translate_point", [("点名称", "", POINT), ("x位移", "0", VALUE), ("y位移", "0", VALUE)]),
        ("绕定点旋转", "rotate_point", [("点名称", "", POINT), ("旋转角", "0", VALUE), ("旋转中心名称", "", POINT)]),
        ("点关于直线反射", "reflect_point", [("点名称", "", POINT), ("直线名称", "", LINE)]),
    ],
    "直线": [
        ("直线方程", "line_equation", [("点1名称", "", POINT), ("点2名称", "", POINT)]),
        ("直线斜率", "line_slope", [("点1名称", "", POINT), ("点2名称", "", POINT)]),
        ("两直线交点", "line_intersection", [("直线1名称", "", LINE), ("直线2名称", "", LINE)]),
        ("点到直线距离", "point_to_line_distance", [("点名称", "", POINT), ("直线名称", "", LINE)]),
        ("两直线夹角", "angle_between_lines", [("直线1名称", "", LINE), ("直线2名称", "", LINE)]),
        ("平行判断", "parallel_check", [("直线1名称", "", LINE), ("直线2名称", "", LINE)]),
        ("垂直判断", "perpendicular_check", [("直线1名称", "", LINE), ("直线2名称", "", LINE)]),
    ],
    "圆": [
        ("圆心坐标", "circle_center", [("圆名称", "", CIRCLE)]),
        ("半径", "circle_radius", [("圆名称", "", CIRCLE)]),
        ("面积", "circle_area", [("圆名称", "", CIRCLE)]),
        ("周长", "circle_circumference", [("圆名称", "", CIRCLE)]),
        ("两圆交点", "circle_intersection", [("圆1名称", "", CIRCLE), ("圆2名称", "", CIRCLE)]),
        ("切线方程", "circle_tangent_lines", [("点名称", "", POINT), ("圆名称", "", CIRCLE)]),
    ],
    "三角形": [
        ("面积", "triangle_area", [("三角形名称", "", TRIANGLE)]),
        ("周长", "triangle_perimeter", [("三角形名称", "", TRIANGLE)]),
        ("外心", "triangle_circumcenter", [("三角形名称", "", TRIANGLE)]),
        ("外接圆半径", "triangle_circumradius", [("三角形名称", "", TRIANGLE)]),
        ("内心", "triangle_incenter", [("三角形名称", "", TRIANGLE)]),
        ("内切圆半径", "triangle_inradius", [("三角形名称", "", TRIANGLE)]),
        ("重心", "triangle_centroid", [("三角形名称", "", TRIANGLE)]),
        ("垂心", "triangle_orthocenter", [("三角形名称", "", TRIANGLE)]),
        ("直角三角形判断", "triangle_is_right", [("三角形名称", "", TRIANGLE)]),
        ("等腰三角形判断", "triangle_is_isosceles", [("三角形名称", "", TRIANGLE)]),
        ("等边三角形判断", "triangle_is_equilateral", [("三角形名称", "", TRIANGLE)]),
    ],
    "多边形": [
        ("面积", "polygon_area_func", [("顶点数", 3, QUANTITY), ("顶点{}名称", "", POINT)]),
        ("周长", "polygon_perimeter_func", [("顶点数", 3, QUANTITY), ("顶点{}名称", "", POINT)]),
    ],
}

SOLID_OPS = {
    "点": [
        ("两点距离", "point3d_distance", [("点1名称", "", POINT), ("点2名称", "", POINT)]),
        ("中点坐标", "point3d_midpoint", [("点1名称", "", POINT), ("点2名称", "", POINT)]),
        ("点到平面距离", "point3d_to_plane_distance", [("点名称", "", POINT), ("平面名称", "", PLANE)]),
        ("点到直线距离", "point3d_to_line_distance", [("点名称", "", POINT), ("直线名称", "", LINE)]),
        ("点在平面上的投影", "point3d_projection_on_plane", [("点名称", "", POINT), ("平面名称", "", PLANE)]),
        ("点在直线上的投影", "point3d_projection_on_line", [("点名称", "", POINT), ("直线名称", "", LINE)]),
        ("共面判断", "are_coplanar", [("点数", 4, QUANTITY), ("点{}名称", "", POINT)]),
        ("四面体体积", "tetrahedron_volume",
         [("点1名称", "", POINT), ("点2名称", "", POINT), ("点3名称", "", POINT), ("点4名称", "", POINT)]),
    ],
    "直线": [
        ("方向向量", "line3d_direction", [("直线名称", "", LINE)]),
        ("两直线交点", "line3d_intersection", [("直线1名称", "", LINE), ("直线2名称", "", LINE)]),
        ("两直线夹角", "line3d_angle", [("直线1名称", "", LINE), ("直线2名称", "", LINE)]),
        ("平行判断", "line3d_parallel_check", [("直线1名称", "", LINE), ("直线2名称", "", LINE)]),
        ("垂直判断", "line3d_perpendicular_check", [("直线1名称", "", LINE), ("直线2名称", "", LINE)]),
        ("在平面上的投影", "line3d_projection_on_plane", [("直线名称", "", LINE), ("平面名称", "", PLANE)]),
        ("与平面的夹角", "line_plane_angle", [("直线名称", "", LINE), ("平面名称", "", PLANE)]),
    ],
    "平面": [
        ("三点求平面方程", "plane_equation_from_points",
         [("点1名称", "", POINT), ("点2名称", "", POINT), ("点3名称", "", POINT)]),
        ("法向量", "plane_normal_vector", [("平面名称", "", PLANE)]),
        ("两平面夹角", "plane_angle_between", [("平面1名称", "", PLANE), ("平面2名称", "", PLANE)]),
        ("两平面交线", "plane_intersection", [("平面1名称", "", PLANE), ("平面2名称", "", PLANE)]),
        ("平行判断", "plane_parallel_check", [("平面1名称", "", PLANE), ("平面2名称", "", PLANE)]),
        ("垂直判断", "plane_perpendicular_check", [("平面1名称", "", PLANE), ("平面2名称", "", PLANE)]),
        ("与直线的交点", "plane_line_intersection", [("平面名称", "", PLANE), ("直线名称", "", LINE)]),
    ],
}

OPS = {"plane": PLANE_OPS, "solid": SOLID_OPS}
_LINE_PAIR_OPS = {"line_intersection", "angle_between_lines", "parallel_check", "perpendicular_check"}
_LINE_POINT_OPS = {"point_to_line_distance", "reflect_point"}
_TRIANGLE_OPS = {
    "triangle_area", "triangle_perimeter", "triangle_circumcenter", "triangle_circumradius",
    "triangle_incenter", "triangle_inradius", "triangle_centroid", "triangle_orthocenter",
    "triangle_is_right", "triangle_is_isosceles", "triangle_is_equilateral",
}
_FS_OPS = {"translate_point", "rotate_point"}

DEF_FIXED = [
    [("名称", "f", VALUE), ("表达式", "", VALUE), ("定义域", "Reals", VALUE), ("自变量", "x", VALUE)],
    [("名称", "set", VALUE), ("表达式", "", VALUE)],
    [("名称", "vec", VALUE), ("x", "", VALUE), ("y", "", VALUE)],
]

_SS = {}
_VS = {}
_GP = {}
_GS = {}
_LAST = {"value": None, "text": ""}
_STATE = {"fs": {}}


def _jsonable(obj):
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(x) for x in obj]
    return obj


def _geom_spec(table):
    out = {}
    for obj_type, methods in table.items():
        out[obj_type] = [
            {"name": m[0], "params": _jsonable(m[1]), "category": m[2], "func": m[3]}
            for m in methods
        ]
    return out


def _ops_spec(table):
    out = {}
    for obj_type, operations in table.items():
        out[obj_type] = [
            {"name": o[0], "key": o[1], "params": _jsonable(o[2])}
            for o in operations
        ]
    return out


def objects():
    plane, solid = {}, {}
    for name, value in _GP.items():
        plane.setdefault(value[0], []).append(name)
    for name, value in _GS.items():
        solid.setdefault(value[0], []).append(name)
    return {
        "plane": plane, "solid": solid,
        "函数": list(_STATE["fs"].keys()),
        "集合": list(_SS.keys()), "向量": list(_VS.keys()),
    }


def spec():
    return {
        "calc_functions": CALC_FUNCTION_NAMES,
        "def_types": DEF_TYPE_NAMES,
        "calc_engines": CALC_ENGINE_NAMES,
        "transform_names": TRANSFORM_NAMES,
        "triangle_parts": TRIANGLE_PARTS,
        "triangle_keys": TRIANGLE_KEYS,
        "draw_modes": DRAW_MODE_NAMES,
        "role_category": ROLE_CATEGORY,
        "name_prefix": NAME_PREFIX,
        "def_fixed": _jsonable(DEF_FIXED),
        "geometry": {"plane": _geom_spec(PLANE_GEOMETRY), "solid": _geom_spec(SOLID_GEOMETRY)},
        "ops": {"plane": _ops_spec(PLANE_OPS), "solid": _ops_spec(SOLID_OPS)},
        "objects": objects(),
    }


def _fig_png(fig, dpi=110):
    buf = io.BytesIO()
    fig.savefig(buf, dpi=dpi, format="png", bbox_inches="tight",
                transparent=True, pad_inches=0.15)
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _latex_png(text, theme="light"):
    if not text:
        return None
    fg = "black" if theme == "light" else "#e8eaed"
    try:
        fig = plt.figure(figsize=(0.1, 0.1))
        with rc_context({"text.color": fg, "mathtext.fontset": "cm",
                         "font.family": "DejaVu Sans"}):
            fig.text(0.5, 0.5, "$" + text + "$", fontsize=18,
                     color=fg, ha="center", va="center")
        buf = io.BytesIO()
        fig.savefig(buf, dpi=170, format="png", transparent=True,
                    bbox_inches="tight", pad_inches=0.12)
        plt.close(fig)
        return base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        return None


def _ok(action, **kw):
    out = {"ok": True, "page": "fp", "action": action, "latex": None,
           "png": None, "text": "", "plot_png": None, "error": None}
    out.update(kw)
    return out


def _fail(action, msg):
    return {"ok": False, "page": "fp", "action": action, "latex": None,
            "png": None, "text": "", "plot_png": None, "error": str(msg)}


def _sym(text, fs):
    result = sympify(str(text).strip(), fs)
    if isinstance(result, str):
        raise ValueError(result or "空表达式")
    return result


def _int(text, default=1):
    try:
        return int(str(text).strip())
    except Exception:
        return default


def geo_lookup(dim):
    store = _GP if dim == "plane" else _GS

    def lookup(role, name):
        name = str(name).strip()
        if name in store and store[name][0] == ROLE_CATEGORY.get(role):
            return store[name][1]
        return None

    return lookup


def resolve_one(role, value, lookup):
    if role == VALUE:
        return value
    if role == INTEGER:
        return int(value)
    found = lookup(role, value)
    if found is None:
        raise ValueError("未找到%s '%s'" % (ROLE_CATEGORY.get(role, "对象"), value))
    return found


def resolve_args(params, values, lookup):
    args = []
    index = 0
    for field in params:
        role = field[2]
        if role == QUANTITY:
            index += 1
            continue
        if "{}" in field[0]:
            for value in values[index:]:
                args.append(resolve_one(role, value, lookup))
            index = len(values)
            continue
        if index >= len(values):
            raise ValueError("参数不足：" + field[0])
        args.append(resolve_one(role, values[index], lookup))
        index += 1
    return args


def geometry_method(dim, obj_type, method_title):
    methods = GEOMETRY[dim].get(obj_type)
    if not methods:
        raise ValueError("未知几何对象类型：" + str(obj_type))
    for method in methods:
        if method[0] == method_title:
            return method[1], method[2], method[3]
    raise ValueError("未知创建方式：" + str(method_title))


def build_geometry(dim, obj_type, method_title, values, fs, lookup):
    params, category, func_name = geometry_method(dim, obj_type, method_title)
    if func_name == "perpendicular_bisector":
        seg = lookup(SEGMENT, values[0])
        if seg is None:
            raise ValueError("未找到线段 '%s'" % values[0])
        return category, planes_mod.perpendicular_bisector(seg.points[0], seg.points[1])
    if func_name == "perpendicular_line_from_point":
        pt = lookup(POINT, values[0])
        line = lookup(LINE, values[1])
        if pt is None or line is None:
            raise ValueError("未找到点或直线")
        return category, solids_mod.create_line3d(
            pt, solids_mod.perpendicular_foot_to_line_3d(pt, line))
    if func_name == "create_polygon":
        return category, planes_mod.create_polygon(resolve_args(params, values, lookup))
    args = resolve_args(params, values, lookup)
    module = planes_mod if dim == "plane" else solids_mod
    func = getattr(module, func_name)
    if func_name in _NEEDS_FS:
        return category, func(*args, fs)
    return category, func(*args)


def describe(obj):
    if hasattr(obj, "equation"):
        try:
            return str(obj.equation())
        except Exception:
            pass
    if hasattr(obj, "x") and hasattr(obj, "y"):
        if hasattr(obj, "z"):
            return "(%s, %s, %s)" % (obj.x, obj.y, obj.z)
        return "(%s, %s)" % (obj.x, obj.y)
    points = getattr(obj, "points", None)
    if points is not None and len(points) == 2:
        return describe(points[0]) + " " + describe(points[1])
    return str(obj)


def line_points(line):
    return line.points[0], line.points[1]


def plane_op(key, args, fs):
    if key == "circle_center":
        circle = args[0]
        return (radsimp(circle.center.x), radsimp(circle.center.y))
    if key == "circle_radius":
        return radsimp(args[0].radius)
    if key == "circle_area":
        return radsimp(args[0].area)
    if key == "circle_circumference":
        return radsimp(args[0].circumference)
    if key == "circle_intersection":
        points = args[0].intersection(args[1])
        return [(radsimp(pt.x), radsimp(pt.y)) for pt in points] or "两圆不相交"
    if key == "circle_tangent_lines":
        lines = args[1].tangent_lines(args[0])
        return [simplify(line.equation()) for line in lines] or "无切线"
    if key in _TRIANGLE_OPS:
        return getattr(planes_mod, key)(*args[0].vertices)
    if key in ("collinear_check", "polygon_area_func", "polygon_perimeter_func"):
        return getattr(planes_mod, key)(args)
    if key in _LINE_PAIR_OPS:
        return getattr(planes_mod, key)(*line_points(args[0]), *line_points(args[1]))
    if key in _LINE_POINT_OPS:
        return getattr(planes_mod, key)(args[0], *line_points(args[1]))
    if key in _FS_OPS:
        return getattr(planes_mod, key)(*args, fs)
    return getattr(planes_mod, key)(*args)


def solid_op(key, args, fs):
    if key == "are_coplanar":
        return solids_mod.are_coplanar(args)
    return getattr(solids_mod, key)(*args)


def op_params(dim, obj_type, op_title):
    for operation in OPS[dim].get(obj_type, []):
        if operation[0] == op_title:
            return operation[2]
    raise ValueError("未知计算方式：" + str(op_title))


def compute_geometry(dim, obj_type, op_title, args, fs):
    operations = OPS[dim].get(obj_type)
    if not operations:
        raise ValueError("未知几何对象类型：" + str(obj_type))
    for operation in operations:
        if operation[0] == op_title:
            return (plane_op if dim == "plane" else solid_op)(operation[1], args, fs)
    raise ValueError("未知计算方式：" + str(op_title))


def compute_geometry_result(dim, inputs, fs):
    obj_type, op_title = inputs[0], inputs[1]
    params = op_params(dim, obj_type, op_title)
    args = resolve_args(params, inputs[2:], geo_lookup(dim))
    return compute_geometry(dim, obj_type, op_title, args, fs)


def compute_algebra(inputs, fs):
    engine, expr = inputs[0], inputs[1]
    if engine == CALC_ENGINE_NAMES[0]:
        import math
        import sys
        sys.set_int_max_str_digits(0)
        env = {"__builtins__": {}}
        for name in dir(math):
            if not name.startswith("_"):
                env[name] = getattr(math, name)
        env.update({"abs": abs, "round": round, "int": int, "float": float,
                    "pow": pow, "sum": sum, "min": min, "max": max})
        return eval(expr, env, {}), False, None
    if engine == CALC_ENGINE_NAMES[1]:
        import mpmath as mp
        env = {"__builtins__": {}}
        for name in dir(mp):
            if not name.startswith("_"):
                try:
                    env[name] = getattr(mp, name)
                except Exception:
                    pass
        with mp.workdps(_int(inputs[2] if len(inputs) > 2 else 16, 16)):
            result = eval(expr, env, {})
            text = str(result)
        return result, False, text
    if engine == CALC_ENGINE_NAMES[2]:
        return radsimp(sympify(expr, fs, is_simplify=True)), False, None
    code = latex(sympify(expr, {}))
    return code, True, code


def transform_algebra(inputs, fs):
    method = TRANSFORM_NAMES.index(inputs[0])
    zhuyuan = inputs[2] if len(inputs) > 2 else None
    huanyuan = inputs[3] if len(inputs) > 3 else None
    huanyuanshi = inputs[4] if len(inputs) > 4 else None
    return simplifies(inputs[1], method, zhuyuan, huanyuan, huanyuanshi, fs)


def solve_triangle(inputs, fs):
    angles, sides = {}, {}
    for i in range(0, len(inputs) - 1, 2):
        index = TRIANGLE_PARTS.index(inputs[i]) if inputs[i] in TRIANGLE_PARTS else 0
        text = str(inputs[i + 1]).strip()
        if index == 0 or not text:
            continue
        value = _sym(text, fs)
        key = TRIANGLE_KEYS[index]
        (angles if key.isupper() else sides)[key] = value
    if len(angles) + len(sides) != 3:
        raise ValueError("请填入恰好3个有效且不重复的条件")
    result = solve_sanjiaoxing(angles, sides, fs)
    if not result:
        raise ValueError("无解")
    if isinstance(result, str):
        raise ValueError(result)
    lines, flat = [], []
    for i, (res_angles, res_sides) in enumerate(result):
        parts = ["%s = %s" % (k, latex(v)) for k, v in res_angles.items()]
        parts += ["%s = %s" % (k, latex(v)) for k, v in res_sides.items()]
        prefix = r"\text{解}%d:\ " % (i + 1) if len(result) > 1 else ""
        lines.append(prefix + r",\ ".join(parts))
        flat.append(" | ".join("%s = %s" % (k, v)
                               for k, v in list(res_angles.items()) + list(res_sides.items())))
    return r" \\ ".join(lines), "  ||  ".join(flat)


def solve_group(inputs, fs, idx):
    count = _int(inputs[0], 2)
    if idx == 5:
        equations = [Eq(_sym(inputs[2 + 2 * i], fs), _sym(inputs[3 + 2 * i], fs))
                     for i in range(count)]
        symbols = [Symbol(v.strip()) for v in str(inputs[1]).split(",") if v.strip()]
        return solve_fangchengzu(equations, symbols, fs)
    relations = [Rel(_sym(inputs[2 + 3 * i], fs), _sym(inputs[4 + 3 * i], fs),
                     inputs[3 + 3 * i]) for i in range(count)]
    return solve_budengshizu(relations, Symbol(str(inputs[1]).strip()), fs) or "无解"


def calc(req):
    idx = int(req.get("index", 0))
    inputs = req.get("values") or []
    if not all(str(v).strip() for v in inputs):
        raise ValueError("有参数未输入")
    fs = _STATE["fs"]
    as_latex, output = False, None
    if idx in (7, 8):
        result = compute_geometry_result("plane" if idx == 7 else "solid", inputs, fs)
    elif idx == 10:
        result, output = solve_triangle(inputs, fs)
        as_latex = True
    elif idx == 9:
        result = transform_algebra(inputs, fs)
    elif idx == 0:
        result, as_latex, output = compute_algebra(inputs, fs)
    elif idx == 1:
        result = derivative(inputs[0], inputs[1], inputs[2], "", fs)
    elif idx == 2:
        result = integral(inputs[0], inputs[1], fs)
    elif idx == 3:
        result = solve_fangcheng(Eq(_sym(inputs[0], fs), _sym(inputs[1], fs)),
                                 inputs[2], inputs[3], fs)
    elif idx == 4:
        result = solve_budengshi(Rel(_sym(inputs[0], fs), _sym(inputs[2], fs), inputs[1]),
                                 inputs[3], inputs[4], fs)
    else:
        result = solve_group(inputs, fs, idx)
    if isinstance(result, str) and not as_latex:
        text, value = result, None
    else:
        try:
            text = result if as_latex else latex(result)
        except Exception:
            text = str(result)
        value = None if as_latex else result
        if idx == 5:
            text = text.replace(":", "=")
    plain = output if output is not None else (text if as_latex else str(result))
    _LAST["value"] = value
    _LAST["text"] = plain
    return _ok("calc", latex=text, png=_latex_png(text) if not as_latex else None,
               text=plain)


def def_save(req):
    values = req.get("values") or []
    typ = int(req.get("type", 0))
    if not values or not all(str(v).strip() for v in values):
        raise ValueError("有参数未输入")
    name = str(values[0]).strip()
    fs = _STATE["fs"]
    if typ in (3, 4):
        dim = "plane" if typ == 3 else "solid"
        category, obj = build_geometry(dim, values[1], values[2], values[3:],
                                       fs, geo_lookup(dim))
        if isinstance(obj, str):
            raise ValueError("创建几何对象失败：" + obj)
        store = _GP if dim == "plane" else _GS
        store[name] = (category, obj)
        _DEFS[(dim, name)] = list(values)
    elif typ == 0:
        fs[name] = list(values)
        _DEFS[("func", name)] = list(values)
    elif typ == 1:
        _SS[name] = list(values)
        _DEFS[("set", name)] = list(values)
    else:
        _VS[name] = list(values)
        _DEFS[("vec", name)] = list(values)
    return _ok("def_save", text="已保存定义 " + name, objects=objects())


_DEFS = {}


def def_list():
    groups = {}
    for key, values in _DEFS.items():
        kind, name = key
        label = {"func": "函数", "set": "集合", "vec": "向量",
                 "plane": "平面几何", "solid": "立体几何"}.get(kind, kind)
        groups.setdefault(label, []).append({"name": name, "values": values, "kind": kind})
    return _ok("def_list", objects=objects(), groups=groups)


def def_edit(req):
    name = str(req.get("name", "")).strip()
    for (kind, key), values in _DEFS.items():
        if key == name:
            typ = {"func": 0, "set": 1, "vec": 2, "plane": 3, "solid": 4}.get(kind, 0)
            return _ok("def_edit", type=typ, values=values, objects=objects())
    raise ValueError("未找到定义：" + name)


def def_del(req):
    name = str(req.get("name", "")).strip()
    removed = False
    for key in [k for k in _DEFS if k[1] == name]:
        kind, _ = key
        _DEFS.pop(key, None)
        if kind == "func":
            _STATE["fs"].pop(name, None)
        elif kind == "set":
            _SS.pop(name, None)
        elif kind == "vec":
            _VS.pop(name, None)
        elif kind == "plane":
            _GP.pop(name, None)
        else:
            _GS.pop(name, None)
        removed = True
    if not removed:
        raise ValueError("删除失败，请检查选中的是否为对象")
    return _ok("def_del", text="删除成功：" + name, objects=objects())


def def_preview(req):
    typ = int(req.get("type", 0))
    values = req.get("values") or []
    mode = int(req.get("mode", 0))
    text = str(req.get("text") or "")
    fs = _STATE["fs"]
    if typ in (3, 4):
        if len(values) < 3 or not str(values[0]).strip() or not all(str(v).strip() for v in values[3:]):
            return _ok("def_preview", text="请先填写全部参数")
        dim = "plane" if typ == 3 else "solid"
        try:
            _cat, obj = build_geometry(dim, values[1], values[2], values[3:],
                                       fs, geo_lookup(dim))
            text = obj if isinstance(obj, str) else describe(obj)
        except Exception as e:
            text = str(e)
    if not text:
        return _ok("def_preview", text="")
    expr = sympify(text, fs if mode == 1 else {})
    if isinstance(expr, str):
        return _ok("def_preview", text=text, latex=None)
    return _ok("def_preview", text=str(expr), latex=latex(expr),
               png=_latex_png(latex(expr)))


def save_result(req):
    name = str(req.get("name", "")).strip()
    if not name:
        return _ok("save_result", text="", objects=objects())
    value = _LAST.get("value")
    fs = _STATE["fs"]
    if value is None or not isinstance(value, sympy.Expr):
        raise ValueError("该结果不是表达式，无法保存为函数")
    if name in fs:
        raise ValueError("名称已存在，请更换：" + name)
    symbols = sorted(value.free_symbols, key=str)
    var = str(symbols[0]) if symbols else "x"
    fs[name] = [name, str(value), "Reals", var]
    _DEFS[("func", name)] = list(fs[name])
    return _ok("save_result", text="已保存为函数 " + name, objects=objects())


def draw(req):
    mode = int(req.get("mode", 0))
    names = req.get("names") or []
    fs = _STATE["fs"]
    if mode == 2:
        entries = []
        for name in names:
            if name not in fs:
                continue
            expr = sympify(fs[name][1], fs, is_simplify=True)
            if isinstance(expr, str):
                raise ValueError(expr)
            var = fs[name][3] if len(fs[name]) > 3 else "x"
            entries.append((name, expr, var))
        if not entries:
            raise ValueError("请勾选至少一个函数")
        fig = draw_functions(entries, figsize=(6.0, 5.1), dpi=100, theme="light")
    else:
        store = _GP if mode == 0 else _GS
        painter = draw2d if mode == 0 else draw3d
        objs = [(store[n][1], {"label": n}) for n in names if n in store]
        if not objs:
            raise ValueError("请勾选至少一个几何对象")
        fig = painter(objs, figsize=(6.0, 5.1), dpi=100, theme="light")
    return _ok("draw", plot_png=_fig_png(fig), text="绘制完成")


def handle(req, fs):
    _STATE["fs"] = fs
    action = req.get("action", "spec")
    try:
        if action == "spec":
            return _ok("spec", spec=spec())
        if action == "objects":
            return _ok("objects", objects=objects())
        if action == "def_save":
            return def_save(req)
        if action == "def_list":
            return def_list()
        if action == "def_edit":
            return def_edit(req)
        if action == "def_del":
            return def_del(req)
        if action == "def_preview":
            return def_preview(req)
        if action == "calc":
            return calc(req)
        if action == "save_result":
            return save_result(req)
        if action == "draw":
            return draw(req)
        return _fail(action, "未知操作：" + action)
    except Exception as e:
        import traceback
        return _fail(action, "%s\n%s" % (e, traceback.format_exc()[:400]))
