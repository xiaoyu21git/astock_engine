"""
NLP 分析流水线
==============
输入: 原始文本 (title + content)
输出: 完整标注的 FinancialEvent (含 sentiment, entities, event_type, tags)

组件:
  EntityRecognizer   — HanLP NER + 正则 → 关联标的代码列表
  EventClassifier    — 关键词规则 → 事件类型 (业绩/政策/重大事项/社交/行情异动)
  TagExtractor       — 关键词规则 → 结构化标签 (超预期/立案调查/ST警示...)
  NLPPipeline        — 一站式流水线编排
"""

import logging
import re
import time
from typing import Dict, List, Optional, Tuple

from .event_types import FinancialEvent, FinancialEventType, InfoSource
from .financial_lexicon import FinancialLexicon, SentimentAnalyzer


# ═══════════════════════════════════════════════════════════════
# EntityRecognizer — 实体识别
# ═══════════════════════════════════════════════════════════════

class EntityRecognizer:
    """从金融文本中提取关联的 A 股标的代码

    两步策略:
      1. HanLP NER 识别机构名 → 匹配公司全称/简称
      2. 正则兜底匹配 6 位数字代码
    """

    # 歧义简称 — 单字/双字简称容易跨公司误匹配, 直接排除
    AMBIGUOUS_SHORT_NAMES: set = {
        "平安", "兴业", "中信", "招商", "华夏", "广发",
        "国信", "海通", "华泰", "东方", "西部",
    }

    def __init__(self):
        self._ner = None
        self._stock_names: Dict[str, str] = {}   # 公司名称 → 6位代码
        self._stock_codes: set = set()             # 所有有效 6位代码
        self._loaded = False

    # ── 标的注册表加载 ──

    def load_stock_registry(self, stocks: List[Tuple[str, str, str]]):
        """加载标的注册表

        Args:
            stocks: [(代码, 简称, 全称), ...]
                    例: [("000001", "平安银行", "平安银行股份有限公司"), ...]
        """
        for code, short_name, full_name in stocks:
            self._stock_names[short_name] = code
            self._stock_names[full_name] = code

            # 别名: 去掉 "股份有限公司"/"有限公司" 后缀
            alias = full_name
            for suffix in ("股份有限公司", "有限责任公司", "有限公司", "股份公司"):
                alias = alias.replace(suffix, "")
            if alias and alias != short_name and len(alias) >= 3:
                self._stock_names[alias] = code

            self._stock_codes.add(code)

        # 清空歧义简称
        for ambiguous in self.AMBIGUOUS_SHORT_NAMES:
            self._stock_names.pop(ambiguous, None)

        self._loaded = True
        logging.info("[EntityRecognizer] 标的注册表加载: %d 个标的",
                     len(self._stock_codes))

    def load_from_db(self, db_config: Optional[dict] = None):
        """从 PostgreSQL 加载标的注册表 (与 C++ MarketDataRepository 同源)"""
        try:
            import psycopg2
            conn = psycopg2.connect(
                **(db_config or {
                    "host": "localhost", "port": 5432,
                    "dbname": "astock_quant", "user": "postgres",
                    "password": "", "connect_timeout": 5,
                })
            )
            cur = conn.cursor()
            cur.execute(
                "SELECT si.symbol, si.short_name, si.full_name "
                "FROM ref.symbol_info si "
                r"WHERE si.is_listed = true AND si.symbol ~ '^\d{6}$' "
                "ORDER BY si.symbol"
            )
            rows = cur.fetchall()
            stocks = [(r[0], r[1], r[2]) for r in rows]
            cur.close()
            conn.close()
            self.load_stock_registry(stocks)
            logging.info("[EntityRecognizer] 从 PG 加载 %d 个标的", len(stocks))
        except ImportError:
            logging.warning("[EntityRecognizer] psycopg2 不可用, 请手动调用 load_stock_registry()")
        except Exception as e:
            logging.error("[EntityRecognizer] PG 加载失败: %s", e)

    # ── 实体提取 ──

    def _ensure_ner(self):
        if self._ner is not None:
            return
        try:
            import hanlp
            self._ner = hanlp.load(
                hanlp.pretrained.ner.MSRA_NER_ELECTRA_SMALL_ZH)
            logging.info("[EntityRecognizer] HanLP NER 模型加载完成")
        except ImportError:
            logging.warning("[EntityRecognizer] HanLP 不可用, NER 仅支持正则匹配")
            self._ner = _FALLBACK_NER
        except Exception as e:
            logging.error("[EntityRecognizer] HanLP NER 加载失败: %s", e)
            self._ner = _FALLBACK_NER

    def extract(self, text: str) -> List[str]:
        """从文本中提取关联标的代码列表 (去重有序)"""
        self._ensure_ner()

        symbols: List[str] = []

        # 1. HanLP NER: 机构名匹配
        if self._ner is not _FALLBACK_NER:
            try:
                result = self._ner(text)
                for entity_info in result:
                    entity_text = entity_info[0]
                    entity_type = entity_info[1]
                    if entity_type in ("ORGANIZATION", "PERSON", "LOCATION", "GPE"):
                        code = self._stock_names.get(entity_text)
                        if code and code not in symbols:
                            symbols.append(code)
            except Exception as e:
                logging.warning("[EntityRecognizer] NER 异常: %s", e)

        # 2. 正则兜底: 6 位数字代码
        try:
            code_pattern = re.compile(r'\b(\d{6})\b')
            for m in code_pattern.finditer(text):
                code = m.group(1)
                if code in self._stock_codes and code not in symbols:
                    symbols.append(code)
        except Exception as e:
            logging.warning("[EntityRecognizer] 正则异常: %s", e)

        return symbols


