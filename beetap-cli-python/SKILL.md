---
name: beetap-cli-python
description: >-
  遥控 BeeTap IDEA 插件调试安卓真机的命令行工具(beetap-cli,Python 版,协议 v1 / 插件 1.3.10+)。
  当用户提到 BeeTap / 真机调试 / 连接手机 / 运行或调试 BeeTap 脚本、需要截图取证、抓控件节点、
  跟随日志、手机端 OCR、找色找图,或为自动化测试脚本取证与验证时,使用本 skill。
  任何操作前先运行 `beetap-cli doctor`;设备连接在 IDEA 插件里点「USB 调试」完成(CLI /connect 已禁用,
  用 `connect` / `connect --wait` 查看或等待);写坐标/控件操作前必须先 `screenshot` + `nodes` 取证。
  接口细节以 references/beetap-cli-protocol.md(协议 v1)为准。
compatibility: opencode
metadata:
  tool: beetap-cli
  plugin: BeeTap IDEA 插件
  language: python
  protocol: v1
  target-plugin-version: 1.3.10+
---

# beetap-cli — BeeTap 手机调试(Python)

通过本地 HTTP 端点遥控 IDEA 里的 BeeTap 插件,完成「(插件侧)连接手机 → 编译运行/调试脚本 → 取证与验证」全流程。接口权威文档随技能附带:`references/beetap-cli-protocol.md`(beetap CLI 控制端点对接协议 v1,适用插件 1.3.5+,1.3.10 行为变更已纳入)。

链路:**beetap-cli → HTTP(127.0.0.1:9318) → IDEA BeeTap 插件 → 手机上的 BeeTap 调试 App**。
CLI 不直接连手机:**设备连接、编译、截图落盘全部由插件单点管理**——连接动作只能在 IDEA 插件 UI 里做
(插件 1.3.10+ 起 `/connect` 已禁用,恒返 1001)。实现为**纯 Python 标准库**,无需安装第三方包。

## 环境

按顺序探测入口,使用第一个存在的路径:

1. `<本 skill 目录>/bin/beetap-cli`
2. `PATH` 中的 `beetap-cli`
3. `python3 -m beetap_cli`(需 `beetap_cli` 在 `PYTHONPATH`)

要求系统自带 `python3`(3.9+,本机验证 3.12/3.9.6)。入口脚本已带 shebang;无执行权限时用 `python3 <路径>/bin/beetap-cli` 或先 `chmod +x`。

前提条件(**不满足必然失败**):

- **IntelliJ IDEA 已启动**,且已打开含 BeeTap 工程的项目(控制端点随插件启动,IDEA 关闭即消失);
- 手机已连接:在 IDEA 的 BeeTap 插件里点「USB 调试」(或 WiFi 直连);调试 App 缺失/重装走插件菜单
  (如「手机扫码安装调试 APK」)。连接状态用 `status` / `connect` 查看,也可 `connect --wait 60s` 等待;
- 端点默认 `http://127.0.0.1:9318`;若启动参数改过 `-Dbeetap.cliPort`,用 `-u/--url` 同步;
- **单实例令牌**(插件 1.3.10+):插件每次启动生成 token 覆盖写 `~/.beetap/cli.token`;同机多个 IDEA 实例时
  **后启动者生效**,被接管的实例全部端点返回 `1003`(本 CLI 退出码 7);
- 多工程时必须用 `-m/--module`(工程目录名 / BeeTap.toml 工程名 / 绝对路径,均大小写不敏感);单工程可省略。

## 配置(.env / 环境变量)

命令行参数优先,其次环境变量,其次 `.env` 文件,最后默认值。`.env` 查找顺序:
`--env <path>` → 当前目录 `.env` → 技能根目录 `.env`(不含已知键的文件,如空文件,会被跳过);
模板见技能目录 `.env.example`。

| 键 | 默认 | 说明 |
|---|---|---|
| `BEETAP_URL` | `http://127.0.0.1:9318` | 插件控制端点(端口被 `-Dbeetap.cliPort=` 改过时同步改) |
| `BEETAP_MODULE` | 自动 | 默认 BeeTap 工程(等价 `-m/--module`) |
| `BEETAP_TIMEOUT` | `360s` | 单次 HTTP 超时(run --wait 长脚本请给足,必须大于请求的 timeoutMs) |

