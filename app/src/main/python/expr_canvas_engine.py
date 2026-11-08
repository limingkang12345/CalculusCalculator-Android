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
    Add, Div, Eq, Integer, LatexPrinter, Mul, Pow, Rational,
    from_sympy, parse_sympy,
)


class CanvasItem:
    def __init__(self, item_id, tree, x=0.0, y=0.0, note=""):
        self.item_id = item_id
        self.tree = tree
        self.x = float(x)
        self.y = float(y)
        self.note = note or ""


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

    def _new_item(self, tree, note=""):
        item_id = "c%d" % self.next_id
        self.next_id += 1
        item = CanvasItem(item_id, tree, note=note)
        self.items[item_id] = item
        self.order.append(item_id)
        return item

    def _kind(self, item):
        return "equation" if isinstance(item.tree, Eq) else "expression"

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
             self.items[i].y, self.items[i].note)
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
        for item_id, tree, x, y, note in snap:
            self.items[item_id] = CanvasItem(item_id, tree, x, y, note)
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

    def _vieta_cards(self, eq1, eq2, variables):
        """联立两张方程卡片后对主变量套用韦达定理。

        解析几何里直线与圆锥曲线联立时，需要先用另一张方程消去共有变量
        （如 y = k*x+m 代入椭圆），得到关于主变量 x 的一元二次方程，再取
        两根之和 / 两根之积。旧实现只拿第一张卡片做 Poly，既依赖拖放顺序，
        也不会代入消元，导致"只选 x 变量"时经常无结果或结果不含直线信息。
        """
        var = sympy.Symbol(variables[0] if variables else "x")
        f1 = self._eq_to_expr(eq1)
        f2 = self._eq_to_expr(eq2)
        if f1 is None or f2 is None:
            return []
        if var not in (f1.free_symbols | f2.free_symbols):
            return []
        main, aux = ((f1, f2) if self._poly_degree(f1, var) >= self._poly_degree(f2, var)
                     else (f2, f1))
        shared = (f1.free_symbols & f2.free_symbols) - {var}
        for sym in sorted(shared, key=str):
            try:
                solutions = sympy.solve(aux, sym, dict=True)
            except Exception:
                solutions = []
            value = None
            for solution in solutions:
                candidate = solution.get(sym)
                if candidate is None or sym in getattr(candidate, "free_symbols", set()):
                    continue
                value = candidate
                break
            if value is None:
                continue
            main = sympy.together(main.subs(sym, value))
            aux = sympy.together(aux.subs(sym, value))
        try:
            poly = sympy.Poly(sympy.together(main), var)
        except Exception:
            try:
                poly = sympy.Poly(sympy.cancel(main), var)
            except Exception:
                return []
        if poly.degree() != 2:
            return []
        a, b, c = poly.all_coeffs()
        try:
            sum_roots = sympy.cancel(-b / a)
            prod_roots = sympy.cancel(c / a)
        except Exception:
            return []
        return [
            (from_sympy(sympy.Eq(sympy.Symbol("S"), sum_roots), ordered=True),
             "韦达定理：两根之和 = -b/a"),
            (from_sympy(sympy.Eq(sympy.Symbol("P"), prod_roots), ordered=True),
             "韦达定理：两根之积 = c/a"),
        ]

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
            if item is None or node is None:
                out["error"] = "节点已失效，请重新点击"
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
            roots = self._finite_roots(
                sympy.solveset(node.to_sympy(), sympy.Symbol(variable), domain))
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
                cards = self._vieta_cards(first.tree, second.tree, variables)
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
                    out["error"] = ("未得到关于 %s 的一元二次方程：请把未知量只保留一个变量，"
                                    "或改用「直接求解方程组」"
                                    % (variables[0] if variables else "x"))
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
