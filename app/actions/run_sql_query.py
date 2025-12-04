from __future__ import annotations

import logging
from typing import Any, Dict, List

from sqlalchemy import text

from app.database import engine
from . import ActionPlugin, register_plugin

logger = logging.getLogger(__name__)


class RunSqlQueryPlugin(ActionPlugin):
    """Execute read-only SQL queries against the configured database."""

    name = "run_sql_query"

    def execute(self, task_context: Dict[str, Any]) -> Dict[str, Any]:
        sql = task_context.get("sql")
        params = task_context.get("params") or {}
        limit = int(task_context.get("limit", 50))

        if not sql:
            raise ValueError("run_sql_query requires 'sql'")

        # Guardrails: disallow write operations in this helper
        lowered = sql.strip().lower()
        if any(lowered.startswith(prefix) for prefix in ["update", "delete", "insert", "drop", "alter"]):
            raise ValueError("run_sql_query is limited to SELECT/read-only queries")

        logger.info("[Action] Executing SQL with limit %s", limit)
        with engine.connect() as conn:
            result = conn.execute(text(sql), params)
            rows = [dict(row._mapping) for row in result.fetchmany(limit)]

        return {"rows": rows, "rowcount": len(rows), "limit": limit}


register_plugin(RunSqlQueryPlugin())

__all__ = ["RunSqlQueryPlugin"]
