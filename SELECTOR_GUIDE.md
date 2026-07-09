# 问卷自动填写环境配置与选择器实现说明

本文说明 `auto_fill.py` 的运行环境配置方式，以及当前脚本针对该问卷页面的 DOM 选择器策略。

## 1. 项目文件

当前目录主要文件：

```text
auto_fill.py              自动填写脚本
survey_structured.json    从问卷详情接口整理出的题目结构
survey_raw.json           原始问卷接口返回
```

脚本入口：

```bash
python3 auto_fill.py
```

常用参数：

```bash
python3 auto_fill.py --headless
python3 auto_fill.py --debug
python3 auto_fill.py --seed 123
python3 auto_fill.py --headless --seed 123
```

说明：

- `--headless`：无头浏览器运行。
- `--debug`：保存截图和调试信息。
- `--seed 123`：固定随机种子，便于复现同一批选择。
- `--auto-submit`：填完后自动提交。默认不会提交，建议人工检查后再提交。

## 2. 环境配置

### 2.1 Python

建议使用 Python 3.9 及以上。

检查版本：

```bash
python3 --version
```

### 2.2 安装 Selenium

```bash
python3 -m pip install selenium
```

如果本机有多个 Python，确认安装到当前运行脚本使用的 Python：

```bash
python3 -m pip show selenium
```

### 2.3 Chrome 浏览器与 ChromeDriver

脚本使用 Selenium 启动 Chrome：

```python
driver = webdriver.Chrome(options=opts)
```

需要满足：

- 本机已安装 Chrome。
- Selenium 能找到匹配版本的 ChromeDriver。

新版 Selenium 通常可以自动管理 driver。如果启动失败，可以手动安装 ChromeDriver，或升级 Selenium：

```bash
python3 -m pip install --upgrade selenium
```

### 2.4 语法检查

macOS 上直接 `python3 -m py_compile auto_fill.py` 可能尝试写入用户缓存目录。可以指定 pycache 到 `/tmp`：

```bash
PYTHONPYCACHEPREFIX=/tmp python3 -m py_compile auto_fill.py
```

### 2.5 测试运行

推荐先无头测试，不自动提交：

```bash
python3 auto_fill.py --headless --seed 123
```

期望输出里应看到各题型成功，例如：

```text
✓ [级联]
✓ [单选]
✓ [多选]
✓ [矩阵]
✓ [省市]
```

## 3. 数据来源

这个问卷页面是 Vue 单页应用，首页 HTML 里只有应用壳：

```html
<div id="app"></div>
<script src="js/app.1a17a1dc.js"></script>
```

题目不是直接写在 HTML 里，而是前端运行后请求接口。

当前问卷链接：

```text
https://myd.iscn.org.cn/#/s/yCWFPyRr?sourceID=719419
```

其中：

```text
formKey = yCWFPyRr
```

问卷详情接口：

```text
https://myd.iscn.org.cn/tduck-api/user/form/details/yCWFPyRr?sourceId=719419
```

核心字段：

```text
data.formItems[]
formItemId
type
textLabel / title
scheme.config.options
scheme.table.rows
```

脚本不是靠猜“第几个题”，而是依赖 `survey_structured.json` 里的 `formItemId`、题型和选项文本。

## 4. 总体选择器原则

当前脚本的核心策略是：

```text
先用 formItemId 锁定当前题容器
再只在当前题容器内部找选项
弹层类控件再去全局 popup 中找当前打开的菜单
点击后读取页面状态验证是否真的选中
```

不要优先使用：

```css
input:nth-of-type(...)
.el-radio:nth-child(...)
.el-cascader-node:nth-child(...)
```

这些选择器对页面结构变化非常敏感，也容易点错题。

推荐优先使用：

```css
[formitemid="radio-1779699470812"]
[formitemid="checkbox-1779699997836"]
[formitemid="cascader1781763870534"]
[formitemid="province_city1779700972110"]
```

## 5. 单选题选择器实现

对应函数：

```python
fill_radio(driver, item)
```

### 5.1 真实 DOM

这个页面的单选题不是标准 ElementUI 结构：

```css
label.el-radio
```

实际渲染为自定义块：

