# beetap-skills

BeeTap 相关技能集合(opencode / Agent Skills)。

| 技能 | 说明 |
|---|---|
| [`beetap-cli-python`](beetap-cli-python/) | 遥控 BeeTap IDEA 插件调试安卓真机的命令行工具(纯 Python 标准库,协议 v1 / 插件 1.3.10+) |

## 安装(opencode)

```sh
git clone https://github.com/lu9944/beetap-skills.git
ln -s "$PWD/beetap-skills/beetap-cli-python" ~/.config/opencode/skills/beetap-cli-python
```

或直接复制目录:

```sh
mkdir -p ~/.config/opencode/skills
cp -R beetap-cli-python ~/.config/opencode/skills/
```

## beetap-cli-python 技能

通过本地 HTTP 端点(默认 `http://127.0.0.1:9318`)遥控 IDEA 里的 BeeTap 插件,完成
「(插件侧)连接手机 → 编译运行/调试脚本 → 取证与验证」全流程。

- 命令: `doctor` / `status` / `projects` / `connect` / `run` / `stop` / `pause` / `resume` /
  `logs` / `monitor` / `screenshot` / `nodes` / `node-params` / `ocr` / `test-image` / `raw`
- 安装(技能/全局命令/更新卸载/常见问题): [`beetap-cli-python/INSTALL.md`](beetap-cli-python/INSTALL.md)
- 设备连接由 IDEA 插件单点管理(协议 v1 / 插件 1.3.10+ 起 CLI `/connect` 已禁用)
- 接口契约: [`beetap-cli-python/references/beetap-cli-protocol.md`](beetap-cli-python/references/beetap-cli-protocol.md)
- 用法与约定: [`beetap-cli-python/SKILL.md`](beetap-cli-python/SKILL.md)、[`beetap-cli-python/README.md`](beetap-cli-python/README.md)

## License

MIT(各技能目录内说明为准)
