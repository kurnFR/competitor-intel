import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

from app.services.crawler.job_queue import (
    DEAD_LETTER,
    QUEUED,
    RETRY_WAIT,
    RUNNING,
    SUCCESS,
    calculate_retry_delay,
    claim_retryable_jobs,
    mark_job_failure,
    mark_job_running,
    mark_job_success,
)


class CrawlJobQueueTests(unittest.TestCase):
    def make_job(self, status=QUEUED, max_retries=3):
        return SimpleNamespace(
            status=status,
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

    def test_retry_delay_is_bounded_exponential(self):
        self.assertEqual(calculate_retry_delay(1), 60)
        self.assertEqual(calculate_retry_delay(2), 120)
        self.assertEqual(calculate_retry_delay(3), 240)
        self.assertEqual(calculate_retry_delay(10), 3600)

    def test_job_moves_from_queued_to_running(self):
        now = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)
        job = self.make_job()

        mark_job_running(job, "worker-1", now)

        self.assertEqual(job.status, RUNNING)
        self.assertEqual(job.worker_id, "worker-1")
        self.assertEqual(job.last_attempt_at, now)
        self.assertEqual(job.started_at, now)
        self.assertIsNone(job.next_retry_at)

    def test_failure_schedules_retry(self):
        now = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)
        job = self.make_job(status=RUNNING)

        mark_job_failure(job, "HTTP 503", http_status=503, now=now)

        self.assertEqual(job.status, RETRY_WAIT)
        self.assertEqual(job.retry_count, 1)
        self.assertEqual(job.next_retry_at, now + timedelta(seconds=60))
        self.assertEqual(job.http_status, 503)
        self.assertIsNone(job.completed_at)

    def test_permanent_failure_dead_letters_without_consuming_retry_budget(self):
        now = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)
        job = self.make_job(status=RUNNING, max_retries=3)

        mark_job_failure(job, "HTTP 404", http_status=404, now=now, retryable=False)

        self.assertEqual(job.status, DEAD_LETTER)
        self.assertEqual(job.retry_count, 0)
        self.assertIsNone(job.next_retry_at)
        self.assertEqual(job.completed_at, now)

    def test_failure_after_retry_budget_moves_to_dead_letter(self):
        now = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)
        job = self.make_job(status=RUNNING, max_retries=2)
        job.retry_count = 2

        mark_job_failure(job, "HTTP 503", http_status=503, now=now)

        self.assertEqual(job.status, DEAD_LETTER)
        self.assertEqual(job.retry_count, 3)
        self.assertIsNone(job.next_retry_at)
        self.assertEqual(job.completed_at, now)

    def test_success_clears_retry_state(self):
        now = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)
        job = self.make_job(status=RUNNING)
        job.retry_count = 2
        job.next_retry_at = now - timedelta(minutes=1)
        job.error_message = "old error"

        mark_job_success(job, http_status=200, content_hash="abc", now=now)

        self.assertEqual(job.status, SUCCESS)
        self.assertEqual(job.completed_at, now)
        self.assertIsNone(job.next_retry_at)
        self.assertIsNone(job.error_message)
        self.assertEqual(job.http_status, 200)
        self.assertEqual(job.content_hash, "abc")

    def test_invalid_state_transition_is_rejected(self):
        job = self.make_job(status=SUCCESS)
        with self.assertRaises(ValueError):
            mark_job_running(job, "worker-1")

    def test_claim_query_uses_retryable_statuses_and_row_lock(self):
        query = Mock()
        query.filter.return_value = query
        query.order_by.return_value = query
        query.with_for_update.return_value = query
        query.limit.return_value = query
        query.all.return_value = []

        db = Mock()
        db.query.return_value = query

        jobs = claim_retryable_jobs(db, now=datetime(2026, 9, 5, tzinfo=timezone.utc), limit=5)

        self.assertEqual(jobs, [])
        db.query.assert_called_once()
        query.with_for_update.assert_called_once_with(skip_locked=True)
        query.limit.assert_called_once_with(5)


if __name__ == "__main__":
    unittest.main()
