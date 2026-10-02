"""Read-only queries behind the dashboard (FR-26). session_id None means all sessions."""
import sqlite3

import pandas as pd


def _read(db_path: str, sql: str, params=()) -> pd.DataFrame:
    with sqlite3.connect(db_path) as con:
        return pd.read_sql_query(sql, con, params=list(params))


def _where(session_id: str | None, column: str = "session_id") -> tuple[str, list]:
    return (f"WHERE {column} = ?", [session_id]) if session_id else ("WHERE 1 = 1", [])


def sessions(db_path: str) -> pd.DataFrame:
    return _read(db_path, """
        SELECT session_id, user_id,
               datetime(started_at, 'unixepoch', 'localtime') AS started,
               ROUND((COALESCE(ended_at, started_at) - started_at) / 60.0, 1) AS duration_min,
               total_decisions, end_reason
        FROM session ORDER BY started_at DESC""")


def summary(db_path: str, session_id: str | None, target_ms: int) -> dict:
    where, p = _where(session_id)
    with sqlite3.connect(db_path) as con:
        one = lambda sql: con.execute(sql, p).fetchone()[0]  # noqa: E731
        return {
            "decisions":   one(f"SELECT COUNT(*) FROM decision {where} AND source = 'server'"),
            "phone_stops": one(f"SELECT COUNT(*) FROM decision {where} AND source = 'phone'"),
            "avg_speed":   one(f"SELECT ROUND(AVG(user_speed_ms), 2) FROM decision {where}") or 0.0,
            "agents":      one(f"SELECT COUNT(DISTINCT session_id || ':' || track_id) FROM agent {where} "
                               "AND track_id >= 0"),
            "critical":    one(f"SELECT COUNT(*) FROM agent {where} AND risk = 'critical'"),
            "on_time_pct": one(f"SELECT ROUND(100.0 * AVG(delay_ms <= {int(target_ms)}), 1) FROM decision {where} "
                               "AND source = 'server' AND spoken = 1 AND delay_ms IS NOT NULL"),
        }


def counts(db_path: str, table: str, column: str, session_id: str | None) -> pd.DataFrame:
    assert (table, column) in {("decision", "command"), ("agent", "risk")}
    where, p = _where(session_id)
    return _read(db_path, f"SELECT {column}, COUNT(*) AS count FROM {table} {where} "
                          f"GROUP BY {column} ORDER BY count DESC", p)


def delays(db_path: str, session_id: str | None) -> pd.DataFrame:
    where, p = _where(session_id)
    return _read(db_path, f"SELECT delay_ms FROM decision {where} AND source = 'server' AND spoken = 1 "
                          "AND delay_ms IS NOT NULL", p)


def speed_over_time(db_path: str, session_id: str) -> pd.DataFrame:
    return _read(db_path, "SELECT captured_at - MIN(captured_at) OVER () AS t_s, user_speed_ms FROM decision "
                          "WHERE session_id = ? AND source = 'server' ORDER BY captured_at", [session_id])


def level_time(db_path: str, session_id: str | None) -> pd.DataFrame:
    """Seconds spent at each capability level, from the level-change events."""
    where, p = _where(session_id)
    changes = _read(db_path, f"SELECT session_id, occurred_at, to_level FROM event {where} "
                             "AND type = 'level_change' ORDER BY session_id, occurred_at", p)
    where_s, p = _where(session_id, "s.session_id")
    ends = _read(db_path, f"""
        SELECT s.session_id, COALESCE(s.ended_at, MAX(d.captured_at)) AS end_at
        FROM session s LEFT JOIN decision d ON d.session_id = s.session_id {where_s}
        GROUP BY s.session_id""", p).set_index("session_id")["end_at"]
    totals: dict[str, float] = {}
    for sid, rows in changes.groupby("session_id"):
        times  = list(rows["occurred_at"]) + [ends.get(sid)]
        for level, start, end in zip(rows["to_level"], times, times[1:], strict=False):
            if end is not None and pd.notna(end) and end > start:
                totals[level] = totals.get(level, 0.0) + end - start
    return pd.DataFrame({"level": list(totals), "seconds": [round(v, 1) for v in totals.values()]}) \
             .sort_values("level", ignore_index=True)


def decision_list(db_path: str, session_id: str) -> pd.DataFrame:
    return _read(db_path, "SELECT source, sequence, command FROM decision WHERE session_id = ? "
                          "ORDER BY captured_at", [session_id])


def decision_detail(db_path: str, session_id: str, source: str, sequence: int):
    """The decision with its reason chain, and the agents and openings it was made from."""
    key = [session_id, sequence]
    row = _read(db_path, "SELECT * FROM decision WHERE session_id = ? AND sequence = ? AND source = ?",
                key + [source])
    agents   = _read(db_path, "SELECT track_id, type, dist_m, approach_speed_ms, ttc_s, risk, motion "
                              "FROM agent WHERE session_id = ? AND sequence = ?", key)
    openings = _read(db_path, "SELECT direction, width_m, dist_m, chosen FROM opening "
                              "WHERE session_id = ? AND sequence = ?", key)
    return (row.iloc[0].to_dict() if len(row) else None), agents, openings
