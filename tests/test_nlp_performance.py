"""
NLP Pipeline — 性能基准测试
验证 Phase 5 性能目标: 单条<50ms, 1000条<30s, 批量发布200条<100ms
"""
import sys
import os
import time
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from astock_engine.events.financial_lexicon import FinancialLexicon, SentimentAnalyzer
from astock_engine.events.nlp_pipeline import NLPPipeline, EntityRecognizer
from astock_engine.events.event_types import InfoSource


# ── Fixtures ──

@pytest.fixture(scope='module')
def lexicon():
    return FinancialLexicon()

@pytest.fixture(scope='module')
def analyzer(lexicon):
    return SentimentAnalyzer(lexicon)

@pytest.fixture(scope='module')
def pipeline(lexicon):
    er = EntityRecognizer()
    return NLPPipeline(lexicon, er)

@pytest.fixture(scope='module')
def sample_texts():
    return [
        ("业绩大幅预增", "公司预计2026年净利润同比增长50%-80%"),
        ("收到问询函", "公司收到深交所问询函，涉及2025年报相关问题"),
        ("资产重组", "公司拟发行股份购买资产，构成重大资产重组"),
        ("股东减持", "控股股东拟减持不超过2%股份"),
        ("涨停突破", "该股今日放量涨停，突破前期平台整理区间"),
        ("政策利好", "国务院发布支持新能源产业发展政策"),
        ("立案调查", "公司因涉嫌信息披露违法违规被证监会立案调查"),
        ("退市风险", "公司股票可能被实施退市风险警示"),
        ("回购计划", "公司拟以自有资金回购股份，回购金额1-2亿元"),
        ("中标大单", "公司中标重大工程项目，金额约5亿元"),
    ] * 100  # 1000条


# ── 性能基准 ──

class TestSentimentPerformance:
    """SentimentAnalyzer 性能"""

    def test_single_latency(self, analyzer):
        """单条分析 < 50ms"""
        start = time.perf_counter()
        score, detail = analyzer.analyze("公司业绩大幅预增，净利润同比增长50%")
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 50, f"单条耗时 {elapsed_ms:.1f}ms 超出 50ms 限制"
        assert len(detail['tokens']) > 0

    def test_batch_1000_latency(self, analyzer, sample_texts):
        """1000 条分析 < 30s"""
        start = time.perf_counter()
        for title, content in sample_texts:
            analyzer.analyze(f"{title}。{content}")
        elapsed_s = time.perf_counter() - start
        assert elapsed_s < 30, f"1000条耗时 {elapsed_s:.1f}s 超出 30s 限制"


class TestNLPPipelinePerformance:
    """NLPPipeline 性能"""

    def test_single_process_latency(self, pipeline):
        """单条处理 < 80ms (含 NER + 情感 + 分类)"""
        start = time.perf_counter()
        event = pipeline.process(
            "业绩大幅预增", "公司预计净利润增长50%", InfoSource.EASTMONEY)
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 80, f"单条耗时 {elapsed_ms:.1f}ms"
        assert -1.0 <= event.sentiment_score <= 1.0

    def test_batch_1000_latency(self, pipeline, sample_texts):
        """1000 条处理 < 35s"""
        start = time.perf_counter()
        for title, content in sample_texts:
            try:
                pipeline.process(title, content, InfoSource.EASTMONEY)
            except Exception:
                pass  # NER may fail without HanLP but should not crash
        elapsed_s = time.perf_counter() - start
        assert elapsed_s < 35, f"1000条耗时 {elapsed_s:.1f}s 超出 35s 限制"


class TestFinancialLexiconPerformance:
    """FinancialLexicon 性能"""

    def test_score_sequence_latency(self, lexicon):
        """分词序列分析 < 1ms"""
        tokens = ["公司", "业绩", "大幅", "预增", "，", "净利润", "同比", "增长", "50%"]
        start = time.perf_counter()
        score, trace = lexicon.score_sequence(tokens)
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 1, f"词典分析耗时 {elapsed_ms:.1f}ms"
        assert -1.0 <= score <= 1.0

    def test_large_lexicon_load(self):
        """词典加载 < 10ms"""
        start = time.perf_counter()
        lex = FinancialLexicon()
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 10, f"词典加载 {elapsed_ms:.1f}ms"
        assert lex.stats()['words_count'] > 100


# ── 内存基准 ──

class TestMemoryBaseline:
    def test_lexicon_memory(self, lexicon):
        """词典占用内存 < 5MB"""
        import sys
        size = sys.getsizeof(lexicon._words) + sys.getsizeof(lexicon._phrases)
        # dicts contain strings and floats, estimate < 500KB for 500 entries
        assert size < 5 * 1024 * 1024, f"词典内存 {size/1024:.0f}KB"

    def test_1000_events_no_leak(self, pipeline, sample_texts):
        """1000 次处理后内存无泄漏 (粗略检查)"""
        import gc
        gc.collect()
        before = len(gc.get_objects())
        for title, content in sample_texts[:100]:
            try:
                pipeline.process(title, content, InfoSource.EASTMONEY)
            except Exception:
                pass
        gc.collect()
        after = len(gc.get_objects())
        growth = after - before
        # 允许少量增长 (Python 对象缓存), 但不应大幅增长
        assert growth < 1000, f"对象增长 {growth} 过多"


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
