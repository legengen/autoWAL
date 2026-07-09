#!/usr/bin/env python3
"""
自动填写「网民网络安全感满意度调查活动」问卷
依赖: selenium, chromedriver (Chrome 浏览器)
用法: python auto_fill.py [--debug] [--headless] [--auto-submit] [--seed 123]

  --debug       每步截图 + 打印详细 DOM 信息
  --headless    无头模式
  --auto-submit 填完自动点击提交
  --seed 123    固定随机种子
"""

import json
import random
import time
import os
import argparse
import tempfile

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# ============================================================
SURVEY_URL = "https://myd.iscn.org.cn/#/s/yCWFPyRr?sourceID=719419"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SURVEY_JSON = os.path.join(SCRIPT_DIR, "survey_structured.json")
CHROMEDRIVER = os.path.join(SCRIPT_DIR, "drivers", "chromedriver-win64", "chromedriver.exe")
DEBUG = False


def load_survey(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def init_driver(headless=False):
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--user-data-dir=" + tempfile.mkdtemp(prefix="auto-fill-chrome-"))
    opts.add_argument("--incognito")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.add_argument("--disable-features=TranslateUI")

    service = Service(CHROMEDRIVER) if os.path.exists(CHROMEDRIVER) else None
    driver = webdriver.Chrome(service=service, options=opts)
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
    })
    return driver


def scroll_to(driver, element):
    driver.execute_script(
        "arguments[0].scrollIntoView({block: 'center', behavior: 'instant'});",
        element,
    )
    time.sleep(0.15)


def close_open_popups(driver):
    """关闭上一次级联/下拉残留弹层，避免后续题目误用旧 popup。"""
    try:
        driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
        time.sleep(0.1)
    except Exception:
        pass


def debug_screenshot(driver, tag):
    path = os.path.join(SCRIPT_DIR, f"debug_{tag}.png")
    driver.save_screenshot(path)
    print(f"    [debug] 截图: {path}")


def exec_js(driver, js_code, default=""):
    """执行 JS 并安全获取返回值，防止 None 导致 json.loads 崩溃。"""
    try:
        result = driver.execute_script(js_code)
        return result if result is not None else default
    except Exception as e:
        print(f"    [JS异常] {e}")
        return default


# ============================================================
# 单选
# ============================================================
def fill_radio(driver, item):
    options = item["options"]
    picked = random.choice(options)
    label = picked["label"]
    title = item["title"][:40]
    form_item_id = item["formItemId"]

    try:
        close_open_popups(driver)
        target = driver.execute_script("""
            var FORM_ITEM_ID = arguments[0];
            var LABEL = arguments[1];

            function norm(s) {
                return (s || '').replace(/\\s+/g, '');
            }
            function visible(el) {
                if (!el) return false;
                var style = window.getComputedStyle(el);
                var rect = el.getBoundingClientRect();
                return style.display !== 'none' &&
                       style.visibility !== 'hidden' &&
                       rect.width > 0 &&
                       rect.height > 0;
            }
            var container = document.querySelector('[formitemid="' + FORM_ITEM_ID + '"]') ||
                            document.querySelector('[data-form-item="' + FORM_ITEM_ID + '"]') ||
                            document.querySelector('[data-form-item-id="' + FORM_ITEM_ID + '"]');
            if (!container) {
                return null;
            }

            var labels = Array.prototype.slice.call(container.querySelectorAll(
                '.flattening-item, label.el-radio, .el-radio'
            ));
            var target = null;
            var wanted = norm(LABEL);
            for (var i = 0; i < labels.length; i++) {
                if (!visible(labels[i])) continue;
                var txt = norm(labels[i].textContent);
                if (txt === wanted || txt.indexOf(wanted) >= 0 || wanted.indexOf(txt) >= 0) {
                    target = labels[i];
                    break;
                }
            }
            return target;
        """, form_item_id, label)

        if not target:
            print(f"  ✗ [单选] {title} 失败: option_not_found → {label}")
            return

        scroll_to(driver, target)
        target.click()
        time.sleep(0.15)
        ok = driver.execute_script("""
            var el = arguments[0];
            var input = el.querySelector('input[type="radio"]');
            return el.className.indexOf('active') >= 0 ||
                   el.className.indexOf('is-checked') >= 0 ||
                   !!(input && input.checked) ||
                   !!el.querySelector('.el-radio__input.is-checked');
        """, target)

        if ok:
            print(f"  ✓ [单选] {title}  →  {label}")
        else:
            print(f"  ✗ [单选] {title} 失败: not_checked → {label}")
    except Exception as e:
        print(f"  ✗ [单选] {item['title'][:30]}  错误: {e}")


