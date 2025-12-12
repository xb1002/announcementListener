# 交易所公告监听器

自动监听多个交易所的最新公告，智能打标签，并推送到飞书机器人。

## 功能特性

- 🔄 **自动监听**: 定期从多个交易所获取最新公告
- 🏷️ **智能标签**: 基于正则表达式自动为公告打标签
- 🎯 **灵活过滤**: 只推送感兴趣的标签类型
- 📱 **飞书推送**: 自动推送到飞书群聊
- 🔁 **自动去重**: 避免重复推送相同公告
- ⚙️ **灵活配置**: 所有参数均可通过配置文件调整

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置飞书 Webhook

创建 `.env` 文件：

```bash
# 主频道 - 推送符合过滤规则的公告（必填）
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/your-webhook-token

# 次要频道 - 推送被主频道过滤掉的公告（可选）
FEISHU_SECONDARY_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/your-secondary-token
```

### 3. 配置监听规则

编辑 `config.yaml` 选择要监听的标签：

```yaml
filter:
  allowed_tags:
    - "新币上线"
    - "下架退市"
    - "重要公告"
```

### 4. 运行程序

```bash
# 测试运行（执行一次）
python quickstart.py

# 正式运行（进入循环）
python main.py
```

## 架构设计

### 核心组件

```
┌─────────────────────────────────────────────────────────────┐
│                       主程序 (main.py)                        │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ├──► AnnouncementSource (公告数据源)
                  │    └─ 从交易所获取原始公告
                  │       - Gate, MEXC, Huobi...
                  │
                  ├──► TitleTagger (标签器)
                  │    └─ 根据标题匹配标签
                  │       - 正则表达式规则
                  │
                  ├──► AnnouncementFilter (过滤器)
                  │    └─ 根据标签过滤公告
                  │
                  └──► FeishuNotifier (通知器)
                       └─ 推送到飞书并记录历史
```

### 数据流

```
交易所 API
    │
    ▼
RawAnnouncement (原始公告)
    │
    ▼
TitleTagger (打标签)
    │
    ▼
Announcement (带标签公告)
    │
    ▼
AnnouncementFilter (过滤)
    │
    ▼
FeishuNotifier (推送)
    │
    ▼
飞书群聊
```

### 目录结构

```
announcementListener/
├── core/                  # 核心接口和数据模型
│   ├── interface.py       # AnnouncementSource, TitleTagger, Notifier
│   └── model.py          # RawAnnouncement, Announcement
│
├── exchange/             # 交易所实现（8个）
│   ├── binance.py        # Binance (币安)
│   ├── okx.py           # OKX (欧易)
│   ├── gate.py          # Gate
│   ├── mexc.py          # MEXC
│   ├── huobi.py         # Huobi (HTX)
│   ├── bybit.py         # Bybit
│   ├── bitget.py        # Bitget
│   └── coinex.py        # CoinEx
│
├── main.py              # 主程序入口（持续监听）
├── quickstart.py        # 快速测试脚本（单次运行）
├── test_tagger.py       # 标签规则测试工具
├── fetch_all_raw.py     # 原始公告获取工具
├── tagger.py            # 标签器实现
├── feishu.py            # 飞书通知器
└── config.yaml          # 统一配置文件
```

## 配置说明

所有配置都在 `config.yaml` 中管理，包含三个部分：

### 1. 标签匹配规则 (tag_rules)

定义如何根据标题自动打标签：

```yaml
tag_rules:
  - tag: "新币上线"
    case_sensitive: false
    patterns:
      - "上线.*交易对"
      - "will list"
      - "listing"
```

- 规则按顺序匹配，第一个匹配成功即返回
- `patterns` 中的多个正则表达式是"或"关系
- 支持完整的 Python 正则表达式语法

### 2. 过滤规则 (filter)

控制哪些公告会被推送：

```yaml
filter:
  allowed_tags:
    - "新币上线"
    - "下架退市"
    - "重要公告"
  
  allow_no_tag: false
  max_days_ago: 3
```

- `allowed_tags`: 只推送这些标签的公告
- `allow_no_tag`: 是否推送没有匹配到标签的公告
- `max_days_ago`: 时间过滤，只推送最近 N 天内的公告（默认 3 天）

### 3. 运行参数 (monitor)

控制程序运行行为：

```yaml
monitor:
  init_history_on_first_run: true  # 首次运行是否初始化历史
  max_cycles: 0                    # 循环次数（0=无限）
  interval_seconds: 600            # 间隔时间（秒）
  interval_random: 50              # 随机偏移（秒）
  fetch_limit: 10                  # 每次获取数量
  notify_delay: 1.0                # 推送延迟（秒）
```

