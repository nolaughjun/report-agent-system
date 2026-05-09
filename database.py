# database.py — 数据库连接管理
"""数据库连接管理

特性：
1. SQLAlchemy ORM 支持
2. 异步数据库操作
3. 连接池管理
4. 自动表创建
"""
from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════
# 数据库配置
# ══════════════════════════════════════════════════════════════

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/report_db"
)

# 异步数据库 URL（将 postgresql:// 改为 postgresql+asyncpg://）
ASYNC_DATABASE_URL = DATABASE_URL.replace(
    "postgresql://", "postgresql+asyncpg://"
).replace(
    "postgresql+psycopg2://", "postgresql+asyncpg://"
)

# ══════════════════════════════════════════════════════════════
# 同步引擎和会话
# ══════════════════════════════════════════════════════════════

# 连接池配置（可通过环境变量调整）
POOL_SIZE = int(os.environ.get("DB_POOL_SIZE", "20"))
POOL_MAX_OVERFLOW = int(os.environ.get("DB_POOL_MAX_OVERFLOW", "10"))
POOL_RECYCLE = int(os.environ.get("DB_POOL_RECYCLE", "3600"))  # 1 小时
POOL_TIMEOUT = int(os.environ.get("DB_POOL_TIMEOUT", "30"))  # 30 秒

engine = create_engine(
    DATABASE_URL,
    pool_size=POOL_SIZE,
    max_overflow=POOL_MAX_OVERFLOW,
    pool_pre_ping=True,  # 连接前检查可用性
    pool_recycle=POOL_RECYCLE,  # 回收长时间连接
    pool_timeout=POOL_TIMEOUT,  # 获取连接超时
    echo=os.environ.get("SQL_ECHO", "false").lower() == "true",
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

# ══════════════════════════════════════════════════════════════
# 异步引擎和会话
# ══════════════════════════════════════════════════════════════

async_engine = create_async_engine(
    ASYNC_DATABASE_URL,
    pool_size=POOL_SIZE,
    max_overflow=POOL_MAX_OVERFLOW,
    pool_pre_ping=True,
    pool_recycle=POOL_RECYCLE,
    pool_timeout=POOL_TIMEOUT,
    echo=os.environ.get("SQL_ECHO", "false").lower() == "true",
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# ══════════════════════════════════════════════════════════════
# 基类
# ══════════════════════════════════════════════════════════════

Base = declarative_base()


# ══════════════════════════════════════════════════════════════
# 数据库连接检查
# ══════════════════════════════════════════════════════════════

def check_database_connection() -> bool:
    """检查数据库连接是否正常"""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("[Database] 连接正常")
        return True
    except Exception as e:
        logger.error(f"[Database] 连接失败: {e}")
        return False


async def check_database_connection_async() -> bool:
    """异步检查数据库连接"""
    try:
        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("[Database] 异步连接正常")
        return True
    except Exception as e:
        logger.error(f"[Database] 异步连接失败: {e}")
        return False


# ══════════════════════════════════════════════════════════════
# 会话管理
# ══════════════════════════════════════════════════════════════

@contextmanager
def get_db() -> Generator[Session, None, None]:
    """获取数据库会话（同步）"""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


from typing import AsyncGenerator

async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """获取异步数据库会话

    Yields:
        AsyncSession: 异步数据库会话实例

    Example:
        async for session in get_async_db():
            # 使用 session
            pass
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ══════════════════════════════════════════════════════════════
# 表创建
# ══════════════════════════════════════════════════════════════

def init_database():
    """初始化数据库表"""
    logger.info("[Database] 开始初始化表...")

    try:
        # 导入模型以确保它们被注册
        from models import ReportTask, ReportHistory, UserQuota

        # 创建所有表
        Base.metadata.create_all(bind=engine)
        logger.info("[Database] 表初始化完成")
        return True
    except Exception as e:
        logger.error(f"[Database] 表初始化失败: {e}")
        return False


async def init_database_async():
    """异步初始化数据库表"""
    logger.info("[Database] 开始异步初始化表...")

    try:
        from models import ReportTask, ReportHistory, UserQuota

        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        logger.info("[Database] 异步表初始化完成")
        return True
    except Exception as e:
        logger.error(f"[Database] 异步表初始化失败: {e}")
        return False


# ══════════════════════════════════════════════════════════════
# 数据库事件
# ══════════════════════════════════════════════════════════════

@event.listens_for(engine, "connect")
def receive_connect(dbapi_connection, connection_record):
    """数据库连接事件"""
    logger.debug("[Database] 新连接创建")


@event.listens_for(engine, "checkout")
def receive_checkout(dbapi_connection, connection_record, connection_proxy):
    """连接从池中取出"""
    logger.debug("[Database] 连接从池中取出")


@event.listens_for(engine, "checkin")
def receive_checkin(dbapi_connection, connection_record):
    """连接归还到池中"""
    logger.debug("[Database] 连接归还到池中")