# ============================================================
# 多选
# ============================================================
def fill_checkbox(driver, item, min_pick=2, max_pick=5):
    options = [
        opt for opt in item["options"]
        if not any(x in opt["label"] for x in ("均不符合", "不采取任何措施", "以上都不是"))
    ] or item["options"]
    n = random.randint(min_pick, min(max_pick, len(options)))
    picked = random.sample(options, n)
    picked_labels = [p["label"] for p in picked]
    form_item_id = item["formItemId"]

    try:
        close_open_popups(driver)
        targets = driver.execute_script("""
            var FORM_ITEM_ID = arguments[0];
            var TARGETS = arguments[1];

            function norm(s) {
                return (s || '').replace(/\\s+/g, '');
            }
            function visible(el) {
                if (!el) return false;
                var style = window.getComputedStyle(el);
                var rect = el.getBoundingClientRect();
                return style.display !== 'none' &&
                       style.visibility !== 'hidden' &&
                       rect.width > 0 &&
                       rect.height > 0;
            }
            var container = document.querySelector('[formitemid="' + FORM_ITEM_ID + '"]') ||
                            document.querySelector('[data-form-item="' + FORM_ITEM_ID + '"]') ||
                            document.querySelector('[data-form-item-id="' + FORM_ITEM_ID + '"]');
            if (!container) {
                return [];
            }

            var labels = Array.prototype.slice.call(container.querySelectorAll(
                '.flattening-item, label.el-checkbox, .el-checkbox'
            ));
            var found = [];

            for (var t = 0; t < TARGETS.length; t++) {
                var wanted = norm(TARGETS[t]);
                var target = null;
                for (var i = 0; i < labels.length; i++) {
                    if (!visible(labels[i])) continue;
                    var txt = norm(labels[i].textContent);
                    if (txt === wanted || txt.indexOf(wanted) >= 0 || wanted.indexOf(txt) >= 0) {
                        target = labels[i];
                        break;
                    }
                }
                if (!target) {
                    continue;
                }
                found.push(target);
            }
            return found;
        """, form_item_id, picked_labels)

        clicked_labels = []
        for target in targets:
            scroll_to(driver, target)
            is_checked = driver.execute_script("""
                var el = arguments[0];
                var input = el.querySelector('input[type="checkbox"]');
                return el.className.indexOf('active') >= 0 ||
                       el.className.indexOf('is-checked') >= 0 ||
                       !!(input && input.checked) ||
                       !!el.querySelector('.el-checkbox__input.is-checked');
            """, target)
            if not is_checked:
                target.click()
                time.sleep(0.12)
            checked_after = driver.execute_script("""
                var el = arguments[0];
                var input = el.querySelector('input[type="checkbox"]');
                return el.className.indexOf('active') >= 0 ||
                       el.className.indexOf('is-checked') >= 0 ||
                       !!(input && input.checked) ||
                       !!el.querySelector('.el-checkbox__input.is-checked');
            """, target)
            if checked_after:
                clicked_labels.append(target.text.strip())

        short = ", ".join(p[:12] for p in picked_labels)
        if len(clicked_labels) == len(picked_labels):
            print(f"  ✓ [多选] {item['title'][:35]}  →  勾 {n} 项: {short}")
        else:
            print(f"  ✗ [多选] {item['title'][:30]}  失败: {len(clicked_labels)}/{len(picked_labels)} 项选中")
    except Exception as e:
        print(f"  ✗ [多选] {item['title'][:30]}  错误: {e}")


