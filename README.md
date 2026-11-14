# CalculusCalculator 安卓工程（Chaquopy 内嵌 Python · 完全离线）

把 **CalculusCalculator（微积分计算器）** 打包成安卓 App：**APK 内嵌 Python 3.11 + SymPy/NumPy/Matplotlib**，
所有计算都在手机本地完成，**安装后无需联网、无需服务器**。

原项目是 Python 3.10+ / PySide6 桌面程序。本工程**不改其计算内核**，直接复用原项目的纯计算模块与
表达式树、Blockly 积木定义，仅把运行前端从 PySide6 窗口换成安卓 WebView + Chaquopy。

---

## ⚠ 零、最常见的三个编译失败（务必先看）

### 1. `Couldn't find Python` / `generateDebugPythonRequirements` 失败

**原因**：Chaquopy 在「构建时」必须调用**构建机（你的 Windows）上的 CPython** 来生成 requirements、编译
`.pyc`。它不会把构建机 Python 打进 APK，但构建过程必须能找到它。Windows 上没装 Python 或没勾选
`Add python.exe to PATH` 时就会报这个错。

**解决（任选其一）**：

1. 安装 **Python 3.11 (64-bit)**：<https://www.python.org/downloads/release/python-3119/>
   - 安装时**务必勾选 `Add python.exe to PATH`**
   - 装完**重启 Android Studio**（PATH 变更需要重启才生效）
2. 或在 `gradle.properties` 里显式指定已安装的解释器（取消注释并改成真实路径，Windows 用正斜杠）：
   ```properties
   chaquopy.buildPython=C:/Users/<用户名>/AppData/Local/Programs/Python/Python311/python.exe
   ```

`app/build.gradle` 会自动探测 Python（gradle.properties 覆盖 → 环境变量 `CHAQUOPY_BUILD_PYTHON` →
PATH 中的 `python.exe` → Windows 常见安装目录 → `py -3`），并在构建日志里打印
`Chaquopy: 构建机 Python 3.11 -> ...`。**目标运行时固定为 3.11**；构建机若为其它 3.x 版本仍可构建，
只是 `.pyc` 预编译会跳过（不影响功能，启动稍慢）。

> 注意：Chaquopy 15 起使用新的 `chaquopy { }` DSL，旧的 `android.defaultConfig.python { }` 已废弃，
> 本工程已迁移。若你从旧版本工程复制配置，请一并更新。

### 2. `resource android:style/Theme.DevicesDefault.NoActionBar not found`

**原因**：`Theme.DevicesDefault` 是 Android 内部隐藏主题，compileSdk 34 的公开资源里不存在。
已改为公开主题 `android:Theme.Material.Light.NoActionBar`（见 `res/values/themes.xml`）。

### 3. pip 相关两类失败：`ReadTimeoutError` 与 `Chaquopy_cannot_compile_native_code`

`generateDebugPythonRequirements` 在构建时执行 `pip install`。国内网络下会遇到两种报错：

| 现象 | 根因 |
|---|---|
| `ReadTimeoutError: HTTPSConnectionPool(host='files.pythonhosted.org')`、`Chaquopy: Exit status 2` | 默认主源 `pypi.org` 的 wheel 在境外 CDN，下载 6MB 的 sympy 时读超时 |
| `Downloading numpy-2.x.x.tar.gz` → `Unknown compiler(s): [['Chaquopy_cannot_compile_native_code']]`、`Failed to install numpy` | 只配了 PyPI 镜像、**把 Chaquopy 私有源挤掉了**，pip 找不到 Android 预编译 wheel，退而下载源码包并尝试在构建机上编译 |

**两者都不是工程或功能问题。** 正确配置（已写入 `app/build.gradle`）：

```groovy
pip {
    options("--index-url", "https://mirrors.aliyun.com/pypi/simple/")
    options("--extra-index-url", "https://chaquo.com/pypi-13.1/")
    options("--only-binary", ":all:")
    options("--timeout", "60")
    options("--retries", "5")
    install "sympy"
    install "numpy"
    install "matplotlib"
    install "mpmath"
    install "latex2sympy2_extended"
}
```

三行关键配置各管一件事，缺一不可：

| 配置 | 作用 |
|---|---|
| `--index-url` 阿里云 | 纯 Python 包（sympy / mpmath / latex2sympy2_extended / antlr4）走国内 CDN，实测 6.3MB 一次成功 |
| `--extra-index-url` **chaquo 私有源** | numpy / matplotlib / pillow / kiwisolver / contourpy 的 **Android 预编译 wheel 唯一来源**。Chaquopy 默认用环境变量注入它，命令行一旦出现 `--extra-index-url` 就会覆盖环境变量，因此**必须显式写这一行**（Chaquopy 官方 FAQ 的镜像写法同样如此） |
| `--only-binary=:all:` | 禁止源码包。否则镜像里版本更高的 `numpy-2.4.6.tar.gz` 会被选中并触发假编译器报错；加上后 pip 只选私有源里匹配 Android 标签的 wheel（实测选中 `numpy-1.26.2-0-cp311-cp311-android_21_arm64_v8a.whl`） |

> ⚠️ **不要**把 `--extra-index-url` 写成 PyPI 镜像，也**不要**加 `--no-index` —— 两者都会让
> Android wheel 消失。换 PyPI 镜像只改第 1 行 URL（清华源 `https://pypi.tuna.tsinghua.edu.cn/simple/`）。

