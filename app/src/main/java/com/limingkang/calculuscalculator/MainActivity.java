package com.limingkang.calculuscalculator;

import android.app.Activity;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.View;
import android.view.ViewGroup;
import android.webkit.JavascriptInterface;
import android.webkit.RenderProcessGoneDetail;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.ProgressBar;

import com.chaquo.python.PyObject;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;

import org.json.JSONObject;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * CalculusCalculator 安卓端（Chaquopy 内嵌 Python，离线可运行）。
 *
 * 三大功能共用一个 Python 进程：
 *  - 功能集成  index.html              -> calc_engine.compute(json)
 *  - 积木编辑器 blockly/index.html     -> blockly_engine 系列接口
 *  - 解几计算器 expr_canvas/index.html -> expr_canvas_engine.handle(json)
 *
 * 前端通过 AndroidBridge（addJavascriptInterface 注入）调用本机 Python，
 * 结果由 Java 回帖到对应页面的 JS 全局函数。
 */
public class MainActivity extends Activity {

    private static final int VIEW_CALC = 0;
    private static final int VIEW_BLOCKLY = 1;
    private static final int VIEW_EXPR = 2;

    private WebView mainWebView;
    private WebView blocklyWebView;
    private WebView exprWebView;
    private WebView currentView;
    private ProgressBar progressBar;
    private Button tabCalc;
    private Button tabBlockly;
    private Button tabExpr;
    private boolean blocklyLoaded = false;
    private boolean exprLoaded = false;

    private ExecutorService executor;
    private final Handler mainHandler = new Handler(Looper.getMainLooper());

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        if (!Python.isStarted()) {
            Python.start(new AndroidPlatform(this));
        }
        executor = Executors.newSingleThreadExecutor();

        mainWebView = findViewById(R.id.webView);
        blocklyWebView = findViewById(R.id.blocklyWebView);
        exprWebView = findViewById(R.id.exprWebView);
        progressBar = findViewById(R.id.progressBar);
        tabCalc = findViewById(R.id.tabCalc);
        tabBlockly = findViewById(R.id.tabBlockly);
        tabExpr = findViewById(R.id.tabExpr);

        configureWebView(mainWebView);
        configureWebView(blocklyWebView);
        configureWebView(exprWebView);

        mainWebView.addJavascriptInterface(new Bridge(mainWebView), "AndroidBridge");
        blocklyWebView.addJavascriptInterface(new Bridge(blocklyWebView), "AndroidBridge");
        exprWebView.addJavascriptInterface(new Bridge(exprWebView), "AndroidBridge");

        mainWebView.loadUrl("file:///android_asset/index.html");
        switchView(VIEW_CALC);

