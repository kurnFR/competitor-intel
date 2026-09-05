import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from app.services.crawler.job_errors import PermanentCrawlJobError
from app.services.crawler.job_worker import process_retryable_jobs
from app.services.crawler.job_queue import DEAD_LETTER, RETRY_WAIT, SUCCESS


class Query:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def with_for_update(self, **kwargs):
        return self

    def limit(self, value):
        return self

    def all(self):
        return self.rows

    def first(self):
        return self.rows[0] if self.rows else None


class FakeDb:
    def __init__(self, jobs):
        self.jobs = jobs
        self.commits = 0
        self.rollbacks = 0

    def query(self, model):
        return Query(self.jobs)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class CrawlJobWorkerTests(unittest.TestCase):
    def make_job(self, max_retries=3):
        return SimpleNamespace(
            id="job-1",
            status="QUEUED",
            started_at=None,
            completed_at=None,
            last_attempt_at=None,
            next_retry_at=None,
            worker_id=None,
            error_message=None,
            retry_count=0,
            max_retries=max_retries,
            http_status=None,
            content_hash=None,
        )

    def test_successful_processor_marks_job_success(self):
        job = self.make_job()
        db = FakeDb([job])
        now = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)

        processed = process_retryable_jobs(
            db,
            "worker-1",
            lambda _: (200, "abc123"),
            now=now,
            limit=1,
        )

        self.assertEqual(processed, 1)
        self.assertEqual(job.status, SUCCESS)
        self.assertEqual(job.worker_id, "worker-1")
        self.assertEqual(job.http_status, 200)
        self.assertEqual(job.content_hash, "abc123")
        self.assertGreaterEqual(db.commits, 2)

    def test_failed_processor_persists_retry_state(self):
        job = self.make_job()
        db = FakeDb([job])
        now = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)

        def fail(_):
            raise RuntimeError("temporary source failure")

        processed = process_retryable_jobs(db, "worker-1", fail, now=now, limit=1)

        self.assertEqual(processed, 0)
        self.assertEqual(job.status, RETRY_WAIT)
        self.assertEqual(job.retry_count, 1)
        self.assertIn("temporary source failure", job.error_message)
        self.assertEqual(db.rollbacks, 1)
        self.assertGreaterEqual(db.commits, 1)

    def test_permanent_processor_failure_dead_letters_without_retry(self):
        job = self.make_job(max_retries=3)
        db = FakeDb([job])

        def fail(_):
            raise PermanentCrawlJobError("HTTP 404")

        process_retryable_jobs(db, "worker-1", fail, limit=1)

        self.assertEqual(job.status, DEAD_LETTER)
        self.assertEqual(job.retry_count, 0)

    def test_exhausted_processor_failure_dead_letters_job(self):
        job = self.make_job(max_retries=0)
        db = FakeDb([job])

        def fail(_):
            raise RuntimeError("permanent source failure")

        process_retryable_jobs(db, "worker-1", fail, limit=1)

        self.assertEqual(job.status, DEAD_LETTER)
        self.assertEqual(job.retry_count, 1)


if __name__ == "__main__":
    unittest.main()