> **旧工程手动修法**：把上面 5 行 `options(...)` 替换进 `pip { }`（`install` 行不动），
> `File → Sync Project with Gradle Files` 后重新构建。**不要点 `Clean Project`**：
> 会清掉 `app/build/python/` 里已下载好的包。

仍然超时的可选做法：

1. 换清华 / 中科大镜像（改第 1 行 URL）。
2. 纯 Python 包预下载到本地，再加 `options("--find-links", "wheels")`：
   ```bat
   python -m pip download -d app\wheels sympy mpmath latex2sympy2_extended --only-binary=:all:
   ```
   numpy / matplotlib 仍走 Chaquopy 私有源。
3. 首次构建可临时把 `ndk { abiFilters }` 只留 `'arm64-v8a'`：pip 安装会**按 ABI 各跑一遍**，
   少一个 ABI 就少一轮下载（真机够用；要用 x86_64 模拟器时再改回去）。

### 4. 其它说明
- **不需要安装 NDK / CMake**：Chaquopy 15 的 native 库已预编译并剥离，本工程不再设置 `ndkVersion`。
- 首次构建仍需联网：Gradle 插件与 Python 运行时、Chaquopy 私有源、国内 PyPI 镜像（见「零、3」），
  约百兆，仅首次；之后有缓存。Blockly / MathJax / MathLive 已随工程离线打包，APK 装好后完全离线运行。
- Chaquopy 私有源在境外，numpy / matplotlib 的 Android wheel（约 15MB）下载会比国内镜像慢，
  `--timeout 60 --retries 5` 会自动重试，首次构建请耐心等待；不要中途 Clean。
- `Chaquopy: 构建机 Python 版本未知` / `Warning: Python version 3.11 may have fewer packages`
  与 `SDK XML version 4` 警告都可忽略，不影响构建。

---

## 一、三大功能（对应原项目 `ui/__init__.py` 的 tabs_dict）

| 原项目 Tab | 安卓端 | 实现 |
|---|---|---|
| **功能集成** | 顶部「计算器」Tab（**仅此一页**） | `calc_engine.py` + `functions_page.py` 完整复刻 `functions.ui` 的定义区 / 计算区 / 绘图区 |
| **积木编辑器** | 顶部「积木模式」Tab | 离线 Blockly + `blockly_engine.py` |
| **解几计算器 + 表达式树** | 顶部「解几计算器」Tab | `expr_canvas/index.html` 表达式画布 + `expr_canvas_engine.py` + `expr_tree.py` |

### 1. 功能集成（计算器）

**计算器页现在就是「功能集成」单页**：原「微积分 / 平面几何 / 立体几何 / 3D 绘图 / 表达式树」
5 个分类 Tab 及其前端面板、算子已全部移除，页面只保留 `functions.ui` 的三区结构（详见 1.1）。
后端 `calc_engine.py` 的 30+ 个 `op` 仍保留，供功能集成页的 11 项计算与几何运算复用。

| 能力 | 内容 |
|---|---|
| 数值计算 | 四种计算引擎：Python 内置 / Mpmath 高精度（可设 dps）/ SymPy 符号 / LaTeX 代码生成 |
| 定义区 | 定义函数 `f(x)=x**2+1`，之后可直接写 `f(3)`、`f(g(2))` 参与运算 |
| 表达式变形 / 微积分 | 13 种变形（含指数展开、换元）、求导 / 积分 / 解方程 / 不等式 / 方程组 / 不等式组 / 解三角形 |
| 平面 / 立体几何 | 按名称引用对象，32 项平面运算 + 22 项立体运算 |
| 绘图 | 平面几何 / 立体几何 / 函数 3 种模式 |

结果以 **LaTeX + PNG**（matplotlib 离线渲染）展示；输入支持 SymPy 语法与 `$LaTeX$`。
**所有表达式输入框内最右侧都带 `∑` 按钮**，单击直接弹出 MathLive 原生可视化键盘（见 3.1）。

### 1.1 完全对齐桌面版 `ui/functions.ui` 的「功能集成」页

计算器页现在**只保留「功能集成」这一页**，按原桌面版 `functions.ui` 的三区布局完整复刻。
规格由 `python/functions_page.py` 提供（常量与原版 `ui/functions.py` 逐项一致），
前端据此动态生成输入表，仍走 `AndroidBridge.compute`，无需改动 Java 桥接。

| 区 | 对齐内容 |
|---|---|
| **定义区** | 5 种类型：函数（名称/表达式/定义域/自变量）、集合、向量、平面几何（6 类对象 × 多种创建方式）、立体几何（4 类对象 × 多种创建方式）；对象树（类型→对象→属性）、编辑定义 / 删除定义 / 保存输入 / 清空输入、预览与「直接模式 / 替换模式」、输出 |
| **计算区** | 原版 11 项：计算（4 引擎）、求导、积分、解方程、解不等式、解方程组、解不等式组、平面计算、立体计算、变形（13 种）、解三角形；动态输入表（左右式分离、不等号下拉、方程/不等式数量按行展开、3 组条件类型下拉）、清空、结果预览、**保存为**（把结果存为自定义函数） |
| **绘图区** | 3 种模式：平面几何模式 / 立体几何模式 / 函数模式；可勾选对象列表，绘制已定义几何对象或自定义函数 |

