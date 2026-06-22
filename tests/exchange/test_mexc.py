import unittest
from datetime import datetime, timezone

from exchange.mexc import MexcAnnouncementSource


class MexcAnnouncementSourceTest(unittest.TestCase):
    def test_parse_markdown_listing(self):
        markdown = """Title: MEXC

URL Source: https://www.mexc.com/zh-MY/announcements/delistings

Markdown Content:
MEXC 将于 2026年6月23日 15:00 (UTC+8) 下架 TEST 永续合约。 请注意其他事项。

MEXC 将于 2026年6月22日 12:30 (UTC+8) 下架 DEMO 永续合约。 请注意其他事项。
"""
        source = MexcAnnouncementSource()

        announcements = source._parse_markdown_listing(
            markdown,
            "https://www.mexc.com/zh-MY/announcements/delistings",
            limit=10,
        )

        self.assertEqual(len(announcements), 2)
        self.assertEqual(
            announcements[0].title,
            "MEXC 将于 2026年6月23日 15:00 (UTC+8) 下架 TEST 永续合约。",
        )
        self.assertEqual(
            announcements[0].announcement_time,
            datetime(2026, 6, 23, 7, 0, tzinfo=timezone.utc),
        )
        self.assertIn("#announcement-", announcements[0].url)
        self.assertNotEqual(announcements[0].url, announcements[1].url)

    def test_markdown_fingerprint_is_stable(self):
        markdown = "Markdown Content:\nMEXC 将于 2026年6月23日 15:00 下架 TEST。"
        source = MexcAnnouncementSource()

        first = source._parse_markdown_listing(markdown, "https://example.com", 1)
        second = source._parse_markdown_listing(markdown, "https://example.com", 1)

        self.assertEqual(first[0].url, second[0].url)
        self.assertEqual(first[0].announcement_time, second[0].announcement_time)

    def test_reader_payload_uses_real_article_links(self):
        payload = {
            "data": {
                "content": "MEXC 将于 2026年6月23日 15:00 下架 TEST。",
                "links": [
                    ["币种下架", "https://www.mexc.com/zh-MY/announcements/delistings"],
                    [
                        "TEST 永续合约下架通知",
                        "https://www.mexc.com/zh-MY/announcements/article/delisting-test-123",
                    ],
                ],
            }
        }
        source = MexcAnnouncementSource()

        announcements = source._parse_reader_payload(
            payload,
            "https://www.mexc.com/zh-MY/announcements/delistings",
            10,
        )

        self.assertEqual(announcements[0].title, "TEST 永续合约下架通知")
        self.assertEqual(
            announcements[0].url,
            "https://www.mexc.com/zh-MY/announcements/article/delisting-test-123",
        )


if __name__ == "__main__":
    unittest.main()
