# beeTap CLI 控制端点对接协议（v1）

> 读者：想脱离 `beetap-android-cli`（Go）用任意语言重新实现一个 CLI 的开发者。
> 本文档描述 CLI 与 BeeTap IDEA 插件控制端点之间的 HTTP 契约，依据双方源码整理：
> 适用插件版本 1.3.5+（控制端点随插件自动启动）。

## 1. 架构与职责边界

```
终端/AI → 你的 CLI → HTTP(127.0.0.1:9318) → BeeTap IDEA 插件(控制端点) → adb/wifi → 手机 BeeTap 调试 App
```

- **CLI 不直接连手机**。设备连接、编译、截图落盘全部由插件单点管理；CLI 只是对本机回环 HTTP 服务的遥控器。
- 插件未启动（IDEA 没开）时表现为 TCP 连接拒绝，这是最常见的"离线"形态。
- 插件↔手机之间的私有指令通道（"1"运行、"3"停止、"4"截图、"5"抓节点、"6"暂停、"7"继续、adb forward 9317 等）
  **不属于本协议**，对接方无需也不应实现。

## 2. 传输层约定

| 项 | 值 |
|---|---|
| 基地址 | `http://127.0.0.1:9318`（默认） |
| 绑定 | 仅回环 `127.0.0.1`；**单实例令牌**——插件每次启动生成新随机 token 覆盖写 `~/.beetap/cli.token`，请求时重读校验，被新启动的 IDEA 实例接管后本实例全部端点返回 `1003`（1.3.10 起） |
| 端口覆盖 | IDEA VM options 加 `-Dbeetap.cliPort=<1024-65535>`；CLI 侧用 `-u/--url` 跟随（多实例改端口绕不开令牌接管：后启动者生效，先启动者失效） |
| 实例 | 进程级单例：IDEA 开多个工程窗口也只有一个端点 |
| 请求 | GET 无请求体；POST 请求体为 JSON，**建议始终发 `{}` 起步**（服务端把空/坏请求体按 `{}` 处理，缺字段走默认值） |
| 响应 | **恒为 HTTP 200** + `application/json`；错误语义全在信封 `code`，不能靠 HTTP 状态码判错 |
| 超时 | 服务端 handler 是阻塞式（编译/等设备回帧，最长可达请求里的 `timeoutMs`），**客户端 HTTP 超时必须大于请求的 `timeoutMs`**（参照实现默认 6 分钟） |
| 编码 | UTF-8；服务端忽略未知 JSON 字段（`org.json` opt* 语义），新增字段向后兼容 |

探活/版本协商：`GET /status` 看 `pluginVersion` 是否为 BeeTap 插件、`cliPort` 回显实际端口。

## 3. 统一响应信封

所有端点（含出错）返回同一信封：

```json
{ "code": 0, "msg": "ok", "data": { } }
```

- `code=0` 成功；非 0 见第 4 节错误码表。
- `data` 可能整体缺省或为 `null`（如 `stop`/`pause`/`resume` 成功时无 data）。
- `data` 内的单个字段也可能为 `null`（如设备未握过手时 `device.mode`/`serial`），客户端必须可空处理。
- 失败时人类可读信息在信封 `msg`（注意：失败响应的 `data` 里**没有** `message` 字段，只有成功响应才有）。

## 4. 错误码与建议退出码

`code` 由服务端定义；`9001` 是客户端本地约定（连不上端点/响应非法），服务端永不返回。

| code | 含义 | 建议进程退出码 |
|---|---|---|
| 0 | 成功 | 0 |
| 1001 | 请求参数错误（mode/format/method 非法、缺必填等）；`/connect` 已禁用，恒返此码 | 1 用法错误 |
| 1002 | 已有 CLI 运行进行中（run 单飞行） | 6 运行中 |
| 1003 | 本实例已被新启动的 IDEA 实例接管，token 不匹配，全部端点拒绝 | 7 未识别的响应 |
| 2001 | 设备未连接 | 4 设备未连接 |
| 2002 | 编译失败/调试包生成失败 | 3 其它失败 |
| 3001 | 捕获/连接等待超时（截图、节点） | 3 其它失败 |
| 4001 | 工程未找到（含没有打开的 IDEA 工程） | 1 用法错误 |
| 4002 | 工程多义（未传 module 且打开的 BeeTap 工程不止一个） | 1 用法错误 |
| 5000 | 插件内部错误 | 3 其它失败 |
| 9001 | （仅客户端本地）端点不可达/响应非法 JSON | 5 插件不可达 |

