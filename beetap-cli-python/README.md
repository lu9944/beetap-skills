# beetap-cli (Python) — BeeTap 手机调试命令行工具

通过本地 HTTP 端点遥控 IDEA 里的 BeeTap 插件,完成「(插件侧)连接手机 → 编译运行/调试脚本 → 取证与验证」全流程。

```
终端 / AI → beetap-cli → HTTP(127.0.0.1:9318) → IDEA BeeTap 插件 → 手机 BeeTap 调试 App
```

本仓库是项目级 opencode 技能(`.opencode/skills/beetap-cli-python`),接口细节以
[`references/beetap-cli-protocol.md`](references/beetap-cli-protocol.md)(beeTap CLI 控制端点对接协议 v1,
适用插件 1.3.5+,1.3.10 行为变更已纳入)为准。

## 特点

- **零第三方依赖**:仅使用 Python 标准库(`urllib` / `xml.etree`),系统自带 `python3`(3.9+)即可运行。
- **覆盖协议全部有效端点**:status / projects / logs、run / stop / pause / resume、截图、节点树、节点参数、
  OCR、图色测试,外加 `raw` 透传任意端点。
- **连接职责归插件**:协议 v1(插件 1.3.10+)起 `/connect` 已禁用,设备连接只能在 IDEA 插件 UI 完成;
  本 CLI 的 `connect` 只做「查看 + 可选等待 + 指引」(`connect --wait 60s` 你点插件按钮,它连上就返回)。
- **模板自动落位**:协议 1.3.10+ 要求 `run --template` / `findpic --template` 位于工程目录内,
  工程外路径会自动复制到 `<工程>/bt_work_temp/android/` 再提交,越界 1001 不再发生。
- **退出码与官方 `beetap-android-cli` 对齐**:0 成功 / 1 用法 / 2 等待超时 / 3 失败 / 4 设备未连接 /
  5 插件不可达 / 6 busy / 7 未识别的响应(含 1003 端点被新 IDEA 实例接管),智能体无需解析中文文案。
- **证据先行的工作流**:`screenshot` / `nodes` 落盘本机路径并渲染紧凑节点表(中心点即点击坐标),
  `monitor -k` 等标记(关键字忽略大小写),`logs --since` 增量取证。
- **`-f json` 机器可读**:stdout 一行完整信封 `{code,msg,data}`,字段名即协议端点字段
  (官方 CLI 的 `-f json` 只输出 data 渲染结果,注意差异)。
- **回环端点绕过代理**:客户端内置空 ProxyHandler,`http_proxy` 环境变量不会拦截本地端点请求。

## 环境要求

- Python 3.9+(本机验证 3.12 / 3.9.6)
- IntelliJ IDEA 已启动,且已打开含 BeeTap 工程的项目(控制端点随插件启动,协议 v1 / 插件 1.3.5+,建议 1.3.10+)
- 设备已在 **IDEA 插件**里连接(插件里点「USB 调试」/「WiFi 直连」);CLI 不提供连接动作

## 快速开始

```sh
# 1) 环境检查(Python/配置/插件/工程/设备/工程能力)
./bin/beetap-cli doctor

# 2) 设备未连接时:先在 IDEA 插件里点「USB 调试」;
#    本命令只查看状态,并给出插件侧操作指引,--wait 可等连接完成
./bin/beetap-cli connect --wait 60s

# 3) 看一眼状态
./bin/beetap-cli status

# 4) 运行工程并等待结束(命中关键字提前返回)
./bin/beetap-cli run -m lark-tap --wait-timeout 5m -k '登录成功|||登录失败'

# 5) 运行一段脚本片段(模板图工程外会自动复制进工程)
./bin/beetap-cli run --snippet 'toast("hi"); logd("snippet ok");'

# 6) 取证:截图 + 节点树
./bin/beetap-cli screenshot -o shot.png
./bin/beetap-cli nodes --dir evidence

# 7) 跟随日志
./bin/beetap-cli monitor -k '脚本已停止运行' --max-duration 2m
```

也可以直接以模块方式运行:`python3 -m beetap_cli status`(需 `beetap_cli` 在 `PYTHONPATH`)。

完整命令见 [`commands.md`](commands.md);技能说明见 [`SKILL.md`](SKILL.md)。

## 配置(环境变量 / .env)

