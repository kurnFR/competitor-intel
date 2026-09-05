"""Run a bounded batch of durable crawler jobs.

Usage:
    python scripts/run_crawl_worker.py --limit 10 --worker-id crawler-01
"""

import argparse
import logging
import os

from app.db.session import SessionLocal
from app.services.crawler.job_processor import CrawlJobProcessor
from app.services.crawler.job_worker import process_retryable_jobs

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("CrawlWorker")


def main() -> int:
    parser = argparse.ArgumentParser(description="Process durable competitor-intel crawl jobs")
    parser.add_argument("--limit", type=int, default=10, help="Maximum jobs to process in this batch")
    parser.add_argument(
        "--worker-id",
        default=os.getenv("CRAWLER_WORKER_ID", "crawler-worker-1"),
        help="Stable identifier for this worker instance",
    )
    args = parser.parse_args()

    if args.limit < 1:
        parser.error("--limit must be >= 1")

    db = SessionLocal()
    try:
        processed = process_retryable_jobs(
            db,
            worker_id=args.worker_id,
            processor=CrawlJobProcessor(db),
            limit=args.limit,
        )
        logger.info("Crawl worker finished: %d job(s) completed successfully", processed)
        return 0
    except Exception:
        db.rollback()
        logger.exception("Crawl worker failed")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