```html
<div formitemid="radio-1779699470812" class="el-radio-group">
  <div class="flattening-wrap grid-auto">
    <div class="flattening-item">少于 1 小时</div>
    <div class="flattening-item">1-2 小时</div>
    <div class="flattening-item">3-4 小时</div>
  </div>
</div>
```

点击后选中项会增加：

```css
.active
```

### 5.2 当前策略

先锁定当前题容器：

```js
document.querySelector('[formitemid="' + FORM_ITEM_ID + '"]')
```

再只在当前容器内查找选项：

```js
container.querySelectorAll('.flattening-item, label.el-radio, .el-radio')
```

匹配选项文本时会去掉空白：

```js
function norm(s) {
  return (s || '').replace(/\s+/g, '');
}
```

找到目标元素后，不能用 JS 的 `element.click()`，因为这个页面不会触发完整选中态。脚本使用 Selenium 原生点击：

```python
target.click()
```

点击后验证：

```js
el.className.indexOf('active') >= 0 ||
el.className.indexOf('is-checked') >= 0 ||
input.checked
```

## 6. 多选题选择器实现

对应函数：

```python
fill_checkbox(driver, item)
```

### 6.1 真实 DOM

多选题同样不是标准：

```css
label.el-checkbox
```

实际也是：

```css
.flattening-item
```

示例：

```html
<div formitemid="checkbox-1779699997836" class="el-checkbox-group">
  <div class="flattening-wrap grid-auto">
    <div class="flattening-item">即时通信</div>
    <div class="flattening-item">搜索引擎</div>
    <div class="flattening-item">网络购物</div>
  </div>
</div>
```

### 6.2 当前策略

先锁定题目：

```js
[formitemid="checkbox-1779699997836"]
```

再找当前题内部所有可点击项：

```js
.flattening-item, label.el-checkbox, .el-checkbox
```

逐个用 Selenium 原生点击：

```python
target.click()
```

点击后验证 `.active`：

```js
el.className.indexOf('active') >= 0
```

### 6.3 排斥选项处理

有些多选题存在排斥选项，例如：

```text
以上情况均不符合
不采取任何措施
以上都不是
```

这些选项和其他选项同时选择会导致页面自动取消其他项，或者逻辑冲突。

脚本默认过滤这些选项：

```python
if not any(x in opt["label"] for x in ("均不符合", "不采取任何措施", "以上都不是"))
```

## 7. 级联选择器实现

对应函数：

```python
fill_cascader(driver, item)
```

典型题目：

```text
1. 您上网已经有多少年（网龄）？
14. 您的年龄：
```

对应 `formItemId`：

```text
网龄：cascader1781763960123
年龄：cascader1781763870534
```

### 7.1 输入框定位

优先用 `formItemId` 找当前题：

```js
document.querySelector('[formitemid="' + FORM_ITEM_ID + '"]')
```

再找内部可见 input：

```js
input[type="text"],
input:not([type]),
input.el-input__inner
```

如果强锚点失败，再用题干和 placeholder 打分兜底：

```text
请选择网龄
请选择年龄
```

### 7.2 弹层选择

级联选项不在题目容器内部，而是挂在页面全局 popup 中。

因此点开 input 后，需要从全局找可见弹层：

```js
.el-cascader__dropdown
.el-cascader-panel
.el-popper
.t-cascader__dropdown
.t-cascader__panel
.t-popup
.t-popup__content
[class*="cascader"][class*="dropdown"]
[class*="cascader"][class*="panel"]
```

菜单列优先使用：

```js
.el-cascader-menu
.t-cascader__menu
```

选项节点：

```js
.el-cascader-node
.el-cascader-node__label
.t-cascader__item
.t-cascader__item-label
li
```

### 7.3 分级点击

例如年龄选择：

```text
51-60 > 59
```

执行流程：

```text
点击年龄 input
在第 0 列找 51-60 并点击
等待第 1 列出现
在第 1 列找 59 并点击
读取 input.value 验证
```

代码中使用 `WebDriverWait` 等待每一级渲染，而不是在 JS 里死循环等待。这样不会阻塞 Vue 更新。

## 8. 省市选择器实现

对应函数：

```python
fill_province_city(driver, item)
```

对应 `formItemId`：

