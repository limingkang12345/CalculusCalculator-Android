# CalculusCalculator 安卓工程（Chaquopy 内嵌 Python · 完全离线）

把 **CalculusCalculator（微积分计算器）** 打包成安卓 App：**APK 内嵌 Python 3.11 + SymPy/NumPy/Matplotlib**，
所有计算都在手机本地完成，**安装后无需联网、无需服务器**。

原项目是 Python 3.10+ / PySide6 桌面程序。本工程**不改其计算内核**，直接复用原项目的纯计算模块与
表达式树、Blockly 积木定义，仅把运行前端从 PySide6 窗口换成安卓 WebView + Chaquopy。

---

## 一、三大功能（对应原项目 `ui/__init__.py` 的 tabs_dict）

| 原项目 Tab | 安卓端 | 实现 |
|---|---|---|
| **功能集成** | 顶部「计算器」Tab + **「功能集成」Tab** | `calc_engine.py` + 5 个板块，另加 `functions_page.py` 完整复刻 `functions.ui` 的定义区 / 计算区 / 绘图区 |
| **积木编辑器** | 顶部「积木模式」Tab | 离线 Blockly + `blockly_engine.py` |
| **解几计算器 + 表达式树** | 顶部「解几计算器」Tab | `expr_canvas/index.html` 表达式画布 + `expr_canvas_engine.py` + `expr_tree.py` |

### 1. 功能集成（计算器）
| 板块 | 内容 |
|---|---|
| 微积分 | 13 种表达式变形（含指数展开、换元）/ 求导 / 积分 / 解微分方程 / 方程·不等式·方程组·不等式组 / 函数性质 / 解三角形 / 函数绘图 |
| 数值计算 | 四种计算引擎：Python 内置 / Mpmath 高精度（可设 dps）/ SymPy 符号 / LaTeX 代码生成 |
| 定义区 | 定义函数 `f(x)=x**2+1`，之后可直接写 `f(3)`、`f(g(2))` 参与运算 |
| 平面几何 | 30 类运算（距离、直线、圆、三角形各类心、多边形、平移/旋转/反射、向量） |
| 立体几何 | 37 类运算（点线面距离/投影/夹角、四面体体积、平面交线、向量叉积、斜二测换算） |
| 3D 绘图 | 点/线/线段/射线/平面，生成关系图 |
| 表达式树 | 结构化变形（化简/展开/因式分解/约分/通分/拆分/三角化简/有理化） |

结果以 **LaTeX + PNG**（matplotlib 离线渲染）展示；输入支持 SymPy 语法与 `$LaTeX$`。

### 1.1 完全对齐桌面版 `ui/functions.ui` 的「功能集成」页

顶部新增第 6 个 Tab **「功能集成」**，按原桌面版 `functions.ui` 的三区布局完整复刻。规格由
`python/functions_page.py` 提供（常量与原版 `ui/functions.py` 逐项一致），前端据此动态生成输入表，
无需改动 Java 桥接，仍走 `AndroidBridge.compute`。

| 区 | 对齐内容 |
|---|---|
| **定义区** | 5 种类型：函数（名称/表达式/定义域/自变量）、集合、向量、平面几何（6 类对象 × 多种创建方式）、立体几何（4 类对象 × 多种创建方式）；对象树（类型→对象→属性）、编辑定义 / 删除定义 / 保存输入 / 清空输入、预览与「直接模式 / 替换模式」、输出 |
| **计算区** | 原版 11 项：计算（4 引擎）、求导、积分、解方程、解不等式、解方程组、解不等式组、平面计算、立体计算、变形（13 种）、解三角形；动态输入表（左右式分离、不等号下拉、方程/不等式数量按行展开、3 组条件类型下拉）、清空、结果预览、**保存为**（把结果存为自定义函数） |
| **绘图区** | 3 种模式：平面几何模式 / 立体几何模式 / 函数模式；可勾选对象列表，绘制已定义几何对象或自定义函数 |

几何对象按**名称引用**：先在定义区创建点 / 线 / 圆 / 三角形 / 平面等，再在「平面计算 / 立体计算」
从下拉框选择，共 **32 项平面运算 + 22 项立体运算**，复用原项目 `functions/planes.py`、`solids.py`。
绘图复用 `paint2D.draw2d` / `paint3D.draw3d` / `paint2D.draw_functions`。

> 原有「微积分 / 平面几何 / 立体几何 / 3D 绘图 / 表达式树」5 个 Tab **全部保留**（直接坐标输入的
> 30 / 37 类运算继续可用）；功能集成页是增量补齐，不回退任何既有能力。两处的函数定义表共享，
> 在任一处定义 `f` 后，另一处可直接写 `f(3)`。

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
- 两张方程卡片重叠：联立求解 / 韦达定理，结果生成带注释卡片
- 节点拖拽到另一张卡片：弹出操作对话框，把拖拽节点应用到目标表达式
- 画布级 **撤销 / 重做**
- **可视化数学键盘**：输入框右侧的 `∑` 按钮（对话框里「输入表达式」旁也有）打开公式键盘

> 原桌面版的 Qt 模态对话框在此以页内 HTML 对话框等价实现；QWebChannel 桥接替换为
> `AndroidBridge`（WebView `addJavascriptInterface`）。

