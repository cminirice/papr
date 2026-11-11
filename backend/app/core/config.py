from dataclasses import dataclass
import os
from pathlib import Path
from urllib.parse import urlsplit

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _origins(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    db_path: Path
    generated_root: Path
    user_origins: tuple[str, ...] = ("http://127.0.0.1:5173", "http://localhost:5173")
    admin_origins: tuple[str, ...] = ("http://127.0.0.1:5174", "http://localhost:5174")
    cookie_secure: bool = False
    rate_limit_key_path: Path | None = None
    identity_limit: int = 20
    pdf_node: Path | None = None
    pdf_browser: Path | None = None
    pdf_font: Path | None = None

    def __post_init__(self) -> None:
        if self.rate_limit_key_path is None:
            object.__setattr__(self, "rate_limit_key_path", self.db_path.parent / "rate-limit.key")
        for path in (self.db_path, self.generated_root, self.rate_limit_key_path):
            if not path.is_absolute():
                raise ValueError("数据库、生成文件与密钥路径必须为绝对路径")
        if self.db_path == self.generated_root or self.generated_root in self.db_path.parents:
            raise ValueError("数据库文件必须位于生成文件目录之外")
        if self.rate_limit_key_path == self.db_path or self.rate_limit_key_path == self.generated_root or self.generated_root in self.rate_limit_key_path.parents:
            raise ValueError("限流密钥必须与数据库文件及生成目录隔离")
        for path in (self.pdf_node, self.pdf_browser, self.pdf_font):
            if path is not None and not path.is_absolute():
                raise ValueError("PDF运行程序和字体必须使用绝对路径")
        for origins in (self.user_origins, self.admin_origins):
            if not origins:
                raise ValueError("Origin白名单不能为空")
            for origin in origins:
                parsed = urlsplit(origin)
                if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
                    raise ValueError("Origin必须为完整的scheme://host[:port]，不可带路径")
                if not self.cookie_secure and (parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}):
                    raise ValueError("关闭Secure仅允许本机HTTP开发Origin")
                if self.cookie_secure and parsed.scheme != "https":
                    raise ValueError("Secure部署必须配置HTTPS Origin")
        if self.identity_limit < 1:
            raise ValueError("新身份限流阈值必须大于0")

    @classmethod
    def from_env(cls) -> "Settings":
        secure = os.environ.get("PAPR_COOKIE_SECURE", "false").lower()
        if secure not in {"true", "false"}:
            raise ValueError("PAPR_COOKIE_SECURE必须为true或false")
        key_path = os.environ.get("PAPR_RATE_LIMIT_KEY_PATH")
        return cls(
            db_path=Path(os.environ.get("PAPR_DB_PATH", BACKEND_ROOT / "var/papr.sqlite3")),
            generated_root=Path(os.environ.get("PAPR_GENERATED_ROOT", BACKEND_ROOT / "var/generated")),
            user_origins=_origins(os.environ.get("PAPR_USER_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173")),
            admin_origins=_origins(os.environ.get("PAPR_ADMIN_ORIGINS", "http://127.0.0.1:5174,http://localhost:5174")),
            cookie_secure=secure == "true",
            pdf_node=Path(os.environ["PAPR_PDF_NODE"]) if os.environ.get("PAPR_PDF_NODE") else None,
            pdf_browser=Path(os.environ["PAPR_PDF_BROWSER"]) if os.environ.get("PAPR_PDF_BROWSER") else None,
            pdf_font=Path(os.environ["PAPR_PDF_FONT"]) if os.environ.get("PAPR_PDF_FONT") else None,
            rate_limit_key_path=Path(key_path) if key_path else None,
        )
