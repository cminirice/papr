# Ubuntu 22.04 部署与配置迁移

更新：2026-11-11。代码仓库：https://github.com/cminirice/papr 。

## 系统兼容性

数学组件使用Python，不依赖macOS；Ubuntu 22.04可作为部署目标。此前PDF独立解析器及worker就绪检查仅支持macOS，本次增加pypdf解析分支并解除该限制，保留macOS原生解析路径。业务时间始终为Asia/Shanghai，与服务器所在地无关。

要求Python 3.12（Ubuntu自带3.10不满足）、Node 22.12以上且小于23、锁定版本Playwright的Chromium、中文字体。不要复制Mac的虚拟环境、node_modules或Chrome路径到服务器。

验证边界：本机已执行跨平台解析器及配置导入测试；尚未在用户的Ubuntu服务器执行实际安装和完整出卷。服务器仍需执行下文PDF样张和发布验收。Playwright支持Ubuntu 22.04，见[官方环境要求](https://playwright.dev/docs/intro)和[浏览器安装说明](https://playwright.dev/docs/browsers)。

## 1. 系统准备与代码

以下假定代码放在`/opt/papr`，以普通用户`papr`运行API和worker；命令中的域名必须替换。首次部署执行，已有目录或账号时复用，不覆盖现有数据。

```bash
sudo apt-get update
sudo apt-get install -y git curl ca-certificates sqlite3 nginx
sudo useradd --create-home --shell /bin/bash papr
sudo install -d -o papr -g papr /opt/papr /var/lib/papr
sudo install -d -m 750 -o root -g papr /etc/papr
sudo -iu papr
cd /opt/papr
git clone https://github.com/cminirice/papr.git .
```

私有仓库需使用自己的GitHub访问权限，不把凭据放进仓库地址或配置文件。

安装Node 22（22.12以上、小于23），使用[Node官方发布包](https://nodejs.org/en/download)选择服务器架构，建议放在`/usr/local/bin/node`。下面所有命令要求`node`、`npm`可用；服务配置中的`PAPR_PDF_NODE`须填写`command -v node`返回的绝对路径。

按[uv官方说明](https://docs.astral.sh/uv/getting-started/installation/)为papr用户安装uv，再创建独立Python环境（[Python安装说明](https://docs.astral.sh/uv/guides/install-python/)）：

```bash
uv python install 3.12
uv venv --python 3.12 backend/.venv
uv pip sync --python backend/.venv/bin/python backend/requirements.lock
npm ci
npm run build
```

## 2. Chromium及中文字体

仍在`/opt/papr`，以papr用户安装浏览器；系统依赖命令需要sudo，由有sudo权限的运维用户执行。不要使用root运行worker或添加`--no-sandbox`。

```bash
# 运维用户：用Node的实际绝对路径替换/usr/local/bin/node。
sudo /usr/local/bin/node /opt/papr/node_modules/playwright-core/cli.js install-deps chromium
# papr用户：
export PLAYWRIGHT_BROWSERS_PATH=/opt/papr/browsers
node node_modules/playwright-core/cli.js install chromium
node --input-type=module -e 'import {chromium} from "playwright-core"; console.log(chromium.executablePath())'
mkdir -p fonts
curl -fL https://raw.githubusercontent.com/notofonts/noto-cjk/main/Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Regular.otf -o fonts/NotoSansCJKsc-Regular.otf
curl -fL https://raw.githubusercontent.com/notofonts/noto-cjk/main/Sans/LICENSE -o fonts/LICENSE
```

字体来自[Noto CJK官方仓库](https://github.com/notofonts/noto-cjk/tree/main/Sans/OTF/SimplifiedChinese)。当前渲染器支持TTF、OTF、WOFF2，不接受Ubuntu部分字体包提供的TTC合集。字体改变后须重新验证模板样张；仓库不提交下载的字体、浏览器及生成文件。

## 3. 配置环境与导入SQL

运维用户复制并编辑：

```bash
sudo install -m 640 -o root -g papr /opt/papr/deploy/production.env.example /etc/papr/papr.env
sudoedit /etc/papr/papr.env
```

填入两个正式HTTPS域名、Node和浏览器实际路径。API和worker必须加载同一份配置。应用不自动读取`.env`。

以papr用户执行：

```bash
cd /opt/papr
set -a
. /etc/papr/papr.env
set +a
backend/.venv/bin/python -m alembic -c backend/alembic.ini upgrade head
sqlite3 -bail "$PAPR_DB_PATH" < deploy/config.sql
PYTHONPATH=backend backend/.venv/bin/python -m app.cli init-security
PYTHONPATH=backend backend/.venv/bin/python -m app.cli init-admin --username owner
```

SQL只导入配置：12条目录、14条组件启停配置、2个模板及2个版本、3项系统设置。出题算法在代码中。没有管理员账号/口令、Cookie、匿名用户、历史、审题结论、任务或PDF。

导入保留目录和组件关联、模板内容与标签；模板统一停用并将最新版本设为草稿。目标服务器必须重新生成样例、验证、审题、发布，不沿用Mac上的运行指纹和审核证据。

**必须使用`sqlite3 -bail`且只在首次空配置库执行**：脚本校验迁移版本和配置表为空，防止覆盖已有配置。导入失败时停止后续初始化并排查；不要删除生产表来绕过检查。系统设置包含从本机默认值物化的配置；上线前在后台确认保留策略。

以后需要重新导出时（源库只读）：

```bash
backend/.venv/bin/python scripts/export_config_sql.py --database /绝对路径/papr.sqlite3 --output /目标路径/config.sql
```

## 4. PDF验证与服务

以papr用户、加载上面环境后，先生成开发样张：

```bash
backend/.venv/bin/python scripts/check_pdf_sample.py --node "$PAPR_PDF_NODE" --browser "$PAPR_PDF_BROWSER" --font "$PAPR_PDF_FONT"
```

确认两份PDF可解析，再打开检查中文字符、图形、换页和A4留白。只打印`browser_ready`不能说明PDF链路通过。以上命令不发布模板。

运维用户安装服务：

```bash
sudo cp /opt/papr/deploy/papr-api.service /opt/papr/deploy/papr-worker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now papr-api papr-worker
sudo systemctl status papr-api papr-worker
sudo journalctl -u papr-worker -n 80 --no-pager
```

worker应输出“PDF真实探针通过，用户worker就绪”。API仅监听127.0.0.1:8001；保持一个API进程和一个worker。数据库使用SQLite，无需独立数据库服务或Redis。

```bash
sudo systemctl restart papr-api papr-worker
sudo systemctl stop papr-api papr-worker
```

## 5. 两个前端与HTTPS

生产前端使用`web/dist`和`admin/dist`，由Nginx分别绑定用户域名和管理域名，不使用Vite开发服务。两个站点都配置以下API转发（放在各自server块内）：

```nginx
location /api/ {
    proxy_pass http://127.0.0.1:8001;
    proxy_set_header Host $host;
    proxy_set_header Origin $http_origin;
    proxy_read_timeout 90s;
}
location /admin/api/ {
    proxy_pass http://127.0.0.1:8001;
    proxy_set_header Host $host;
    proxy_set_header Origin $http_origin;
    proxy_read_timeout 90s;
}
location / {
    try_files $uri $uri/ /index.html;
}
```

用户站点root为`/opt/papr/web/dist`，管理站点root为`/opt/papr/admin/dist`。配置正式域名、有效TLS证书、443监听及80跳转HTTPS；`PAPR_COOKIE_SECURE=true`要求实际使用HTTPS。Nginx用户需能读取dist目录。不要把`/var/lib/papr/generated`映射为静态路径；PDF只能走鉴权接口。

API当前不信任代理头，Nginx转发请求的IP限流按代理地址共享；匿名Cookie身份仍独立。公网多人使用前按实际流量核对限流配置，不应盲目启用任意来源的代理头信任。

```bash
sudo nginx -t
sudo systemctl reload nginx
```

## 6. 首次验收与更新

1. 管理端登录，检查一级目录及11个二级目录与组件关联。
2. 启用实际要开放的目录，编辑模板，生成完整样例、自动验证、人工审题、发布。
3. 用户端选择已发布模板，生成、下载学生版/解析版、查看历史；成功后600秒冷却。
4. 验证中文、判断题、应用题及几何图示，不把解析器通过当作人工审题通过。
5. 重启两服务，检查历史及下载仍可用。

更新时先停止worker和API，备份SQLite（使用sqlite3的`.backup`避免仅复制主文件遗漏WAL）、generated和rate-limit.key，再拉取代码、同步依赖、构建、迁移、启动。**已有生产库更新不要重导config.sql**。打印资源改变后必须重启worker重新探针；已有PDF保持快照。
