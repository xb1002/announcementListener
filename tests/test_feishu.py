import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from core.model import Announcement
from feishu import FeishuNotifier, FeishuSecondaryNotifier


class FeishuNotifierTest(unittest.TestCase):
    def setUp(self):
        self.announcement = Announcement(
            exchange="Test",
            title="测试公告",
            announcement_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
            url="https://example.com/announcement",
            tag="测试",
        )

    @staticmethod
    def _successful_response():
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"code": 0, "msg": "success"}
        return response

    def test_single_webhook_remains_supported(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            notifier = FeishuNotifier(
                webhook_url="https://example.com/one",
                history_file=str(Path(temp_dir) / "history.txt"),
            )

            with patch("feishu.requests.post", return_value=self._successful_response()) as post:
                notifier.notify(self.announcement)

            post.assert_called_once()
            self.assertIn(self.announcement.hash, notifier.sent_hashes)

    def test_comma_separated_webhooks_receive_the_same_announcement(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            notifier = FeishuNotifier(
                webhook_url="https://example.com/one, https://example.com/two",
                history_file=str(Path(temp_dir) / "history.txt"),
            )

            with patch("feishu.requests.post", return_value=self._successful_response()) as post:
                notifier.notify(self.announcement)

            self.assertEqual(
                [call.args[0] for call in post.call_args_list],
                ["https://example.com/one", "https://example.com/two"],
            )
            self.assertIn(self.announcement.hash, notifier.sent_hashes)

    def test_webhooks_are_loaded_from_comma_separated_environment_value(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(
                os.environ,
                {"FEISHU_WEBHOOK_URL": "https://example.com/one,https://example.com/two"},
            ):
                notifier = FeishuNotifier(
                    history_file=str(Path(temp_dir) / "history.txt"),
                )

            self.assertEqual(
                notifier.webhook_urls,
                ["https://example.com/one", "https://example.com/two"],
            )

    def test_history_is_not_written_when_any_webhook_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            history_file = Path(temp_dir) / "history.txt"
            failed_response = self._successful_response()
            failed_response.json.return_value = {"code": 1, "msg": "failed"}
            notifier = FeishuNotifier(
                webhook_url="https://example.com/one,https://example.com/two",
                history_file=str(history_file),
            )

            with patch(
                "feishu.requests.post",
                side_effect=[failed_response, self._successful_response()],
            ) as post:
                with self.assertRaises(RuntimeError):
                    notifier.notify(self.announcement)

            self.assertEqual(post.call_count, 2)
            self.assertNotIn(self.announcement.hash, notifier.sent_hashes)
            self.assertFalse(history_file.exists())

    def test_secondary_notifier_supports_multiple_webhooks(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            notifier = FeishuSecondaryNotifier(
                webhook_url="https://example.com/one,https://example.com/two",
                history_file=str(Path(temp_dir) / "history.txt"),
            )

            self.assertTrue(notifier.enabled)
            self.assertEqual(len(notifier.webhook_urls), 2)


if __name__ == "__main__":
    unittest.main()