| 键 | 默认 | 说明 |
|---|---|---|
| `BEETAP_URL` | `http://127.0.0.1:9318` | 插件控制端点(端口被 `-Dbeetap.cliPort=` 改过时同步改) |
| `BEETAP_MODULE` | 自动 | 默认 BeeTap 工程名或路径(多工程时必填) |
| `BEETAP_TIMEOUT` | `360s` | 单次 HTTP 超时(默认 6m,必须大于请求的 timeoutMs;`run --wait` 长脚本请给足) |

设备连接没有任何 CLI 配置项(连接在 IDEA 插件里完成)。命令行参数优先。
`.env` 查找顺序:`--env <path>` → 当前目录 `.env` → 技能根目录 `.env`(空/不含已知键的文件会被跳过);模板见 [`.env.example`](.env.example)。

示例(项目 `.env`):

```sh
BEETAP_MODULE=lark-tap
BEETAP_TIMEOUT=6m
```

## 安装为全局命令(可选)

```sh
# 方式一:软链接到 PATH
sudo ln -s "$(pwd)/bin/beetap-cli" /usr/local/bin/beetap-cli

# 方式二:有 pip 的环境下安装
pip install .
```

## 作为 Skill 使用(opencode / Claude Code)

技能目录自带 `SKILL.md`,把整个目录复制到对应技能位置即可,例如:

```sh
cp -R . ~/.config/opencode/skills/beetap-cli-python
```

## 仓库结构

```
beetap-cli-python/
├── SKILL.md               # 技能主体(触发条件、配置、操作流程、关键约定、排障)
├── commands.md            # 完整命令速查
├── README.md              # 本文件
├── .env.example           # 配置模板(插件端点 / 工程 / HTTP 超时)
├── pyproject.toml         # 可选的 pip 安装配置(控制台入口 beetap-cli)
├── references/
│   └── beetap-cli-protocol.md  # beeTap CLI 控制端点对接协议 v1(接口权威文档)
├── beetap_cli/            # Python 包(零第三方依赖)
│   ├── main.py            #   argparse 命令树与分发
│   ├── config.py          #   .env / 环境变量 / 命令行覆盖
│   ├── client.py          #   urllib HTTP 客户端 + 信封/错误码处理(回环绕过代理)
│   ├── errors.py          #   错误类型与退出码映射(0-7,与官方 CLI 对齐)
│   ├── output.py          #   text/json 输出与日志行渲染
│   ├── commands.py        #   status / projects / logs / monitor / raw
│   ├── device.py          #   connect(引导/等待)/ run / stop / pause / resume
│   ├── project.py         #   工程解析 + 模板图落位(工程目录包含规则)
│   ├── capture.py         #   screenshot / nodes / node-params / ocr / test-image
│   ├── nodes.py           #   节点 XML 解析与紧凑表格渲染
│   └── doctor.py          #   6 项环境体检
├── bin/
│   └── beetap-cli         # 可执行入口(#!/usr/bin/env python3)
└── tests/                 # unittest 单元测试(不依赖插件在线)
```

## 测试

```sh
python3 -m unittest discover -s tests -v
```

覆盖:时长解析、.env 解析与配置优先级、信封错误码映射(含 1003/未知码/非 JSON)、URL 构造与请求发送、
运行请求体构造与 wait-timeout 钳位、连接引导(不触达 /connect)、stop/pause/resume 请求体、
关键字展开、BUSY/JS 异常日志识别、图色请求体、节点参数、节点 XML 解析与表格渲染、
工程解析与模板落位(工程内原样/工程外复制)。

## 关键约定摘要

- 退出码即成败标准(0-7,见上);`run` 的 JS 运行期错误不产生 HTTP 错误码,需看日志中是否有 `JS 执行异常`。
- 设备端同一时刻只跑一个脚本;busy 时退出码 6,先 `stop`。
- `wait=true` 时 CLI 自动保证 HTTP 超时大于 `timeoutMs`;`--wait-timeout` 先按服务端区间 [5s,30m] 钳位;
  超时返回 `stopReason=timeout` 且退出码 2。
- `screenshot` / `nodes` 返回的是**本机**插件落盘路径(工程 `bt_work_temp/android/` 下),需自己读文件
  (可用 `-o` / `--dir` 另存)。
- 设备连接只能在 IDEA 插件里做(协议 v1 / 插件 1.3.10+);同机多 IDEA 实例只有最新启动者生效,
  被接管实例返回 1003(退出码 7,`-u/--url` 指向正确实例)。
- OCR 依赖 App 打包能力与设备初始化;`/ocr` `result=null` 时先查 `logs`,脚本侧 `ocr.*` 包装函数可用。

## License

MIT