def _FALLBACK_NER(text: str) -> list:
    """HanLP 不可用时的降级 NER (空实现)"""
    return []


# ═══════════════════════════════════════════════════════════════
# EventClassifier — 事件分类
# ═══════════════════════════════════════════════════════════════

class EventClassifier:
    """基于关键词规则将金融文本归类到 FinancialEventType"""

    TYPE_RULES: List[Tuple[FinancialEventType, List[str]]] = [
        (FinancialEventType.EARNINGS, [
            "业绩预告", "业绩快报", "年报", "季报", "半年报",
            "净利润", "营收", "每股收益", "净资产收益率",
            "预增", "预减", "预亏", "预盈", "扭亏", "首亏", "续亏",
        ]),
        (FinancialEventType.POLICY, [
            "证监会", "银保监", "央行", "国务院", "发改委", "工信部",
            "财政部", "商务部", "交易所", "深交所", "上交所",
            "产业政策", "监管政策", "行业规范", "管理办法",
            "宏观政策", "货币政策", "财政政策",
        ]),
        (FinancialEventType.MATERIAL, [
            "重组", "收购", "并购", "增发", "配股", "借壳",
            "资产注入", "整体上市", "重大资产",
            "增持", "减持", "回购", "注销",
            "分红", "送转", "派息", "股权激励", "员工持股",
            "重大合同", "中标", "协议", "战略合作",
            "停牌", "复牌", "暂停上市",
        ]),
        (FinancialEventType.QUOTE_ALERT, [
            "涨停", "跌停", "放量", "缩量", "异动",
            "拉升", "跳水", "冲高", "回落", "震荡",
            "新高", "新低", "突破", "破位",
            "一字板", "天地板", "地天板",
        ]),
        (FinancialEventType.SOCIAL, [
            "股吧", "雪球", "热议", "热搜", "讨论区",
            "人气", "关注度", "浏览量", "转发", "评论",
        ]),
    ]

    def classify(self, text: str, source: InfoSource) -> FinancialEventType:
        """关键词投票 → 最高分事件类型"""
        scores: Dict[FinancialEventType, int] = {
            t: 0 for t in FinancialEventType
        }

        for event_type, keywords in self.TYPE_RULES:
            for kw in keywords:
                if kw in text:
                    scores[event_type] += 1

        # 社交来源偏向 SOCIAL 类型
        if source in (InfoSource.XUEQIU, InfoSource.CLS):
            scores[FinancialEventType.SOCIAL] += 2

        # 返回最高分
        best = max(scores, key=scores.get)
        return best if scores[best] > 0 else FinancialEventType.ALERT


# ═══════════════════════════════════════════════════════════════
# TagExtractor — 结构化标签提取
# ═══════════════════════════════════════════════════════════════