# ============================================================
# 级联选择（网龄、年龄）—— 纯 JS 驱动 + 返回值验证
# ============================================================
CASCADER_JS = r"""
(function() {
    var TITLE = <<TITLE>>;
    var L1 = <<L1>>;
    var L2 = <<L2>>;
    var LEVELS = <<LEVELS>>;
    var FORM_ITEM_ID = <<FORM_ITEM_ID>>;

    // ---- 1. 找到当前题的 input ----
    var targetInput = null;

    // 策略 A：用 formItemId 属性匹配
    var container = document.querySelector('[formitemid="' + FORM_ITEM_ID + '"]') ||
                    document.querySelector('[data-form-item="' + FORM_ITEM_ID + '"]');
    if (container) {
        targetInput = container.querySelector('input[type="text"], input:not([type]), input.el-input__inner');
    }

    // 策略 B：遍历所有可见 input，按标题文字匹配
    if (!targetInput) {
        var allInputs = document.querySelectorAll('input');
        for (var i = 0; i < allInputs.length; i++) {
            var inp = allInputs[i];
            if (inp.offsetParent === null) continue;
            var p = inp.closest('[class*="form-item"], [class*="el-form-item"]');
            if (!p) p = inp.parentElement;
            for (var up = p; up && up !== document.body; up = up.parentElement) {
                if (up.textContent && up.textContent.indexOf(TITLE) >= 0) {
                    targetInput = inp;
                    break;
                }
            }
            if (targetInput) break;
        }
    }

    // 策略 C：找 placeholder 含 '请选择' 的可见 input
    if (!targetInput) {
        var allInputs = document.querySelectorAll('input[placeholder*="请选择"], input[placeholder*="选择"]');
        for (var i = 0; i < allInputs.length; i++) {
            if (allInputs[i].offsetParent !== null) {
                targetInput = allInputs[i];
                break;
            }
        }
        // 验证是否匹配题目
        if (targetInput) {
            var p = targetInput.closest('[class*="form-item"], [class*="el-form-item"]');
            if (p && p.textContent.indexOf(TITLE) < 0) {
                targetInput = null;
            }
        }
    }

    if (!targetInput) {
        return JSON.stringify({ok: false, error: 'input_not_found'});
    }

    var oldValue = targetInput.value || '';

    // ---- 2. 打开级联面板 ----
    targetInput.scrollIntoView({block: 'center', behavior: 'instant'});
    targetInput.focus();
    targetInput.click();

    // ---- 3. 等待面板出现 ----
    var panel = null;
    var deadline = Date.now() + 2500;
    while (!panel && Date.now() < deadline) {
        var poppers = document.querySelectorAll(
            '.el-cascader-panel, .el-plus-cascader-panel, ' +
            '[class*="cascader"]:not([class*="cascader-node"]), ' +
            '.el-popper, [class*="popper"], ' +
            '[class*="dropdown"]:not([class*="dropdown-item"]), ' +
            '[class*="cascader-menus"]'
        );
        for (var j = 0; j < poppers.length; j++) {
            try {
                var cs = window.getComputedStyle(poppers[j]);
                if (cs.display !== 'none' && cs.visibility !== 'hidden' &&
                    poppers[j].offsetHeight > 10) {
                    panel = poppers[j];
                    break;
                }
            } catch(e) {}
        }
    }

    if (!panel) {
        return JSON.stringify({ok: false, error: 'panel_not_open', oldValue: oldValue});
    }

    // ---- 4. 在面板中找菜单列 ----
    var menus = panel.querySelectorAll(
        '.el-cascader-menu, [class*="cascader-menu"]:not([class*="node"]), ' +
        'ul, ol, .el-scrollbar__view, [class*="menu-list"]'
    );
    if (menus.length === 0) menus = [panel];

    // ---- 5. 点一级 ----
    var l1Clicked = false;
    for (var m = 0; m < menus.length; m++) {
        var nodes = menus[m].querySelectorAll(
            '.el-cascader-node__label, li, [class*="cascader-node"] span, ' +
            'li span, [class*="node"] [class*="label"], li > *'
        );
        if (nodes.length === 0) nodes = menus[m].querySelectorAll('li');

        for (var k = 0; k < nodes.length; k++) {
            var txt = (nodes[k].textContent || '').trim().replace(/\s+/g, '');
            if (txt === L1.replace(/\s+/g, '') || txt.indexOf(L1.replace(/\s+/g, '')) === 0) {
                nodes[k].click();
                l1Clicked = true;
                break;
            }
        }
        // 宽松匹配
        if (!l1Clicked) {
            for (var k = 0; k < nodes.length; k++) {
                var txt2 = (nodes[k].textContent || '').trim();
                if (txt2.indexOf(L1.trim()) >= 0 && txt2.length < 30) {
                    nodes[k].click();
                    l1Clicked = true;
                    break;
                }
            }
        }
        if (l1Clicked) break;
    }

    if (!l1Clicked) {
        document.body.click();
        return JSON.stringify({ok: false, error: 'l1_not_clicked', label: L1, oldValue: oldValue});
    }

    // ---- 6. 点二级（如有） ----
    if (LEVELS >= 2 && L2) {
        // 等第二列渲染
        var menu2 = null;
        var d2 = Date.now() + 2500;
        while (!menu2 && Date.now() < d2) {
            var freshMenus = panel.querySelectorAll(
                '.el-cascader-menu, [class*="cascader-menu"]:not([class*="node"]), ul, ol'
            );
            if (freshMenus.length >= 2) menu2 = freshMenus[1];
        }

        if (!menu2) {
            document.body.click();
            return JSON.stringify({ok: false, error: 'menu2_not_found', oldValue: oldValue});
        }

        var l2Nodes = menu2.querySelectorAll(
            '.el-cascader-node__label, li span, li, ' +
            '[class*="cascader-node"] span, li > *'
        );
        if (l2Nodes.length === 0) l2Nodes = menu2.querySelectorAll('li');

        var l2Clicked = false;
        for (var k = 0; k < l2Nodes.length; k++) {
            var txt = (l2Nodes[k].textContent || '').trim();
            if (txt === L2 || txt === L2.replace(/\s+/g, '')) {
                l2Nodes[k].click();
                l2Clicked = true;
                break;
            }
        }
        if (!l2Clicked) {
            for (var k = 0; k < l2Nodes.length; k++) {
                var txt2 = (l2Nodes[k].textContent || '').trim();
                if (txt2.indexOf(L2) >= 0 && txt2.length < 20) {
                    l2Nodes[k].click();
                    l2Clicked = true;
                    break;
                }
            }
        }

        if (!l2Clicked) {
            document.body.click();
            return JSON.stringify({ok: false, error: 'l2_not_clicked', label: L2, oldValue: oldValue});
        }
    }

    // ---- 7. 验证结果 ----
    var endWait = Date.now(); while (Date.now() - endWait < 300) {}
    var newValue = targetInput.value || '';
    if (!newValue) {
        newValue = targetInput.getAttribute('value') || targetInput.getAttribute('data-value') || '';
    }
    var changed = (newValue && newValue !== oldValue) ||
                  (L1 && newValue.indexOf(L1.trim()) >= 0);
    return JSON.stringify({
        ok: changed,
        oldValue: oldValue,
        newValue: newValue,
        l1: L1, l2: L2 || ''
    });
})();
"""


