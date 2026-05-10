# wiki.py — Wiki 知识库模块
"""Wiki 知识库系统

功能：
1. 报告自动入库 - 生成的报告自动提取知识点存入知识库
2. 智能索引 - 基于向量相似度的语义搜索
3. 知识复用 - 新报告生成时检索相关知识片段
4. 版本管理 - 知识点的版本追踪

架构：
- PostgreSQL: 存储知识点元数据和内容
- Redis: 缓存热门知识点和搜索结果
- 向量数据库(可选): 语义搜索支持
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from datetime import UTC, datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════
# 配置
# ══════════════════════════════════════════════════════════════

WIKI_ENABLED = os.environ.get("WIKI_ENABLED", "true").lower() == "true"
WIKI_MIN_CONTENT_LENGTH = int(os.environ.get("WIKI_MIN_CONTENT_LENGTH", "100"))
WIKI_MAX_CHUNK_SIZE = int(os.environ.get("WIKI_MAX_CHUNK_SIZE", "1000"))
WIKI_SIMILARITY_THRESHOLD = float(os.environ.get("WIKI_SIMILARITY_THRESHOLD", "0.7"))

# ══════════════════════════════════════════════════════════════
# 数据模型
# ══════════════════════════════════════════════════════════════

# 全局知识点存储（无数据库时的降级模式）
_knowledge_store: dict[str, dict] = {}
_knowledge_index: dict[str, list[str]] = {}  # 关键词 -> 知识点ID列表


class KnowledgeEntry:
    """知识点条目"""

    def __init__(
        self,
        id: str,
        title: str,
        content: str,
        source_report_id: str,
        category: str = "general",
        tags: list[str] = None,
        keywords: list[str] = None,
        embedding: list[float] = None,
        created_at: str = None,
        updated_at: str = None,
        version: int = 1,
        metadata: dict = None,
    ):
        self.id = id
        self.title = title
        self.content = content
        self.source_report_id = source_report_id
        self.category = category
        self.tags = tags or []
        self.keywords = keywords or []
        self.embedding = embedding
        self.created_at = created_at or utcnow()
        self.updated_at = updated_at or utcnow()
        self.version = version
        self.metadata = metadata or {}

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "source_report_id": self.source_report_id,
            "category": self.category,
            "tags": self.tags,
            "keywords": self.keywords,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "version": self.version,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "KnowledgeEntry":
        return cls(
            id=data["id"],
            title=data["title"],
            content=data["content"],
            source_report_id=data["source_report_id"],
            category=data.get("category", "general"),
            tags=data.get("tags", []),
            keywords=data.get("keywords", []),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            version=data.get("version", 1),
            metadata=data.get("metadata", {}),
        )


def utcnow() -> str:
    """获取 UTC 时间字符串"""
    return datetime.now(UTC).isoformat()


# ══════════════════════════════════════════════════════════════
# 知识提取
# ══════════════════════════════════════════════════════════════


def extract_knowledge_from_report(
    report_content: str,
    report_id: str,
    report_title: str,
    report_type: str = "research",
) -> list[KnowledgeEntry]:
    """从报告中提取知识点

    Args:
        report_content: 报告内容
        report_id: 报告 ID
        report_title: 报告标题
        report_type: 报告类型

    Returns:
        知识点列表
    """
    if not WIKI_ENABLED:
        return []

    entries = []

    # 按章节分割
    sections = _split_into_sections(report_content)

    for section_title, section_content in sections:
        if len(section_content) < WIKI_MIN_CONTENT_LENGTH:
            continue

        # 生成知识点 ID
        entry_id = _generate_entry_id(report_id, section_title)

        # 提取关键词
        keywords = _extract_keywords(section_title, section_content)

        # 创建知识点
        entry = KnowledgeEntry(
            id=entry_id,
            title=f"{report_title} - {section_title}",
            content=section_content[:WIKI_MAX_CHUNK_SIZE * 3],  # 限制大小
            source_report_id=report_id,
            category=_determine_category(section_title, report_type),
            keywords=keywords,
            metadata={
                "report_type": report_type,
                "section_title": section_title,
                "char_count": len(section_content),
            },
        )

        entries.append(entry)

    logger.info("[Wiki] 从报告 %s 提取了 %d 个知识点", report_id, len(entries))

    return entries


def _split_into_sections(content: str) -> list[tuple[str, str]]:
    """将报告按章节分割

    Args:
        content: 报告内容

    Returns:
        (章节标题, 章节内容) 列表
    """
    sections = []

    # Markdown 标题分割
    pattern = r'^(#{1,3})\s+(.+?)$'
    lines = content.split('\n')

    current_title = "引言"
    current_content = []

    for line in lines:
        match = re.match(pattern, line)
        if match:
            # 保存上一个章节
            if current_content:
                sections.append((current_title, '\n'.join(current_content).strip()))

            # 开始新章节
            current_title = match.group(2).strip()
            current_content = []
        else:
            current_content.append(line)

    # 保存最后一个章节
    if current_content:
        sections.append((current_title, '\n'.join(current_content).strip()))

    return sections


def _generate_entry_id(report_id: str, section_title: str) -> str:
    """生成知识点 ID"""
    hash_input = f"{report_id}:{section_title}"
    return hashlib.sha256(hash_input.encode()).hexdigest()[:16]


def _extract_keywords(title: str, content: str) -> list[str]:
    """提取关键词

    Args:
        title: 章节标题
        content: 章节内容

    Returns:
        关键词列表
    """
    keywords = set()

    # 从标题提取
    title_words = re.findall(r'[\w一-鿿]+', title)
    keywords.update(title_words[:5])

    # 从内容提取高频词
    content_words = re.findall(r'[\w一-鿿]+', content)
    word_freq = {}
    for word in content_words:
        if len(word) >= 2:
            word_freq[word] = word_freq.get(word, 0) + 1

    # 取高频词
    sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
    keywords.update(word for word, _ in sorted_words[:10])

    # 过滤停用词
    stopwords = {'的', '是', '在', '了', '和', '与', '或', '等', '及', '为', '以', '及'}
    keywords = [w for w in keywords if w not in stopwords and len(w) >= 2]

    return list(keywords)[:15]


def _determine_category(section_title: str, report_type: str) -> str:
    """确定知识点分类

    Args:
        section_title: 章节标题
        report_type: 报告类型

    Returns:
        分类名称
    """
    category_keywords = {
        "技术": ["技术", "架构", "实现", "方案", "系统", "平台"],
        "市场": ["市场", "竞争", "行业", "趋势", "规模", "增长"],
        "数据": ["数据", "统计", "分析", "指标", "图表"],
        "风险": ["风险", "挑战", "问题", "困难", "障碍"],
        "建议": ["建议", "对策", "策略", "措施", "方案"],
    }

    for category, keywords in category_keywords.items():
        if any(kw in section_title for kw in keywords):
            return category

    return report_type


# ══════════════════════════════════════════════════════════════
# 知识存储
# ══════════════════════════════════════════════════════════════


def save_knowledge_entry(entry: KnowledgeEntry) -> bool:
    """保存知识点

    Args:
        entry: 知识点条目

    Returns:
        是否成功
    """
    try:
        # 使用数据库存储
        if os.environ.get("DATABASE_URL"):
            return _save_to_database(entry)

        # 降级到内存存储
        _knowledge_store[entry.id] = entry.to_dict()

        # 更新索引
        for keyword in entry.keywords:
            if keyword not in _knowledge_index:
                _knowledge_index[keyword] = []
            if entry.id not in _knowledge_index[keyword]:
                _knowledge_index[keyword].append(entry.id)

        logger.debug("[Wiki] 保存知识点: %s", entry.id)
        return True

    except Exception as e:
        logger.error("[Wiki] 保存知识点失败: %s", e)
        return False


def _save_to_database(entry: KnowledgeEntry) -> bool:
    """保存到数据库"""
    try:
        from database import get_db_session
        from models import WikiKnowledge

        with get_db_session() as session:
            # 检查是否存在
            existing = session.query(WikiKnowledge).filter_by(id=entry.id).first()

            if existing:
                # 更新
                existing.title = entry.title
                existing.content = entry.content
                existing.keywords = entry.keywords
                existing.tags = entry.tags
                existing.updated_at = datetime.now(UTC)
                existing.version += 1
            else:
                # 新建
                db_entry = WikiKnowledge(
                    id=entry.id,
                    title=entry.title,
                    content=entry.content,
                    source_report_id=entry.source_report_id,
                    category=entry.category,
                    keywords=entry.keywords,
                    tags=entry.tags,
                    metadata=entry.metadata,
                )
                session.add(db_entry)

            session.commit()

        return True

    except Exception as e:
        logger.error("[Wiki] 数据库保存失败: %s", e)
        return False


# ══════════════════════════════════════════════════════════════
# 知识检索
# ══════════════════════════════════════════════════════════════


def search_knowledge(
    query: str,
    category: str = None,
    limit: int = 10,
    use_semantic: bool = True,
) -> list[dict]:
    """搜索知识点

    Args:
        query: 搜索查询
        category: 分类过滤
        limit: 返回数量限制
        use_semantic: 是否使用语义搜索

    Returns:
        知识点列表
    """
    if not WIKI_ENABLED:
        return []

    # 提取查询关键词
    query_keywords = _extract_keywords(query, query)

    results = []

    # 关键词匹配
    if os.environ.get("DATABASE_URL"):
        results = _search_from_database(query_keywords, category, limit)
    else:
        results = _search_from_memory(query_keywords, category, limit)

    # 语义搜索增强
    if use_semantic and len(results) < limit:
        semantic_results = _semantic_search(query, limit - len(results))
        results.extend(semantic_results)

    # 按相关度排序
    results = _rank_results(results, query_keywords)

    logger.info("[Wiki] 搜索 '%s' 找到 %d 条结果", query, len(results))

    return results[:limit]


def _search_from_memory(
    query_keywords: list[str],
    category: str = None,
    limit: int = 10,
) -> list[dict]:
    """从内存存储搜索"""
    matched_ids = set()

    for keyword in query_keywords:
        if keyword in _knowledge_index:
            matched_ids.update(_knowledge_index[keyword])

    results = []
    for entry_id in matched_ids:
        if entry_id in _knowledge_store:
            entry = _knowledge_store[entry_id]
            if category is None or entry.get("category") == category:
                results.append(entry)

    return results[:limit]


def _search_from_database(
    query_keywords: list[str],
    category: str = None,
    limit: int = 10,
) -> list[dict]:
    """从数据库搜索"""
    try:
        from database import get_db_session
        from models import WikiKnowledge

        with get_db_session() as session:
            query = session.query(WikiKnowledge)

            if category:
                query = query.filter_by(category=category)

            # 关键词匹配
            conditions = []
            for keyword in query_keywords:
                conditions.append(WikiKnowledge.keywords.contains([keyword]))

            if conditions:
                from sqlalchemy import or_
                query = query.filter(or_(*conditions))

            entries = query.limit(limit).all()

            return [
                {
                    "id": e.id,
                    "title": e.title,
                    "content": e.content,
                    "category": e.category,
                    "keywords": e.keywords,
                    "relevance_score": 1.0,
                }
                for e in entries
            ]

    except Exception as e:
        logger.error("[Wiki] 数据库搜索失败: %s", e)
        return []


def _semantic_search(query: str, limit: int) -> list[dict]:
    """语义搜索（使用 LLM）"""
    try:
        # 使用 LLM 生成查询向量或相关关键词
        from tools.llm import chat

        prompt = f"""分析以下查询，提取最相关的关键词和概念：

