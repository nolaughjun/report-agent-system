# models.py — SQLAlchemy 数据模型
"""SQLAlchemy 数据模型

模型：
1. ReportTask - 报告任务
2. ReportHistory - 报告历史版本
3. UserQuota - 用户配额
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    JSON,
    Index,
)
from sqlalchemy.orm import relationship

from database import Base


def utcnow():
    """返回时区感知的当前 UTC 时间"""
    return datetime.now(timezone.utc)


# ══════════════════════════════════════════════════════════════
# 报告任务模型
# ══════════════════════════════════════════════════════════════

class ReportTask(Base):
    """报告任务表"""
    __tablename__ = "report_tasks"

    # 主键
    thread_id = Column(String(32), primary_key=True, index=True)

    # 用户信息
    user_id = Column(String(64), index=True, nullable=True)
    api_key_hash = Column(String(64), nullable=True)

    # 任务输入
    topic = Column(String(500), nullable=False)
    abstract = Column(Text, nullable=True)
    report_type = Column(String(50), default="research")
    language = Column(String(50), default="中文")

    # 配置参数
    quality_threshold = Column(Float, default=0.55)
    max_retry = Column(Integer, default=3)
    max_concurrent = Column(Integer, default=5)

    # 任务状态
    status = Column(String(50), default="pending", index=True)
    current_step = Column(String(50), nullable=True)
    progress = Column(Float, default=0.0)
    retry_count = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)

    # 结果
    draft_content = Column(Text, nullable=True)
    final_report = Column(Text, nullable=True)
    export_path = Column(String(500), nullable=True)
    quality_score = Column(Float, nullable=True)

    # Token 统计
    total_prompt_tokens = Column(Integer, default=0)
    total_completion_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)

    # 性能指标
    total_time_ms = Column(Integer, nullable=True)
    planning_time_ms = Column(Integer, nullable=True)
    collection_time_ms = Column(Integer, nullable=True)
    drafting_time_ms = Column(Integer, nullable=True)
    review_time_ms = Column(Integer, nullable=True)

    # 时间戳
    created_at = Column(DateTime, default=utcnow, index=True)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Celery 任务 ID
    celery_task_id = Column(String(64), nullable=True, index=True)

    # 关联
    history = relationship("ReportHistory", back_populates="task", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<ReportTask(thread_id={self.thread_id}, status={self.status})>"

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "thread_id": self.thread_id,
            "user_id": self.user_id,
            "topic": self.topic,
            "report_type": self.report_type,
            "status": self.status,
            "current_step": self.current_step,
            "progress": self.progress,
            "retry_count": self.retry_count,
            "quality_score": self.quality_score,
            "export_path": self.export_path,
            "total_tokens": self.total_tokens,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


# ══════════════════════════════════════════════════════════════
# 报告历史版本模型
# ══════════════════════════════════════════════════════════════

class ReportHistory(Base):
    """报告历史版本表"""
    __tablename__ = "report_history"

    # 主键
    id = Column(Integer, primary_key=True, autoincrement=True)

    # 关联任务（外键约束）
    thread_id = Column(String(32), ForeignKey("report_tasks.thread_id"), nullable=False, index=True)
    task = relationship("ReportTask", back_populates="history")

    # 版本信息
    version = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    change_note = Column(Text, nullable=True)

    # 质量信息
    quality_score = Column(Float, nullable=True)
    quality_issues = Column(JSON, nullable=True)

    # 时间戳
    created_at = Column(DateTime, default=utcnow)

    def __repr__(self):
        return f"<ReportHistory(thread_id={self.thread_id}, version={self.version})>"


# ══════════════════════════════════════════════════════════════
# 用户配额模型
# ══════════════════════════════════════════════════════════════

class UserQuota(Base):
    """用户配额表"""
    __tablename__ = "user_quotas"

    # 主键
    id = Column(Integer, primary_key=True, autoincrement=True)

    # 用户标识
    user_id = Column(String(64), unique=True, nullable=False, index=True)
    api_key_hash = Column(String(64), unique=True, nullable=True)

    # 配额设置
    daily_limit = Column(Integer, default=50)  # 每日限制
    monthly_limit = Column(Integer, default=1000)  # 每月限制

    # 使用统计
    daily_used = Column(Integer, default=0)
    monthly_used = Column(Integer, default=0)
    total_reports = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)

    # 时间戳
    last_daily_reset = Column(DateTime, default=utcnow)
    last_monthly_reset = Column(DateTime, default=utcnow)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    # 状态
    is_active = Column(Boolean, default=True)

    def __repr__(self):
        return f"<UserQuota(user_id={self.user_id}, daily_used={self.daily_used})>"

    def can_create_report(self) -> bool:
        """检查是否可以创建报告"""
        if not self.is_active:
            return False
        if self.daily_used >= self.daily_limit:
            return False
        if self.monthly_used >= self.monthly_limit:
            return False
        return True

    def increment_usage(self):
        """增加使用量"""
        self.daily_used += 1
        self.monthly_used += 1
        self.total_reports += 1
        self.updated_at = utcnow()

    def reset_daily(self):
        """重置每日配额"""
        self.daily_used = 0
        self.last_daily_reset = utcnow()

    def reset_monthly(self):
        """重置每月配额"""
        self.monthly_used = 0
        self.last_monthly_reset = utcnow()


# ══════════════════════════════════════════════════════════════
# Wiki 知识库模型
# ══════════════════════════════════════════════════════════════

class WikiKnowledge(Base):
    """Wiki 知识库表"""
    __tablename__ = "wiki_knowledge"

    # 主键
    id = Column(String(32), primary_key=True)

    # 内容
    title = Column(String(500), nullable=False)
    content = Column(Text, nullable=False)

    # 来源
    source_report_id = Column(String(32), ForeignKey("report_tasks.thread_id"), nullable=True)

    # 分类和标签
    category = Column(String(50), default="general", index=True)
    tags = Column(JSON, default=list)
    keywords = Column(JSON, default=list)

    # 向量嵌入（用于语义搜索）
    embedding = Column(JSON, nullable=True)

    # 元数据
    metadata = Column(JSON, default=dict)

    # 版本控制
    version = Column(Integer, default=1)

    # 时间戳
    created_at = Column(DateTime, default=utcnow, index=True)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    # 访问统计
    view_count = Column(Integer, default=0)
    last_accessed = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<WikiKnowledge(id={self.id}, title={self.title[:30]}...)>"

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "source_report_id": self.source_report_id,
            "category": self.category,
            "tags": self.tags or [],
            "keywords": self.keywords or [],
            "version": self.version,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "view_count": self.view_count,
            "metadata": self.metadata or {},
        }


class WikiCollection(Base):
    """Wiki 知识集合（用于组织知识点）"""
    __tablename__ = "wiki_collections"

    id = Column(String(32), primary_key=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)

    # 知识点 ID 列表
    knowledge_ids = Column(JSON, default=list)

    # 所有者
    user_id = Column(String(64), nullable=True, index=True)
    is_public = Column(Boolean, default=True)

    # 时间戳
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "knowledge_ids": self.knowledge_ids or [],
            "is_public": self.is_public,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ══════════════════════════════════════════════════════════════
# 索引
# ══════════════════════════════════════════════════════════════

Index('ix_report_tasks_status_created', ReportTask.status, ReportTask.created_at)
Index('ix_report_tasks_user_created', ReportTask.user_id, ReportTask.created_at)
Index('ix_wiki_knowledge_category', WikiKnowledge.category)
Index('ix_wiki_knowledge_created', WikiKnowledge.created_at)


# ══════════════════════════════════════════════════════════════
# 数据库操作函数
# ══════════════════════════════════════════════════════════════

def create_task_record(
    thread_id: str,
    topic: str,
    user_id: str = None,
    **kwargs
) -> ReportTask:
    """创建任务记录"""
    from database import get_db

    with get_db() as db:
        task = ReportTask(
            thread_id=thread_id,
            topic=topic,
            user_id=user_id,
            **kwargs
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        return task


def update_task_record(thread_id: str, **kwargs) -> Optional[ReportTask]:
    """更新任务记录"""
    from database import get_db

    with get_db() as db:
        task = db.query(ReportTask).filter(
            ReportTask.thread_id == thread_id
        ).first()

        if task:
            for key, value in kwargs.items():
                if hasattr(task, key):
                    setattr(task, key, value)
            db.commit()
            db.refresh(task)

        return task


def get_task_record(thread_id: str) -> Optional[ReportTask]:
    """获取任务记录"""
    from database import get_db

    with get_db() as db:
        return db.query(ReportTask).filter(
            ReportTask.thread_id == thread_id
        ).first()


def get_user_tasks(
    user_id: str,
    limit: int = 20,
    offset: int = 0
) -> list[ReportTask]:
    """获取用户的任务列表"""
    from database import get_db

    with get_db() as db:
        return db.query(ReportTask).filter(
            ReportTask.user_id == user_id
        ).order_by(
            ReportTask.created_at.desc()
        ).offset(offset).limit(limit).all()


def check_user_quota(user_id: str) -> bool:
    """检查用户配额

    Args:
        user_id: 用户 ID

    Returns:
        是否可以创建报告
    """
    from database import get_db
    from datetime import timedelta

    with get_db() as db:
        quota = db.query(UserQuota).filter(
            UserQuota.user_id == user_id
        ).first()

        if not quota:
            # 创建默认配额
            quota = UserQuota(user_id=user_id)
            db.add(quota)
            db.commit()
            return True

        # 检查是否需要重置（使用时区感知的时间比较）
        now = utcnow()
        if quota.last_daily_reset and (now - quota.last_daily_reset) > timedelta(days=1):
            quota.reset_daily()
        if quota.last_monthly_reset and (now - quota.last_monthly_reset) > timedelta(days=30):
            quota.reset_monthly()

        db.commit()
        return quota.can_create_report()


def increment_user_usage(user_id: str, tokens: int = 0):
    """增加用户使用量"""
    from database import get_db

    with get_db() as db:
        quota = db.query(UserQuota).filter(
            UserQuota.user_id == user_id
        ).first()

        if quota:
            quota.increment_usage()
            quota.total_tokens += tokens
            db.commit()
