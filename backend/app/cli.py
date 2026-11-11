"""python -m app.cli；口令只通过终端隐藏输入，不接受命令行明文参数。"""
import argparse
import getpass
import warnings

from sqlalchemy.exc import OperationalError
from app.auth.security import initialize_rate_key
from app.core.config import Settings
from app.core.database import make_engine
from app.core.errors import ServiceError
from app.core.time import beijing_now
from app.services.identity.sessions import initialize_admin
from app.services.content_seed import seed_content


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="纸上练本地初始化工具")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init-security", help="创建独立限流HMAC密钥，不覆盖已有文件")
    admin = sub.add_parser("init-admin", help="交互设置唯一管理员，需先执行数据库迁移")
    admin.add_argument("--username", required=True)
    content = sub.add_parser("seed-content", help="幂等导入首个乘法草稿，不覆盖已有内容或发布")
    content.add_argument("--admin-username", required=True)
    args = parser.parse_args(argv)
    engine = None
    try:
        settings = Settings.from_env()
        if args.command == "init-security":
            created = initialize_rate_key(settings.rate_limit_key_path)
            print("限流密钥已创建。" if created else "限流密钥已存在，保持不变。")
            return 0
        if args.command == "seed-content":
            engine = make_engine(settings.db_path)
            result = seed_content(engine, args.admin_username, beijing_now())
            print(f"草稿导入完成：新增{result['created']}条，保持{result['unchanged']}条；未发布。")
            return 0
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            password = getpass.getpass("管理员口令（12–128字符）：")
            confirmation = getpass.getpass("再次输入口令：")
        if password != confirmation:
            raise ValueError("两次口令不一致")
        engine = make_engine(settings.db_path)
        initialize_admin(engine, args.username, password, beijing_now())
        print("管理员已创建；没有输出或保存明文口令。")
        return 0
    except OperationalError:
        print("数据库尚未就绪，请先执行迁移并检查配置。")
    except (ValueError, ServiceError, OSError, getpass.GetPassWarning):
        print("初始化失败：请检查参数、终端隐藏输入、路径权限或是否已存在管理员。")
    except (EOFError, KeyboardInterrupt):
        print("初始化已取消。")
    finally:
        if engine is not None:
            engine.dispose()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
