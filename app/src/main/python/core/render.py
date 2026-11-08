"""Qt 无关的渲染辅助模块（Android / Chaquopy 版本）。

原始桌面版 core/render.py 依赖 PySide6 把公式渲染进 QGraphicsView；
在安卓端我们用 matplotlib 的 Agg 后端直接出 PNG，因此这里只保留
paint2D / draw_functions 真正需要的 applyPlotTheme 函数，其余 Qt 相关
逻辑全部移除，避免引入 PySide6 依赖。
"""


def applyPlotTheme(fig, ax, theme='light'):
    """将 matplotlib Figure/Axes 适配为浅色 / 深色主题配色。

    参数:
        fig: matplotlib.figure.Figure
        ax: matplotlib Axes（2D 或 3D）
        theme: 'light' 或 'dark'
    返回:
        (bg, fg, grid_color, axis_color)
    """
    dark = theme == 'dark'
    if dark:
        bg, fg, grid_c, axis_c = '#202124', '#e8eaed', '#5f6368', '#9aa0a6'
    else:
        bg, fg, grid_c, axis_c = 'white', 'black', '#cccccc', 'black'

    fig.patch.set_facecolor(bg)
    ax.set_facecolor(bg)
    ax.tick_params(colors=fg)
    try:
        for spine in ax.spines.values():
            spine.set_color(axis_c)
    except Exception:
        for aname in ('xaxis', 'yaxis', 'zaxis'):
            axi = getattr(ax, aname, None)
            if axi is not None:
                try:
                    axi.pane.set_facecolor(bg)
                    axi.pane.set_edgecolor(axis_c)
                except Exception:
                    pass
    return bg, fg, grid_c, axis_c
