-- papr SQLite 参数示例；在已连接到目标数据库文件后使用。
-- 初始化阶段执行，检查返回值为 wal；不是业务建表脚本。
PRAGMA journal_mode = WAL;

-- 以下在每个新连接、事务开始前设置；应用连接事件也必须设置。
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;
PRAGMA synchronous = FULL;

-- 只读核验：
PRAGMA journal_mode;
PRAGMA foreign_keys;
SELECT sqlite_version();
