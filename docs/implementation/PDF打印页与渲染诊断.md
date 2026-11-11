# PDF打印页与渲染诊断

日期：2026-10-28。本批继续定位PDF阻塞，未修改业务数据库、启用任务受理或发布真实内容。

## 已实现

- 从已有npm缓存读取Playwright Core 1.56.1压缩包，复制到工程可写的`.npm-cache`后离线安装。固定registry tarball URL和package-lock integrity；作为运行依赖保存。不修改系统缓存权限、不执行包安装脚本，没有下载浏览器。
- 新增`print/`共享打印工程，Vue SSR直接复用`frontend-shared/QuestionRenderer.vue`。学生版不含解析；解析版含同一原卷和另起页的答案。CSS指定A4、15mm页边距、黑白及题块尽量完整分页。
- `npm run build`包括打印工程；`npm test`先构建打印工程再验证实际SSR产物。打印资源位于忽略提交的`print/dist`，没有为打印另开HTTP服务。
- `scripts/pdf_renderer.mjs`实现内部双版PDF渲染入口：只接受结构化输入、明确本地浏览器/字体绝对路径；独立浏览器上下文，不传Cookie，离线模式、阻止请求、HTML CSP禁用脚本及远程资源。等待指定字体载入、显式render-ready标记，拒绝超出A4可用高度的单题。
- 渲染入口设60秒双版预算并关闭浏览器，记录浏览器、Playwright、Vue、输入、字体与打印资源指纹。当前仅有PDF传输格式检查（头、尾、非空），**未完成独立PDF解析器、页数、中文覆盖与实际版面验收**，返回metadata明确`pdf_parser_checked=false`，不能用于正式ready发布。
- `scripts/prepare_print_sample.py`使用既有数学生成器准备确定性开发输入；`scripts/pdf_probe.mjs`验证浏览器启动或输出两版开发样张。样张输出要求新目录，不覆盖旧输出，也不写数据库。样张只供开发，report固定`production_ready=false`。

## 实际结果

- Playwright Core 1.56.1离线安装成功，npm锁文件已更新。没有声称浏览器版本与该控制库已完成兼容验收。
- 浏览器探针失败：`stage=browser_launch`、`code=BROWSER_LAUNCH_FAILED`。已有Chrome崩溃报告为SIGABRT，调用栈位于macOS `_RegisterApplication`/`TransformProcessType`，尚未进入打印页面；具体底层原因未确定。
- 12题开发输入已通过数学引擎生成并保存到`/tmp/papr-print-sample-20261028.json`；未生成真实PDF。
- 前端13项测试通过，其中新增4项检查实际构建的SSR页面、学生/解析分离、独立起页CSS、北京时间、转义/CSP、输入约束及字体路径限制。测试使用合成字体字节，只验证HTML序列化，**不是字体/浏览器/PDF测试**。
- vue-tsc、用户端、管理端与打印页构建通过。后端业务代码未修改，本批未重复运行此前101项后端测试。
- Chrome启动失败路径真实执行过；没有用mock冒充真实PDF生成。渲染成功、超时后浏览器进程树回收及纸面A4仍待实际环境验收。

## 下一步定位命令

在普通本机终端、工程根目录执行（Node 22）：

```bash
npm run pdf:probe -- --browser "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
```

若返回`browser_ready`，说明普通终端可启动浏览器，而当前代理执行环境不可；后续可据此安排真实渲染验证。若仍为`BROWSER_LAUNCH_FAILED`，需要继续定位Chrome/系统启动环境。仅浏览器启动成功仍不代表PDF完成。

浏览器可用且准备好可嵌入的固定中文TTF/OTF/WOFF2字体后（本批未提供或确认最终部署字体），可生成开发样张：

```bash
npm run build:print
backend/.venv/bin/python scripts/prepare_print_sample.py --output /tmp/papr-print-input.json --count 12
npm run pdf:probe -- --browser "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --input /tmp/papr-print-input.json --font /绝对路径/中文字体.otf --output /tmp/papr-pdf-sample
```

输入文件和输出目录需为尚不存在的位置。字体路径是待替换示例，TTC系统字体集合目前不支持；不得直接把未经确认的系统字体复制进仓库或当作部署资源。

之后仍须接独立PDF解析器、真实字体覆盖/版面验收、worker续租、pending/ready资产、原子文件保存和成功事务、历史鉴权下载。当前`executor_ready()`仍为False，用户出卷未开放。无Git提交号、无推送或部署。


## 普通终端验证进展与一键样张（2026-10-28）

用户已在普通终端运行浏览器探针，返回`browser_ready`、Chrome `156.0.8078.48`；这确认普通终端可启动浏览器，不代表PDF/字体检查通过。用户提供HTTP代理`http://127.0.0.1:10808`后，代理执行环境显式curl测试npm/PyPI仍立即连接失败；未修改永久代理配置，不能据此判断用户普通终端的代理是否正常。

找到本机`/System/Library/Fonts/Supplemental/Arial Unicode.ttf`（约22MB），只用于本机开发样张，不复制进仓库或视为已确认部署字体。新增`scripts/check_pdf_sample.py`组合打印构建、12题数学输入、双PDF渲染、独立解析检查，每次写入独立的`backend/var/pdf-samples/北京时间日期-随机值`目录，不覆盖已有文件。

独立开发检查器`inspect_pdf_macos.py`通过Python ctypes调用系统CoreGraphics，接口签名依据本机Apple SDK头文件。检查PDF可解析、非加密、1–100页、每页纵向A4及文件SHA256；不能证明中文无缺字、纸面布局可用或数学已审定，更不能代替未来跨平台生产验证器。解析结果写入独立`parsed-report.json`，渲染阶段原report仍保留其当时的未解析状态。

3项新增解析测试通过：读取已知A4测试文档、拒绝非A4、拒绝空/截断/损坏文档。这些是合成PDF夹具，不是Chrome生成样张；尚未在本执行环境运行真实双版PDF成功流程。

普通终端在工程根目录执行：

```bash
backend/.venv/bin/python scripts/check_pdf_sample.py --node /Users/eric/.local/node-v22.23.2/bin/node
```

命令默认使用上述Chrome和Arial Unicode字体，可用`--browser`、`--font`覆盖。成功最后输出`pdf_samples_parsed`、目录及两版页数；需打开学生版/解析版人工查看中文、留白和分页。任务受理仍关闭。


## 样张反馈：竖式题双列（2026-10-28）

用户普通终端已成功生成并解析第一版12题样张：学生版4页、含原卷的解析版9页，目录`backend/var/pdf-samples/20261028-4jzssmmn`。用户查看后指出单列浪费纸张，要求竖式一行两题。

已将学生题面改为按题序每行两道，10mm列间隔、4mm行间隔，整行尽量不拆页；仍保留profile指定的35mm计算留白，奇数题末行保留单题。解析版中的原题也使用双列；答案步骤保持单列，避免压缩说明文字。旧PDF保留，新样张须重新执行一键命令生成，不能把旧样张页数当作新布局页数。代理执行环境仍不能启动Chrome，新版页数与实际分页待普通终端复验。
