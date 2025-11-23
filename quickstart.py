"""
快速测试脚本 - 执行一次完整流程

用于测试配置是否正确，不会进入无限循环。
"""

import os
from main import AnnouncementMonitor

def main():
    """单次运行测试"""
    
    # 检查环境变量
    webhook_url = os.getenv("FEISHU_WEBHOOK_URL")
    if not webhook_url:
        print("❌ 错误: 未设置 FEISHU_WEBHOOK_URL 环境变量")
        print("\n请在 .env 文件中配置：")
        print("FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/your-token")
        return
    
    print(f"✅ Webhook 配置: {webhook_url[:50]}...")
    print()
    
    # 创建监听器
    monitor = AnnouncementMonitor()
    
    # 检查是否需要初始化
    stats = monitor.notifier.get_stats()
    if stats["total_sent"] == 0 and monitor.init_history:
        print("\n⚠️  检测到首次运行，将初始化历史记录")
        print("这将标记当前所有公告为已推送，避免重复推送")
        response = input("\n是否继续？(y/n): ")
        if response.lower() != 'y':
            print("已取消")
            return
        monitor.initial_load()
    elif stats["total_sent"] > 0:
        print(f"\n✅ 已有历史记录: {stats['total_sent']} 条")
    
    # 执行一次监听
    print("\n" + "=" * 80)
    print("开始单次监听...")
    print("=" * 80)
    print()
    
    monitor.run_once()
    
    # 显示统计
    print("\n" + "=" * 80)
    print("测试完成")
    print("=" * 80)
    final_stats = monitor.notifier.get_stats()
    print(f"\n📊 统计信息:")
    print(f"  - 历史推送总计: {final_stats['total_sent']} 条")
    print(f"  - 标签规则数: {len(monitor.tagger.rules)} 条")
    print(f"  - 允许的标签: {monitor.filter.allowed_tags or '全部'}")
    print()
    print("💡 提示:")
    print("  - 如需正式运行，执行: python main.py")
    print("  - 修改配置: 编辑 config.yaml")
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  已中断")
    except Exception as e:
        print(f"\n\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
