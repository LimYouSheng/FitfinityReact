"""Prove actual PostgreSQL contention at the atomic commit boundary without timing the work."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic

from sqlalchemy import text

from app.database import Database


def contend_at_commit(settings, write):
    """Hold flushed originals until PostgreSQL reports the independent competitor waiting."""
    replicas = [Database(settings), Database(settings), Database(settings)]
    prepared, release = Event(), Event()
    pids = {}

    def apply(index):
        with replicas[index].transaction() as session:
            pids[index] = session.scalar(text("SELECT pg_backend_pid()"))
            result = write(session, index)
            session.flush()
            if index == 0:
                prepared.set()
                assert release.wait(4), "Commit was not released after observing contention"
            return pids[index], result

    try:
        # Warm the independent observer before holding any business locks.
        with replicas[2].engine.connect() as observer, ThreadPoolExecutor(max_workers=2) as pool:
            observer.execute(text("SELECT 1"))
            first = pool.submit(apply, 0)
            try:
                assert prepared.wait(4), "Original writer did not prepare its atomic effects"
                second = pool.submit(apply, 1)
                deadline = monotonic() + 4
                while monotonic() < deadline:
                    waiting = observer.scalar(
                        text(
                            "SELECT EXISTS (SELECT 1 FROM pg_locks "
                            "WHERE pid = :pid AND locktype = 'advisory' AND NOT granted)"
                        ),
                        {"pid": pids.get(1, -1)},
                    )
                    if waiting:
                        break
                    assert not second.done(), "Competitor did not wait for the original commit"
                else:
                    raise AssertionError("PostgreSQL did not report the competing lock wait")
            finally:
                release.set()
            return [first.result(), second.result()]
    finally:
        for database in replicas:
            database.close()
