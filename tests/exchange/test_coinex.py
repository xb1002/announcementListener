import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

from exchange.coinex import CoinExAnnouncementSource


class CoinExAnnouncementSourceTest(unittest.TestCase):
    def test_parse_zendesk_articles(self):
        source = CoinExAnnouncementSource()
        payload = {
            "articles": [
                {
                    "title": "CoinEx关于支持DATA（Streamr）更名为STREAMR（Streamr）的公告",
                    "html_url": "https://coinex-announcement.zendesk.com/hc/zh-cn/articles/50787410078868",
                    "created_at": "2026-06-29T02:45:59Z",
                    "draft": False,
                }
            ]
        }

        announcements = source._parse_zendesk_articles(payload)

        self.assertEqual(len(announcements), 1)
        self.assertEqual(
            announcements[0].title,
            "CoinEx关于支持DATA（Streamr）更名为STREAMR（Streamr）的公告",
        )
        self.assertEqual(
            announcements[0].announcement_time,
            datetime(2026, 6, 29, tzinfo=timezone(timedelta(hours=8))),
        )
        self.assertEqual(
            announcements[0].url,
            "https://coinex-announcement.zendesk.com/hc/zh-cn/articles/50787410078868",
        )

    def test_fetch_by_category_falls_back_to_zendesk_when_markdown_has_no_announcements(self):
        source = CoinExAnnouncementSource()
        markdown_response = Mock()
        markdown_response.text = "根据相关部门针对数字货币产业的监管要求，我们无法为您IP所在地区的用户提供服务。"
        zendesk_response = Mock()
        zendesk_response.json.return_value = {
            "articles": [
                {
                    "title": "CoinEx测试公告",
                    "html_url": "https://coinex-announcement.zendesk.com/hc/zh-cn/articles/1",
                    "created_at": "2026-06-29T01:00:00Z",
                    "draft": False,
                }
            ]
        }

        with patch.object(
            source,
            "_get_with_retries",
            side_effect=[markdown_response, zendesk_response],
        ) as get_with_retries:
            announcements = source._fetch_by_category(None, limit=1)

        self.assertEqual(len(announcements), 1)
        self.assertEqual(announcements[0].title, "CoinEx测试公告")
        self.assertEqual(get_with_retries.call_count, 2)


if __name__ == "__main__":
    unittest.main()