        tabCalc.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) { switchView(VIEW_CALC); }
        });
        tabBlockly.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) {
                if (!blocklyLoaded) {
                    blocklyWebView.loadUrl("file:///android_asset/blockly/index.html");
                    blocklyLoaded = true;
                }
                switchView(VIEW_BLOCKLY);
            }
        });
        tabExpr.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) {
                if (!exprLoaded) {
                    exprWebView.loadUrl("file:///android_asset/expr_canvas/index.html");
                    exprLoaded = true;
                }
                switchView(VIEW_EXPR);
            }
        });
    }

    private void configureWebView(WebView w) {
        WebSettings s = w.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setAllowFileAccess(true);
        s.setAllowContentAccess(true);
        try { s.setAllowFileAccessFromFileURLs(true); } catch (Throwable ignored) {}
        try { s.setAllowUniversalAccessFromFileURLs(true); } catch (Throwable ignored) {}
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);

        w.setWebViewClient(new WebViewClient() {
            @Override public void onPageFinished(WebView view, String url) {
                if (view == currentView) progressBar.setVisibility(ProgressBar.GONE);
            }

            @Override public boolean onRenderProcessGone(WebView view, RenderProcessGoneDetail detail) {
                mainHandler.post(new Runnable() {
                    @Override public void run() { rebuildWebView(view); }
                });
                return true;
            }
        });
        w.setWebChromeClient(new WebChromeClient() {
            @Override public void onProgressChanged(WebView view, int p) {
                if (view != currentView) return;
                if (p < 100) {
                    progressBar.setVisibility(ProgressBar.VISIBLE);
                    progressBar.setProgress(p);
                } else {
                    progressBar.setVisibility(ProgressBar.GONE);
                }
            }
        });
    }

    private WebView createWebView(int id) {
        WebView w = new WebView(this);
        w.setId(id);
        w.setLayoutParams(new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT));
        configureWebView(w);
        w.addJavascriptInterface(new Bridge(w), "AndroidBridge");
        return w;
    }

    private void rebuildWebView(WebView old) {
        if (old == null) return;
        ViewGroup parent = (ViewGroup) old.getParent();
        if (parent == null) return;
        int index = parent.indexOfChild(old);
        int id = old.getId();
        int visibility = old.getVisibility();
        String url;
        boolean wasMain = old == mainWebView;
        boolean wasBlockly = old == blocklyWebView;
        boolean wasExpr = old == exprWebView;
        if (wasMain) url = "file:///android_asset/index.html";
        else if (wasBlockly) url = "file:///android_asset/blockly/index.html";
        else if (wasExpr) url = "file:///android_asset/expr_canvas/index.html";
        else return;
        parent.removeView(old);
        try { old.destroy(); } catch (Throwable ignored) {}
        WebView fresh = createWebView(id);
        fresh.setVisibility(visibility);
        parent.addView(fresh, index);
        if (wasMain) mainWebView = fresh;
        else if (wasBlockly) { blocklyWebView = fresh; blocklyLoaded = true; }
        else { exprWebView = fresh; exprLoaded = true; }
        if (currentView == old) currentView = fresh;
        fresh.loadUrl(url);
    }

    private void switchView(int which) {
        WebView next = (which == VIEW_CALC) ? mainWebView
                    : (which == VIEW_BLOCKLY) ? blocklyWebView : exprWebView;
        if (currentView != null && currentView != next) dismissKeyboard(currentView);
        currentView = next;
        mainWebView.setVisibility(which == VIEW_CALC ? View.VISIBLE : View.GONE);
        blocklyWebView.setVisibility(which == VIEW_BLOCKLY ? View.VISIBLE : View.GONE);
        exprWebView.setVisibility(which == VIEW_EXPR ? View.VISIBLE : View.GONE);
        tabCalc.setAlpha(which == VIEW_CALC ? 1.0f : 0.55f);
        tabBlockly.setAlpha(which == VIEW_BLOCKLY ? 1.0f : 0.55f);
        tabExpr.setAlpha(which == VIEW_EXPR ? 1.0f : 0.55f);
        progressBar.setVisibility(ProgressBar.GONE);
    }

    private void dismissKeyboard(WebView w) {
        if (w == null) return;
        w.evaluateJavascript(
                "(function(){try{" +
                "if(window.MathKeyboard&&MathKeyboard.close)MathKeyboard.close();" +
                "if(window.mathVirtualKeyboard&&window.mathVirtualKeyboard.hide)" +
                "window.mathVirtualKeyboard.hide({animate:false});" +
                "}catch(e){}})()", null);
    }

    @Override
    protected void onPause() {
        dismissKeyboard(currentView);
        super.onPause();
    }

    @Override
    protected void onDestroy() {
        if (executor != null) executor.shutdown();
        super.onDestroy();
    }

    @Override
    public void onBackPressed() {
        if (currentView != null && currentView.canGoBack()) {
            currentView.goBack();
        } else {
            super.onBackPressed();
        }
    }

    /** 同步调用 Python（用于需要立即返回值的桥接方法）。 */
    private String callPythonSync(final String module, final String attr,
                                  final String arg, final String def) {
        try {
            return executor.submit(() -> {
                PyObject m = Python.getInstance().getModule(module);
                PyObject r = (arg == null) ? m.callAttr(attr) : m.callAttr(attr, arg);
                return r.toString();
            }).get();
        } catch (Exception e) {
            return def;
        }
    }

    /** JS 可调用的桥接：每个 WebView 注入一个实例，回帖到自身页面。 */
    public class Bridge {
        private final WebView host;

        Bridge(WebView host) { this.host = host; }

        /** 功能集成：执行 calc_engine.compute，结果回帖到 window.Calc.onResult。 */
        @JavascriptInterface
        public void compute(final String requestJson) {
            executor.execute(new Runnable() {
                @Override public void run() {
                    String result;
                    try {
                        PyObject m = Python.getInstance().getModule("calc_engine");
                        result = m.callAttr("compute", requestJson).toString();
                    } catch (Exception e) {
                        result = "{\"ok\":false,\"error\":" +
                                JSONObject.quote(String.valueOf(e.getMessage())) + "}";
                    }
                    final String out = result;
                    mainHandler.post(new Runnable() {
                        @Override public void run() {
                            host.evaluateJavascript("window.Calc.onResult(" + out + ")", null);
                        }
                    });
                }
            });
        }

        /** 解几计算器：执行 expr_canvas_engine.handle，回帖到 window.applyCanvasResult。 */
        @JavascriptInterface
        public void canvas(final String requestJson) {
            executor.execute(new Runnable() {
                @Override public void run() {
                    String result;
                    try {
                        PyObject m = Python.getInstance().getModule("expr_canvas_engine");
                        result = m.callAttr("handle", requestJson).toString();
                    } catch (Exception e) {
                        result = "{\"actions\":[],\"error\":" +
                                JSONObject.quote("执行错误: " + e.getMessage()) + "}";
                    }
                    final String out = result;
                    final String jsArg = JSONObject.quote(out);
                    mainHandler.post(new Runnable() {
                        @Override public void run() {
                            host.evaluateJavascript("window.applyCanvasResult(" + jsArg + ")", null);
                        }
                    });
                }
            });
        }

        /** 积木编辑器：执行 Blockly 生成的 Python 代码，回帖到 window.renderBlocklyResult。 */
        @JavascriptInterface
        public void runBlockly(final String code) {
            executor.execute(new Runnable() {
                @Override public void run() {
                    String result;
                    try {
                        PyObject m = Python.getInstance().getModule("blockly_engine");
                        result = m.callAttr("execute_blockly", code).toString();
                    } catch (Exception e) {
                        result = "{\"outputs\":[],\"error\":" +
                                JSONObject.quote("执行错误: " + e.getMessage()) + "}";
                    }
                    final String out = result;
                    final String jsArg = JSONObject.quote(out);
                    mainHandler.post(new Runnable() {
                        @Override public void run() {
                            host.evaluateJavascript("window.renderBlocklyResult(" + jsArg + ")", null);
                        }
                    });
                }
            });
        }

        /** 积木编辑器：同步输入表格到 Python。 */
        @JavascriptInterface
        public void setInputs(final String json) {
            executor.execute(new Runnable() {
                @Override public void run() {
                    try {
                        Python.getInstance().getModule("blockly_engine").callAttr("set_inputs", json);
                    } catch (Exception ignored) {}
                }
            });
        }

        /** 积木编辑器：返回已定义函数名列表（JSON 数组字符串）。 */
        @JavascriptInterface
        public String getFunctions() {
            return callPythonSync("blockly_engine", "get_functions_json", null, "[]");
        }

        /** 积木编辑器：同步"定义函数"积木中的函数名到 Python fs。 */
        @JavascriptInterface
        public void setFunctionNames(final String json) {
            executor.execute(new Runnable() {
                @Override public void run() {
                    try {
                        Python.getInstance().getModule("blockly_engine")
                                .callAttr("set_function_names", json);
                    } catch (Exception ignored) {}
                }
            });
        }

        /** 积木编辑器：保存工作区状态。 */
        @JavascriptInterface
        public void setState(final String json) {
            executor.execute(new Runnable() {
                @Override public void run() {
                    try {
                        Python.getInstance().getModule("blockly_engine").callAttr("set_state", json);
                    } catch (Exception ignored) {}
                }
            });
        }

        /** 复制文本到系统剪贴板。 */
        @JavascriptInterface
        public void copyText(final String text) {
            mainHandler.post(new Runnable() {
                @Override public void run() {
                    ClipboardManager cm =
                            (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
                    if (cm != null) {
                        cm.setPrimaryClip(ClipData.newPlainText(
                                "code", text == null ? "" : text));
                    }
                }
            });
        }
    }
}
