from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import hashlib

@dataclass(frozen=True)
class Announcement:
    exchange: str
    title: str
    announcement_time: datetime
    url: str
    tag: Optional[str]   # 初始为 None

    @property
    def announcement_time_local(self) -> datetime:
        return self.announcement_time.astimezone()
    

    @property
    def hash(self) -> str:
        # unique_string = f"{self.exchange}-{self.title}-{self.announcement_time.isoformat()}-{self.url}"
        # 由于监听不同的category可能会抓取到相同标题和时间的公告，因此去掉url以避免重复
        unique_string = f"{self.exchange}-{self.title}-{self.announcement_time.isoformat()}"
        return hashlib.sha256(unique_string.encode('utf-8')).hexdigest()

@dataclass(frozen=True)
class RawAnnouncement:
    exchange: str
    title: str
    announcement_time: datetime
    url: str