**参数说明：**

- `init_history_on_first_run`: 首次运行时标记现有公告为已推送，避免重复
- `max_cycles`: 最大循环次数，0 表示无限循环
- `interval_seconds`: 每次循环的平均间隔时间
- `interval_random`: 间隔时间的随机偏移，实际等待时间 = interval_seconds ± random(0, interval_random)
- `fetch_limit`: 每个交易所每次获取的公告数量
- `notify_delay`: 推送每条公告后等待的时间，避免发送过快被限流

## 使用示例

### 基本使用

```bash
# 直接运行（无限循环）
python main.py
```

程序会：
1. 首次运行时初始化历史记录
2. 从所有配置的交易所获取公告
3. 自动打标签并过滤
4. 推送到飞书
5. 等待指定时间后重复

### 测试运行

使用 `quickstart.py` 进行单次测试：

```bash
python quickstart.py
```

适合测试配置是否正确，不会进入循环。

### 工具脚本

项目提供了额外的工具脚本：

**1. 测试标签规则 (`test_tagger.py`)**

测试配置文件中的标签匹配规则是否正确：

```bash
# 默认获取每个交易所10条公告进行测试
python test_tagger.py

# 获取更多公告测试
python test_tagger.py -l 20

# 使用自定义配置文件
python test_tagger.py -c my_config.yaml
```

输出内容：
- 标签统计（每个标签匹配到多少条）
- 按标签分组的详细列表
- 每条公告的交易所、标题和匹配的标签

### 自定义使用

```python
from exchange.gate import GateAnnouncementSource
from tagger import RegexTitleTagger
from feishu import FeishuNotifier

# 1. 获取公告
source = GateAnnouncementSource()
raw_announcements = source.fetch_latest(limit=10)

# 2. 打标签
tagger = RegexTitleTagger()
announcements = [tagger.tag(raw) for raw in raw_announcements]

# 3. 推送
notifier = FeishuNotifier()
for ann in announcements:
    if ann.tag == "新币上线":
        notifier.notify(ann, delay=1.0)
```

## 如何扩展

### 扩展现有交易所的监听范围

如果你想为已支持的交易所添加更多公告类型（如新币上线、活动公告等），请参考：

📖 **[扩展交易所监听范围教程](docs/extend_exchange_monitoring.md)**

该文档详细说明了：
- 如何获取各交易所的分类参数（catalogId / category / section path 等）
- 如何修改配置字典
- 包含所有 8 个交易所的详细步骤和截图参考

### 添加新的交易所

1. 在 `exchange/` 目录创建新文件，例如 `binance.py`

2. 继承 `AnnouncementSource` 接口：

```python
from core.interface import AnnouncementSource
from core.model import RawAnnouncement
from typing import Sequence

class BinanceAnnouncementSource(AnnouncementSource):
    exchange = "Binance"
    
    def fetch_latest(self, limit: int = 20) -> Sequence[RawAnnouncement]:
        """从 Binance 获取公告"""
        # 实现获取逻辑
        announcements = []
        
        # ... 调用 API 获取数据 ...
        
        # 构造 RawAnnouncement 对象
        for item in data:
            ann = RawAnnouncement(
                exchange=self.exchange,
                title=item['title'],
                announcement_time=parse_time(item['time']),
                url=item['url']
            )
            announcements.append(ann)
        
        return announcements
```

3. 在 `main.py` 中注册：

```python
from exchange.binance import BinanceAnnouncementSource

class AnnouncementMonitor:
    def __init__(self, config_file: str = "config.yaml"):
        # ...
        self.sources = [
            GateAnnouncementSource(),
            MexcAnnouncementSource(),
            HuobiAnnouncementSource(),
            BinanceAnnouncementSource(),  # 添加新交易所
        ]
```

### 自定义标签规则

在 `config.yaml` 中添加新规则：

```yaml
tag_rules:
  - tag: "价格预警"
    case_sensitive: false
    patterns:
      - "价格异常"
      - "price alert"
      - "波动提示"
  
  - tag: "系统公告"
    patterns:
      - "系统.*公告"
      - "system.*notice"
```

**技巧：**

- 将优先级高的规则放在前面
- 使用 `(?<!xxx)` 排除特定模式
- 测试规则：`python tagger.py`

### 自定义通知器

如果想推送到其他平台（钉钉、企业微信等）：

1. 创建新的通知器，例如 `dingtalk.py`

2. 继承 `Notifier` 接口：