几何对象按**名称引用**：先在定义区创建点 / 线 / 圆 / 三角形 / 平面等，再在「平面计算 / 立体计算」
从下拉框选择，共 **32 项平面运算 + 22 项立体运算**，复用原项目 `functions/planes.py`、`solids.py`。
绘图复用 `paint2D.draw2d` / `paint3D.draw3d` / `paint2D.draw_functions`。

> 原「微积分 / 平面几何 / 立体几何 / 3D 绘图 / 表达式树」5 个分类 Tab 已从**前端删除**，页面只留
> 功能集成；后端 `calc_engine.py` 的算子仍保留，功能集成页的 11 项计算已覆盖其主要能力，并额外补齐
> 了按名称引用的几何对象体系与 32 + 22 项几何运算。函数定义表前后端共享，定义 `f` 后可直接写 `f(3)`。

### 2. 积木编辑器
完整离线 Blockly：拖拽积木 → 生成 Python 代码 → 本地执行 → 结果区用 MathJax 排版。
支持定义/调用函数、求导、积分、函数属性、13 种代数变形、解方程/方程组/不等式/三角形、
输入变量、输出变量、控制/逻辑/数学积木、代码预览与复制、工作区存档。

### 3. 解几计算器（表达式画布）
移植自原项目 `expr_calculator/expr_viewer.py`，复用其 `expr_tree.py` 的 `LatexPrinter`
（红→绿→蓝→紫按树深度分层着色 + `\cssId` 节点标记）与整套 HTML/JS 画布：

- 多表达式卡片、自动避让摆放、拖拽移动、复制 / 删除、全局字号滑块
- 节点级交互：点击选中、悬停灰底、详情面板显示节点结构与 SymPy 表达式
- 点击 `+` / `−` 交换相邻项、点击括号展开
- 「变」对话框：13 种 SymPy 变形 + 8 种节点操作（替换/加/乘/除/乘方/倒数/平方/平方根）
- 方程求解：选中方程节点按变量与范围求根，每个根生成独立卡片
- 两张方程卡片重叠：联立求解 / 韦达定理（自动消元后给出两根之和、两根之积），结果生成带注释卡片
- 节点拖拽到另一张卡片：弹出「重叠的表达式」对话框，**在目标公式上点选节点**后应用 11 种运算（见 3.2）
- 画布级 **撤销 / 重做**
- **数学输入**：主输入框与对话框输入框**内最右侧**的 `∑` 按钮，单击直接弹出 MathLive 原生键盘（见 3.1）

> 原桌面版的 Qt 模态对话框在此以页内 HTML 对话框等价实现；QWebChannel 桥接替换为
> `AndroidBridge`（WebView `addJavascriptInterface`）。

#### 3.1 统一数学输入：内嵌 ∑ 按钮 + MathLive 原生键盘

**所有表达式输入框共用同一套模块**（`assets/mathkeyboard.js` + `mathkeyboard.css`，两页都加载），
对齐桌面版 `math_input/MathLiveDialog`，但**不再提供任何自绘符号键盘**：

- `∑` 按钮用 `position:absolute` 内嵌在**输入框内部最右侧**，输入框留 `padding-right:42px`；
  不再是独立占一行的方块。
- **单击 `∑` → 直接弹出 MathLive 原生虚拟键盘**：打开时聚焦 `<math-field>` 并调用
  `mathVirtualKeyboard.show()`，输入、布局切换、光标移动、退格全部由 MathLive 提供。顶部只剩一条
  薄输入条（公式域 +「取消 / 确定」），没有分组标签、数字键、工具行与 LaTeX 预览。
- 资源全部离线（`assets/mathlive/dist/`，含 KaTeX 字体），公式域沿用紫色边框样式。

| 页面 | 带 `∑` 按钮的输入框 |
|---|---|
| 计算器（功能集成） | 定义区 / 计算区**动态生成的每一个文本输入框**（表达式、左式/右式、变量、定义域、条件值、坐标…）与「保存为」 |
| 解几计算器 | 顶部主输入框 `#expr-input`，以及变换 / 求解 / 联立对话框里的「输入表达式 / 求解变量 / 未知量」 |

| 组成 | 说明 |
|---|---|
| WYSIWYG 公式域 | MathLive `<math-field>`，`math-virtual-keyboard-policy="manual"` + `inputmode="none"` 避免与系统软键盘冲突；打开即 `show()` 原生键盘 |
| 回填链路 | 确定 → `MathKeyboard.normalizeLatex()` 补全 `\sqrt3`/`\frac12` 省略花括号 → 按页面分流：计算器页 `AndroidBridge.compute({op:"latexToExpr"})`、解几页 `AndroidBridge.canvas({action:"latexToExpr"})` → Python `sympify('$'+latex, {})` 转 SymPy 表达式字符串 → `MathKeyboard.applyExpr()` 填回目标输入框并触发 `change` |
| 降级 | MathLive 未加载时自动改用 `<textarea>` 纯 LaTeX 输入，确定链路不变 |

`latexToExpr` 后端有两个等价入口：`calc_engine.py` 的 `_op_latex_to_expr`（计算器页）与
`expr_canvas_engine.py` 的 `latexToExpr` action（解几页），均复用 `core.sympify.sympify` 与新增的
`core.sympify.ordered_expr_text()`。