def fill_cascader(driver, item):
    """用 Selenium 等待级联菜单逐级渲染，避免在 JS busy-wait 中堵住 Vue 更新。"""
    l1_options = item["options"]
    l1 = random.choice(l1_options)
    l1_label = l1["label"]
    children = l1.get("children", [])
    l2 = random.choice(children) if children else None
    l2_label = l2["label"] if l2 else None
    form_item_id = item["formItemId"]
    title = item["title"]
    placeholder = ""
    if "年龄" in title:
        placeholder = "请选择年龄"
    elif "网龄" in title:
        placeholder = "请选择网龄"

    if DEBUG:
        debug_screenshot(driver, f"cascader_before_{form_item_id}")

    try:
        close_open_popups(driver)
        target_input = driver.execute_script("""
            var FORM_ITEM_ID = arguments[0];
            var TITLE = arguments[1];
            var PLACEHOLDER = arguments[2];

            function norm(s) {
                return (s || '').replace(/<[^>]*>/g, '').replace(/\\s+/g, '');
            }
            function visible(el) {
                if (!el) return false;
                var style = window.getComputedStyle(el);
                var rect = el.getBoundingClientRect();
                return style.display !== 'none' &&
                       style.visibility !== 'hidden' &&
                       rect.width > 0 &&
                       rect.height > 0 &&
                       !el.disabled;
            }
            function firstVisibleInput(root) {
                if (!root) return null;
                var inputs = root.querySelectorAll('input[type="text"], input:not([type]), input.el-input__inner');
                for (var i = 0; i < inputs.length; i++) {
                    if (visible(inputs[i])) return inputs[i];
                }
                return null;
            }

            var selectors = [
                '[formitemid="' + FORM_ITEM_ID + '"]',
                '[data-form-item="' + FORM_ITEM_ID + '"]',
                '[data-form-item-id="' + FORM_ITEM_ID + '"]',
                '[name="' + FORM_ITEM_ID + '"]',
                '[id="' + FORM_ITEM_ID + '"]'
            ];
            for (var s = 0; s < selectors.length; s++) {
                var container = document.querySelector(selectors[s]);
                var input = firstVisibleInput(container);
                if (input) return input;
            }

            var inputs = Array.prototype.slice.call(document.querySelectorAll('input'));
            var best = null;
            var bestScore = -1;
            var titleNeedle = norm(TITLE).slice(0, 8);
            for (var i = 0; i < inputs.length; i++) {
                var inp = inputs[i];
                if (!visible(inp)) continue;

                var score = 0;
                var ph = inp.getAttribute('placeholder') || '';
                if (PLACEHOLDER && ph === PLACEHOLDER) score += 100;
                else if (PLACEHOLDER && ph.indexOf(PLACEHOLDER.replace('请选择', '')) >= 0) score += 40;

                for (var up = inp; up && up !== document.body; up = up.parentElement) {
                    var text = norm(up.textContent);
                    if (titleNeedle && text.indexOf(titleNeedle) >= 0) {
                        score += 80;
                        break;
                    }
                }

                if (score > bestScore) {
                    best = inp;
                    bestScore = score;
                }
            }
            return bestScore > 0 ? best : null;
        """, form_item_id, title, placeholder)

        if not target_input:
            print(f"  ✗ [级联] {title[:30]}  失败: input_not_found")
            return

        scroll_to(driver, target_input)
        old_value = target_input.get_attribute("value") or ""
        target_input.click()

        def click_cascader_node(level_index, label):
            return driver.execute_script("""
                var LEVEL_INDEX = arguments[0];
                var LABEL = arguments[1];

                function norm(s) {
                    return (s || '').replace(/\\s+/g, '');
                }
                function visible(el) {
                    if (!el) return false;
                    var style = window.getComputedStyle(el);
                    var rect = el.getBoundingClientRect();
                    return style.display !== 'none' &&
                           style.visibility !== 'hidden' &&
                           rect.width > 0 &&
                           rect.height > 0;
                }

                var panels = Array.prototype.slice.call(document.querySelectorAll(
                    '.el-cascader__dropdown, .el-cascader-panel, .el-popper, ' +
                    '.t-cascader__dropdown, .t-cascader__panel, .t-popup, .t-popup__content, ' +
                    '[class*="cascader"][class*="dropdown"], [class*="cascader"][class*="panel"]'
                )).filter(visible);

                for (var p = panels.length - 1; p >= 0; p--) {
                    var panel = panels[p];
                    if (norm(panel.textContent).indexOf(norm(LABEL)) < 0) continue;

                    var menus = Array.prototype.slice.call(panel.querySelectorAll(
                        '.el-cascader-menu, .t-cascader__menu'
                    )).filter(function(menu) {
                        return visible(menu) && norm(menu.textContent).length > 0;
                    });
                    if (menus.length === 0) {
                        menus = Array.prototype.slice.call(panel.querySelectorAll(
                            '.el-scrollbar__view, ul, ol'
                        )).filter(function(menu) {
                            return visible(menu) && norm(menu.textContent).length > 0;
                        });
                    }

                    if (menus.length === 0) menus = [panel];
                    var menu = menus[Math.min(LEVEL_INDEX, menus.length - 1)];
                    var nodes = Array.prototype.slice.call(menu.querySelectorAll(
                        '.el-cascader-node, .el-cascader-node__label, ' +
                        '.t-cascader__item, .t-cascader__item-label, li'
                    )).filter(visible);

                    for (var i = 0; i < nodes.length; i++) {
                        var node = nodes[i];
                        var text = norm(node.textContent);
                        if (text === norm(LABEL)) {
                            var clickTarget = node.closest('.el-cascader-node, .t-cascader__item') || node;
                            clickTarget.click();
                            return {
                                ok: true,
                                panelClass: panel.className,
                                menuCount: menus.length,
                                clickedText: node.textContent.trim()
                            };
                        }
                    }
                }
                return {ok: false};
            """, level_index, label)

        wait = WebDriverWait(driver, 8)
        def wait_click(level_index, label):
            def _attempt(_):
                result = click_cascader_node(level_index, label)
                return result if result and result.get("ok") else False
            return wait.until(_attempt)

        l1_result = wait_click(0, l1_label)
        if not l1_result.get("ok"):
            print(f"  ✗ [级联] {title[:30]}  失败: l1_not_clicked")
            return

        if l2_label:
            l2_result = wait_click(1, l2_label)
            if not l2_result.get("ok"):
                print(f"  ✗ [级联] {title[:30]}  失败: l2_not_clicked")
                print(f"        target=({l1_label}, {l2_label})")
                return

        time.sleep(0.35)
        new_value = target_input.get_attribute("value") or ""
        expected_tail = l2_label or l1_label
        ok = expected_tail in new_value or (new_value and new_value != old_value)

        if DEBUG:
            debug_screenshot(driver, f"cascader_after_{form_item_id}")

        if ok:
            label = f"{l1_label} > {l2_label}" if l2_label else l1_label
            print(f"  ✓ [级联] {item['title'][:35]} → {label}")
            close_open_popups(driver)
        else:
            print(f"  ✗ [级联] {item['title'][:30]}  失败: value_not_changed")
            print(f"        old={old_value!r}  new={new_value!r}  target=({l1_label}, {l2_label or '—'})")
            if DEBUG:
                debug_info = exec_js(driver, """
                    var all = document.querySelectorAll('[class*="cascader"], .el-popper, [class*="popper"], [class*="dropdown"]');
                    var info = [];
                    for (var i=0; i<Math.min(all.length,10); i++) {
                        var el = all[i];
                        var cs = window.getComputedStyle(el);
                        info.push({
                            tag: el.tagName,
                            classes: el.className.substring(0,80),
                            display: cs.display,
                            visible: el.offsetHeight > 0,
                            text: (el.textContent||'').trim().substring(0,60)
                        });
                    }
                    return JSON.stringify(info, null, 2);
                """)
                print(f"        DOM 探测:\n{debug_info}")

    except TimeoutException:
        print(f"  ✗ [级联] {item['title'][:30]}  超时: target=({l1_label}, {l2_label or '—'})")
        if DEBUG:
            debug_screenshot(driver, f"cascader_timeout_{form_item_id}")
    except Exception as e:
        print(f"  ✗ [级联] {item['title'][:30]}  异常: {e}")