参照实现的完整退出码表：`0` 成功 / `1` 用法错误 / `2` 等待超时（run --wait、monitor 未命中关键字）/ `3` 其它失败 /
`4` 设备未连接 / `5` 插件不可达 / `6` 已有运行进行中 / `7` 未识别的响应（未知 code）。
**注意 `run --wait` 超时比较特殊**：服务端视为成功（code=0，`stopReason="timeout"`），由客户端把退出码修正为 2。

## 5. 端点详解

12 个有效端点：GET `/status`、`/projects`、`/logs`；POST `/run`、`/stop`、`/pause`、`/resume`、
`/screenshot`、`/nodes`、`/node-params`、`/test-image`、`/ocr`。
另有 POST `/connect`（1.3.10 起禁用，保留路由恒返 `1001`，msg 提示走 IDEA 插件连接）。

### 5.1 GET /status — 状态一览

```json
{ "code": 0, "msg": "ok", "data": {
    "pluginVersion": "1.3.8",
    "cliPort": 9318,
    "captureMode": "FAST",
    "device": {
      "connected": true, "mode": "ADB_DIRECT", "serial": "emu32a",
      "brand": "Xiaomi", "model": "22127PN0CC",
      "appVersion": "3.40.0", "androidVersion": "13"
    },
    "projects": [ { "name": "demo", "projectName": "demo", "path": "D:/work/demo" } ]
} }
```

- `device.mode`：`ADB_DIRECT` | `WIFI_DIRECT` | `null`（未连接）。
- `projects[].name`：BeeTap 工程目录名（即 `-m/--module` 可传的值）；`projectName` 是 BeeTap.toml 里的工程名；`path` 为绝对路径。
- `captureMode`：内部截图方式枚举名，仅展示用。

### 5.2 GET /projects — 工程列表

`data = { "projects": [同上 ProjectRef...] }`。

### 5.3 POST /connect — 已禁用（1.3.10 起）

设备连接只能在 IDEA 插件里操作（USB 调试 / WiFi 直连均在插件 UI 完成）。保留该路由仅为给存量
CLI 一个明确报错：任何请求体都返回 `code=1001`，msg 为「CLI 连接已禁用：请在 IDEA 插件里点
「USB 调试」连接设备后再用 CLI」。历史字段（mode/serial/host/port/timeoutMs）全部忽略。

### 5.4 POST /screenshot — 截图

请求：`{ "format": "png" | "jpg", "quality": 90, "timeoutMs": 15000 }`

- `format` 只支持 png/jpg（传 `jpeg` 会归一为 jpg，其它 → 1001）；`quality` 钳位 [1,100]，仅 jpg 有效；`timeoutMs` 钳位 [2000, 60000]。
- 需先连接设备（未连接 → 2001）；等设备回帧超时 → 3001。

成功 data：

```json
{ "path": "D:/work/demo/bt_work_temp/android/screenshot/1710000000123.png", "bytes": 238400 }
```

`path` 是**插件所在机器**的绝对路径（回环场景即本机）。客户端不要自己拼路径，始终以返回值为准；
文件名是毫秒时间戳，落到打开工程的 `bt_work_temp/android/screenshot/`。

### 5.5 POST /nodes — 抓控件节点树（图 + XML）

请求：

```json
{ "mode": 1, "invisible": false, "notImportant": true, "algorithm": "nsf", "timeoutMs": 20000 }
```

- `mode`：1=增强型（全部交互窗口）2=快速型；`algorithm` ∈ `nsf|bsf|dsf`（非法值回落 nsf）。
- **覆盖语义**：`mode/invisible/notImportant/algorithm` 四个字段**任一出现**即视为一次性覆盖——只对本次抓取生效，不持久化；
  四个都缺省则把插件当前持久化设置同步到设备后抓取。
- 需先连接设备（2001）；超时 → 3001；`timeoutMs` 钳位 [3000, 120000]。

成功 data：

```json
{ "imagePath": "D:/work/demo/bt_work_temp/android/node/1710000000456.png",
  "xmlPath":   "D:/work/demo/bt_work_temp/android/node/1710000000456.xml" }
```

图与 XML 同名成对（毫秒时间戳）。参照实现会把 XML 渲染成紧凑节点表（text/desc/中心点/flags）——这是**纯客户端行为**，
与协议无关，重写时可自行决定是否渲染。

### 5.6 POST /node-params — 持久化节点抓取参数

请求同 5.5 的四个参数（此处均为生效值，无覆盖语义）：`{ "mode": 1, "invisible": false, "notImportant": true, "algorithm": "nsf" }`。
服务端保存设置并同步到手机（随通道连接自动生效），成功 data 回显这四个字段。不需要设备已连接。

### 5.7 POST /run — 运行工程 / 脚本片段（核心端点）

请求：

```json
{ "module": "demo", "wait": true, "timeoutMs": 300000,
  "keywords": ["登录成功", "登录失败"],
  "code": "...js 源码（可选）...", "templatePath": "D:/tmp/patch.png（可选，仅 code 模式）" }
```