**公式输入保序（左式两项顺序不调换）**：SymPy 的 `str()` 会按 `as_ordered_terms()` 重排 `Add`
的项，把 `\frac{x^{2}}{a^{2}}+\frac{y^{2}}{b^{2}}` 显示为 `y**2/(b**2) + x**2/(a**2)`；回填到
输入框后，画布按这个字符串构造表达式树，渲染出来的左式就前后颠倒。现在改用
`sstr(expr, order="none")` 按 `.args` 构造顺序（即输入顺序）输出：

| 页面 | 回填格式 | 示例 |
|---|---|---|
| 解几计算器 | `lhs = rhs`，交给 `parse_sympy(evaluate=False)` 保序构造表达式树 | `\frac{x^{2}}{a^{2}}+\frac{y^{2}}{b^{2}}=1` → `x**2/(a**2) + y**2/(b**2) = 1` → 渲染仍是 `x²/a² + y²/b² = 1` |
| 计算器（功能集成） | 保持 `Eq(lhs, rhs)` 形式，兼容 `_safe_sympify` 单表达式解析 | `x^{2}=4` → `Eq(x**2, 4)` |

转换结果如 `\frac{x^{2}+1}{2}` → `(x**2 + 1)/2`，可直接参与计算或被画布表达式树解析；
若公式未填完整导致转换失败，会回填原始 LaTeX 并提示，可手动修改。

**键盘稳定性（切换分类页闪退修复）**：MathLive 0.110 只识别 `math-virtual-keyboard-policy`，
不识别旧写法 `virtual-keyboard-mode`；公式域已固定为 `manual`。但仅靠策略不够 —— MathLive 的
`hide()` 会直接 `this._element.remove()` 销毁整个键盘 DOM，而 `focusout` 300ms 自动隐藏、`window blur`、
键盘分类页（`123` / `abc` / 希腊字母）`switchKeyboardLayer` 重建、`resize` 等**多条路径都会调
`hide()`**。真机录屏复现为：切换分类页后键盘先错位只剩左半屏，紧接着键盘与输入条整体消失、
公式丢失、输入框仍是原值。

因此在虚拟键盘的事件层做了最终兜底（不依赖 MathLive 内部策略）：

| 场景 | 处理 |
|---|---|
| MathLive 内部任意来源的隐藏 | `mathVirtualKeyboard` 上监听 `before-virtual-keyboard-toggle`，当 `detail.visible === false` 且遮罩仍打开时 `preventDefault()`。MathLive 的 `stateWillChange()` 返回 false → `hide()` 整段不执行，键盘 DOM 不会被移除 |
| MathLive 绕过 `hide()` 直接置隐藏 | 监听 `virtual-keyboard-toggle`，若 `visible === false` 且遮罩仍打开则重新 `show()`，最多 3 次防循环 |
| 用户点「取消 / 确定」或切 Tab | `MathKeyboard.close()` 通过 `allowHide` 标志放行 `hide()`，正常收起 |
| 切换分类页时布局错位 | `body > .ML__keyboard` 强制 `left/right:0`、`width:100%`；`MLK__layer` / `MLK__backdrop` 禁用 `transition/animation`，消除 WebView 上层切换动画造成的半屏残影 |
| 误触遮罩 | 删除「点击遮罩空白处关闭」，只有「取消 / 确定」能关闭；遮罩内 `click` 等事件全部 `stopPropagation()` |
| 切换顶部功能 Tab / App 退后台 | `MainActivity.dismissKeyboard()` 主动 `close()` + `mathVirtualKeyboard.hide()` |
| WebView 渲染进程崩溃 | `WebViewClient.onRenderProcessGone()` 返回 true 并 `rebuildWebView()` 销毁重建该 WebView、重新注入 `AndroidBridge` 并 `loadUrl`，避免整个应用退出 |
| 瞬时 `visibilitychange` | 延时 400ms 二次确认 `document.hidden` 才收起，避免 WebView 弹键盘时短暂失焦误关 |
| 页面不可见 / 卸载、输入框被重建 | `pagehide` 自动收起；`renderRows()` 清空 DOM 前先 `close()`；`resize` 校验目标是否仍在 DOM |
| 键盘打开期间画布交互 | 解几页 `click/mousemove/scroll/resize` 业务监听在 `MathKeyboard.isOpen()` 时早退 |
| 结果回填 | `applyExpr()` 目标脱离 DOM 时按 id 重新定位 |

`switchKeyboardLayer` 内部只调幂等的 `show()` + 设置 `currentLayer`，不调 `hide()`，所以拦截隐藏
**不会影响分类页切换**。`open()` 先 `hide()` 上一次残留、聚焦公式域，再延时 120ms `show()`；
`[data-kbd]` 委托在**捕获阶段**注册，保证点击 `∑` 时业务层看到的 `isOpen()` 已为 `true`。

> 动态输入框的 `id` 按容器加前缀（`kbd-fpDefRows-N` / `kbd-fpCalcRows-N`），避免定义区与计算区
> 序号重复导致 `∑` 回填到错误的输入框。

#### 3.2 拖拽节点对话框「重叠的表达式」

对齐桌面版 `expr_viewer.ExpressionDialog`：把一张卡片里的节点拖到另一张卡片后，弹出的不再是
「对整张目标卡片做运算」的简易下拉，而是**在目标表达式的分层着色公式上点选节点**：