# ============================================================
# 矩阵评分
# ============================================================
MATRIX_JS = r"""
(function() {
    var FORM_ITEM_ID = <<FORM_ITEM_ID>>;
    var ROWS = <<ROWS>>;
    var SCORE = <<SCORE>>;
    var results = [];

    // 找矩阵容器
    var matrix = document.querySelector('[formitemid="' + FORM_ITEM_ID + '"]');
    if (!matrix) {
        // 退而求其次：在整个页面找包含行标签的 tr 或 .el-table__row
        matrix = document;
    }

    function norm(s) {
        return (s || '').replace(/[：:]/g, '').replace(/\s+/g, '');
    }

    function visible(el) {
        if (!el) return false;
        var style = window.getComputedStyle(el);
        var rect = el.getBoundingClientRect();
        return style.display !== 'none' &&
               style.visibility !== 'hidden' &&
               rect.width > 0 &&
               rect.height > 0;
    }

    function findRow(needle) {
        var compactNeedle = norm(needle);
        var shortNeedle = compactNeedle.slice(0, Math.min(10, compactNeedle.length));
        var candidates = matrix.querySelectorAll(
            '.tr:not(.t-header), tr, .el-table__row, [class*="matrix-row"], [class*="table-row"]'
        );
        for (var c = 0; c < candidates.length; c++) {
            var text = norm(candidates[c].textContent);
            if (text.indexOf(compactNeedle) >= 0 || text.indexOf(shortNeedle) >= 0) {
                return candidates[c];
            }
        }

        // 有些评分表把行名拆在多个内部元素里，先找到文本节点所在元素再回溯到行。
        var all = matrix.querySelectorAll('*');
        for (var i = 0; i < all.length; i++) {
            var t = norm(all[i].textContent);
            if (t.indexOf(compactNeedle) >= 0 || t.indexOf(shortNeedle) >= 0) {
                return all[i].closest('.tr:not(.t-header), tr, .el-table__row, [class*="matrix-row"], [class*="table-row"]') || all[i].parentElement;
            }
        }
        return null;
    }

    function clickScore(row) {
        var selectors = [
            '.el-rate__item',
            '.el-rate__icon',
            '[class*="rate"] i',
            '[class*="rate"] svg',
            '[class*="star"]'
        ];
        for (var s = 0; s < selectors.length; s++) {
            var nodes = Array.prototype.slice.call(row.querySelectorAll(selectors[s])).filter(visible);
            if (nodes.length >= SCORE) {
                var target = nodes[SCORE - 1];
                target.scrollIntoView({block: 'center', behavior: 'instant'});
                target.click();
                return true;
            }
        }
        return false;
    }

    for (var r = 0; r < ROWS.length; r++) {
        var needle = ROWS[r];
        var found = false;
        var row = findRow(needle);

        if (row) {
            try {
                if (clickScore(row)) {
                    results.push({row: needle, ok: true});
                } else {
                    results.push({row: needle, ok: false, error: 'score_nodes_not_found'});
                }
                found = true;
            } catch(e) {
                results.push({row: needle, ok: false, error: 'click_failed'});
                found = true;
            }
        }
        if (!found) {
            results.push({row: needle, ok: false, error: 'row_not_found'});
        }
    }
    return JSON.stringify(results);
})();
"""