| 字段 | 说明 |
|---|---|
| `module` | 工程目录名 / BeeTap.toml 工程名 / 绝对路径（均大小写不敏感）。省略时恰好一个工程→用它；零个→4001；多个→4002 |
| `wait` | 默认 true。false = 只编译下发不等待，立即返回 |
| `timeoutMs` | wait=true 的最长等待，钳位 [5000, 1800000]，默认 120000 |
| `keywords` | string[]；日志文本**忽略大小写的子串匹配**，任一命中即结束等待 |
| `code` | 脚本片段源码（优先于 `codePath`）；提供时走「运行选中代码」链路而不是整工程入口 |
| `codePath` | 服务端本机的脚本文件路径，**必须位于解析到的 BeeTap 工程目录内**（越界 → 1001；CLI 场景一般直接传 `code`） |
| `templatePath` | 模板图路径，仅 code 模式，**必须位于解析到的 BeeTap 工程目录内**（越界 → 1001）；服务端读图后作为 `cli_template.png` 随调试包下发。不可读 → 1001 |

行为与耗时特征：检查连接（未连接 → 2001）→ 保存 IDEA 未存文档 → 依赖检查/编译（失败 → 2002）→ 下发设备 →
（wait=true）每 200ms 轮询日志直到 **脚本停止 / 命中「脚本已停止运行」内置停止字 / 命中 keyword / 设备断开 / 超时**。
同一时刻只允许一个 run（单飞行），并发请求 → 1002。

成功 data（wait=true）：

```json
{ "stopReason": "keyword", "message": "命中停止关键字: 登录成功",
  "durationMs": 15230,
  "logs": [ { "seq": 431, "time": 1710000000000, "level": "info", "text": "..." } ] }
```

- `stopReason` 取值：`dispatched`（wait=false 下发即回，此时无 logs）｜`script_stopped`（脚本自然结束，含内置停止字命中）｜
  `keyword`（命中 keywords 之一，message 注明是哪个）｜`disconnected`（设备断开）｜`timeout`（超时，**code 仍为 0**，客户端自行把退出码改写为 2）。
- `logs` 是从下发前游标起的全量期间日志（最多 2000 条）；wait=false 时无 `logs` 字段。
- 失败（2001/2002/5000）时 data 只有 `stopReason`(null)/`durationMs`/`logs`，说明文字在信封 `msg`。

### 5.8 POST /stop · /pause · /resume — 运行控制

请求 `{ "module": "可选" }`；成功无 `data`。未连接设备 → 2001。
`module` 仅被 `/stop` 用来定位工程以复位运行会话状态；`/pause`、`/resume` 忽略一切参数。
指令是发后即忘的：成功只代表指令已发出，不代表脚本已停。

### 5.9 GET /logs — 日志缓冲增量拉取

```
GET /logs?since=431&lines=500&project=D:/work
```

| 参数 | 说明 |
|---|---|
| `since` | 游标：只返回 `seq > since` 的日志，首传 0；之后传上次响应的 `cursor` |
| `lines` | 最多返回条数，钳位 [1, 4000]，默认 200 |
| `project` | 可选，按 **IDEA 工程根路径**精确过滤（不是 BeeTap 工程目录） |

响应：

```json
{ "code": 0, "msg": "ok", "data": {
    "cursor": 438,
    "logs": [ { "seq": 432, "time": 1710000000100, "level": "warn", "text": "..." } ]
} }
```

- 缓冲是容量 4000 的环形队列；`seq` 服务端进程生命周期内单调递增；`time` 为 epoch 毫秒；`level` ∈ `debug|info|warn|error`。
- `cursor` = 本批最后一条的 seq（空批则原样回 `since`）——**游标推进必须用它，不要自己 `max(seq)`**。
- 内容包含：设备 LOGC 日志、编译输出、插件自身消息。
- 日志为空批时 `logs` 可能是空数组，属正常（轮询场景）。

### 5.10 POST /test-image — 图色测试（在手机上执行）

请求（公共）：`{ "method": "...", "module": "可选", "threshold": 0.9, "timeoutMs": 60000 }`，按 method 追加：

| method | 必填 | 可选 | result 语义 |
|---|---|---|---|
| `findcolor` | `color`（支持偏色写法 `0xCDD7E9-0x101010`） | `x,y,ex,ey` 区域、`limit`（默认 1）、`orz`（0-4，4=中心向外） | `[{"x":100,"y":200},...]` |
| `findmulticolor` | `firstColor` 锚点色 + `points`（`dx\|dy\|0xRRGGBB` 逗号分隔） | 同上区域参数 | 同上 |
| `cmpcolor` | `points`（`x\|y\|0xRRGGBB` 逗号分隔） | — | `true` / `false` |
| `findpic` | `templatePath`（**工程目录内**模板图路径，越界 → 1001） | `deltaColor`（如 `0x101010`）、`x1,y1,x2,y2` 区域 | `{"index":0,"left":..,"top":..,"right":..,"bottom":..,"centerX":..,"centerY":..}` 或 `null` |

