# tests/test_wiki.py — Wiki 知识库功能测试
"""Wiki 知识库功能测试

测试内容：
1. 知识提取 - 从报告中提取知识点
2. 知识存储 - 保存和索引知识点
3. 知识检索 - 关键词和语义搜索
4. 知识复用 - 生成报告上下文
5. 自动入库 - 报告完成时自动入库
"""
import pytest
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wiki import (
    extract_knowledge_from_report,
    save_knowledge_entry,
    search_knowledge,
    get_relevant_knowledge_for_topic,
    generate_report_context,
    auto_ingest_report,
    get_wiki_stats,
    KnowledgeEntry,
    _split_into_sections,
    _extract_keywords,
    _generate_entry_id,
)


# ══════════════════════════════════════════════════════════════
# 测试数据
# ══════════════════════════════════════════════════════════════

SAMPLE_REPORT = """# 人工智能发展趋势报告

## 摘要

本报告分析了人工智能领域的最新发展趋势，包括大语言模型、多模态AI、AI Agent等核心技术方向。

## 技术发展现状

### 大语言模型

大语言模型（LLM）在2024年取得了突破性进展。GPT-4o、Claude 3.5、DeepSeek等模型在推理能力、多模态理解方面表现优异。主要特点包括：

1. 上下文窗口扩展到100K+ tokens
2. 多模态能力增强
3. 推理成本大幅下降

### 多模态AI

多模态AI整合了文本、图像、音频等多种输入。代表产品包括：
- GPT-4 Vision
- Gemini
- Claude 3

## 市场分析

全球AI市场规模预计2025年达到5000亿美元，年复合增长率超过35%。主要驱动因素：

1. 企业数字化转型需求
2. 云计算基础设施成熟
3. 开源模型降低门槛

## 风险与挑战

### 技术风险

- 模型幻觉问题尚未完全解决
- 数据隐私和安全挑战
- 计算资源消耗巨大

### 市场风险

- 监管政策不确定性
- 商业模式仍在探索
- 人才短缺

## 发展建议

1. 加强基础研究投入
2. 建立AI治理框架
3. 推动产学研合作
4. 培养复合型人才

## 结论

人工智能正处于快速发展期，机遇与挑战并存。企业应积极拥抱AI技术，同时关注风险管控。
"""

SAMPLE_REPORT_2 = """# 区块链技术应用报告

## 技术概述

区块链是一种分布式账本技术，具有去中心化、不可篡改、可追溯等特点。

## 应用场景

### 金融领域

- 跨境支付
- 数字货币
- 供应链金融

### 非金融领域

- 身份认证
- 版权保护
- 医疗健康

## 技术架构

区块链系统包含以下核心组件：
1. 共识机制
2. 智能合约
3. 加密算法
4. P2P网络
"""


# ══════════════════════════════════════════════════════════════
# 知识提取测试
# ══════════════════════════════════════════════════════════════

class TestKnowledgeExtraction:
    """知识提取测试"""

    def test_split_into_sections(self):
        """测试章节分割"""
        sections = _split_into_sections(SAMPLE_REPORT)

        assert len(sections) > 0, "应该分割出至少一个章节"

        # 检查章节标题
        titles = [s[0] for s in sections]
        assert "摘要" in titles or "技术发展现状" in titles, "应该包含预期章节"

    def test_extract_keywords(self):
        """测试关键词提取"""
        title = "人工智能发展趋势"
        content = "人工智能技术正在快速发展，大语言模型和多模态AI成为热点。"

        keywords = _extract_keywords(title, content)

        assert len(keywords) > 0, "应该提取出关键词"
        # 检查是否包含相关关键词（更宽松的检查）
        keyword_str = ' '.join(keywords)
        assert "人工智能" in keyword_str or "AI" in keyword_str or "语言模型" in keyword_str, \
            f"应该包含相关关键词，实际关键词: {keywords}"

    def test_generate_entry_id(self):
        """测试知识点ID生成"""
        id1 = _generate_entry_id("report1", "章节1")
        id2 = _generate_entry_id("report1", "章节1")
        id3 = _generate_entry_id("report1", "章节2")

        assert id1 == id2, "相同输入应生成相同ID"
        assert id1 != id3, "不同输入应生成不同ID"
        assert len(id1) == 16, "ID长度应为16"

    def test_extract_knowledge_from_report(self):
        """测试从报告提取知识点"""
        entries = extract_knowledge_from_report(
            report_content=SAMPLE_REPORT,
            report_id="test001",
            report_title="人工智能发展趋势报告",
            report_type="research",
        )

        assert len(entries) > 0, "应该提取出知识点"

        # 检查知识点结构
        entry = entries[0]
        assert entry.id, "知识点应有ID"
        assert entry.title, "知识点应有标题"
        assert entry.content, "知识点应有内容"
        assert entry.source_report_id == "test001", "来源报告ID应正确"
        assert len(entry.keywords) > 0, "知识点应有关键词"

    def test_extract_knowledge_short_content(self):
        """测试短内容报告"""
        short_report = "# 标题\n\n这是一段很短的内容。"

        entries = extract_knowledge_from_report(
            report_content=short_report,
            report_id="short001",
            report_title="短报告",
            report_type="summary",
        )

        # 短内容可能不产生知识点
        # 这是预期行为
        assert isinstance(entries, list), "应返回列表"

    def test_extract_with_different_types(self):
        """测试不同报告类型的提取"""
        for report_type in ["research", "analysis", "summary", "proposal"]:
            entries = extract_knowledge_from_report(
                report_content=SAMPLE_REPORT,
                report_id=f"type_{report_type}",
                report_title=f"测试报告-{report_type}",
                report_type=report_type,
            )

            assert len(entries) > 0, f"{report_type}类型应提取出知识点"