def fill_matrix_scale(driver, item):
    rows = item.get("rows", [])
    if not rows:
        return
    form_item_id = item["formItemId"]
    score = random.choice([7, 8, 9])
    row_labels = [row["label"] for row in rows]

    js_code = (MATRIX_JS
        .replace("<<FORM_ITEM_ID>>", json.dumps(form_item_id))
        .replace("<<ROWS>>", json.dumps(row_labels, ensure_ascii=False))
        .replace("<<SCORE>>", str(score))
    )

    try:
        result_str = exec_js(driver, "return " + js_code.strip())
        if not result_str:
            print(f"  ✗ [矩阵] {item['title'][:30]}  JS 返回空")
            return

        results = json.loads(result_str)
        ok_count = sum(1 for r in results if r.get("ok"))
        print(f"  ✓ [矩阵] {item['title'][:35]}  ({ok_count}/{len(rows)} 行有效, 分值={score})")
        if DEBUG:
            for r in results:
                status = "✓" if r.get("ok") else f"✗ ({r.get('error','?')})"
                print(f"    {status} {r['row'][:50]}")
    except Exception as e:
        print(f"  ✗ [矩阵] {item['title'][:30]}  异常: {e}")


def fill_province_city(driver, item):
    try:
        close_open_popups(driver)
        target_input = driver.execute_script("""
            var FORM_ITEM_ID = arguments[0];
            var TITLE = arguments[1];
            function norm(s) {
                return (s || '').replace(/\\s+/g, '');
            }
            function visible(el) {
                if (!el) return false;
                var style = window.getComputedStyle(el);
                var rect = el.getBoundingClientRect();
                return style.display !== 'none' &&
                       style.visibility !== 'hidden' &&
                       rect.width > 0 &&
                       rect.height > 0 &&
                       !el.disabled;
            }
            function firstVisibleInput(root) {
                if (!root) return null;
                var inputs = root.querySelectorAll('input[type="text"], input:not([type]), input.el-input__inner');
                for (var i = 0; i < inputs.length; i++) {
                    if (visible(inputs[i])) return inputs[i];
                }
                return null;
            }

            var container = document.querySelector('[formitemid="' + FORM_ITEM_ID + '"]') ||
                            document.querySelector('[data-form-item="' + FORM_ITEM_ID + '"]') ||
                            document.querySelector('[data-form-item-id="' + FORM_ITEM_ID + '"]');
            var exactInput = firstVisibleInput(container);
            if (exactInput) return exactInput;

            var inputs = Array.prototype.slice.call(document.querySelectorAll('input'));
            var best = null;
            var bestScore = -1;
            var titleNeedle = norm(TITLE).slice(0, 8);
            for (var i = 0; i < inputs.length; i++) {
                var inp = inputs[i];
                if (!visible(inp)) continue;
                var score = 0;
                var ph = inp.getAttribute('placeholder') || '';
                if (ph.indexOf('常住') >= 0 || ph.indexOf('地区') >= 0 ||
                    ph.indexOf('省') >= 0 || ph.indexOf('市') >= 0) {
                    score += 100;
                }
                for (var up = inp; up && up !== document.body; up = up.parentElement) {
                    if (titleNeedle && norm(up.textContent).indexOf(titleNeedle) >= 0) {
                        score += 80;
                        break;
                    }
                }
                if (score > bestScore) {
                    best = inp;
                    bestScore = score;
                }
            }
            return bestScore > 0 ? best : null;
        """, item["formItemId"], item["title"])

        if not target_input:
            print(f"  ✗ [省市] 未找到输入框")
            return

        scroll_to(driver, target_input)
        old_value = target_input.get_attribute("value") or ""
        target_input.click()

        def click_first_area_node(level_index):
            return driver.execute_script("""
                var LEVEL_INDEX = arguments[0];
                function norm(s) {
                    return (s || '').replace(/\\s+/g, '');
                }
                function visible(el) {
                    if (!el) return false;
                    var style = window.getComputedStyle(el);
                    var rect = el.getBoundingClientRect();
                    return style.display !== 'none' &&
                           style.visibility !== 'hidden' &&
                           rect.width > 0 &&
                           rect.height > 0;
                }

                var panels = Array.prototype.slice.call(document.querySelectorAll(
                    '.el-cascader__dropdown, .el-cascader-panel, .el-popper, ' +
                    '.t-cascader__dropdown, .t-cascader__panel, .t-popup, .t-popup__content, ' +
                    '[class*="cascader"][class*="dropdown"], [class*="cascader"][class*="panel"]'
                )).filter(function(panel) {
                    if (!visible(panel)) return false;
                    var text = norm(panel.textContent);
                    return text.indexOf('北京') >= 0 &&
                           text.indexOf('上海') >= 0 &&
                           text.indexOf('广东') >= 0;
                });

                for (var p = panels.length - 1; p >= 0; p--) {
                    var panel = panels[p];
                    var menus = Array.prototype.slice.call(panel.querySelectorAll(
                        '.el-cascader-menu, .t-cascader__menu'
                    )).filter(function(menu) {
                        return visible(menu) && norm(menu.textContent).length > 0;
                    });
                    if (menus.length === 0) {
                        menus = Array.prototype.slice.call(panel.querySelectorAll(
                            '.el-scrollbar__view, ul, ol'
                        )).filter(function(menu) {
                            return visible(menu) && norm(menu.textContent).length > 0;
                        });
                    }
                    if (menus.length <= LEVEL_INDEX) continue;

                    var menu = menus[LEVEL_INDEX];
                    var nodes = Array.prototype.slice.call(menu.querySelectorAll(
                        '.el-cascader-node, .t-cascader__item, li'
                    )).filter(function(node) {
                        return visible(node) &&
                               norm(node.textContent).length > 0 &&
                               !node.className.match(/disabled|is-disabled/);
                    });

                    if (nodes.length > 0) {
                        var limit = Math.min(nodes.length, 6);
                        var node = nodes[Math.floor(Math.random() * limit)];
                        var text = node.textContent.trim().replace(/\\s+/g, '');
                        var clickTarget = node.closest('.el-cascader-node, .t-cascader__item') || node;
                        clickTarget.click();
                        return {ok: true, text: text, menuCount: menus.length};
                    }
                }
                return {ok: false};
            """, level_index)

        wait = WebDriverWait(driver, 8)
        def wait_click(level_index):
            def _attempt(_):
                result = click_first_area_node(level_index)
                return result if result and result.get("ok") else False
            return wait.until(_attempt)

        picked_parts = []
        province = wait_click(0)
        picked_parts.append(province.get("text", ""))

        for level_index in (1, 2, 3):
            try:
                part = WebDriverWait(driver, 2).until(
                    lambda _: (
                        lambda result: result if result and result.get("ok") else False
                    )(click_first_area_node(level_index))
                )
                picked_parts.append(part.get("text", ""))
                time.sleep(0.2)
            except TimeoutException:
                break

        time.sleep(0.35)
        new_value = target_input.get_attribute("value") or ""

        if new_value and new_value != old_value:
            print(f"  ✓ [省市] {item['title'][:35]} → {new_value}")
            close_open_popups(driver)
        else:
            print(f"  ⚠ [省市] 已点击但未验证到输入值: {' / '.join(p for p in picked_parts if p)}")
    except Exception as e:
        print(f"  ✗ [省市] 错误: {e}")