| 组成 | 说明 |
|---|---|
| 可点选公式 | 后端用 `LatexPrinter(colorize=True, id_prefix="dlg__")` 重渲染目标卡片（独立 id 前缀，不与主画布冲突），MathJax SVG + 透明命中区；点节点显示虚线选中框与「类型 · 第 N 层 · 表达式」 |
| 信息区 | 目标卡片、拖拽节点类型与文本、「运算顺序：选中节点 运算 拖拽节点」（拖拽节点为零时额外提示） |
| 操作按钮（互斥） | 6 个基础：替换 / 加 / **减** / 乘 / 除 / 乘方；2 个 **Div 专用**：上下同乘 / 上下同除（仅选中分式节点时启用）；3 个单目：取倒数 / 平方 / 算术平方根 |
| 确定 | 未选节点或未选操作时禁用；结果**只替换目标表达式中的选中节点**（`_replace_node` 负责 Add/Mul 展平），可撤销；切换到非 Div 节点会自动清掉已选的 Div 专用操作 |
| 后端 | `dropNode` 返回 `latex` / `info` / `nodeType` / `nodeText` / `nodeZero` 并保存对话框节点映射；`applyNodeOp` 接收 `target_node_id`，按桌面版 `_apply` 语义构造子树，对零节点作为除数或上下同乘/同除给出明确报错 |

**触摸拖拽修复**（针对「卡片 / 节点拖到一半断触」）：

| 原问题 | 修复 |
|---|---|
| 页面缺 `viewport` meta，触摸坐标与 CSS 像素不一致 | 补 `width=device-width, initial-scale=1.0` |
| 拖拽 handle 未设 `touch-action`，Android WebView 把滑动判成画布滚动并派发 `pointercancel` | `.drag-handle` / `#node-handle` / `#drag-overlay` 设 `touch-action: none`；`pointermove` 以 `{passive:false}` 阻止默认滚动 |
| `pointermove/up/cancel` 绑在会被隐藏或随 MathJax 重排被替换的 handle 上，指针捕获丢失 | 移动/结束统一挂 `document`，按 `pointerId` 过滤多指；指针捕获改到常驻的 `document.body` |
| 拖拽中 scroll 事件会 `hideSelection()` 把节点拖拽手柄设为 `display:none` | scroll 回调在拖拽期间直接返回 |
| 24px / 20px 的拖拽圆点在触屏上难以按准 | 用 `::after` 把命中区扩大到 40px 左右，视觉尺寸不变 |
| 手指移出手柄后事件中断 | 拖拽期间启用全屏 `#drag-overlay` 代理层接管指针，结束即隐藏 |

卡片拖拽与节点拖拽共用这一套全局监听；碰撞回退、`moveItem` / `dropNode` 桥接逻辑保持不变。

---

## 二、在 Android Studio 编译出 APK

### 1. 准备环境（一次性）
- **Android Studio**（Hedgehog / Iguana / Jellyfish / Koala 及以上）
- **JDK 17**（Android Studio 自带）
- **Android SDK Platform 34**：SDK Manager → SDK Platforms → 勾选 Android 14 / API 34
- **Python 3.11 (64-bit)**：见「零、最常见的两个编译失败」——**这是硬性前置条件**
- **联网**（仅首次构建：Gradle 插件、Chaquopy 私有源、国内 PyPI 镜像；见「零、3」）

### 2. 打开并构建
1. `File → Open` 选择本工程根目录（含 `build.gradle` 的 `CalculusCalculator-Android` 文件夹）
2. 等待 **Gradle Sync**（自动下载 Gradle 8.9、生成 `gradle-wrapper.jar`）
3. `Build → Build Bundle(s) / APK(s) → Build APK(s)`
4. 产物：`app/build/outputs/apk/debug/app-debug.apk`（传到手机安装即可）
5. 正式发布：`Build → Generate Signed Bundle / APK` 配置签名

### 3. 命令行（可选）
```bash
gradlew.bat assembleDebug
```
> `gradle-wrapper.jar` 由 Android Studio 导入时自动生成；纯命令行请先执行
> `gradle wrapper --gradle-version 8.9`。

### 4. 构建报错速查
| 报错 | 处理 |
|---|---|
| `Couldn't find Python` | 装 Python 3.11 并勾选 Add to PATH，重启 Android Studio；或配 `chaquopy.buildPython` |
| `Theme.DevicesDefault.NoActionBar not found` | 已修复；若你改过 `themes.xml`，用 `Theme.Material.Light.NoActionBar` |
| `ReadTimeoutError` / `Read timed out`（`files.pythonhosted.org`） | 见「零、3」：已默认改用阿里云镜像 + 加大超时；旧工程替换 5 行 `options(...)` 即可 |
| `Chaquopy_cannot_compile_native_code` / `numpy-*.tar.gz` 编译失败 | 见「零、3」：必须同时写明 `--extra-index-url https://chaquo.com/pypi-13.1/` 与 `--only-binary=:all:`；仅换 PyPI 镜像会挤掉私有源 |
| `可能已分配变量 out` / `variable out might already have been assigned` | 已修复：`MainActivity.java` 三处 blank final 在 try/catch 双赋值，改为「非 final 中间变量 + 一次 final 赋值」 |
| pip 下载 `latex2sympy2_extended` 失败 | 注释掉 `app/build.gradle` 中该 `install` 行；纯 SymPy 输入不受影响（`core/sympify.py` 已延迟导入），仅 `$LaTeX$` 输入降级 |
| `No matching variant` / NDK 相关 | 本工程不需要 NDK，确认未被旧配置残留覆盖 |
| `lintVitalAnalyzeRelease` / `groovy:3.0.17` / `httpclient:4.5.6` 返回 403 Forbidden | Release 构建专用的 lint 检查要从 Maven Central 拉依赖，国内常被拒。已禁用 `checkReleaseBuilds` 并配置阿里云 Maven 镜像，见下方说明 |