查询: {query}

请返回 JSON 格式：
{{"keywords": ["关键词1", "关键词2"], "concepts": ["概念1", "概念2"]}}"""

        response = chat(
            messages=[{"role": "user", "content": prompt}],
            json_mode=True,
            temperature=0.1,
            node="wiki_semantic_search",
        )

        result = json.loads(response)
        expanded_keywords = result.get("keywords", []) + result.get("concepts", [])

        # 使用扩展关键词再次搜索
        return _search_from_memory(expanded_keywords, None, limit)

    except Exception as e:
        logger.warning("[Wiki] 语义搜索失败: %s", e)
        return []


def _rank_results(results: list[dict], query_keywords: list[str]) -> list[dict]:
    """对结果排序

    Args:
        results: 搜索结果
        query_keywords: 查询关键词

    Returns:
        排序后的结果
    """
    for result in results:
        # 计算关键词匹配分数
        entry_keywords = set(result.get("keywords", []))
        query_set = set(query_keywords)
        overlap = len(entry_keywords & query_set)

        result["relevance_score"] = overlap / max(len(query_set), 1)

    # 按分数降序
    results.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)

    return results


# ══════════════════════════════════════════════════════════════
# 知识复用
# ══════════════════════════════════════════════════════════════


def get_relevant_knowledge_for_topic(
    topic: str,
    report_type: str = "research",
    max_entries: int = 5,
) -> list[dict]:
    """获取与主题相关的知识点

    Args:
        topic: 报告主题
        report_type: 报告类型
        max_entries: 最大返回数量

    Returns:
        相关知识点列表
    """
    # 搜索相关知识
    results = search_knowledge(
        query=topic,
        category=None,  # 不限制分类
        limit=max_entries * 2,
        use_semantic=True,
    )

    # 过滤和增强
    relevant = []
    for entry in results:
        # 检查相关性
        if _is_relevant_to_topic(entry, topic, report_type):
            relevant.append(entry)

        if len(relevant) >= max_entries:
            break

    logger.info("[Wiki] 为主题 '%s' 找到 %d 条相关知识", topic, len(relevant))

    return relevant


def _is_relevant_to_topic(entry: dict, topic: str, report_type: str) -> bool:
    """判断知识点是否与主题相关"""
    # 简单的关键词匹配
    topic_words = set(re.findall(r'[\w一-鿿]+', topic.lower()))
    entry_words = set(entry.get("keywords", []))

    overlap = topic_words & entry_words

    # 至少有一个关键词匹配
    return len(overlap) > 0


def generate_report_context(topic: str, report_type: str = "research") -> str:
    """生成报告上下文

    基于知识库中的相关知识，生成可用于报告的上下文。

    Args:
        topic: 报告主题
        report_type: 报告类型

    Returns:
        上下文字符串
    """
    # 获取相关知识
    knowledge = get_relevant_knowledge_for_topic(topic, report_type)

    if not knowledge:
        return ""

    # 构建上下文
    context_parts = ["## 相关知识库内容\n"]
    context_parts.append("以下是从知识库中检索到的相关内容，可用于参考：\n")

    for i, entry in enumerate(knowledge, 1):
        context_parts.append(f"\n### 参考资料{i}: {entry['title']}\n")
        context_parts.append(f"分类: {entry.get('category', 'general')}\n")
        context_parts.append(f"内容摘要:\n{entry['content'][:500]}...\n")

    context = '\n'.join(context_parts)

    logger.info("[Wiki] 生成上下文长度: %d 字符", len(context))

    return context


# ══════════════════════════════════════════════════════════════
# 报告自动入库
# ══════════════════════════════════════════════════════════════


def auto_ingest_report(
    report_content: str,
    report_id: str,
    report_title: str,
    report_type: str = "research",
) -> int:
    """自动将报告入库到知识库

    Args:
        report_content: 报告内容
        report_id: 报告 ID
        report_title: 报告标题
        report_type: 报告类型

    Returns:
        入库的知识点数量
    """
    if not WIKI_ENABLED:
        logger.warning("[Wiki] 知识库未启用")
        return 0

    # 提取知识点
    entries = extract_knowledge_from_report(
        report_content=report_content,
        report_id=report_id,
        report_title=report_title,
        report_type=report_type,
    )

    # 保存
    saved_count = 0
    for entry in entries:
        if save_knowledge_entry(entry):
            saved_count += 1

    logger.info("[Wiki] 报告 %s 入库完成: %d/%d 知识点",
                report_id, saved_count, len(entries))

    return saved_count


# ══════════════════════════════════════════════════════════════
# 统计信息
# ══════════════════════════════════════════════════════════════


def get_wiki_stats() -> dict:
    """获取知识库统计信息"""
    if os.environ.get("DATABASE_URL"):
        try:
            from database import get_db_session
            from models import WikiKnowledge
            from sqlalchemy import func

            with get_db_session() as session:
                total = session.query(func.count(WikiKnowledge.id)).scalar()
                categories = session.query(
                    WikiKnowledge.category,
                    func.count(WikiKnowledge.id)
                ).group_by(WikiKnowledge.category).all()

                return {
                    "total_entries": total,
                    "by_category": dict(categories),
                    "enabled": WIKI_ENABLED,
                }

        except Exception as e:
            logger.error("[Wiki] 获取统计失败: %s", e)

    # 内存模式
    return {
        "total_entries": len(_knowledge_store),
        "by_category": {},
        "enabled": WIKI_ENABLED,
        "mode": "memory",
    }
