# beetap-cli 命令速查(Python / 协议 v1)

首次使用:确认 IDEA 已打开 BeeTap 工程、设备已在 IDEA 插件里连接(插件里点「USB 调试」),然后运行 `beetap-cli doctor`。

全局参数(`-u/--url`、`-m/--module`、`--timeout`、`-f/--format`、`--env`)放在子命令前后均可。
数据 → stdout,进度/错误 → stderr(前缀 `[beetap-cli]`);退出码约定见 SKILL.md「关键约定」。
完整端点字段、错误码与 1.3.10 行为变更见 `references/beetap-cli-protocol.md`(技能目录内)。

## 会话与状态

| 命令 | 说明 |
|---|---|
| `doctor` | 环境检查六项:Python / 配置 / 插件连通性 / 工程解析 / 设备连接 / 工程能力 |
| `status` | 插件版本/端口/设备连接状态(品牌/型号/app 版本/serial/mode)/工程列表 |
| `projects` | 列出 IDEA 中打开的 BeeTap 工程(name + 路径) |
| `connect [--wait DUR]` | 查看设备连接状态;未连接时给出插件侧连接指引。`--wait 60s` 轮询等待(先在 IDEA 插件里点「USB 调试」/「WiFi 直连」) |
| `raw <GET\|POST> <PATH> [-b JSON] [--body-file PATH]` | 原始端点透传,调试与未来接口兜底;text 模式输出缩进 JSON,退出码按 `code` 映射(未知 code → 7) |

`connect` 细节:

- 协议 v1(插件 1.3.10+)起 **`/connect` 已禁用**(恒返 1001):设备连接只能在 IDEA 插件 UI 完成,本命令不再触发连接;
- 旧参数(`--mode` / `--serial` / `--host` / `--port`)被接受但**忽略并告警**,仅为兼容旧脚本;
- `--wait 20s` 之类只是本地轮询 `/status` 的最长时间,连上即返回;超时退出码 4;
- 调试 App 缺失/重装:走插件菜单(如「手机扫码安装调试 APK」);adb 兜底见 SKILL.md「操作流程」。

## 运行控制

| 命令 | 说明 |
|---|---|
| `run [-m M] [--wait-timeout 5m] [-k KW] [--code FILE] [--snippet JS] [--template IMG]` | 编译整个工程并下发运行;默认阻塞等待结束(`stop=` 摘要 + 全部日志),`-k` 命中提前返回(退出码 0) |
| `run --no-wait` | 只下发不等待(返回 `stop=dispatched`) |
| `stop` / `pause` / `resume` | 停止 / 暂停 / 继续设备上正在运行的脚本(发后即忘:成功只代表指令已发出) |

`run` 细节:

- `-k/--stop-on` 支持 `'a|||b'` 或重复 `-k`,任一命中(**忽略大小写的子串匹配**)即提前返回;等待超时退出码 2、`stopReason=timeout`。
- `--code FILE` 只跑一段脚本片段(不动工程入口),`-` 表示读标准输入;`--snippet 'toast("hi");'` 内联片段。
- `--template IMG` 仅片段模式有效;协议要求模板位于工程目录内(越界 1001),工程外路径会**自动复制**到
  `<工程>/bt_work_temp/android/beetap_cli_template.<ext>` 后再提交。
- `--wait-timeout` 先按服务端区间 [5s,30m] 钳位(超界提示);HTTP 超时自动取 `max(--timeout, --wait-timeout+30s)`,避免本地先超时。
- 设备端 busy 时日志出现 `BUSY:`,退出码 6,先 `stop` 再重试;`/run` 并发请求(单飞行)返回 `code=1002`,同样退出码 6。
- JS 运行期错误不产生 HTTP 错误码:日志出现 `JS 执行异常` 时本 CLI 在 stderr 给出警告(退出码仍 0,按需自行判断)。
- `stop` 会把 `-m/--module` 一并提交(用于复位该工程的运行会话);`pause`/`resume` 忽略参数。

## 日志

| 命令 | 说明 |
|---|---|
| `logs [--since N] [--lines 200] [--project P]` | 拉取插件日志缓冲;text 模式原样打印,末行 `cursor=N count=K` 供增量 |
| `monitor [-k KW] [--max-duration 10m] [--lines 500] [--initial]` | 跟随日志流:500ms 增量拉取,命中任一关键字(忽略大小写)退出 0,超时退出 2;默认停止字「脚本已停止运行」,`--initial` 从缓冲最旧开始 |

增量拉取用法:记下 `logs` 末行的 `cursor=N`,下次 `logs --since N` 只拿新日志(游标以响应的 `cursor` 字段为准,不要自己取 max(seq))。
`monitor` 起点按协议先 `GET /logs?since=0&lines=1` 取当前 cursor,避免捞历史日志;`-f json` 时 `logs` 输出完整信封,`monitor` 输出逐行 JSON(JSONL)。

## 取证