**Release 构建的 lint 403**：`lintVitalAnalyzeRelease` 是 AGP 打 Release 包时自动插入的检查，
运行期通过 `detachedConfiguration` 解析 `lint-gradle:31.5.2` 的传递依赖（`groovy:3.0.17`、
`httpclient:4.5.6` 等），这些只存在于 Maven Central，国内直连常返回 403 Forbidden。本工程做两层处理：

- `app/build.gradle` 的 `android { lint { checkReleaseBuilds = false; abortOnError = false } }`
  让 AGP 不把 lintVital 挂到 `assembleRelease` 依赖链上，从根源不再解析这些依赖；lint 不是产出
  APK 的必需步骤，不影响任何功能。
- `settings.gradle` 的 `pluginManagement` 与 `dependencyResolutionManagement` 两个仓库块，在官方源
  之前加了阿里云镜像（`repository/public`、`repository/google`、`repository/gradle-plugin`）作为
  其它 Maven 依赖的兜底；官方 `google()`、`mavenCentral()`、`maven.chaquo.com` 保留在后，缺件时
  自动回退。实测镜像已覆盖 `groovy:3.0.17` 与 `httpclient:4.5.6`。

若确需跑 lint，可执行 `gradlew.bat lintDebug`（Debug 变体不走 lintVital），或把
`checkReleaseBuilds` 改回 `true` 并确保构建机可访问 Maven Central。

---

## 三、运行原理

```
┌──────────────────────── 安卓 App ──────────────────────────┐
│ MainActivity.java：顶部 3 个 Tab，共用 1 个 Python 进程      │
│  ┌ 计算器 ──────────┐┌ 积木模式 ────────┐┌ 解几计算器 ──────┐│
│  │ AndroidBridge.   ││ AndroidBridge.   ││ AndroidBridge.   ││
│  │   compute(json)  ││  runBlockly(code)││   canvas(json)   ││
│  └────────┬─────────┘└────────┬─────────┘└────────┬─────────┘│
│           │   @JavascriptInterface（注入名 AndroidBridge）    │
│           ▼                   ▼                   ▼          │
│        Python 运行时（APK 内嵌，Chaquopy，单线程串行）        │
│   calc_engine      blockly_engine      expr_canvas_engine    │
│      │                  │                    │              │
│   原项目计算模块    生成的 Python 代码     expr_tree 表达式树 │
│   sympy/matplotlib  （复用计算模块）      LatexPrinter 着色  │
│           │                  │                    │          │
│   LaTeX+PNG 回传    结构化输出→MathJax   actions→画布更新    │
│   Calc.onResult     renderBlocklyResult  applyCanvasResult   │
└─────────────────────────────────────────────────────────────┘
```

三个 WebView 分别注入 `AndroidBridge` 实例（回帖到各自页面）。所有 Python 调用串行化到单线程
executor，避免并发与线程状态问题。Python 包、Blockly、MathJax、MathLive 全部随 APK 打包。

---

## 四、目录结构

```
CalculusCalculator-Android/
├── build.gradle / settings.gradle       # AGP 8.5.2 + Chaquopy 15.0.1
├── gradle.properties                   # 可选：chaquopy.buildPython 覆盖
├── app/build.gradle                    # ★ chaquopy { defaultConfig { version/buildPython/pip } }
├── app/src/main/
│   ├── AndroidManifest.xml
│   ├── java/.../MainActivity.java       # 3 WebView + AndroidBridge（compute/canvas/runBlockly...）
│   ├── res/                             # 布局 / 主题（顶部 3 Tab）+ 桌面版同款启动图标
│   │   ├── mipmap-*/                    #   ic_launcher.png / ic_launcher_round.png（5 档密度）
│   │   ├── drawable-*/                  #   ic_launcher_foreground.png（自适应图标前景）
│   │   └── mipmap-anydpi-v26/           #   自适应图标 XML（API 26+）
│   ├── assets/
│   │   ├── favicon.ico                         # 桌面版原始图标资源（三页 <link rel="icon"> 引用）
│   │   ├── index.html / app.js / styles.css    # 功能集成页（计算器页唯一页面）
│   │   ├── mathkeyboard.js / .css             # ★ 两页共享：内嵌 ∑ 按钮 + MathLive 原生键盘
│   │   ├── mathlive/                           # 离线 MathLive（两页共用，含 KaTeX 字体）
│   │   ├── blockly/                            # ★ 离线积木编辑器
│   │   ├── expr_canvas/                        # ★ 解几计算器表达式画布
│   │   │   ├── index.html                      #   原 expr_viewer.PAGE（已改 AndroidBridge + 触摸拖拽）
│   │   │   ├── extra.css / extra.js            #   工具栏 / 对话框（含拖拽节点）/ 回帖
│   │   └── mathjax/                            # 离线 MathJax（含 color.js / html.js 补丁）
│   └── python/                          # ★ 打进 APK 的 Python 代码
│       ├── calc_engine.py               # 功能集成入口 compute(json) + latexToExpr 公式转换
│       ├── functions_page.py            # ★ functions.ui 三区：定义区/计算区/绘图区 + 规格
│       ├── blockly_engine.py            # 积木引擎 execute_blockly(code)
│       ├── expr_canvas_engine.py        # ★ 表达式画布引擎 handle(json) + latexToExpr 公式转换
│       ├── core/sympify.py              # 原项目表达式解析（去 Qt 依赖）
│       ├── core/render.py               # 主题着色（Qt 无关替身）
│       ├── functions/                   # 原项目纯计算模块（原样复用）
│       │   ├── derivative.py / integral.py / simplification.py / solvers.py
│       │   ├── functions.py / paint2D.py / planes.py / solids.py / paint3D.py
│       │   └── __init__.py              # 重导出，供积木生成代码 import
│       └── expr_calculator/expr_tree.py # 表达式树 + LatexPrinter 分层着色
└── README.md
```