class TagExtractor:
    """从文本中提取结构化标签 (键→值)"""

    TAG_PATTERNS: Dict[str, List[str]] = {
        "超预期":     ["超预期", "好于预期", "优于预期", "超出市场预期", "大超预期"],
        "低于预期":   ["低于预期", "不及预期", "差于预期", "不达预期", "低于市场预期"],
        "立案调查":   ["立案调查", "被证监会调查", "涉嫌信息披露违规", "涉嫌信披违规",
                       "收到立案告知书", "被立案"],
        "问询函":     ["问询函", "关注函", "监管函", "警示函", "监管关注"],
        "ST警示":     ["ST", "*ST", "退市风险警示", "实施其他风险警示",
                       "可能被实施退市风险", "可能被*ST"],
        "高分红":     ["高分红", "高送转", "高比例分红", "大比例分红", "高股息"],
        "大额减持":   ["大额减持", "清仓减持", "大幅减持", "减持计划", "拟减持"],
        "回购计划":   ["回购计划", "股份回购", "回购方案", "回购注销", "回购股份"],
        "重大合同":   ["中标", "重大合同", "大单", "战略合作", "签订协议"],
        "资产重组":   ["重组", "重大资产重组", "资产注入", "借壳", "整体上市"],
        "业绩预告":   ["业绩预告", "业绩快报", "年报预告", "半年报预告", "季报预告"],
        "停复牌":     ["停牌", "复牌", "临时停牌", "紧急停牌", "暂停交易"],
    }

    def extract(self, text: str) -> Dict[str, str]:
        """提取标签 → 值为 "true" 表示命中"""
        tags: Dict[str, str] = {}
        for tag_name, patterns in self.TAG_PATTERNS.items():
            for pat in patterns:
                if pat in text:
                    tags[tag_name] = "true"
                    break
        return tags


# ═══════════════════════════════════════════════════════════════
# NLPPipeline — 一站式流水线
# ═══════════════════════════════════════════════════════════════

class NLPPipeline:
    """NLP 分析流水线: 实体识别 + 情感分析 + 事件分类 + 标签提取"""

    def __init__(
        self,
        lexicon: FinancialLexicon,
        entity_recognizer: EntityRecognizer,
        classifier: Optional[EventClassifier] = None,
        tag_extractor: Optional[TagExtractor] = None,
    ):
        self._sentiment = SentimentAnalyzer(lexicon)
        self._entities = entity_recognizer
        self._classifier = classifier or EventClassifier()
        self._tags = tag_extractor or TagExtractor()

    def process(
        self,
        title: str,
        content: str,
        source: InfoSource,
    ) -> FinancialEvent:
        """完整 NLP 分析流水线

        Args:
            title:   新闻标题
            content: 新闻正文
            source:  信息来源

        Returns:
            完整标注的 FinancialEvent
        """
        # 合并: 标题 + 正文前 500 字
        full_text = f"{title}。{content[:500]}"
        summary = content[:200] if len(content) > 200 else content

        # 1. 实体识别 → 关联标的代码
        symbols = self._entities.extract(full_text)

        # 2. 金融情感分析
        score, detail = self._sentiment.analyze(full_text)
        confidence = min(
            1.0,
            detail["matched_count"] / max(1, detail["token_count"]))

        # 3. 事件分类
        event_type = self._classifier.classify(full_text, source)

        # 4. 标签提取
        tags = self._tags.extract(full_text)

        return FinancialEvent(
            source=source.value,
            title=title,
            summary=summary,
            symbols=symbols,
            sentiment_score=score,
            event_type=event_type,
            confidence=confidence,
            tags=tags,
            timestamp=int(time.time() * 1000),
        )

    def process_batch(
        self,
        items: List[Tuple[str, str, InfoSource]],
    ) -> List[FinancialEvent]:
        """批量处理多条新闻"""
        results = []
        for title, content, source in items:
            try:
                event = self.process(title, content, source)
                if event.symbols:  # 只保留有关联标的的事件
                    results.append(event)
            except Exception as e:
                logging.error(
                    "[NLPPipeline] 批量处理异常: %s | %s",
                    title[:50], e)
        return results
