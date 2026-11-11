# 纸上练 · papr

按模板生成可打印练习。当前工作流：两级目录树 → 叶子关联代码出题组件 → 多规则模板 → 完整PDF样例 → 自动验证 → 人工审题发布 → 用户选择模板生成 → 历史下载与打印。

支持整数乘法、含零乘法、大数读写，模板可混合题型、难度、题数和自由标签。用户无需注册；双版PDF保存并成功提交后开始600秒冷却，查看历史不触发冷却。业务时间统一Asia/Shanghai，页面不重复标注时区。

## 使用入口

- [后台从零发布案例](docs/manual/内容管理高保真试用.md)
- [用户端操作](docs/manual/用户端高保真试用.md)
- [Ubuntu 22.04部署与配置SQL导入](docs/manual/Ubuntu22.04部署.md)
- [四个服务编译、启动、停止](docs/manual/服务编译启动与停止手册.md)
- [当前设计与接口](docs/design/v1/00-设计入口.md)
- [本轮实现及验证结果](docs/implementation/两级目录与多规则后端联调.md)
- [前期开发规划](docs/implementation/开发计划.md) · [设计来源](docs/来源说明.md)

## 环境与安装

Python 3.12、Node 22.12以上的22版本。根目录统一npm workspaces和锁文件：

```bash
uv venv --python 3.12 backend/.venv
uv pip sync --python backend/.venv/bin/python backend/requirements.lock
npm ci
npm run build
```

已有依赖时不重复创建虚拟环境。PDF还需要本机Chrome和字体，配置见服务手册；macOS使用原生PDF解析，Linux使用pypdf。跨平台解析及配置导入已通过本机测试，Ubuntu服务器的完整安装与出卷待按部署手册验收。

## 数据和启动

当前默认库`backend/var/papr.sqlite3`，PDF根`backend/var/generated`。本机使用用户已录入目录的papr.sqlite3，管理员沿用该库原账号；此前空内容库papr-v2.sqlite3保留。浏览器旧目录模板可在管理端导入空的新库，但导入不自动发布。不要执行旧seed-content命令来建立当前模板。

应用不自动载入`.env`。在四个终端分别载入本地配置，再启动API、worker和两个前端；本机API用8001，避免占用其他项目8000端口：

```bash
export PATH="/Users/eric/.local/node-v22.23.2/bin:$PATH"
set -a
. ./.env
set +a
export PAPR_API_PROXY_TARGET=http://127.0.0.1:8001
```

四个终端分别执行：

```bash
backend/.venv/bin/uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8001 --no-proxy-headers
backend/.venv/bin/python -u scripts/worker.py
npm run dev:web
npm run dev:admin
```

以上四条是四个常驻进程，不是在同一个终端依次执行。用户端5173、管理端5174；worker探针通过且持续心跳后才能生成。打印资源更新前停止worker，构建后再重启。

`scripts/init_workflow_v2.py`仅供需要隔离新库的开发场景使用，本机不要重复初始化。日常升级使用`backend/.venv/bin/alembic -c backend/alembic.ini upgrade head`，当前head为0013。不要重设已有管理员或删除业务库。

## 验证

```bash
backend/.venv/bin/python -m pytest -q backend/tests
npm test
backend/.venv/bin/python scripts/export_contracts.py --check
PAPR_REAL_PDF=1 backend/.venv/bin/python -m pytest -q backend/tests/test_workflow_v2.py::test_real_pdf_end_to_end
```

最后一项使用临时库和真实Chrome/原生PDF解析器，不发布正式内容；普通测试默认跳过。实际教学合理性、A4纸张打印效果仍由管理员审题确认。前期实施记录保留在docs/implementation，旧结果不代替新流程验收。

## 2026-11-11 当前运行数据路径

已核对用户实际录入的“四年级数学上册”及11个二级目录位于`backend/var/papr.sqlite3`（已包含v2业务表），运行配置恢复为此库和`backend/var/generated`。`papr-v2.sqlite3`空内容库原样保留，不合并或删除两库历史。绑定前备份在`backend/var/backups/20261111-090315-648340/papr.sqlite3`。新增组件及教学覆盖边界见`docs/implementation/四年级上册出题组件.md`。