---

## 五、输入格式与示例

| 场景 | 示例 |
|---|---|
| 表达式语法 | `x**2 + 2*x**2`、`sin(x)`、`x**2 = 4`；也可点输入框内最右侧 `∑` 用 MathLive 键盘可视化输入 |
| 求导 | `x**3`，阶数 `2` → `6*x` |
| 定积分 | `x**2`，下限 `0`，上限 `1` → `1/3` |
| 解方程 | `x**2 = 4`，定义域 `Reals` → `{-2, 2}` |
| 解方程组 | 两行 `x + y = 3` / `x - y = 1`，未知量 `x,y` |
| 解不等式组 | 两行 `x > 0` / `x < 5` → `(0, 5)` |
| 换元 | 表达式 `x**2+1`，换元符号 `t`，换元式 `x-1` → `t**2+2t+2` |
| 数值计算 | `2+3*4`；Mpmath 引擎可填 `dps=30` 算 `mp.pi` |
| 定义函数 | 名称 `f`，表达式 `x**2+1` → 之后 `f(3)` 得 `10` |
| 解三角形 | 角度带 `°`（`A=30°,B=60`），边长如 `a=5` |
| 表达式画布 | `2*(x+1) + 1/(x-1)`、`x^2=4`（支持 `^`、隐式乘法、单个 `=`） |
| 功能集成·定义点 | 定义区选「平面几何」→ 点 → 按坐标创建 → 名称 `p1`，x=`0`，y=`0` |
| 功能集成·定义三角形 | 定义区选「平面几何」→ 三角形 → 三点创建 → 名称 `t1`，依次选 `p1,p2,p3` |
| 功能集成·几何计算 | 计算区选「平面计算」→ 三角形 → 面积 → 选择 `t1` → `6` |
| 功能集成·解方程组 | 计算区选「解方程组」→ 数量 `2` → 变量 `x,y` → 逐行填左式 / 右式 |
| 功能集成·解三角形 | 计算区选「解三角形」→ 3 组条件类型下拉（角 A / 边 a …）+ 条件值 |
| 功能集成·绘图 | 绘图区选「平面几何模式」，勾选 `p1`、`t1` 后点「绘制」；「函数模式」绘制已定义函数 |
| 功能集成·保存为 | 计算前在「保存为」填 `h`，结果自动存入函数表，之后可写 `h(3)` |

---

## 六、如何扩展

- **加 Python 依赖**：编辑 `app/build.gradle` 的 `chaquopy { defaultConfig { pip { install "包名" } } }`。
- **加计算器算子**：在 `python/calc_engine.py` 的 `_DISPATCH` 登记新 `op`；若要暴露到功能集成页，
  在 `python/functions_page.py` 的规格表加一项，并在 `assets/app.js` 的 `Fp.calcRows()` 补对应输入行。
- **给新输入框加数学键盘**：把文本框与一个带 `data-kbd="该id"` 的 `.kbd-open` 按钮一起包进
  `<div class="kbd-field-row">`（按钮会自动贴在输入框内部最右），共享模块 `assets/mathkeyboard.js`
  的全局委托会自动接管；动态生成的输入框用法见 `Fp.renderRows()`。
- **加功能集成页的对象 / 运算**：编辑 `python/functions_page.py` 的 `PLANE_GEOMETRY` /
  `SOLID_GEOMETRY` / `PLANE_OPS` / `SOLID_OPS`，`spec()` 会自动把新规格推给前端动态渲染，
  无需改 HTML。
- **加积木类型**：在 `assets/blockly/blocks.js` 增加积木定义与 Python 生成器；若调用新的 Python
  辅助函数，在 `python/blockly_engine.py` 的 `env` 中登记。
- **加画布操作**：在 `python/expr_canvas_engine.py` 的 `_run()` 增加 action，返回值用
  `{"fn": "JS函数名", "args": [...]}` 描述前端动作；对话框类型在 `assets/expr_canvas/extra.js` 扩展。

---

## 七、已知限制（不影响核心计算）

1. **渲染图片中的中文字形**：功能集成页结果图由 matplotlib 渲染，内置字体不含中文，
   「奇函数 / 偶函数」等在**图片**中显示为方框，但页面同时给出**文本结果**，不影响阅读。
   积木页与表达式画布由 MathJax 排版矢量公式，不受此限制。