```text
province_city1779700972110
```

### 8.1 为什么不能只靠 placeholder

常住地输入框 placeholder 是：

```text
请选择
```

年龄、网龄等输入框也可能有类似“请选择”。如果只靠 placeholder，容易误点到年龄级联。

因此省市必须优先用：

```js
[formitemid="province_city1779700972110"]
```

### 8.2 防止误用年龄弹层

省市弹层必须包含省份文本：

```text
北京
上海
广东
```

脚本用这个条件过滤弹层，避免把年龄弹层当成省市弹层。

### 8.3 支持两级或三级

有些地区是两级：

```text
北京 / 东城区
天津 / 和平区
```

有些地区是三级：

```text
内蒙古自治区 / 赤峰市 / 巴林右旗
```

脚本最多尝试点击 3 级：

```text
省/直辖市
市/区
区县
```

每点击一级后等待下一列出现；如果弹层关闭或没有下一列，就停止。

## 9. 矩阵星级题实现

对应函数：

```python
fill_matrix_scale(driver, item)
```

真实 DOM 结构是自定义表格：

```html
<div formitemid="matrix_scale1779765006292" class="rt-container">
  <div class="rt-table">
    <div class="tr t-header">...</div>
    <div class="tr">
      <div class="td">网络不良信息治理成效：</div>
      <div class="el-rate rate">
        <span class="el-rate__item">...</span>
      </div>
    </div>
  </div>
</div>
```

### 9.1 行定位

不能用：

```css
[class*=row]
```

因为它会匹配页面外层的 `.el-row`，导致所有星星都从同一个大容器里找，实际只点第一行。

当前只在当前矩阵题内部找真实行：

```js
.tr:not(.t-header),
tr,
.el-table__row,
[class*="matrix-row"],
[class*="table-row"]
```

### 9.2 星星定位

每行内部查找评分节点：

```js
.el-rate__item
.el-rate__icon
[class*="rate"] i
[class*="rate"] svg
[class*="star"]
```

如果目标分值是 8，则点击该行第 8 个星星：

```js
nodes[SCORE - 1].click()
```

验证方式是读取每行评分组件的：

```html
aria-valuenow
```

例如：

```text
matrix_scale1779765006292 rates: 8,8,8,8,8
```

## 10. 残留弹层处理

级联和省市控件会生成全局 popup。上一个弹层如果没关闭，后续题目可能误用旧弹层。

脚本在打开级联/省市/单选/多选前，会先发送 `ESCAPE`：

```python
close_open_popups(driver)
```

实现：

```python
driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
```

## 11. 调试方法

### 11.1 开启截图

```bash
python3 auto_fill.py --debug --headless --seed 123
```

会在当前目录生成：

```text
debug_page_loaded.png
debug_cascader_before_*.png
debug_cascader_after_*.png
```

### 11.2 查看某题真实 DOM

浏览器控制台可用：

```js
document.querySelector('[formitemid="radio-1779699470812"]').innerHTML
```

查看选中项：

```js
Array.from(
  document.querySelectorAll('[formitemid="radio-1779699470812"] .flattening-item.active')
).map(el => el.textContent.trim())
```

查看矩阵评分：

```js
Array.from(
  document.querySelectorAll('[formitemid="matrix_scale1779765006292"] .el-rate')
).map(el => el.getAttribute('aria-valuenow'))
```

查看级联值：

```js
document.querySelector('[formitemid="cascader1781763870534"] input').value
```

查看省市值：

```js
document.querySelector('[formitemid="province_city1779700972110"] input').value
```

## 12. 当前验证结论

已用无头模式验证：

```bash
python3 auto_fill.py --headless --seed 123
```

并额外读取页面 DOM 状态确认：

```text
单选题：当前题内 .flattening-item.active
多选题：当前题内多个 .flattening-item.active
矩阵题：每行 .el-rate 的 aria-valuenow
级联题：当前题 input.value
省市题：当前题 input.value
```

关键结论：

```text
单选/多选必须使用 Selenium 原生 WebElement.click()
不能只用 JS element.click()
题目必须优先用 formItemId 锚定
弹层类控件必须防止复用旧 popup
矩阵题必须按真实 .tr 行逐行定位
```
