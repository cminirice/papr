# SQLite数据模型

更新：2026-11-05。当前迁移为`0013_workflow_v2`；以下描述已实施模型。数据类型、索引及触发器以`backend/migrations/versions/0013_workflow_v2.py`为准。

## 数据边界

新运行库为`backend/var/papr-v2.sqlite3`，旧库与旧PDF保留，不原地清空。沿用身份、会话、限流、运行设置和worker就绪表；为兼容旧路由保留旧业务表，但当前页面的新内容不写入旧业务表。初始化脚本仅复制旧管理员账号和密码哈希，不复制会话、匿名历史和已发布内容。

## 当前业务表

| 表 | 关键内容与约束 |
| --- | --- |
| v2_directory | parent_id为空即一级目录，否则二级；名称、编码、状态、排序、revision及组件key数组。根编码唯一，同父编码唯一；触发器禁止第三级、改变父级、根绑定组件 |
| v2_component_state | 代码组件key、enabled、revision；实际能力来自已部署代码，不接受在线脚本 |
| v2_template | 稳定编码、发布版本指针、enabled、revision；发布指针的归属由服务事务校验 |
| v2_version | 模板外键、递增版本号、sealed、content JSON、content_hash；每模板最多一个草稿，封存版本禁止UPDATE |
| v2_task | 用户或管理员二选一、paper/preview/validate、版本外键、幂等key及请求hash、plan JSON、结果snapshot JSON、状态、attempt/token/lease、完成时间和错误 |
| v2_artifact | 任务、attempt/token、学生/解析类型、pending/ready/failed、文件metadata JSON；同任务同attempt同类型唯一，同任务同类型最多一个ready |
| v2_review | 版本、预览任务、验证任务、管理员、content_hash、通过/拒绝、意见；追加保存证据 |
| v2_audit | 操作者、动作、实体、detail JSON；内容操作、发布和试卷勘误/撤回记录 |

规则保存在版本content中，包含一级目录、名称、自由标签、列数及有序规则（叶子目录、组件、题型、难度、数量）；没有独立知识点、达成目标、分类字典或年级字段。目录组件关联也使用JSON数组，引用完整性在保存、准入、发布及最终提交校验。未采用此前建议的独立template_rule、directory_component或paper表，避免并行维护同一配置；任务snapshot就是已生成试卷快照。

## 一致性

- UUID主键；时间使用显式+08:00的固定微秒文本；SQLite WAL、外键、短写事务。
- 编辑带revision，冲突拒绝覆盖。封存后编辑生成新草稿，线上指针保留到下一次发布。
- 同主体同key唯一；部分唯一索引限制用户最多一个queued/running任务。
- 同一成功事务保存ready文件索引、成功状态和600秒冷却。文件系统不是数据库事务的一部分，中间文件通过attempt/token隔离。
- JSON配置经严格请求schema及生成内核验证；SQLite对配置、执行计划和快照字段做json_valid约束。
- 当前提供启停，不提供目录物理删除接口。迁移降级仅允许v2表全空时执行，有业务数据则拒绝自动删除。

## 初始化与恢复

`python scripts/init_workflow_v2.py`创建独立新库；目标存在则拒绝覆盖。日常升级使用Alembic，不重复初始化。备份需在停止API和worker后保存数据库、生成目录及安全配置；回退旧库不等于把两套历史合并。详细操作见[服务手册](../../manual/服务编译启动与停止手册.md)。