```python
from core.interface import Notifier
from core.model import Announcement

class DingTalkNotifier(Notifier):
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url
        self.sent_hashes = set()
        # ... 加载历史记录 ...
    
    def notify(self, ann: Announcement, delay: float = 0) -> None:
        """推送到钉钉"""
        if ann.hash in self.sent_hashes:
            return
        
        # 构建钉钉消息格式
        message = {
            "msgtype": "text",
            "text": {
                "content": f"{ann.title}\n{ann.url}"
            }
        }
        
        # 发送请求
        response = requests.post(self.webhook_url, json=message)
        
        # 记录历史
        if response.ok:
            self.sent_hashes.add(ann.hash)
            # ... 保存历史记录 ...
```

3. 在 `main.py` 中使用：

```python
from dingtalk import DingTalkNotifier

class AnnouncementMonitor:
    def __init__(self):
        # ...
        self.notifier = DingTalkNotifier(webhook_url="...")
```

### 扩展标签器

如果需要更复杂的标签逻辑（如使用 AI 模型）：

```python
from core.interface import TitleTagger
from core.model import RawAnnouncement, Announcement

class AITitleTagger(TitleTagger):
    def __init__(self):
        # 初始化 AI 模型
        pass
    
    def tag(self, raw: RawAnnouncement) -> Announcement:
        """使用 AI 模型打标签"""
        # 调用 AI 模型
        tag = self.ai_model.predict(raw.title)
        
        return Announcement(
            exchange=raw.exchange,
            title=raw.title,
            announcement_time=raw.announcement_time,
            url=raw.url,
            tag=tag
        )
```

## 常见问题

### Q: 如何避免首次运行推送大量公告？

A: 确保 `config.yaml` 中设置：

```yaml
monitor:
  init_history_on_first_run: true
```

这会在首次运行时将现有公告标记为已推送。

### Q: 如何调整监听频率？

A: 修改 `config.yaml`：

```yaml
monitor:
  interval_seconds: 300  # 5分钟检查一次
  interval_random: 30    # ±30秒随机偏移
```

### Q: 如何临时禁用某个标签？

A: 在 `config.yaml` 中注释掉：

```yaml
filter:
  allowed_tags:
    - "新币上线"
    # - "下架退市"  # 临时禁用
```

### Q: 推送失败怎么办？

A: 检查：
1. 飞书 Webhook URL 是否正确
2. 网络连接是否正常
3. 是否触发了飞书的限流（增加 `notify_delay`）

### Q: 如何查看历史记录？

A: 历史记录保存在 `feishu_sent_history.txt`：

```bash
# Windows查看记录数量
Get-Content feishu_sent_history.txt | Measure-Object -Line

# Linux/Mac查看记录数量
wc -l feishu_sent_history.txt

# 清空历史（谨慎使用！）
rm feishu_sent_history.txt
```

### Q: 如何测试标签规则是否正确？

A: 使用标签测试工具：

```bash
python test_tagger.py -l 10
```

这会获取公告并显示每条公告匹配的标签，帮助你调整 `config.yaml` 中的规则。


## 项目文件说明

### 主程序
- `main.py` - 主程序，持续监听并推送公告
- `quickstart.py` - 快速测试脚本，执行一次完整流程

### 工具脚本
- `test_tagger.py` - 测试标签匹配规则

### 核心模块
- `core/interface.py` - 定义核心接口
- `core/model.py` - 数据模型定义
- `tagger.py` - 标签器实现
- `feishu.py` - 飞书通知器实现

### 交易所适配器
- `exchange/binance.py` - Binance (币安)
- `exchange/okx.py` - OKX (欧易)
- `exchange/gate.py` - Gate
- `exchange/mexc.py` - MEXC
- `exchange/huobi.py` - Huobi (HTX)
- `exchange/bybit.py` - Bybit
- `exchange/bitget.py` - Bitget
- `exchange/coinex.py` - CoinEx

### 配置文件
- `config.yaml` - 统一配置（标签规则、过滤、运行参数）
- `.env` - 环境变量（飞书Webhook URL）
- `requirements.txt` - Python依赖包

### 数据文件
- `feishu_sent_history.txt` - 已推送公告的哈希记录

## 运行要求

- Python 3.7+
- 依赖包：
  - requests >= 2.31.0
  - python-dotenv >= 1.0.0
  - pyyaml >= 6.0.1

## 支持的交易所

- Binance (币安)
- OKX (欧易)
- Gate
- MEXC
- Huobi (HTX)
- Bybit
- Bitget
- CoinEx

## License

MIT
