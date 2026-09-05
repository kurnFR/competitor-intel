import tempfile
import unittest
from pathlib import Path

from app.services.storage import LocalRawDocumentStore


class RawDocumentStoreTests(unittest.TestCase):
    def test_put_is_content_addressed_and_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = LocalRawDocumentStore(tmp)
            first = store.put(b"promotion brochure", "application/pdf", "source/1", "pdf")
            second = store.put(b"promotion brochure", "application/pdf", "source/1", "pdf")

            self.assertEqual(first.uri, second.uri)
            self.assertEqual(first.sha256, second.sha256)
            self.assertEqual(first.size_bytes, len(b"promotion brochure"))
            self.assertEqual(store.get(first.uri), b"promotion brochure")
            self.assertTrue(Path(first.uri[7:]).exists())

    def test_different_content_gets_different_object(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = LocalRawDocumentStore(tmp)
            first = store.put(b"one", "text/html", "source-1", "html")
            second = store.put(b"two", "text/html", "source-1", "html")
            self.assertNotEqual(first.uri, second.uri)
            self.assertNotEqual(first.sha256, second.sha256)


if __name__ == "__main__":
    unittest.main()