# ============================================================
# 主流程
# ============================================================

def fill_all(driver, survey, auto_submit=False):
    total = len([it for it in survey if it["type"] != "DESC_TEXT"])
    done = 0

    for item in survey:
        t = item["type"]

        if t == "DESC_TEXT":
            print(f"  — [说明] 跳过")
            continue

        if t == "RADIO":
            fill_radio(driver, item)
        elif t == "CHECKBOX":
            fill_checkbox(driver, item)
        elif t == "CASCADER":
            fill_cascader(driver, item)
        elif t == "MATRIX_SCALE":
            fill_matrix_scale(driver, item)
        elif t == "PROVINCE_CITY":
            fill_province_city(driver, item)
        else:
            print(f"  ? [未知题型] {t}: {item['title'][:30]}")

        done += 1
        time.sleep(random.uniform(0.12, 0.35))

    print(f"\n{'='*50}")
    print(f"填写完成: {done}/{total} 道题已处理")

    if auto_submit:
        print("查找提交按钮...")
        time.sleep(2)
        try:
            btns = driver.find_elements(By.XPATH,
                "//button[contains(.,'提交') or contains(.,'确认') or contains(.,'submit')]")
            if btns:
                scroll_to(driver, btns[0])
                btns[0].click()
                print("✅ 已点击提交")
                time.sleep(3)
            else:
                print("⚠ 未找到提交按钮，请手动提交")
        except Exception as e:
            print(f"⚠ 提交失败: {e}")
    else:
        print("（未开启自动提交，请手动检查后点击提交）")


