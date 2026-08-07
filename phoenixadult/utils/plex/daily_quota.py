from __future__ import annotations

import time
from datetime import date, datetime, timedelta

from phoenixadult.utils import db

_PRUNE_AFTER_DAYS = 30


def today() -> str:
    return date.today().isoformat()


def seconds_until_midnight(now: float | None = None) -> int:
    moment = datetime.fromtimestamp(now if now is not None else time.time())
    midnight = datetime.combine(moment.date() + timedelta(days=1), datetime.min.time())
    return max(1, int((midnight - moment).total_seconds()))


def bump(scope: str, key: str, day: str | None = None) -> int:
    when = day or today()
    conn = db.connect()
    with conn:
        conn.execute(
            'INSERT INTO daily_requests (scope, key, day, count) VALUES (?, ?, ?, 1) '
            'ON CONFLICT(scope, key, day) DO UPDATE SET count = daily_requests.count + 1',
            (scope, key, when),
        )
        row = conn.execute('SELECT count FROM daily_requests WHERE scope = ? AND key = ? AND day = ?', (scope, key, when)).fetchone()
        conn.execute('DELETE FROM daily_requests WHERE day < ?', ((date.fromisoformat(when) - timedelta(days=_PRUNE_AFTER_DAYS)).isoformat(),))
    return int(row['count']) if row else 0


def usage(scope: str, key: str, day: str | None = None) -> int:
    row = db.connect().execute('SELECT count FROM daily_requests WHERE scope = ? AND key = ? AND day = ?', (scope, key, day or today())).fetchone()
    return int(row['count']) if row else 0
