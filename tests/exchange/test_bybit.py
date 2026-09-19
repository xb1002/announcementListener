import unittest
from datetime import datetime, timezone
from unittest.mock import Mock

from exchange.bybit import BybitAnnouncementSource


class BybitAnnouncementSourceTest(unittest.TestCase):
    def test_fetches_announcements_from_official_api(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "retCode": 0,
            "retMsg": "OK",
            "result": {
                "list": [
                    {
                        "title": "Bybit 将下架 TEST 交易对",
                        "url": "https://announcements.bybit.com/zh-MY/article/test/",
                        "publishTime": 1789639208000,
                    }
                ]
            },
        }
        source = BybitAnnouncementSource(categories=["delistings"])
        source.session.get = Mock(return_value=response)

        announcements = source.fetch_latest(limit=5)

        source.session.get.assert_called_once_with(
            source.API_URL,
            params={"locale": "zh-MY", "type": "delistings", "limit": 5},
            timeout=20,
        )
        self.assertEqual(len(announcements), 1)
        self.assertEqual(announcements[0].title, "Bybit 将下架 TEST 交易对")
        self.assertEqual(
            announcements[0].announcement_time,
            datetime.fromtimestamp(1789639208, tz=timezone.utc),
        )
        self.assertEqual(
            announcements[0].url,
            "https://announcements.bybit.com/zh-MY/article/test/",
        )

    def test_api_error_returns_no_announcements_for_failed_category(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "retCode": 10001,
            "retMsg": "invalid request",
            "result": {},
        }
        source = BybitAnnouncementSource(categories=["delistings"])
        source.session.get = Mock(return_value=response)

        self.assertEqual(source.fetch_latest(limit=5), [])


if __name__ == "__main__":
    unittest.main()