- method 大小写不敏感；缺必填 → 1001；`threshold` 省略时脚本用引擎默认（0.9）。
- 实现上服务端会动态生成一段微脚本并内部转调 `/run`（wait=true，timeoutMs 默认 60000），所以 run 的 2001/1002/2002 错误同样适用。
- 成功 data 在 run 的结构上多一个 `result` 字段（字符串，内容为上表 JSON 的原始文本）：

```json
{ "stopReason": "script_stopped", "message": "脚本运行结束", "durationMs": 3120,
  "logs": [...], "result": "[{\"x\":100,\"y\":200}]" }
```

### 5.11 POST /ocr — OCR 当前手机屏幕

请求：`{ "module": "可选", "source": "screen", "type": "mlkit", "timeoutMs": 60000 }`

- v1 仅支持 `source=screen`（其它值 → 1001）；识别本机图片请用 `/run` 的 code 自行实现。
- `type` ∈ `mlkit | mlkitChinese | mlkitLatin | paddleOcrV4 | paddleOcrV5`，省略用设备会话默认。
- 响应结构同 5.10（SnippetData），`result` 为 `[{"label":"...","confidence":0.97,"x":..,"y":..,"width":..,"height":..},...]` 的 JSON 文本。

## 6. 微脚本结果协议 BT_RESULT（服务端内部，了解即可）

`/test-image`、`/ocr` 的 `result` 来自日志标记：脚本把结果打成一行 `BT_RESULT|<json>` 写进日志，
服务端取**最后一条**含该标记的日志行、取**最后一个**标记之后的内容，trim 掉 `*` 和空白后放入 `data.result`。
没有标记 → `result` 为 `null`。自定义微脚本也可以按此约定回传结构化结果（自己在 code 里 `log` 一行 `BT_RESULT|{...}`，
再从 run 的 logs 里取——但注意 run 端点本身不做提取，提取只发生在 test-image/ocr）。

## 7. 重写 CLI 的客户端约定（与现 CLI 保持兼容）

协议只约束 HTTP 契约；下面是参照实现对外呈现的终端行为，重写时建议保持一致，避免破坏既有 AI/脚本依赖：

1. **stdout 只放数据，stderr 放进度与错误**；`-f json` 时 stdout 输出单个 JSON 对象（data 渲染结果，一行），text 模式输出人读多行文本。
2. **退出码**按第 4 节映射（0/1/2/3/4/5/6/7），调用方靠退出码分流。
3. **全局参数**：`-u/--url`（默认 `http://127.0.0.1:9318`）、`-m/--module`、`-f/--format text|json`、`--timeout`（HTTP 超时，默认 6m，必须 > 各请求的 timeoutMs）。
4. **monitor 跟随模式**（纯客户端轮询，无服务端支持）：
   先 `GET /logs?since=0&lines=1` 拿当前 `cursor` 作为起点（避免捞历史日志），
   然后 500ms 间隔循环 `GET /logs?since=<cursor>&lines=500`，逐条打 stdout 并做关键字（忽略大小写子串）匹配，命中即 exit 0；
   超时未命中 exit 2。默认停止字「脚本已停止运行」。
5. **`run --wait` 是一次长阻塞 HTTP 请求**，不要自己实现等待循环；`stopReason=timeout` 时把退出码修正为 2。
6. 超时类参数客户端先钳位/给足，服务端会二次钳位并静默修正越界值（不会报错）。

## 8. 兼容性与版本化

- 协议无版本号字段；以 `GET /status` 的 `pluginVersion` 判别能力。v1 对应插件 1.3.5+。
- **1.3.10 行为变更**：`/connect` 禁用（恒返 1001）；新增单实例令牌（见第 2 节），同机多 IDEA 实例只有最新启动者生效（1003）；
  `/run` 的 `codePath`/`templatePath` 与 findpic 模板图收敛到解析后的 BeeTap 工程目录内（越界 1001）。
- 服务端忽略未知请求字段、响应可能新增字段——客户端解析必须宽容（字段缺失/为 null 不致命）。
- 新增端点、新增可选字段视为兼容变更；改字段语义或删除字段需大版本。
- 端口被占用时插件启动端点失败（IDEA 日志有记录），此时所有命令表现为 9001 不可达——排查顺序：
  IDEA 是否启动 → 端口是否被别的进程占用 → `-Dbeetap.cliPort=` 与 `-u` 是否匹配。