def main():
    global DEBUG
    parser = argparse.ArgumentParser(description="自动填写网民网络安全感满意度调查问卷")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--auto-submit", action="store_true")
    parser.add_argument("--debug", action="store_true", help="每步截图 + DOM 探测")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--interactive", action="store_true",
                        help="填写完成后等待按 Enter 才关闭浏览器（默认不等待）")
    args = parser.parse_args()

    DEBUG = args.debug

    if args.seed is not None:
        random.seed(args.seed)
        print(f"随机种子: {args.seed}")

    print(f"加载问卷: {SURVEY_JSON}")
    survey = load_survey(SURVEY_JSON)
    print(f"共 {len(survey)} 个表单项\n")

    driver = init_driver(headless=args.headless)

    try:
        print(f"打开页面: {SURVEY_URL}")
        driver.get(SURVEY_URL)

        print("等待渲染...")
        WebDriverWait(driver, 60).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, ".el-form-item, .el-radio, .el-checkbox, .el-cascader, .form-item-component, [class*='form-item']")
            )
        )
        time.sleep(2)
        print("就绪，开始填写\n")

        if DEBUG:
            debug_screenshot(driver, "page_loaded")

        fill_all(driver, survey, auto_submit=args.auto_submit)

        if args.interactive or not args.headless:
            print("\n按 Enter 关闭浏览器...")
            try:
                input()
            except EOFError:
                print("(非交互模式，自动关闭)")
                time.sleep(3)

    except TimeoutException:
        print("⚠ 加载超时，强制尝试...")
        fill_all(driver, survey, auto_submit=False)
        time.sleep(3)
    except Exception as e:
        print(f"❌ 异常: {e}")
        import traceback
        traceback.print_exc()
        time.sleep(3)
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
