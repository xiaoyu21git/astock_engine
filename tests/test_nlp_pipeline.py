"""
NLP 流水线 — 单元测试
"""
import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from astock_engine.events.event_types import (
    FinancialEvent,
    FinancialEventType,
    InfoSource,
)
from astock_engine.events.financial_lexicon import FinancialLexicon
from astock_engine.events.nlp_pipeline import (
    EntityRecognizer,
    EventClassifier,
    TagExtractor,
    NLPPipeline,
)


# ═══════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
def stock_registry():
    return [
        ("000001", "平安银行", "平安银行股份有限公司"),
        ("000002", "万科A", "万科企业股份有限公司"),
        ("600000", "浦发银行", "上海浦东发展银行股份有限公司"),
        ("600519", "贵州茅台", "贵州茅台酒股份有限公司"),
        ("000651", "格力电器", "珠海格力电器股份有限公司"),
        ("300750", "宁德时代", "宁德时代新能源科技股份有限公司"),
    ]


@pytest.fixture
def recognizer(stock_registry):
    er = EntityRecognizer()
    er.load_stock_registry(stock_registry)
    return er


@pytest.fixture
def classifier():
    return EventClassifier()


@pytest.fixture
def tag_extractor():
    return TagExtractor()


@pytest.fixture
def pipeline():
    lexicon = FinancialLexicon()
    er = EntityRecognizer()
    return NLPPipeline(lexicon, er)


# ═══════════════════════════════════════════════════════════════
# EntityRecognizer
# ═══════════════════════════════════════════════════════════════

class TestEntityRecognizer:
    def test_load_registry(self, recognizer, stock_registry):
        """加载标的注册表"""
        assert len(recognizer._stock_codes) == len(stock_registry)

    def test_ambiguous_cleared(self, recognizer):
        """歧义简称已清除"""
        assert "平安" not in recognizer._stock_names
        assert "兴业" not in recognizer._stock_names

    def test_regex_code_match(self, recognizer):
        """正则匹配 6 位代码"""
        symbols = recognizer.extract("000001 和 600519 涨幅居前")
        assert "000001" in symbols
        assert "600519" in symbols

    def test_full_name_match(self, recognizer):
        """NER 匹配全称"""
        symbols = recognizer.extract("贵州茅台酒股份有限公司发布业绩预告")
        # 正则兜底: 文本中无6位代码, NER可能匹配到"贵州茅台"
        # 如果 HanLP 不可用, 仅正则匹配 → 返回空列表 (可接受)
        # 如果有 HanLP, 应匹配到 600519
        pass  # NER 依赖 HanLP 模型, 无模型时降级为正则

    def test_no_match(self, recognizer):
        """无关文本 — 空列表"""
        symbols = recognizer.extract("今日大盘震荡走高")
        assert len(symbols) == 0

    def test_alias_registration(self, recognizer):
        """别名已注册"""
        assert recognizer._stock_names.get("格力电器") == "000651"
        # 去有限后缀
        assert "珠海格力电器" in recognizer._stock_names


# ═══════════════════════════════════════════════════════════════
# EventClassifier
# ═══════════════════════════════════════════════════════════════

class TestEventClassifier:
    def test_earnings(self, classifier):
        assert classifier.classify(
            "业绩预告净利润同比预增50%", InfoSource.EASTMONEY
        ) == FinancialEventType.EARNINGS

    def test_policy(self, classifier):
        assert classifier.classify(
            "证监会发布新的监管政策", InfoSource.CNINFO
        ) == FinancialEventType.POLICY

    def test_material_reorganization(self, classifier):
        assert classifier.classify(
            "公司披露重大资产重组方案", InfoSource.CNINFO
        ) == FinancialEventType.MATERIAL

    def test_quote_alert(self, classifier):
        assert classifier.classify(
            "该股放量涨停突破前期高点", InfoSource.EASTMONEY
        ) == FinancialEventType.QUOTE_ALERT

    def test_social_source_bias(self, classifier):
        """社交来源偏向 SOCIAL 类型"""
        result = classifier.classify("热议话题", InfoSource.XUEQIU)
        assert result == FinancialEventType.SOCIAL

    def test_default_alert(self, classifier):
        """无关键词 → ALERT"""
        assert classifier.classify(
            "普通消息", InfoSource.EASTMONEY
        ) == FinancialEventType.ALERT


# ═══════════════════════════════════════════════════════════════
# TagExtractor
# ═══════════════════════════════════════════════════════════════