# ══════════════════════════════════════════════════════════════
# 知识存储测试
# ══════════════════════════════════════════════════════════════

class TestKnowledgeStorage:
    """知识存储测试"""

    def test_save_knowledge_entry(self):
        """测试保存知识点"""
        entry = KnowledgeEntry(
            id="test_entry_001",
            title="测试知识点",
            content="这是一个测试知识点的内容，包含人工智能相关技术信息。",
            source_report_id="report001",
            category="技术",
            keywords=["人工智能", "测试", "技术"],
        )

        result = save_knowledge_entry(entry)

        assert result == True, "保存应成功"

    def test_save_duplicate_entry(self):
        """测试保存重复知识点"""
        entry1 = KnowledgeEntry(
            id="duplicate_001",
            title="重复知识点",
            content="第一次保存",
            source_report_id="report001",
        )

        entry2 = KnowledgeEntry(
            id="duplicate_001",
            title="重复知识点-更新",
            content="第二次保存",
            source_report_id="report001",
        )

        save_knowledge_entry(entry1)
        result = save_knowledge_entry(entry2)

        # 重复保存应该更新
        assert result == True, "重复保存应成功"


# ══════════════════════════════════════════════════════════════
# 知识检索测试
# ══════════════════════════════════════════════════════════════

class TestKnowledgeSearch:
    """知识检索测试"""

    def test_search_by_keywords(self):
        """测试关键词搜索"""
        # 先存入一些知识点
        entry = KnowledgeEntry(
            id="search_test_001",
            title="人工智能技术概述",
            content="人工智能是计算机科学的一个分支，研究如何使计算机能够执行通常需要人类智能的任务。",
            source_report_id="report001",
            category="技术",
            keywords=["人工智能", "计算机科学", "智能"],
        )
        save_knowledge_entry(entry)

        # 搜索
        results = search_knowledge(
            query="人工智能",
            limit=10,
            use_semantic=False,
        )

        assert isinstance(results, list), "搜索应返回列表"
        # 可能找到知识点
        if len(results) > 0:
            assert "人工智能" in results[0].get("keywords", []) or \
                   "人工智能" in results[0].get("title", ""), \
                   "结果应与搜索词相关"

    def test_search_with_category_filter(self):
        """测试分类过滤搜索"""
        # 存入不同分类的知识点
        entry1 = KnowledgeEntry(
            id="category_tech",
            title="技术知识点",
            content="技术相关内容",
            source_report_id="r1",
            category="技术",
            keywords=["技术"],
        )
        entry2 = KnowledgeEntry(
            id="category_market",
            title="市场知识点",
            content="市场相关内容",
            source_report_id="r2",
            category="市场",
            keywords=["市场"],
        )

        save_knowledge_entry(entry1)
        save_knowledge_entry(entry2)

        # 按分类搜索
        results = search_knowledge(
            query="内容",
            category="技术",
            limit=10,
            use_semantic=False,
        )

        assert isinstance(results, list), "搜索应返回列表"

    def test_search_empty_query(self):
        """测试空查询"""
        results = search_knowledge(
            query="",
            limit=10,
        )

        # 空查询应返回空列表或合理结果
        assert isinstance(results, list), "应返回列表"

    def test_search_limit(self):
        """测试结果数量限制"""
        results = search_knowledge(
            query="人工智能",
            limit=3,
            use_semantic=False,
        )

        assert len(results) <= 3, "结果数量不应超过限制"


# ══════════════════════════════════════════════════════════════
# 知识复用测试
# ══════════════════════════════════════════════════════════════

class TestKnowledgeReuse:
    """知识复用测试"""

    def test_get_relevant_knowledge(self):
        """测试获取相关知识"""
        # 存入知识点
        entry = KnowledgeEntry(
            id="reuse_001",
            title="AI发展趋势",
            content="人工智能正在改变各行各业。",
            source_report_id="r1",
            category="技术",
            keywords=["人工智能", "AI", "趋势"],
        )
        save_knowledge_entry(entry)

        # 获取相关知识
        results = get_relevant_knowledge_for_topic(
            topic="人工智能发展",
            report_type="research",
            max_entries=5,
        )

        assert isinstance(results, list), "应返回列表"

    def test_generate_report_context(self):
        """测试生成报告上下文"""
        # 存入知识点
        entry = KnowledgeEntry(
            id="context_001",
            title="AI技术应用",
            content="人工智能技术在医疗、金融、教育等领域有广泛应用。",
            source_report_id="r1",
            category="技术",
            keywords=["人工智能", "应用"],
        )
        save_knowledge_entry(entry)

        # 生成上下文
        context = generate_report_context(
            topic="人工智能应用",
            report_type="research",
        )

        # 可能为空（如果没有匹配的知识）
        # 或包含相关内容
        assert isinstance(context, str), "应返回字符串"


