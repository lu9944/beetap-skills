"""beetap-cli — BeeTap 插件 HTTP 控制接口的 Python 客户端(纯标准库)。

架构:beetap-cli → HTTP(127.0.0.1:9318) → IDEA BeeTap 插件 → 手机 BeeTap App。
设备连接由 IDEA 插件单点管理(协议 v1 / 插件 1.3.10+ 起 CLI /connect 已禁用)。

安装/使用见同目录 README.md;接口权威文档见 references/beetap-cli-protocol.md。
"""

__version__ = "1.3.10"  # 对齐协议 v1(/connect 禁用、单实例令牌 1003 等 1.3.10 行为已纳入)
