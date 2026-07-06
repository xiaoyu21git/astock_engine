"""
金融情感词典 — 单元测试
"""
import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from astock_engine.events.financial_lexicon import (
    FinancialLexicon,
    SentimentAnalyzer,
)


@pytest.fixture(scope="module")
def lexicon():
    return FinancialLexicon()


@pytest.fixture(scope="module")
def analyzer(lexicon):
    return SentimentAnalyzer(lexicon)


# ═══════════════════════════════════════════════════════════════
# FinancialLexicon — 词典查询
# ═══════════════════════════════════════════════════════════════

class TestFinancialLexicon:
    def test_word_scores(self, lexicon):
        """基础词查询"""
        assert lexicon.word_score("预增") == 0.55
        assert lexicon.word_score("立案调查") == -0.9
        assert lexicon.word_score("涨停") == 0.85
        assert lexicon.word_score("跌停") == -0.85

    def test_unknown_word(self, lexicon):
        """未知词返回 0"""
        assert lexicon.word_score("不存在的词xyz") == 0.0

    def test_phrase_priority(self, lexicon):
        """词组优先于单词"""
        assert lexicon.phrase_score("大幅预增") == 0.8

    def test_stats(self, lexicon):
        stats = lexicon.stats()
        assert stats["words_count"] >= 100
        assert stats["phrases_count"] >= 30


# ═══════════════════════════════════════════════════════════════
# SentimentAnalyzer — 情感分析
# ═══════════════════════════════════════════════════════════════

class TestSentimentAnalyzer:
    def test_positive_text(self, analyzer):
        """正面新闻 — 情感分 > 0"""
        score, detail = analyzer.analyze("公司业绩大幅预增，净利润同比增长50%")
        assert score > 0.0
        assert detail["token_count"] > 0
        assert detail["matched_count"] > 0

    def test_negative_text(self, analyzer):
        """负面新闻 — 情感分 < 0"""
        score, detail = analyzer.analyze(
            "公司被证监会立案调查，涉嫌信息披露违规")
        assert score < 0.0
        assert detail["matched_count"] > 0

    def test_degree_adverb(self, analyzer):
        """程度副词加权: 大幅预增 > 小幅预增"""
        s_strong, _ = analyzer.analyze("大幅预增")
        s_weak, _ = analyzer.analyze("小幅预增")
        assert s_strong > s_weak

    def test_negation_flip(self, analyzer):
        """否定词翻转: 未能扭亏 应接近负分"""
        score, _ = analyzer.analyze("公司未能扭亏，续亏")
        assert score < 0.0

    def test_mixed_text(self, analyzer):
        """混合文本 — 正负抵消, 接近中性"""
        score, detail = analyzer.analyze(
            "公司业绩大幅预增，但同时收到深交所问询函")
        # 正负情感抵消
        assert -0.5 < score < 0.8
        assert detail["matched_count"] >= 2  # 至少匹配两个情感词

    def test_empty_text(self, analyzer):
        """空文本 — 返回 0"""
        score, detail = analyzer.analyze("")
        assert score == 0.0
        assert detail["token_count"] == 0

    def test_no_sentiment_text(self, analyzer):
        """无情感文本 — 返回 0 或极低覆盖率"""
        score, detail = analyzer.analyze("今日上证指数收于3000点")
        assert abs(score) < 0.1
        assert detail["coverage"] < 0.2

    def test_delisting_risk(self, analyzer):
        """退市风险 — 强负面"""
        score, _ = analyzer.analyze(
            "公司股票可能被实施退市风险警示，面临终止上市风险")
        assert score < -0.5

    def test_buyback_positive(self, analyzer):
        """回购 — 正面"""
        score, _ = analyzer.analyze("公司拟回购股份，回购金额不低于1亿元")
        assert score > 0.0

    def test_limit_up(self, analyzer):
        """涨停 — 强正面"""
        score, _ = analyzer.analyze("该股今日涨停，连续三日涨停")
        assert score > 0.5

    def test_coverage_field(self, analyzer):
        """coverage 字段存在且在 [0, 1]"""
        _, detail = analyzer.analyze("净利润同比增长20%")
        assert 0.0 <= detail["coverage"] <= 1.0
        assert "trace" in detail
        for item in detail["trace"]:
            assert "word" in item
            assert "score" in item


# ═══════════════════════════════════════════════════════════════
# Fuzz — 模糊输入不崩溃
# ═══════════════════════════════════════════════════════════════

class TestLexiconFuzz:
    FUZZ_INPUTS = [
        "",
        "<html><body>公告内容</body></html>",
        "\\x00\\x01\\x02",
        "A" * 10000,
        "业绩预增!@#$%^&*()",
        "1234567890" * 100,
    ]

    def test_fuzz_no_crash(self, analyzer):
        """模糊输入不崩溃"""
        for text in self.FUZZ_INPUTS:
            try:
                score, detail = analyzer.analyze(text)
                assert -1.0 <= score <= 1.0
                assert isinstance(detail, dict)
            except Exception as e:
                pytest.fail(
                    f"Fuzz input crashed: {repr(text[:50])} | {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
