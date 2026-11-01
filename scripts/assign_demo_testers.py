"""Spread the audit trail's past runs across the demo testing team.

Usage:
    python -m scripts.assign_demo_testers

Creates the testers named in the cycle-activity directory (Rohan Mehta,
Priya Nair, Karan Joshi) as accounts that cannot sign in, then reassigns every
recorded test run to one of them or to the demo sign-in account, Anshu Sharma,
who takes most of them (about 70%). The choice is a hash of the log id, so
re-running gives the same result. New runs are recorded under whoever is
signed in, which in the demo is Anshu.
"""

from __future__ import annotations

import asyncio
import secrets
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.core.security import hash_password
from app.db.base import *  # noqa: F401,F403 — register all models for relationship resolution
from app.db.session import async_session_maker, engine
from app.models.test_log import TestLog
from app.models.user import User

LEAD = "Anshu Sharma"
# (name, email, title, share of runs out of 100)
TEAM = [
    ("Rohan Mehta", "rohan.mehta@velora-assurance.com", "Associate, Controls Testing", 15),
    ("Priya Nair", "priya.nair@velora-assurance.com", "Associate, Controls Testing", 10),
    ("Karan Joshi", "karan.joshi@velora-assurance.com", "Associate, Controls Testing", 5),
]


async def main() -> None:
    async with async_session_maker() as db:
        lead = (await db.execute(select(User).where(User.user_name == LEAD))).scalars().first()
        if lead is None:
            raise SystemExit(f"No {LEAD} account — run scripts.setup_phased_cycle first.")

        bands: list[tuple[int, int]] = []  # (upper bound of the hash band, user id)
        upper = 0
        for name, email, title, share in TEAM:
            user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
            if user is None:
                # A random password nobody holds: the account exists for the
                # audit trail only and cannot be signed in to.
                user = User(
                    user_name=name,
                    email=email,
                    password_hash=hash_password(secrets.token_urlsafe(32)),
                    job_title=title,
                    department="Controls Testing",
                    status="Inactive",
                )
                db.add(user)
                await db.flush()
                print(f"Created tester {name} <{email}>")
            upper += share
            bands.append((upper, user.user_id))

        logs = (await db.execute(select(TestLog))).scalars().all()
        counts: dict[int, int] = {}
        for log in logs:
            roll = zlib.crc32(f"log-{log.log_id}".encode()) % 100
            owner = next((uid for bound, uid in bands if roll < bound), lead.user_id)
            log.changed_by = owner
            counts[owner] = counts.get(owner, 0) + 1
        await db.commit()

        names = {u.user_id: u.user_name for u in (await db.execute(select(User))).scalars()}
        total = sum(counts.values()) or 1
        for uid, n in sorted(counts.items(), key=lambda kv: -kv[1]):
            print(f"  {names.get(uid, uid):<14} {n:>4} runs  ({n * 100 // total}%)")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