设备连接没有任何 CLI 配置项:连接在 IDEA 插件里完成,CLI 侧零配置。

## 操作流程

任何设备操作前先执行:

```sh
beetap-cli doctor          # 六项检查:Python/配置/插件/工程/设备/工程能力
```

设备未连接时(连接动作只能在 IDEA 插件里做):

```sh
beetap-cli connect                         # 查看连接状态;未连接时给出插件侧操作指引
beetap-cli connect --wait 60s              # 等你到 IDEA 插件里点「USB 调试」,连上后自动返回
beetap-cli status                          # 复核设备/工程状态
```

调试 App 缺失/重装(以 IDEA 插件为主):连接与装包都由插件管理;插件安装不便时可 adb 兜底——
调试 APK 模板在插件 jar 内(`apk-template/bt.apk`),`adb -s <serial> install -r -t <bt.apk>`;
重装会重置无障碍/录屏等权限,按手机端或插件菜单提示重新授权(插件有「adb 免重启开启无障碍服务」)。

编译并运行工程(或只跑一段脚本片段):

```sh
beetap-cli run -m lark-tap --wait-timeout 5m -k '登录成功|||登录失败'
beetap-cli run --snippet 'toast("hi"); logd("snippet ok");'
beetap-cli run --code hook.js --template tpl.png    # 模板图在工程目录外时,CLI 自动复制进工程
beetap-cli stop | pause | resume
```

取证(写脚本/点坐标前必做):

```sh
beetap-cli screenshot -o shot.png      # 第一行 stdout=插件落盘路径;图片本机可读
beetap-cli nodes --dir evidence        # 图+XML 成对落盘并打印紧凑节点表(中心点即点击坐标)
beetap-cli ocr                         # 当前屏幕 OCR(需设备/App 具备 OCR 能力;result=null 时查 logs)
beetap-cli test-image --method findcolor --color 0xCDD7E9-0x101010
beetap-cli test-image --method findpic --template tpl.png   # 模板同样自动落位到工程目录
```

跟随日志:

```sh
beetap-cli logs --lines 200            # 一次性拉取;末行输出 cursor=N,下次 --since N 增量
beetap-cli monitor -k '脚本已停止运行' --max-duration 2m   # 命中退出 0,超时退出 2(关键字忽略大小写)
```

完整参数见同目录 `commands.md`。

## 关键约定

1. **退出码是判断成败的唯一标准**(与官方 `beetap-android-cli` 一致,不要解析中文文案):

   | 退出码 | 含义 |
   |---|---|
   | 0 | 成功(含 `run`/`monitor` 命中关键字) |
   | 1 | 用法/参数错误(含 `-m` 未找到、工程歧义、参数非法) |
   | 2 | `run --wait`/`monitor` 等待超时未命中关键字 |
   | 3 | 其它失败(编译失败/截图节点超时/内部错误) |
   | 4 | 设备未连接 |
   | 5 | 插件不可达(IDEA 没开/端口不对/响应非法,即协议本地码 9001) |
   | 6 | 已有运行在进行中(busy) |
   | 7 | 未识别的响应(未知 code;含 1003 端点被新 IDEA 实例接管) |

