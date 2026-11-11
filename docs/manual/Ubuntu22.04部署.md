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
sudo apt-get install -y git curl ca-certificates sqlite3
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

## 4. PDF验证

以papr用户、加载第3节环境后，先生成开发样张：

```bash
cd /opt/papr
backend/.venv/bin/python scripts/check_pdf_sample.py --node "$PAPR_PDF_NODE" --browser "$PAPR_PDF_BROWSER" --font "$PAPR_PDF_FONT"
```

确认两份PDF可解析，再打开检查中文字符、图形、换页和A4留白。只打印`browser_ready`不能说明PDF链路通过。以上命令不发布模板。

## 5. 安装Nginx并配置两个前端

### 安装与开机启动

回到有sudo权限的运维用户终端执行；如果此前使用`sudo -iu papr`切换账号，先执行`exit`。以下安装和服务管理命令不要使用无sudo权限的papr账号执行。

```bash
sudo apt-get update
sudo apt-get install -y nginx
nginx -v
sudo nginx -t
sudo systemctl enable --now nginx
sudo systemctl status nginx --no-pager
```

服务器安全组允许80、443端口进入。如果已启用UFW，执行`sudo ufw allow 'Nginx Full'`；不需要为本项目额外开放8001、5173、5174端口。保留现有SSH访问规则。

生产前端使用已构建的`web/dist`和`admin/dist`，由同一个Nginx分别托管两个域名。用户前端和管理前端各有一个启动脚本，用于独立启用对应站点；它们不启动Vite或额外Node进程。

### 配置站点与HTTPS

仓库提供两个完整站点配置，包含80跳转HTTPS、443监听、SPA路由回退及API转发。首次安装复制，已有配置时直接编辑，不重复覆盖：

```bash
sudo install -m 644 /opt/papr/deploy/nginx/papr-web.conf /etc/nginx/sites-available/papr-web
sudo install -m 644 /opt/papr/deploy/nginx/papr-admin.conf /etc/nginx/sites-available/papr-admin
sudoedit /etc/nginx/sites-available/papr-web /etc/nginx/sites-available/papr-admin
```

按实际域名修改两份配置：

| 站点 | 默认域名（须替换） | 静态目录 |
| --- | --- | --- |
| 用户前端 | practice.example.com | /opt/papr/web/dist |
| 管理前端 | admin.example.com | /opt/papr/admin/dist |

将域名DNS解析到服务器，配置有效TLS证书。模板中的`/etc/papr/tls/域名/fullchain.pem`和`privkey.pem`只是路径示例，须改为实际证书路径；证书必须存在后再启动站点。可以使用已有证书或证书服务商提供的证书文件。同步修改`/etc/papr/papr.env`中的两个Origin，保留`PAPR_COOKIE_SECURE=true`，浏览器实际使用HTTPS访问。

Nginx的`www-data`用户需能读取两个dist目录，并对其父目录具有遍历权限。可在运维终端检查：

```bash
sudo -u www-data test -r /opt/papr/web/dist/index.html
sudo -u www-data test -r /opt/papr/admin/dist/index.html
```

两个命令均应退出成功；失败时修复静态资源目录权限，不要开放数据库和密钥目录。PDF只走鉴权接口，不把`/var/lib/papr/generated`配置为公开静态路径。

两个站点均将`/api/`和`/admin/api/`原路径转发到`127.0.0.1:8001`。API当前不信任代理头，IP限流按代理地址共享，匿名Cookie身份仍独立；公网多人使用前按实际流量核对限流配置。

## 6. 使用脚本启动四个服务入口

### 首次安装API和worker服务

以有sudo权限的运维用户执行：

```bash
sudo cp /opt/papr/deploy/papr-api.service /opt/papr/deploy/papr-worker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable papr-api papr-worker
```

这一步仅安装并设置开机启动；下面的脚本负责立即启动。API和worker由systemd以papr用户运行，统一加载`/etc/papr/papr.env`。API监听`127.0.0.1:8001`，保持一个API进程和一个worker；数据库为SQLite，无需数据库服务或Redis。

### 四个启动脚本

完成构建、数据库初始化、PDF验证及Nginx站点配置后，依次执行：

```bash
sudo bash /opt/papr/deploy/start-backend.sh
sudo bash /opt/papr/deploy/start-worker.sh
sudo bash /opt/papr/deploy/start-user-frontend.sh
sudo bash /opt/papr/deploy/start-admin-frontend.sh
```

| 脚本 | 作用 |
| --- | --- |
| `deploy/start-backend.sh` | 启动systemd中的papr-api服务 |
| `deploy/start-worker.sh` | 启动systemd中的papr-worker服务；启动后仍需确认PDF探针就绪 |
| `deploy/start-user-frontend.sh` | 启用papr-web站点，检查配置后启动或重载Nginx |
| `deploy/start-admin-frontend.sh` | 启用papr-admin站点，检查配置后启动或重载Nginx |

四个脚本共用同目录的`start-service.sh`，应随整个deploy目录保留。脚本可重复执行，不重复拉起API或worker。前端脚本不会覆盖已有冲突站点链接；Nginx检查失败时撤回本次新增链接，不重载正在运行的配置。脚本不自动安装依赖、构建、迁移数据库或申请证书。

API和worker的“已启动”表示systemd进程启动成功，不代表业务已就绪。检查状态和日志：

```bash
sudo systemctl status papr-api papr-worker nginx --no-pager
sudo journalctl -u papr-api -n 80 --no-pager
sudo journalctl -u papr-worker -n 80 --no-pager
sudo tail -n 80 /var/log/nginx/error.log
```

worker应输出“PDF真实探针通过，用户worker就绪”。随后用浏览器分别访问两个正式HTTPS域名。两个前端的站点链接会保留，Nginx开机启动时自动加载。

### 停止与重启

```bash
# 后端与worker：配置或代码变更后使用restart，start不会重启已有进程。
sudo systemctl restart papr-api papr-worker
sudo systemctl stop papr-api papr-worker

# 两个前端共用Nginx：停止会同时影响其托管的其他站点。
sudo systemctl stop nginx
sudo systemctl start nginx

# 修改站点配置后，检查通过再重载。
sudo nginx -t && sudo systemctl reload nginx
```

只停用一个前端时，移除其`sites-enabled`链接（不是`sites-available`原配置），检查并重载：

```bash
# 停用用户前端；管理前端保持运行。
sudo rm /etc/nginx/sites-enabled/papr-web
sudo nginx -t && sudo systemctl reload nginx
# 恢复用户前端。
sudo bash /opt/papr/deploy/start-user-frontend.sh
```

停用管理前端对应`papr-admin`和`start-admin-frontend.sh`。停止systemd服务不会取消开机启动；需要取消时使用`sudo systemctl disable papr-api papr-worker`。

## 7. 首次验收与更新

1. 管理端登录，检查一级目录及11个二级目录与组件关联。
2. 启用实际要开放的目录，编辑模板，生成完整样例、自动验证、人工审题、发布。
3. 用户端选择已发布模板，生成、下载学生版/解析版、查看历史；成功后600秒冷却。
4. 验证中文、判断题、应用题及几何图示，不把解析器通过当作人工审题通过。
5. 重启API和worker，检查两个前端、历史及下载仍可用。

更新时先停止worker和API，备份SQLite（使用sqlite3的`.backup`避免仅复制主文件遗漏WAL）、generated和rate-limit.key，再拉取代码、同步依赖、构建、迁移、启动。**已有生产库更新不要重导config.sql**。打印资源改变后必须重启worker重新探针；已有PDF保持快照。
