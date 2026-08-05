"""
Python → C++ 事件桥接器
========================
将 FinancialEvent 写入 PG live.event_bridge 表,
C++ EventBridgePoller 轮询消费并发布到 C++ EventBus。

设计要点:
  - 仅写入, 不消费 (消费由 C++ 侧负责)
  - 批量 INSERT, 定期清理旧数据
  - 与 EventPublisher 并行, 互不阻塞
"""

import json
import logging
from datetime import datetime
from typing import List

logger = logging.getLogger("PgBridge")


class PgEventBridge:
    """PG 事件桥接器 — 写入端"""

    MAX_BATCH = 200      # 每批最多写入条数
    MAX_RETAIN_DAYS = 7  # 保留天数

    def __init__(self, pg_conn=None):
        self._pg = pg_conn
        self._write_count = 0

    def _ensure_pg(self) -> bool:
        if self._pg is not None:
            return True
        try:
            from tools.db_config import pg_connect
            self._pg = pg_connect()
            return True
        except Exception as e:
            logger.warning("[PgBridge] PG 连接失败: %s", e)
            return False

    def write_one(self, event) -> bool:
        """写入单条事件到桥接表"""
        return self.write_batch([event]) > 0

    def write_batch(self, events: list) -> int:
        """批量写入事件

        events: FinancialEvent 对象 (有 .event_type, .to_event_format_data())
        Returns: 成功写入条数
        """
        if not events:
            return 0
        if not self._ensure_pg():
            return 0

        written = 0
        try:
            cur = self._pg.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS live.event_bridge (
                    id          BIGSERIAL PRIMARY KEY,
                    created_at  TIMESTAMPTZ DEFAULT NOW(),
                    consumed    BOOLEAN DEFAULT FALSE,
                    event_type  VARCHAR(64)  NOT NULL,
                    data        JSONB        NOT NULL DEFAULT '{}',
                    metadata    JSONB        DEFAULT '{}'
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_event_bridge_consumed
                    ON live.event_bridge(consumed, id)
                    WHERE consumed = FALSE
            """)

            for i in range(0, len(events), self.MAX_BATCH):
                batch = events[i:i + self.MAX_BATCH]
                for event in batch:
                    payload = event.to_event_format_data()
                    data_json = json.dumps(payload.get("data", {}), ensure_ascii=False)
                    meta_json = json.dumps(payload.get("metadata", {}), ensure_ascii=False)
                    # 先尝试带 event_hash 的去重写入(需要 DDL 先执行), 失败则回退普通 INSERT
                    try:
                        import hashlib
                        eh = hashlib.sha256(event.title[:500].encode()).hexdigest()[:16]
                        cur.execute(
                            "INSERT INTO live.event_bridge (event_type, data, metadata, event_hash) "
                            "VALUES (%s,%s,%s,%s) ON CONFLICT (event_hash) DO NOTHING",
                            (event.event_type.value, data_json, meta_json, eh))
                    except Exception:
                        self._pg.rollback()
                        cur.execute(
                            "INSERT INTO live.event_bridge (event_type, data, metadata) "
                            "VALUES (%s,%s,%s)",
                            (event.event_type.value, data_json, meta_json))
                    written += 1

            self._pg.commit()
            self._write_count += written

            # 定期清理旧数据
            self._cleanup_old()

        except Exception as e:
            logger.error("[PgBridge] 写入失败: %s", e)
            try:
                self._pg.rollback()
            except Exception:
                pass
        return written

    def _cleanup_old(self):
        """清理超过保留期的旧数据"""
        try:
            cur = self._pg.cursor()
            cur.execute(
                "DELETE FROM live.event_bridge WHERE created_at < NOW() - INTERVAL '%s days'",
                (str(self.MAX_RETAIN_DAYS),)
            )
            self._pg.commit()
        except Exception:
            try:
                self._pg.rollback()
            except Exception:
                pass

    @property
    def write_count(self) -> int:
        return self._write_count
