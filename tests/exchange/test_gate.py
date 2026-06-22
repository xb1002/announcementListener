import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch

from exchange.gate import GateAnnouncementSource


class GateAnnouncementSourceTest(unittest.TestCase):
    def test_parse_markdown_listing(self):
        markdown = (
            "[Gate 关于下架 TEST 的公告 2026-06-18 3,876]"
            "(https://www.gate.com/zh/announcements/article/100216)"
        )
        source = GateAnnouncementSource(fetch_details=False)

        announcements = source._parse_markdown_listing(markdown, limit=10)

        self.assertEqual(len(announcements), 1)
        self.assertEqual(announcements[0].title, "Gate 关于下架 TEST 的公告")
        self.assertEqual(
            announcements[0].announcement_time,
            datetime(2026, 6, 18, tzinfo=timezone.utc),
        )
        self.assertTrue(announcements[0].url.endswith("/100216"))

    def test_relative_time_uses_article_detail(self):
        markdown = (
            "[Gate 测试公告 2 小时前 1,509]"
            "(https://www.gate.com/zh/announcements/article/100258)"
        )
        source = GateAnnouncementSource(fetch_details=False)

        with patch.object(
            source,
            "_fetch_markdown_detail_time",
            return_value=datetime(2026, 6, 22, 8, 0, tzinfo=timezone.utc),
        ) as fetch_time:
            announcements = source._parse_markdown_listing(markdown, limit=10)

        fetch_time.assert_called_once()
        self.assertEqual(announcements[0].title, "Gate 测试公告")
        self.assertEqual(
            announcements[0].announcement_time,
            datetime(2026, 6, 22, 8, 0, tzinfo=timezone.utc),
        )

    def test_fetch_markdown_detail_time_converts_utc8_to_utc(self):
        source = GateAnnouncementSource(fetch_details=False)
        response = Mock()
        response.text = "2026-06-22 16:38 (UTC+8)136 浏览量"
        response.raise_for_status.return_value = None

        with patch.object(source.session, "get", return_value=response):
            result = source._fetch_markdown_detail_time(
                "https://www.gate.com/zh/announcements/article/100261"
            )

        self.assertEqual(result, datetime(2026, 6, 22, 8, 38, tzinfo=timezone.utc))


if __name__ == "__main__":
    unittest.main()
