"""Background worker: `python -m app.worker` (or `--once` from cron)."""

import logging
import sys
import time

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.services.jobs import run_all

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
log = logging.getLogger("greenplot.worker")


def main() -> None:
    interval = get_settings().worker_interval_seconds
    while True:
        with SessionLocal() as db:
            try:
                log.info("jobs: %s", run_all(db))
            except Exception:
                log.exception("job run failed")
                db.rollback()
        if "--once" in sys.argv:
            return
        time.sleep(interval)


if __name__ == "__main__":
    main()
