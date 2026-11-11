# 模板验证任务与worker验证

日期：2026-10-27，北京时间。单终端顺序实施T0迁移/契约、T2验证报告、T4验证队列执行及T6后台接线；未启动子代理。

## 已实现

- 0004新增validation_run和validation_failure；同一事务创建job、固定草稿快照及run。快照包含版本/hash/lock_version、算法与目标依赖、profiles、固定用例、profile ID映射和检查策略版本。
- POST `/admin/api/v1/template-versions/{id}/validation-jobs`，body为`{lock_version,content_hash}`，必须有UUID Idempotency-Key、管理员Cookie、Origin和CSRF；返回202及ValidationView。相同key、相同请求返回原run，包括失败/过期任务；同key不同请求409。重新验证用新key。
- GET `/admin/api/v1/validation-runs/{id}`读取状态/报告；GET `/admin/api/v1/template-versions/{id}/validation-runs`读取最近20条。均须管理员会话，不向匿名用户开放。
- 后台可发起“验证已保存草稿”，展示排队/运行/通过/失败/过期，运行时每3秒刷新。显示各档精确容量、通过的题量和失败样例。请求响应丢失后重试保留原key；CSRF刷新重试沿用原快照请求。未保存表单不会被带入验证。

## 检查和报告语义

每档检查固定用例、100个随机样例、3/6/8/10/12候选档位中不超过max_per_paper的每档20组整卷，以及精确参数容量。生成器仍有限采样、不跨难度或悄悄减少题量；没有任何可用题量的profile失败。

默认种子成功报告共1765道成功校验样题，基础容量493、提高容量80100，两档题量均为3/6/8/10/12；另保存5道固定样题的完整结构化快照供后续审题引用。sample_count计成功校验的题目（不同卷可重复），failure_count计失败检查次数，完整计数保留；失败明细最多100条，超出标记truncated。每个固定用例最多保存一道样题，当前最多30道。

内容不通过时，job仍可succeeded（成功完成检查并产出报告），run为failed；子进程超时或运行错误时job为failed，错误码ENGINE_TIMEOUT或VALIDATION_ENGINE_ERROR。数学通过不等于人工审题通过或PDF排版合格；报告明确保留human_review/pdf_review=pending。

## 执行与恢复

运行一个API进程、一个worker；worker只有一个执行槽，只消费template_validate，不消费paper_generate或template_preview。API受理不执行数学批量检查。worker每个任务启动独立Python子进程，使用stdin快照/stdout报告，子进程不访问数据库。

本批验证任务默认：最多10个queued/running验证任务、120秒固定租约、子进程60秒硬超时、最多2次执行尝试；常量在validation_jobs.py/worker.py中，后续压测再调整。短批量任务采用“硬超时小于租约”约束，不启用续租；不能把该策略直接套用于更长的PDF任务。未实现多主机或多个worker部署。

claim在短BEGIN IMMEDIATE中领取任务并增加attempt、生成新lease_token；数学与子进程等待均在事务外。过期租约重新排队一次，达到尝试上限终止WORKER_LOST；旧worker的token/attempt/截止时间不匹配就禁止提交。执行失败不自动无限重试；显式超时/进程错误终止，管理员可用新key重试。

完成事务重验租约和当前版本/依赖/算法状态。编辑草稿立即将旧run标stale；执行中的旧快照仍可留下历史报告，但不写回当前有效题量。仅当前passed报告在同一事务写回profiles的validated_count_options。成功提交重复调用无效；不发布模板、不增加公开epoch、不写用户冷却。

0004回退会删除报告表并使相关验证任务终止，清空受影响profiles的有效题量；保留job历史，避免重升后出现没有run的可执行任务。旧key明确返回记录不可用而非重建任务。该回退仅在临时测试库执行，未操作运行库。

## 启动

先完成迁移、管理员初始化及草稿导入（见README）。另开一个终端，在工程根目录：

```bash
backend/.venv/bin/python scripts/worker.py
```

仅处理一个任务可用`--once`，没有待执行任务则直接退出。长期运行的进程监管、部署服务及PDF渲染仍待实现；本批没有留下后台服务或设置真实管理员。

## 真实验证结果

- 全量后端70项通过；报告增加固定样题快照后，8项验证任务专项再次通过。保留2项既有依赖弃用告警。
- 真实Python子进程执行完整报告；另通过scripts/worker.py --once独立进程访问临时SQLite完成任务，验证不是仅mock runner。
- 同key并发与重放、异payload冲突、有界队列、报告鉴权、hash冲突、草稿变更旧报告过期、单次领取、租约到期恢复、旧token隔离、最多两次尝试、重复最终提交均覆盖。
- 狭窄空间导致101次失败检查，持久化100条明细且标截断；这是实际数学/去重失败。超时路径使用注入TimeoutExpired测试，不宣称真实挂死进程或操作系统kill恢复已验收。
- 带报告的迁移降至0003并重升、模型无漂移通过；所有数据库检查为真实临时SQLite。
- 前端7项测试通过（API为mock fetch）；两端构建和共享类型检查通过，导出契约无漂移。浏览器实际点击/轮询、人工审题、PDF/A4及用户出卷链路仍未验收。

下一步：绑定同hash有效报告的人工审题、发布最小流程，并接共享题目渲染与PDF样张；不自动替管理员提交“人工审核通过”。