#### 3.1 可视化数学键盘与触摸拖拽

**数学键盘**对齐桌面版 `math_input/MathLiveDialog`，资源全部离线（`assets/mathlive/dist/`，含 KaTeX 字体）：

| 组成 | 说明 |
|---|---|
| WYSIWYG 公式域 | MathLive `<math-field>`，可视化显示分数 / 根式 / 上下标，`virtual-keyboard-mode="manual"` + `inputmode="none"` 避免与系统软键盘冲突 |
| 6 组符号键盘 | 基础（数字/四则/括号）、变量、结构（分数/根式/幂/积分/求和）、函数（三角/对数/双曲）、关系（不等号/集合）、希腊字母 |
| 编辑工具 | 左右移动光标、退格、清空；LaTeX 实时预览；分组标签切换 |
| 回填链路 | 确定 → `kbdNormalizeLatex()` 补全 `\sqrt3`/`\frac12` 这类省略花括号 → `AndroidBridge.canvas({action:"latexToExpr"})` → Python `sympify('$'+latex, {})` 转 SymPy 表达式字符串 → 填回目标输入框 |
| 降级 | MathLive 未加载时自动改用 `<textarea>` 纯 LaTeX 输入，按钮仍可在光标处插入片段，链路不变 |

输入框、卡片变换/求解/联立等对话框里的表达式输入框都可用。转换结果如
`\frac{x^{2}+1}{2}` → `(x**2 + 1)/2`、`x^{2}=4` → `Eq(x**2, 4)`，可直接被画布表达式树解析；
若公式未填完整导致转换失败，会回填原始 LaTeX 并在状态栏提示，可手动修改。

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
│   ├── res/...                          # 布局 / 图标 / 主题（顶部 3 Tab）
│   ├── assets/
│   │   ├── index.html / app.js / styles.css    # 功能集成页
│   │   ├── mathlive/                           # 离线 MathLive（功能集成页 + 解几计算器共用）
│   │   ├── blockly/                            # ★ 离线积木编辑器
│   │   ├── expr_canvas/                        # ★ 解几计算器表达式画布
│   │   │   ├── index.html                      #   原 expr_viewer.PAGE（已改 AndroidBridge + 触摸拖拽）
│   │   │   ├── extra.css / extra.js            #   工具栏 / 对话框 / 可视化数学键盘 / 回帖
│   │   └── mathjax/                            # 离线 MathJax（含 color.js / html.js 补丁）
│   └── python/                          # ★ 打进 APK 的 Python 代码
│       ├── calc_engine.py               # 功能集成入口 compute(json)
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
| 化简 | `x**2 + 2*x**2` 或 `$\frac{x^2+2x^2}{1}$` |
| 求导 | `x**3`，阶数 `2` → `6*x` |
| 定积分 | `x**2`，下限 `0`，上限 `1` → `1/3` |
| 解方程 | `x**2 = 4`，定义域 `Reals` → `{-2, 2}` |
| 解方程组 | 两行 `x + y = 3` / `x - y = 1`，未知量 `x,y` |
| 解不等式组 | 两行 `x > 0` / `x < 5` → `(0, 5)` |
| 换元 | 表达式 `x**2+1`，换元符号 `t`，换元式 `x-1` → `t**2+2t+2` |
| 数值计算 | `2+3*4`；Mpmath 引擎可填 `dps=30` 算 `mp.pi` |
| 定义函数 | 名称 `f`，表达式 `x**2+1` → 之后 `f(3)` 得 `10` |
| 绘图 | 多行 `x**2` / `sin(x)`，x 范围 `-5 ~ 5` |
| 平面几何 | 点用 `x,y`，多点用分号：`0,0;3,0;0,4` |
| 立体几何 | 点用 `x,y,z`，如 `0,0,0` |
| 3D 绘图 | `point 0,0,0` / `line 0,0,0; 1,1,1` / `plane 0,0,0; 1,0,0; 0,1,0` |
| 表达式画布 | `2*(x+1) + 1/(x-1)`、`x^2=4`（支持 `^`、隐式乘法、单个 `=`） |
| 解三角形 | 角度带 `°`（`A=30°,B=60`），边长如 `a=5` |
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
- **加计算器算子**：在 `python/calc_engine.py` 的 `_DISPATCH` 登记新 `op`，
  前端在 `assets/index.html` 的 `<select>` 加选项并在 `assets/app.js` 透传参数。
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
   - 表达式画布的「变 / 求解 / 联立 / 节点拖拽」对话框改为页内 HTML 对话框；
     节点拖拽作用于**目标卡片整式**（桌面版可选目标内部节点）。
   - `saves.py` / 各 Qt UI 模块未移植：存档改为各页内的本地状态（Blockly 工作区、画布撤销栈）。
6. **韦达定理**仅对一元二次方程有效；非二次情形会给出提示。

---

## 八、与原桌面版的关系

本工程**复用原项目计算内核、不改动其功能逻辑**，只是把运行前端从 PySide6 桌面窗口换成安卓
WebView，并用 Chaquopy 把 Python 运行时打进 APK。三大功能（功能集成 / 积木编辑器 /
解几计算器+表达式树）均已接入，所有数学结果与原项目一致。
