import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi import HTTPException


COOKIE = "ledger-visitor"
# Per browser and across the deployment, respectively.
LIMITS = {
    "research": (3, 30),
    "chat": (15, 150),
    "forecast": (20, 200),
    "request": (500, 5000),
    "MCP request": (100, 1000),
}


def visitor_cookie(value, secret):
    def signature(visitor):
        return hmac.new(secret.encode(), visitor.encode(), hashlib.sha256).hexdigest()

    visitor, _, signed = value.partition(".")
    try:
        valid = UUID(visitor).hex == visitor and hmac.compare_digest(signature(visitor), signed)
    except (ValueError, TypeError):
        valid = False
    if valid:
        return visitor, None
    visitor = uuid4().hex
    return visitor, f"{visitor}.{signature(visitor)}"


def charge(store, visitor, category):
    current = datetime.now(timezone.utc)
    day = current.date()
    reset = datetime.combine(day + timedelta(days=1), datetime.min.time(), timezone.utc)
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("DELETE FROM public_usage WHERE day < ?", (day.isoformat(),))
        for scope, limit in zip((visitor, "all"), LIMITS[category]):
            result = db.execute(
                """INSERT INTO public_usage VALUES (?, ?, ?, 1)
                   ON CONFLICT(day, scope, category) DO UPDATE SET used = used + 1
                   WHERE used < ?""",
                (day.isoformat(), scope, category, limit),
            )
            if not result.rowcount:
                audience = "The site's" if scope == "all" else "Your"
                raise HTTPException(
                    429,
                    f"{audience} daily {category} limit has been reached. It resets at midnight UTC.",
                    headers={"Retry-After": str(max(1, int((reset - current).total_seconds())))},
                )
