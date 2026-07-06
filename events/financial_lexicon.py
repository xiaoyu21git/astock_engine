"""
金融情感词典引擎
================

核心算法:
  1. HanLP 分词 → 词组序列
  2. 词典查询: 优先长词组匹配, 回退单词匹配
  3. 程度副词加权: "大幅预增" = 1.5 × 0.55 = 0.825
  4. 否定词翻转: "未能扭亏" → 扭亏(0.6) → 未能(-0.6)
  5. 加权求和 → 归一化到 [-1.0, 1.0]

词典来源:
  - 500 词 + 80 词组 (Phase 1)
  - 漏判日志自动收集低覆盖文本 (SenseAnalyzer.analyze coverage < 0.05)
  - Phase 5 扩充至 2000 词
"""

import json
import logging
import os
from typing import Dict, List, Optional, Tuple


class FinancialLexicon:
    """金融情感词典引擎"""

    # 程度副词权重 — 修饰后续情感词的倍增系数
    DEGREE_ADVERBS: Dict[str, float] = {
        "大幅": 1.5, "显著": 1.3, "明显": 1.2,
        "小幅": 0.7, "略微": 0.5, "微幅": 0.4,
        "极大": 1.6, "严重": 1.5, "极度": 1.7,
        "较大": 1.2, "一定": 0.8,
    }

    # 否定词 — 翻转后续 NEGATION_WINDOW 个词的情感符号
    NEGATION_WORDS: set = {
        "不", "未", "无", "非", "没",
        "难以", "未能", "无法", "尚无",
    }

    NEGATION_WINDOW: int = 4  # 否定词影响范围（词数）

    # 最大内存指纹数
    MAX_FINGERPRINTS: int = 100_000

    def __init__(self, lexicon_path: Optional[str] = None):
        if lexicon_path is None:
            lexicon_path = os.path.join(
                os.path.dirname(__file__),
                "financial_sentiment_lexicon.json",
            )
        with open(lexicon_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._words: Dict[str, float] = data.get("words", {})
        self._phrases: Dict[str, float] = data.get("phrases", {})

    # ── 查询接口 ──

    def word_score(self, word: str) -> float:
        """查询单个词的情感值"""
        return self._words.get(word, 0.0)

    def phrase_score(self, text: str) -> float:
        """查询词组的情感值 — 长词组优先"""
        if text in self._phrases:
            return self._phrases[text]
        return self._words.get(text, 0.0)

    # ── 核心算法: 分词序列 → 加权情感分 ──

    def score_sequence(
        self, tokens: List[str]
    ) -> Tuple[float, List[Tuple[str, float]]]:
        """对 HanLP 分词序列计算金融情感分

        Args:
            tokens: 分词后的词组序列 (HanLP 输出)

        Returns:
            (final_score, trace): 归一化情感分 [-1.0, 1.0] + 每个情感词的得分追踪
        """
        total = 0.0
        trace: List[Tuple[str, float]] = []
        negated = False
        neg_window = 0
        degree_mult = 1.0

        for token in tokens:
            # 程度副词 → 设置倍数 (作用于下一个情感词)
            if token in self.DEGREE_ADVERBS:
                degree_mult = self.DEGREE_ADVERBS[token]
                continue

            # 否定词 → 开启否定窗口
            if token in self.NEGATION_WORDS:
                negated = True
                neg_window = self.NEGATION_WINDOW
                degree_mult = 1.0
                continue

            # 否定窗口递减
            if negated:
                neg_window -= 1
                if neg_window <= 0:
                    negated = False

            # 查询词典
            s = self.phrase_score(token)
            if s != 0.0:
                s *= degree_mult
                if negated:
                    s = -s
                total += s
                trace.append((token, s))

            degree_mult = 1.0  # 程度副词只作用一次

        # 归一化: 除以 max(1, len(tokens) * 0.3) 防止短文本得分过高
        final = max(-1.0, min(1.0, total / max(1.0, len(tokens) * 0.3)))
        return final, trace

    # ── 词典统计 ──

    def stats(self) -> dict:
        return {
            "words_count": len(self._words),
            "phrases_count": len(self._phrases),
        }


class SentimentAnalyzer:
    """金融情感分析器 = HanLP 分词 + FinancialLexicon 词典"""

    def __init__(self, lexicon: FinancialLexicon):
        self._lexicon = lexicon
        self._tokenizer = None

    def _ensure_tokenizer(self):
        """延迟加载 HanLP 分词器 (首次调用 ~5s)"""
        if self._tokenizer is not None:
            return
        try:
            import hanlp
            self._tokenizer = hanlp.load(
                hanlp.pretrained.tok.COARSE_ELECTRA_SMALL_ZH
            )
            logging.info("[SentimentAnalyzer] HanLP 分词器加载完成")
        except ImportError:
            logging.warning(
                "[SentimentAnalyzer] HanLP 不可用, 使用 jieba 降级")
            import jieba
            self._tokenizer = jieba.lcut
        except Exception as e:
            logging.error(f"[SentimentAnalyzer] HanLP 加载失败: {e}")
            import jieba
            self._tokenizer = jieba.lcut

    def analyze(self, text: str) -> Tuple[float, dict]:
        """分析文本的金融情感

        Args:
            text: 待分析文本

        Returns:
            (score, detail): 情感分 [-1.0, 1.0] + 详细追踪
        """
        self._ensure_tokenizer()

        # HanLP 返回 list[str], jieba 也一样
        if callable(self._tokenizer):
            tokens = self._tokenizer(text)
        else:
            tokens = text.split()  # 极端降级

        score, trace = self._lexicon.score_sequence(list(tokens))

        coverage = len(trace) / max(1, len(tokens))

        detail = {
            "tokens": list(tokens),
            "trace": [{"word": w, "score": s} for w, s in trace],
            "token_count": len(tokens),
            "matched_count": len(trace),
            "coverage": coverage,
        }

        # 漏判日志: 文本含疑似情感但词典未命中 (用于持续扩充词典)
        if coverage < 0.05 and len(text) > 20:
            logging.debug(
                "[Lexicon] 低覆盖文本 (coverage=%.2f): %s... | tokens=%s",
                coverage, text[:100], tokens[:20])

        return score, detail
