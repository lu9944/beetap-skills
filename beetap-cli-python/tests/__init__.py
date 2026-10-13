"""beetap-cli 单元测试(纯标准库 unittest,不依赖插件在线)。

运行:python3 -m unittest discover -s tests -v
"""

import os
import sys

# 支持直接运行单个测试文件:python3 tests/test_config.py
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
