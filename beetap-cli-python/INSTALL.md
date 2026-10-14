# beetap-cli-python 安装说明

> 技能用法见 [SKILL.md](SKILL.md),完整命令见 [commands.md](commands.md),接口契约见 [references/beetap-cli-protocol.md](references/beetap-cli-protocol.md)。

本技能有两种用法,可同时安装:

1. **作为 opencode 技能**(推荐):AI 读取 `SKILL.md` 自动使用,命令由技能目录里的 `bin/beetap-cli` 提供;
2. **作为全局命令 `beetap-cli`**:任何终端/AI 会话都能直接调用(软链或 pip 安装)。

## 0. 前提条件

| 项 | 要求 |
|---|---|
| Python | 3.9+(系统自带即可;**零第三方依赖**;本机验证 3.12 / 3.9.6) |
| IDEA | IntelliJ IDEA 已启动,且已打开含 BeeTap 工程的项目(控制端点随插件启动) |
| 插件 | BeeTap 插件协议 v1(1.3.5+,建议 1.3.10+) |
| 设备 | 手机已在 IDEA 插件里连接(CLI 不做连接;插件 1.3.10+ 起 `/connect` 已禁用) |

## 1. 获取代码

```sh
git clone https://github.com/lu9944/beetap-skills.git
cd beetap-skills/beetap-cli-python
```

也可以只把 `beetap-cli-python/` 目录复制到你自己的位置,后续命令按实际路径调整。

## 2. 安装为 opencode 技能

用户级(所有项目可用):

```sh
mkdir -p ~/.config/opencode/skills
# 方式 A:软链(推荐;git pull 后技能自动更新)
ln -s "$(pwd)" ~/.config/opencode/skills/beetap-cli-python
# 方式 B:复制(与仓库解耦,更新时需重新复制)
cp -R . ~/.config/opencode/skills/beetap-cli-python
```

项目级(只对当前项目生效,可随项目 git 一起走):

```sh
mkdir -p <项目>/.opencode/skills
ln -s "$(pwd)" <项目>/.opencode/skills/beetap-cli-python
```

安装后在 opencode 中应能识别到技能 `beetap-cli-python`;也可以让 AI 直接运行 `beetap-cli doctor` 验证。

Claude Code 同理:`cp -R . ~/.claude/skills/beetap-cli-python`。

## 3. 安装为全局命令(可选)

```sh
# 方式 A:软链到 PATH(先给入口脚本执行权限)
chmod +x bin/beetap-cli
sudo ln -s "$(pwd)/bin/beetap-cli" /usr/local/bin/beetap-cli

# 方式 B:pip 安装(pyproject 提供 beetap-cli 控制台入口)
pip install .
```

验证:

```sh
beetap-cli --version     # 应输出 beetap-cli 1.0.0
beetap-cli doctor        # 六项环境检查
```

## 4. 首次使用

1. 确认 IDEA 已打开 BeeTap 工程,手机已在插件里连接(插件里点「USB 调试」/「WiFi 直连」);
2. `beetap-cli doctor` 全部通过后开始:

   ```sh
   beetap-cli status                       # 看插件/设备/工程状态
   beetap-cli run -m <工程名> -k <关键字>    # 编译运行并等待结束
   beetap-cli screenshot -o shot.png       # 截图取证
   beetap-cli nodes --dir evidence         # 抓节点表(center 即点击坐标)
   ```

3. 设备未连接时:`beetap-cli connect --wait 60s`,期间在 IDEA 插件里点「USB 调试」,连上自动返回。

常用配置(`.env` 或环境变量):`BEETAP_URL` / `BEETAP_MODULE` / `BEETAP_TIMEOUT`,模板见 [.env.example](.env.example)。

## 5. 验证安装(可选)

```sh
python3 -m unittest discover -s tests -v    # 单元测试(当前 81 项),不依赖插件在线
```

## 6. 更新 / 卸载

```sh
# 更新
git pull                                    # 软链方式:立即生效
# 复制方式:重新 cp -R . ~/.config/opencode/skills/beetap-cli-python

# 卸载
rm ~/.config/opencode/skills/beetap-cli-python    # 技能(符号链接或目录)
sudo rm /usr/local/bin/beetap-cli                  # 全局命令(软链方式)
pip uninstall beetap-cli                           # 全局命令(pip 方式)
```

## 7. 常见问题

| 现象 | 处置 |
|---|---|
| `doctor` 退出码 5(插件不可达) | IDEA 未启动/插件未加载;或端口被 `-Dbeetap.cliPort=` 改过,用 `-u/--url` 同步 |
| 找不到 `python3` 或版本过低 | 安装 Python 3.9+;或用 `python3.x bin/beetap-cli` 显式指定解释器 |
| 运行入口报 `Permission denied` | `chmod +x bin/beetap-cli`,或改用 `python3 bin/beetap-cli` |
| Windows | 用 `python3 bin\beetap-cli`;或 `pip install .` 后直接 `beetap-cli` |
| 技能未被 opencode 识别 | 确认结构为 `<技能目录>/beetap-cli-python/SKILL.md`,并重启 opencode |

更细的排障(设备连接、模板图、退出码含义等)见 [SKILL.md](SKILL.md)「排障」一节。