| 命令 | 说明 |
|---|---|
| `screenshot [--img-format png\|jpg] [--quality 90] [-o FILE]` | 手机截图;stdout 第一行是插件落盘路径,`-o` 另存一份(目录则保留原文件名) |
| `nodes [--max 120] [--no-table] [--dir DIR] [--override] [节点参数]` | 抓控件节点树:图+XML 成对落盘;stdout 依次输出图路径、XML 路径、另存路径与紧凑节点表 |
| `node-params [节点参数]`(别名 `set-node-params`) | 持久化节点抓取参数并同步手机(等同插件「节点设置」) |
| `ocr [--type mlkit\|mlkitChinese\|mlkitLatin\|paddleOcrV4\|paddleOcrV5]` | 对当前屏幕 OCR(`source=screen`);结果 `[{label,confidence,x,y,width,height}]`,`result=null` 表示无结果(设备/App 能力未开启时常见,查日志定位) |
| `test-image --method ...` | 手机端图色测试(findcolor / findmulticolor / cmpcolor / findpic),底层生成脚本→编译→下发,单次约 10~20 秒 |

节点参数(`nodes --override` 或 `node-params`,字段同插件「节点设置」;`nodes` 下任一参数出现即本次覆盖,不持久化):

| 参数 | 默认 | 说明 |
|---|---|---|
| `--mode 1\|2` | 1 | 1=增强型(全部交互窗口) / 2=快速型 |
| `--invisible` / `--visible` | 不遍历 | 是否遍历不可见节点 |
| `--not-important` / `--important` | 包含 | 是否包含 not-important 节点 |
| `--algorithm nsf\|bsf\|dsf` | nsf | 遍历算法(非法值由服务端回落 nsf) |

节点表列:`# / text / desc / id / class / center / flags`;`flags` 中 `C`=可点击 `L`=长按 `S`=可滚动 `E`=可编辑 `F`=聚焦 `K`=可勾选。`center=(x,y)` 就是该控件可点中心。

`test-image` 字段:

| 参数 | 适用 method | 说明 |
|---|---|---|
| `--color` | findcolor | 目标色 `0xRRGGBB-0x偏色`,如 `0xCDD7E9-0x101010` |
| `--first-color` + `--points` | findmulticolor | 锚点色 + `"dx\|dy\|0x色, ..."` |
| `--points` | cmpcolor | `"x\|y\|0x色, ..."` 逐点比对,输出 true/false |
| `--template` | findpic | 模板图路径(工程目录内;工程外**自动复制**进工程后再提交) |
| `--threshold` | 找色/找图 | 相似度 0-1(省略时用引擎默认 0.9) |
| `--delta-color` | findpic | 各通道允许偏差,如 `0x101010` |
| `--x --y --ex --ey` | findcolor/findmulticolor/findpic | 区域限定(起点 + 宽高,0 表示全屏) |
| `--limit` / `--orz` | findcolor | 最多返回个数(默认 1) / 扫描方向 0-4(4=中心向外) |

区域参数用「起点 + 宽高」(`--ex/--ey` 是宽高,不是右下角);从官方 CLI 的 `--x1/--y1/--x2/--y2`(右下角)换算时 `ex=x2-x1`,`ey=y2-y1`。
`result` 是 JSON 文本:findcolor/findmulticolor 为 `[{"x","y"},...]`,cmpcolor 为 true/false,findpic 为 `{index,left,top,right,bottom,centerX,centerY}` 或 null。

## 全局参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `-u, --url URL` | `http://127.0.0.1:9318` | 插件控制端点(端口被 `-Dbeetap.cliPort=` 改过时同步改) |
| `-m, --module NAME` | 自动 | BeeTap 工程目录名 / BeeTap.toml 工程名 / 绝对路径(均大小写不敏感;多工程必填) |
| `--timeout DUR` | `360s` | 单次 HTTP 超时(默认 6m,必须大于请求的 timeoutMs);`run --wait` 长脚本请给足 |
| `-f, --format text\|json` | text | text 人类可读 / json 完整信封一行(机器解析) |
| `--env PATH` | 自动查找 | .env 文件路径(默认当前目录、技能根目录) |

时长写法:`20s` / `500ms` / `1.5m` / `1h` / `1m30s` / 裸数字(秒)。

## 环境变量 / .env

| 键 | 默认 | 说明 |
|---|---|---|
| `BEETAP_URL` | `http://127.0.0.1:9318` | 插件控制端点 |
| `BEETAP_MODULE` | 自动 | 默认 BeeTap 工程 |
| `BEETAP_TIMEOUT` | `360s` | 默认 HTTP 超时(如 `6m`) |

参数优先级:**命令行 > 环境变量 > .env 文件 > 默认值**。设备连接无任何配置键(连接在 IDEA 插件里完成)。
`.env` 查找顺序:`--env <path>` → 当前目录 `.env` → 技能根目录 `.env`(空/不含已知键的文件会被跳过);模板见 `.env.example`。

示例(项目 `.env`):

```sh
BEETAP_MODULE=lark-tap
BEETAP_TIMEOUT=6m
```

## 退出码

| 退出码 | 含义 |
|---|---|
| 0 | 成功(含 run/monitor 命中关键字) |
| 1 | 用法/参数错误(含 -m 未找到、工程歧义、参数非法) |
| 2 | run --wait / monitor 等待超时 |
| 3 | 其它失败(编译失败/截图节点超时/内部错误) |
| 4 | 设备未连接 |
| 5 | 插件不可达(IDEA 没开/端口不对/响应非法,协议本地码 9001) |
| 6 | 已有运行在进行中(busy) |
| 7 | 未识别的响应(未知 code;含 1003 端点被新 IDEA 实例接管) |
