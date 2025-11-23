"""
Binance 交易所公告监听实现

支持的公告类型:
- 新币上线 (catalogId: 49) https://www.binance.com/zh-CN/support/announcement/list/49
- 新交易对上线 (catalogId: 161) https://www.binance.com/zh-CN/support/announcement/list/161  
- U本位合约上线 (catalogId: 157) https://www.binance.com/zh-CN/support/announcement/list/157

如果需要监听其他类型公告，请参考 Binance 公告页面获取对应的 catalogId
并且添加到 CATALOG_IDS 字典中。

"""

import requests
from typing import Sequence, List
from datetime import datetime
from core.interface import AnnouncementSource
from core.model import RawAnnouncement


class BinanceAnnouncementSource(AnnouncementSource):
    """Binance 交易所公告数据源"""
    
    exchange = "Binance"
    
    # Binance 公告API端点
    BASE_URL = "https://www.binance.com/bapi/composite/v1/public/cms/article/list/query"
    
    # 公告分类ID
    CATALOG_IDS = {
        "new_listing": 49,      # 新币上线
        "new_trading_pair": 161, # 新交易对上线
        "new_futures": 157       # U本位合约上线
    }
    
    def __init__(self, catalog_ids: List[int] = None, timeout: int = 10):
        """
        初始化 Binance 公告源
        
        Args:
            catalog_ids: 要监听的公告分类ID列表，默认监听所有类型
            timeout: API请求超时时间（秒）
        """
        if catalog_ids is None:
            # 默认监听所有类型
            self.catalog_ids = list(self.CATALOG_IDS.values())
        else:
            self.catalog_ids = catalog_ids
        
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        })
    
    def fetch_latest(self, limit: int = 20) -> Sequence[RawAnnouncement]:
        """
        拉取最近的公告
        
        Args:
            limit: 每个分类拉取的公告数量
            
        Returns:
            RawAnnouncement 列表，按时间倒序排列
        """
        all_announcements = []
        
        for catalog_id in self.catalog_ids:
            try:
                announcements = self._fetch_by_catalog(catalog_id, limit)
                all_announcements.extend(announcements)
            except Exception as e:
                print(f"获取 Binance 公告失败 (catalogId={catalog_id}): {e}")
                continue
        
        # 按公告时间倒序排列
        all_announcements.sort(key=lambda x: x.announcement_time, reverse=True)
        
        return all_announcements
    
    def _fetch_by_catalog(self, catalog_id: int, limit: int) -> List[RawAnnouncement]:
        """
        根据分类ID拉取公告
        
        Args:
            catalog_id: 公告分类ID
            limit: 拉取数量
            
        Returns:
            RawAnnouncement 列表
        """
        # 使用 GET 请求，参数作为查询参数
        params = {
            "type": 1,
            "pageNo": 1,
            "pageSize": limit,
        }
        
        try:
            response = self.session.get(
                self.BASE_URL,
                params=params,
                timeout=self.timeout
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get("code") != "000000":
                raise Exception(f"API返回错误代码: {data.get('code')}")
            
            # 从返回的 catalogs 中找到对应的 catalogId
            catalogs = data.get("data", {}).get("catalogs", [])
            if not catalogs:
                raise Exception("API未返回任何 catalog 数据")
            
            # 查找匹配的 catalog
            target_catalog = None
            for catalog in catalogs:
                if catalog.get("catalogId") == catalog_id:
                    target_catalog = catalog
                    break
            
            if target_catalog is None:
                raise Exception(f"未找到 catalogId={catalog_id} 的数据")
            
            articles = target_catalog.get("articles", [])
            
            return self._parse_articles(articles)
            
        except requests.RequestException as e:
            raise Exception(f"API请求失败: {e}")
    
    def _parse_articles(self, articles: List[dict]) -> List[RawAnnouncement]:
        """
        解析文章数据为 RawAnnouncement
        
        Args:
            articles: API返回的文章列表
            
        Returns:
            RawAnnouncement 列表
        """
        announcements = []
        
        for article in articles:
            try:
                # 解析时间戳（毫秒）
                timestamp = article.get("releaseDate")
                if timestamp:
                    announcement_time = datetime.fromtimestamp(timestamp / 1000)
                else:
                    # 如果没有时间戳，使用当前时间
                    announcement_time = datetime.now()
                
                # 构造公告URL
                code = article.get("code", "")
                url = f"https://www.binance.com/zh-CN/support/announcement/{code}"
                
                announcement = RawAnnouncement(
                    exchange=self.exchange,
                    title=article.get("title", ""),
                    announcement_time=announcement_time,
                    url=url
                )
                
                announcements.append(announcement)
                
            except Exception as e:
                print(f"解析公告失败: {e}, article: {article}")
                continue
        
        return announcements
    
    def __del__(self):
        """关闭会话"""
        if hasattr(self, 'session'):
            self.session.close()


# 使用示例
if __name__ == "__main__":
    # 创建 Binance 公告源
    source = BinanceAnnouncementSource()
    
    # 拉取最近20条公告
    announcements = source.fetch_latest(limit=20)
    
    print(f"共获取 {len(announcements)} 条公告:\n")
    
    for ann in announcements:
        print(f"[{ann.exchange}] {ann.announcement_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"标题: {ann.title}")
        print(f"链接: {ann.url}")
        print("-" * 80)