2. **解三角形角度单位**：输入角度请带 `°`；不带 `°` 按弧度处理。
3. **APK 体积**：内嵌 Python + 数学库 + 三套前端资源，debug APK 约 90–140MB，属正常现象。
4. **首次启动**：Chaquopy 解压 Python 运行时约 1–2 秒；积木页 / 画布页首次切换各需约 1 秒加载资源。
5. **Qt 专属交互的等价替换**：
   - 积木页的「公式编辑器弹窗 / 缓存区弹窗」是 PySide6 模态框，已去掉输入框右侧对应按钮，
     公式仍可直接以文本/LaTeX 输入；「复制代码」改接系统剪贴板。
   - 表达式画布的「变 / 求解 / 联立 / 节点拖拽」对话框改为页内 HTML 对话框；其中节点拖拽对话框
     已按桌面版 `ExpressionDialog` 补齐**目标公式内点选节点**与 11 种运算（见 3.2）。
   - `saves.py` / 各 Qt UI 模块未移植：存档改为各页内的本地状态（Blockly 工作区、画布撤销栈）。
6. **韦达定理（联立自动消元）**：把两张方程卡片拖到重叠后选「韦达定理」，只需在「未知量」
   填一个变量（如 `x`）。引擎取两式中关于 `x` 次数较高者为主方程，用另一张方程解出两式共有的
   其它变量（如 `y = kx + m`）代入，得到关于 `x` 的一元二次方程后再给出两根之和 `S = -b/a`、
   两根之积 `P = c/a`。因此**不再依赖拖放顺序**（被拖的是直线还是椭圆都能算），结果里也会带上
   直线参数 `k`、`m`；旧实现只拿第一张卡片做 `Poly`，直线在前时会误判为一次方程而无结果。
   对话框默认只列两式共有的符号（如 `x,y`），不再把 `a,b,k,m` 等参数当未知量。若消元后仍不是
   关于该变量的一元二次方程，会提示只保留一个未知量或改用「直接求解方程组」。

---

## 八、与原桌面版的关系

本工程**复用原项目计算内核、不改动其功能逻辑**，只是把运行前端从 PySide6 桌面窗口换成安卓
WebView，并用 Chaquopy 把 Python 运行时打进 APK。三大功能（功能集成 / 积木编辑器 /
解几计算器+表达式树）均已接入，所有数学结果与原项目一致。

---

## 九、应用图标（来自桌面版 `favicon.ico`）

桌面版源码里唯一的软件图标是 `src-Release/favicon.ico`（64×64，蓝绿对角渐变圆角方块 + 白色
手写公式 `f(x)` / `f′(x)` / `∫dx` / `x=?` / `x≥y`），被三处引用：`ui/main.ui` 的 `windowIcon`、
`ui/main.py` 的 `set_app_icon()`、`setup.py` 的 `Executable(icon="favicon.ico")`。

早期工程用的是**自绘的紫色矢量占位图标**，没有使用桌面原图。原因是 `.ico` 属于 Windows 图标格式，
Android 资源编译器（aapt2）不识别，不能直接放进 `res/` —— 必须转成按密度的 PNG，并拆成自适应图标的
前景 / 背景两层。现已按原图高保真替换：

| 资源 | 内容 |
|---|---|
| `assets/favicon.ico` | 桌面版原始图标文件原样打包；三个页面 `<link rel="icon">` 引用它 |
| `res/mipmap-{mdpi,hdpi,xhdpi,xxhdpi,xxxhdpi}/ic_launcher.png` | 48 / 72 / 96 / 144 / 192 px，原图等比缩放（API < 26 与桌面式启动器使用） |
| `res/mipmap-*/ic_launcher_round.png` | 同尺寸圆形版：蓝绿渐变圆底 + 居中白色公式，公式不会被裁掉 |
| `res/drawable-*/ic_launcher_foreground.png`、`res/drawable/ic_launcher_foreground.png` | 108dp 画布，从原图分离出的**白色公式透明前景**，居中占 74%（图案落在 66dp 安全区内） |
| `res/drawable/ic_launcher_background.xml` | 自适应图标背景：线性渐变 `#0A76DD → #2198A3 → #42AD56`，取自原图采样色 |
| `res/mipmap-anydpi-v26/ic_launcher.xml` / `ic_launcher_round.xml` | API 26+ 自适应图标，背景指向渐变 drawable、前景指向白色公式 PNG，圆形/方圆形遮罩下均完整 |

`AndroidManifest.xml` 的 `android:icon="@mipmap/ic_launcher"` 与
`android:roundIcon="@mipmap/ic_launcher_round"` 保持不变，无需改动代码。
`res/values/ic_launcher_background.xml` 里的紫色 `@color/ic_launcher_background` **特意保留原值**，
因为 `layout/activity_main.xml` 仍把它当根布局背景色使用 —— 本次替换不改动任何现有布局与主题样式。

> 补充（桌面版窗口图标不显示）：`ui/main.ui` 里的 `../favicon.ico` 是 Qt Designer 的**设计期相对路径**，
> 运行期依赖当前工作目录，冻结后常常取不到。`ui/main.py::set_app_icon()` 已改为按「项目根 /
> 可执行文件同级」查找；用 Nuitka、cx_Freeze 打包时要确认 `setup.py` 的 `ICON_FILES` 把
> `favicon.ico` 复制到了 exe 同级目录，否则窗口图标仍会是系统默认图标。