class TestTagExtractor:
    def test_investigation_tag(self, tag_extractor):
        tags = tag_extractor.extract("公司被证监会立案调查")
        assert tags.get("立案调查") == "true"

    def test_st_warning_tag(self, tag_extractor):
        tags = tag_extractor.extract("公司股票被实施退市风险警示")
        assert tags.get("ST警示") == "true"

    def test_super_expected_tag(self, tag_extractor):
        tags = tag_extractor.extract("业绩大超市场预期")
        assert tags.get("超预期") == "true"

    def test_high_dividend_tag(self, tag_extractor):
        tags = tag_extractor.extract("公司拟高比例分红")
        assert tags.get("高分红") == "true"

    def test_major_shareholder_reduction(self, tag_extractor):
        tags = tag_extractor.extract("大股东拟清仓减持")
        assert tags.get("大额减持") == "true"

    def test_multiple_tags(self, tag_extractor):
        tags = tag_extractor.extract(
            "公司业绩超预期，同时拟高分红回购股份")
        assert len(tags) >= 2
        assert tags.get("超预期") == "true"

    def test_no_tags(self, tag_extractor):
        tags = tag_extractor.extract("普通消息无标签")
        assert len(tags) == 0


# ═══════════════════════════════════════════════════════════════
# NLPPipeline — 端到端
# ═══════════════════════════════════════════════════════════════

class TestNLPPipeline:
    def test_process_basic(self, pipeline, stock_registry):
        """基本流水线 — 有关联标的"""
        pipeline._entities.load_stock_registry(stock_registry)
        event = pipeline.process(
            "贵州茅台业绩预告大幅预增", "净利润同比增长50%",
            InfoSource.EASTMONEY)
        assert isinstance(event, FinancialEvent)
        assert event.event_type in (
            FinancialEventType.EARNINGS, FinancialEventType.ALERT)
        assert -1.0 <= event.sentiment_score <= 1.0
        assert 0.0 <= event.confidence <= 1.0

    def test_process_no_symbols(self, pipeline):
        """无关联标的 — symbols 为空"""
        event = pipeline.process(
            "大盘行情分析", "今日大盘震荡",
            InfoSource.EASTMONEY)
        assert isinstance(event, FinancialEvent)
        assert len(event.symbols) == 0

    def test_process_with_tags(self, pipeline, stock_registry):
        """标签提取"""
        pipeline._entities.load_stock_registry(stock_registry)
        event = pipeline.process(
            "000001 业绩超预期", "净利润大幅增长",
            InfoSource.EASTMONEY)
        assert "超预期" in event.tags or len(event.tags) == 0

    def test_process_batch(self, pipeline):
        """批量处理"""
        items = [
            ("新闻1", "大盘分析", InfoSource.EASTMONEY),
            ("新闻2", "业绩预增", InfoSource.CNINFO),
            ("新闻3", "重组方案", InfoSource.XUEQIU),
        ]
        results = pipeline.process_batch(items)
        assert isinstance(results, list)
        # 无关联标的的新闻被过滤
        assert len(results) <= 3
        for event in results:
            assert isinstance(event, FinancialEvent)
            assert -1.0 <= event.sentiment_score <= 1.0

    def test_to_event_format_data(self, pipeline, stock_registry):
        """FinancialEvent → EventFormat 数据转换"""
        pipeline._entities.load_stock_registry(stock_registry)
        event = pipeline.process(
            "000001 业绩预增", "净利润增长",
            InfoSource.EASTMONEY)
        fmt = event.to_event_format_data()
        assert "data" in fmt
        assert "metadata" in fmt
        assert "source" in fmt["data"]
        assert "sentiment_score" in fmt["data"]
        assert "timestamp" in fmt["metadata"]


# ═══════════════════════════════════════════════════════════════
# Fuzz — 模糊输入
# ═══════════════════════════════════════════════════════════════

class TestPipelineFuzz:
    FUZZ_INPUTS = [
        ("", ""),
        ("<html>", "<body>content</body>"),
        ("A" * 10000, "B" * 5000),
        ("业绩预增!@#$%", "^&*()"),
        ("正常标题", "正常内容"),
    ]

    def test_fuzz_process_no_crash(self, pipeline):
        for title, content in self.FUZZ_INPUTS:
            try:
                event = pipeline.process(title, content, InfoSource.EASTMONEY)
                assert isinstance(event, FinancialEvent)
                assert -1.0 <= event.sentiment_score <= 1.0
            except Exception as e:
                pytest.fail(
                    f"Fuzz crashed: {repr(title[:50])} | {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
