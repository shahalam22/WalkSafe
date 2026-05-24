import sqlite3
import pandas as pd

from .schema import DB_PATH


def get_sessions() -> pd.DataFrame:
    with sqlite3.connect(DB_PATH) as con:
        return pd.read_sql_query(
            """
            SELECT
                session_id,
                datetime(started_at, 'unixepoch', 'localtime') AS started,
                ROUND((COALESCE(ended_at, started_at) - started_at) / 60.0, 1) AS duration_min,
                total_frames
            FROM sessions
            ORDER BY started_at DESC
            """,
            con,
        )


def get_summary(session_id=None) -> dict:
    with sqlite3.connect(DB_PATH) as con:
        params = [session_id] if session_id else []
        where  = "WHERE session_id=?" if session_id else ""

        total_frames = con.execute(
            f"SELECT COUNT(*) FROM frames {where}", params
        ).fetchone()[0]

        avg_speed = con.execute(
            f"SELECT ROUND(AVG(ego_speed_ms), 2) FROM frames {where}", params
        ).fetchone()[0]

        total_agents = con.execute(
            f"SELECT COUNT(*) FROM agents {where}", params
        ).fetchone()[0]

        critical_count = con.execute(
            f"SELECT COUNT(*) FROM agents {where} {'AND' if where else 'WHERE'} risk_level='critical'",
            params,
        ).fetchone()[0]

    return {
        "total_frames":   total_frames,
        "avg_speed_ms":   avg_speed or 0.0,
        "total_agents":   total_agents,
        "critical_count": critical_count,
    }


def get_command_distribution(session_id=None) -> pd.DataFrame:
    with sqlite3.connect(DB_PATH) as con:
        if session_id:
            return pd.read_sql_query(
                "SELECT command, COUNT(*) AS count FROM frames WHERE session_id=? GROUP BY command ORDER BY count DESC",
                con, params=[session_id],
            )
        return pd.read_sql_query(
            "SELECT command, COUNT(*) AS count FROM frames GROUP BY command ORDER BY count DESC",
            con,
        )


def get_speed_over_time(session_id) -> pd.DataFrame:
    with sqlite3.connect(DB_PATH) as con:
        return pd.read_sql_query(
            "SELECT frame_idx, ego_speed_ms, action FROM frames WHERE session_id=? ORDER BY frame_idx",
            con, params=[session_id],
        )


def get_risk_distribution(session_id=None) -> pd.DataFrame:
    with sqlite3.connect(DB_PATH) as con:
        if session_id:
            return pd.read_sql_query(
                "SELECT risk_level, COUNT(*) AS count FROM agents WHERE session_id=? GROUP BY risk_level ORDER BY count DESC",
                con, params=[session_id],
            )
        return pd.read_sql_query(
            "SELECT risk_level, COUNT(*) AS count FROM agents GROUP BY risk_level ORDER BY count DESC",
            con,
        )


def get_action_distribution(session_id=None) -> pd.DataFrame:
    with sqlite3.connect(DB_PATH) as con:
        if session_id:
            return pd.read_sql_query(
                "SELECT action, COUNT(*) AS count FROM frames WHERE session_id=? GROUP BY action ORDER BY count DESC",
                con, params=[session_id],
            )
        return pd.read_sql_query(
            "SELECT action, COUNT(*) AS count FROM frames GROUP BY action ORDER BY count DESC",
            con,
        )