2. **先取证后编码**:写任何坐标/控件操作前,先 `screenshot` + `nodes` 拿真实屏幕与节点表;禁止凭记忆猜坐标、猜控件。节点表 `center` 列就是可点中心;只有无节点可用时才用截图目测,并说明依据。
3. **验证闭环**:写完脚本用 `run -k "预期成功标志"` 验证,配合 `logs`/`screenshot` 检查结果;失败先看日志再改代码。运行中再发 `run` 会以 `BUSY:` 日志 + `stopReason=timeout` 拒绝,本 CLI 识别后退出码 6 —— 先 `stop`。
4. **JS 错误不产生 HTTP 错误码**:`run` 返回 `code=0` 且 `stopReason=script_stopped` 时,仍需检查日志;出现 `JS 执行异常: ...` 说明脚本失败(本 CLI 会在 stderr 给出警告)。
5. **一次只跑一个脚本**:设备端同一时刻只允许一个脚本;`run` 撞车退出码 6,先 `stop`。
6. **超时必须给足**:`wait=true` 时 CLI 自动取 `max(--timeout, --wait-timeout+30s)`;`--wait-timeout` 先按服务端区间 [5s,30m] 钳位;超时返回 `stopReason=timeout` 且退出码 2,日志用 `logs` 继续拉。
7. **`-f json` 输出一行完整信封** `{code,msg,data}`(字段名即协议端点字段),供机器解析;text 模式下数据走 stdout、进度与错误走 stderr(前缀 `[beetap-cli]`)。官方 CLI 的 `-f json` 只输出 data 渲染结果,注意差异。
8. **端点只监听回环 + 单实例令牌**:本机任何进程都能遥控手机(令牌只做多实例区分,不做鉴权),不要把 9318 暴露出去。
9. **模板图必须位于工程目录内**(协议 1.3.10+):`run --template` 与 `test-image findpic --template` 传工程外路径时,本 CLI 自动复制到 `<工程>/bt_work_temp/android/beetap_cli_template.<ext>` 再提交(每次调用重新复制);`/run` 的 `codePath` 同样要求工程目录内(本 CLI 不使用,片段直接走 `code`)。
10. **OCR**:`/ocr` 只支持 `source=screen`;`type` ∈ mlkit / mlkitChinese / mlkitLatin / paddleOcrV4 / paddleOcrV5(省略用设备会话默认);结果在 `result`(JSON 文本,`[{label,confidence,x,y,width,height}]`),`null` 表示无结果——设备/App 的 OCR 能力未开启时常见,用 `logs` 定位;脚本侧 SDK 包装函数(`ocr.mlkitOcr` / `ocr.paddleOcrv4` / `ocr.paddleOcrv5`)可直接调用(以工程内技能书为准)。
11. **脚本 API 以工程内技能书为准**(如 `AiSkills/docs/funcs/`);不要编造 beetap-js API。

## 排障

| 现象 | 处置 |
|---|---|
| 退出码 5 插件不可达 | IDEA 未启动/插件未加载;或端口被 `-Dbeetap.cliPort=` 改过,用 `-u` 指定;或 9318 被别的进程占用 |
| 退出码 7(code=1003) | 端点被新启动的 IDEA 实例接管(单实例令牌不匹配);关掉多余 IDEA 实例,或按新实例的 `-Dbeetap.cliPort=` 用 `-u` 指向它 |
| 退出码 4 设备未连接 | 在 IDEA 插件里点「USB 调试」/「WiFi 直连」;`connect --wait 60s` 可在终端等待;仍不行时看插件日志与手机端 App |
| 插件连不上手机/调试 App 缺失 | 用插件菜单连接/安装(如「手机扫码安装调试 APK」);adb 兜底:`adb -s <serial> install -r -t <插件 jar 里的 apk-template/bt.apk>` |
| 重装 App 后无障碍/录屏异常 | 重装会重置权限;按插件菜单/手机端提示重新授权(插件有「adb 免重启开启无障碍服务」) |
| `run` 编译失败(退出码 3) | stdout 日志里有编译错误详情;修完重跑 |
| `run`/`findpic` 报 code=1001 | 检查 `module` 是否匹配工程;模板是否在工程目录内(命令行传工程外路径时 CLI 会自动落位,失败会先报错) |
| `nodes` 超时 | 手机端无障碍/代理未就绪;先在手机 App 开启,或用 `--override --mode 1` 提高覆盖率 |
| `test-image findpic` result=null | 小图不清晰/相似度过高;重新截图裁模板,降低 `--threshold` 再试 |
| `logs` 增量拉取 | 上次输出的 `cursor=N` 作为 `--since N`(游标以响应的 `cursor` 字段为准) |
| 本机用 curl 验证端点 | 加 `--noproxy '*'`,避免 `http_proxy` 环境变量拦截(本 CLI 已内置绕过代理) |

## 参考

- `INSTALL.md` — 安装说明(技能/全局命令/更新卸载/常见问题)
- `references/beetap-cli-protocol.md` — beeTap CLI 控制端点对接协议(v1,接口权威文档)
- `commands.md` — 完整命令速查
- `README.md` — 仓库说明、配置与测试