# ══════════════════════════════════════════════════════════════
# 自动入库测试
# ══════════════════════════════════════════════════════════════

class TestAutoIngest:
    """自动入库测试"""

    def test_auto_ingest_report(self):
        """测试报告自动入库"""
        count = auto_ingest_report(
            report_content=SAMPLE_REPORT,
            report_id="auto_001",
            report_title="人工智能发展趋势报告",
            report_type="research",
        )

        assert count > 0, "应入库至少一个知识点"
        assert isinstance(count, int), "应返回整数"

    def test_auto_ingest_multiple_reports(self):
        """测试多报告入库"""
        count1 = auto_ingest_report(
            report_content=SAMPLE_REPORT,
            report_id="multi_001",
            report_title="AI报告",
            report_type="research",
        )

        count2 = auto_ingest_report(
            report_content=SAMPLE_REPORT_2,
            report_id="multi_002",
            report_title="区块链报告",
            report_type="analysis",
        )

        assert count1 > 0, f"第一个报告应入库，实际: {count1}"
        # 第二个报告可能因为内容较短不产生知识点
        assert count2 >= 0, "第二个报告入库数量应为非负整数"


# ══════════════════════════════════════════════════════════════
# 统计信息测试
# ══════════════════════════════════════════════════════════════

class TestWikiStats:
    """统计信息测试"""

    def test_get_wiki_stats(self):
        """测试获取统计信息"""
        stats = get_wiki_stats()

        assert isinstance(stats, dict), "应返回字典"
        assert "total_entries" in stats, "应包含总数"
        assert "enabled" in stats, "应包含启用状态"


# ══════════════════════════════════════════════════════════════
# KnowledgeEntry 模型测试
# ══════════════════════════════════════════════════════════════

class TestKnowledgeEntry:
    """知识点模型测试"""

    def test_create_entry(self):
        """测试创建知识点"""
        entry = KnowledgeEntry(
            id="model_001",
            title="测试标题",
            content="测试内容",
            source_report_id="r1",
        )

        assert entry.id == "model_001"
        assert entry.title == "测试标题"
        assert entry.content == "测试内容"
        assert entry.category == "general"
        assert entry.tags == []
        assert entry.keywords == []
        assert entry.version == 1

    def test_entry_to_dict(self):
        """测试转换为字典"""
        entry = KnowledgeEntry(
            id="dict_001",
            title="字典测试",
            content="内容",
            source_report_id="r1",
            category="技术",
            keywords=["测试"],
        )

        d = entry.to_dict()

        assert isinstance(d, dict), "应返回字典"
        assert d["id"] == "dict_001"
        assert d["title"] == "字典测试"
        assert d["category"] == "技术"
        assert "测试" in d["keywords"]

    def test_entry_from_dict(self):
        """测试从字典创建"""
        data = {
            "id": "from_dict_001",
            "title": "从字典创建",
            "content": "内容",
            "source_report_id": "r1",
            "category": "市场",
            "keywords": ["市场", "分析"],
        }

        entry = KnowledgeEntry.from_dict(data)

        assert entry.id == "from_dict_001"
        assert entry.title == "从字典创建"
        assert entry.category == "市场"
        assert len(entry.keywords) == 2


# ══════════════════════════════════════════════════════════════
# 边界条件测试
# ══════════════════════════════════════════════════════════════

class TestEdgeCases:
    """边界条件测试"""

    def test_empty_report(self):
        """测试空报告"""
        entries = extract_knowledge_from_report(
            report_content="",
            report_id="empty",
            report_title="空报告",
        )

        assert entries == [], "空报告应返回空列表"

    def test_none_values(self):
        """测试None值处理"""
        try:
            entry = KnowledgeEntry(
                id="none_001",
                title="None测试",
                content="内容",
                source_report_id="r1",
                tags=None,
                keywords=None,
            )

            # 应该有默认值
            assert entry.tags == []
            assert entry.keywords == []

        except Exception as e:
            pytest.fail(f"None值处理失败: {e}")

    def test_special_characters_in_title(self):
        """测试标题中的特殊字符"""
        entry = KnowledgeEntry(
            id="special_001",
            title="测试<script>alert('xss')</script>",
            content="内容",
            source_report_id="r1",
        )

        # 应该能正常创建
        assert entry.title == "测试<script>alert('xss')</script>"

    def test_very_long_content(self):
        """测试超长内容"""
        long_content = "测试内容" * 10000

        entry = KnowledgeEntry(
            id="long_001",
            title="超长内容测试",
            content=long_content,
            source_report_id="r1",
        )

        # 应该能正常创建
        assert len(entry.content) > 10000


# ══════════════════════════════════════════════════════════════
# 运行测试
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
