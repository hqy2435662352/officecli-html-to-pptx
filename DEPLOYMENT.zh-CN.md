# officecli-html-to-pptx V0.6.2 部署与使用指南

## 交付范围

本 ZIP 是客户试用包，包含：

- `core/officecli_html_to_pptx-0.6.2-py3-none-any.whl`：Python Core Product；
- `plugins/officecli-html-to-pptx/`：skills-only Codex Plugin；
- `.agents/plugins/marketplace.json`：本地 Plugin marketplace 清单；
- 本部署与使用指南、README 和 MIT License。

ZIP 不内嵌 Python、Node.js、OfficeCLI、Chromium 或 Python 第三方依赖。
部署机器需要能够从获准的软件源安装这些依赖。

## 环境要求

- 支持的操作系统（二选一）：
  - Windows 10 或 Windows 11；
  - Linux。已通过验收的是 WSL2 上的 Ubuntu 24.04；其他发行版和原生安装尚未验证，
    请先按「Platform Acceptance Track」跑一遍完整流程再投入使用；
- Python `>=3.10,<3.15`，推荐 Python 3.12；
- Node.js `>=20,<23`；
- OfficeCLI `>=1.0.151`，且 `officecli` 命令已加入 `PATH`；
- Playwright `1.62.0` 及其 Chromium revision `1234`；
- 如需 Agent 工作流：支持 Plugin marketplace 的 Codex Desktop/CLI。

OfficeCLI、Python、Node.js 和 Codex 的安装来源由部署方管理。本产品只检查环境，
不会自动安装、升级或改写系统配置。

`capabilities --json` 会同时给出 `platform`（当前运行平台）与
`supported_platforms`（本构建支持的平台），据此判断"此处是否受支持"。

## 安装 Core Product

在 ZIP 解压目录中打开 PowerShell：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install .\core\officecli_html_to_pptx-0.6.2-py3-none-any.whl
.\.venv\Scripts\python.exe -m playwright install chromium
```

上述 `pip install` 会从当前配置的 Python package index 获取 wheel 声明的第三方
依赖。离线部署时，请由部署方另行准备获准的内部镜像或依赖缓存。

先验证运行时：

```powershell
.\.venv\Scripts\officecli-html-to-pptx.exe capabilities --json
.\.venv\Scripts\officecli-html-to-pptx.exe doctor --json
```

只有 `doctor` 返回 exit code `0` 且 JSON `status` 为 `PASS` 时才继续构建。
OfficeCLI 低于 `1.0.151`、Playwright/Chromium 不匹配、Node.js 或路径缺失都会返回
exit code `2` 和可操作的诊断。

## 在 Linux 上部署

安装步骤与 Windows 相同，只是路径不同：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install ./core/officecli_html_to_pptx-0.6.2-py3-none-any.whl
.venv/bin/python -m playwright install --with-deps chromium
.venv/bin/officecli-html-to-pptx capabilities --json
.venv/bin/officecli-html-to-pptx doctor --json
```

Linux 上有三个前置条件，**都不会让 `doctor` 报错**，但每一个都会让构建失败或产出错版：

### 1）不要以 root 运行

产品启动 Chromium 时不传 `--no-sandbox`，而 Chromium 拒绝以 root 运行且不加该参数。
请用普通用户执行，不要 `sudo`。

### 2）先激活虚拟环境

`build` 的最后一步会用 OfficeCLI 渲染 PPTX 对比图，而 OfficeCLI 自行寻找无头浏览器：
它需要一个 **`PATH` 上带 Playwright 的 `python3`**，或一个系统级
`chromium` / `google-chrome` / `chromium-browser`。

激活虚拟环境即可满足（这也正是 Windows 侧要求"在已激活虚拟环境的终端中启动"的原因）：

```bash
source .venv/bin/activate
```

注意两点：

- `CHROME_PATH` 不被识别，设它没有用；
- OfficeCLI 会为每个文档常驻一个 resident 进程，**并把"找不到浏览器"的结果缓存下来**。
  所以如果在修复环境之前已经失败过一次，需要先结束该 resident
  （`pkill -f __resident-serve__`）再重试，否则修好环境也仍然失败。

### 3）安装 Author HTML 声明的字体（最重要）

产品在**构建机**上用 Chromium 测量文本，再据此设定 PPTX 里文本框的宽高。如果构建机
没有该字体，Chromium 会替换字体，框尺寸就按替换字体的度量算出来——**PPTX 里字体名
是对的，尺寸却是错的**，表现为标题折行、文字压住其它元素等可见错版，而 `doctor` 依然
报告 `PASS`。

因此构建机需要安装 Author HTML 声明的字体族，并且**字重字面也要齐**。例如
`font-weight:900` 需要该字体族真的提供 Black 字面（如 `Arial Black`），否则会退到
Bold，度量随之改变。字体来源与授权由部署方按自身许可方式解决。

## 安装 Codex Plugin

ZIP 根目录本身是一个本地 marketplace。使用支持 Plugin marketplace 的 Codex CLI：

```powershell
codex plugin marketplace add "<ZIP解压目录>"
codex plugin add officecli-html-to-pptx@officecli-v062-local
```

安装后新建一个 Codex 任务，使新 Skill 被重新发现。Plugin 只提供
`build-a-pptx-with-html` 工作流，不包含 Core Product；运行 Codex 的进程必须能够
找到上一步虚拟环境中的 `officecli-html-to-pptx.exe`。最简单的做法是在已激活
该虚拟环境的终端中启动 Codex：

```powershell
.\.venv\Scripts\Activate.ps1
codex
```

如果目标 Codex 版本没有 `codex plugin marketplace` 命令，请先升级到组织批准的
支持 Plugin marketplace 的版本，不要直接修改 Codex 内部缓存。

## Agent 使用方式

在新的 Codex 任务中提供现有 HTML、视觉参考图或内容 brief，并明确要求使用
`build-a-pptx-with-html`，例如：

```text
使用 build-a-pptx-with-html，把 D:\work\proposal.html 构建为新的可编辑 PPTX，
输出到 D:\work\proposal.pptx，并完成证据检查和视觉审查。
```

Skill 会执行 Contract-first 工作流：

```text
Candidate HTML
  -> check
  -> build
  -> PPTX + Evidence Bundle
  -> Visual Review
  -> finalize
```

若目标 PPTX 或同名 `.evidence` 目录已经存在，产品会拒绝覆盖。请使用新文件名；
Agent 的自动修订使用 `-r01`、`-r02` 等后缀。

## Product 0.6.2 Workbench and Inspector

The `workbench` command is the sixth public command and is the installed
source-authoritative authoring loop. The Inspector exposes only source-mapped
Contract 1.3 fields: one simple text leaf/run; Shape geometry, solid fill,
border, opacity and simple text; Picture data-image replacement (maximum 10 MiB
decoded bytes) and `object-fit`; merged Table anchor-cell text/fill; and
ChartSpec title, category labels, series names/values/colors and supported
presentation fields. All five chart families are supported; category charts
allow one to three series, while pie and doughnut allow one. Preview displays
chart semantics from the same inert ChartSpec; it does not promise PowerPoint
pixel parity. `capabilities --json` publishes this boundary and exclusions.

```powershell
$tool = ".\.venv\Scripts\officecli-html-to-pptx.exe"
& $tool workbench "D:\work\proposal.html" --no-browser --json
```

The startup envelope reports a loopback URL, an unguessable session token, the
resolved source path and its loaded SHA-256. The bundled wheel contains the
complete editor/Preview UI in the Python package; it has no CDN, remote font,
runtime npm installation, or public-network requirement for editing. The
server accepts one resolved source per session, binds to `127.0.0.1`, serves
local resources only below the source directory, and requires the session token
plus same-session ID for mutations.

Preview, thumbnails, source maps, diagnostics, and browser draft state are
derived products. They are not compiler input and are not written into the
source file. Save is an atomic UTF-8 whole-document replacement guarded by the
loaded source SHA; an external disk change returns `CONFLICT` and preserves the
draft. Save may persist a Contract-invalid Candidate. Build Revision is
disabled until the draft SHA equals the disk SHA, no conflict exists, and Check
has returned `PASS` for that exact saved SHA. Build allocates a new target under
the session-owned output root and calls the ordinary `build_author_html`
Artifact Pair workflow.

The normal installed acceptance is:

```text
workbench startup -> edit -> Preview/navigation/source selection -> draft Check
-> conflict-safe Save -> exact-hash Check -> Build Revision -> independent
readback -> validate/issues -> slide-by-slide Gate 3 -> finalize
```

The #49 tracked Inspector corpus is `tests/fixtures/v06_02_inspector_corpus.html`;
it covers a real editable text leaf and shared-class override, native Shape,
bounded data Picture, merged Table anchor and covered cell, every chart family
and allowed series cardinality, and a localized-fallback object shown
read-only. The #44 regression corpus and conflict/recovery/security cases stay
at `tests/fixtures/v06_01_workbench_corpus.html` and
`tests/fixtures/v06_01_workbench_scenarios.md`. Direct canvas editing,
mixed-run replacement, shared class-rule editing, table/chart structure
changes, existing-PPTX editing, remote collaboration, and editor-specific
export remain outside Product 0.6.2.

## 直接使用 CLI

```powershell
$tool = ".\.venv\Scripts\officecli-html-to-pptx.exe"
& $tool capabilities --json
& $tool doctor --json
& $tool check "D:\work\proposal.html" --json
& $tool build "D:\work\proposal.html" "D:\work\proposal.pptx" --json
& $tool finalize "D:\work\proposal.evidence" --json
```

`build` 成功时返回 exit code `0` 和 `VISUAL_REVIEW_REQUIRED`。这表示 PPTX 与证据包
已生成，但仍需逐页检查 `.evidence\comparisons\slide-*.png`，填写
`visual-review.json` 后再执行 `finalize`。不要把 `VISUAL_REVIEW_REQUIRED` 当成最终
视觉验收通过。

最终结果：

- `PASS`：没有视觉发现；
- `PASS_WITH_FINDINGS`：只有不阻断交付的 minor findings；
- `REVISION_REQUIRED`：存在 major finding，需要修改 Author HTML 并生成新的
  Artifact Pair。

## 输出结构

对 `proposal.pptx`，产品同时创建：

```text
proposal.pptx
proposal.evidence/
  contract.json
  capabilities.json
  runtime.json
  manifest.json
  readback.json
  native-evidence.json
  validate.json
  issues.json
  result.json
  visual-review.json
  comparisons/
    slide-001.png
    ...
```

交付时保留整个 PPTX/Evidence Pair，不要只复制 PPTX，也不要混用不同 build 的
PPTX、JSON 或 Comparison Image。

V0.5.3 的 tracked public corpus 是
`tests/fixtures/v05_03_public_corpus.html`，固定四页：contained CSS effects、
inline SVG、两个不重叠的 localized regions，以及组合原生 text/table/shape/
chart 和一个 rasterized region 的业务页。每个
`data-pptx-rasterize="localized"` 都是一个 atomic visual object；其全部
descendants 不会再被 generic lowering。V0.5.2 chart corpus、V0.5.1 corpus
和 V0.4 projection corpus 仍是独立的回归资产，不进入 V0.5.3 localized
fallback gate 或能力计数。
完成发布验收时必须执行
`capabilities -> doctor -> check -> fresh build -> independent readback ->
validate/issues -> four-slide semantic Gate 3 -> finalize`；authored/compiled/
readback chart counts 必须一致，OfficeCLI validation PASS、issues zero，且
`unsupported`、`unresolved` 和 `material_delta` 必须都是零，minor findings
仍可推导为 `PASS_WITH_FINDINGS`。

## V0.5.3 正式边界

支持：从 Contract 1.3 checked Author HTML 新建 PPTX；保留 V0.5.2 的可编辑
文本框、闭合形状、data-URI 图片、合法矩形合并表格、冻结的文本段落/run
矩阵和 authored native charts，并增加显式 localized visual fallback。

只有大小写敏感的 `data-pptx-rasterize="localized"` 标记会触发该 fallback。
标记节点是 atomic authored object；其 descendants 在 generic discovery 前排除。
捕获使用节点 CSS border box、真正局部隔离渲染和固定 `2 pixels per point`，输出
deterministic PNG picture；区域内文字包含在图片内，不宣称可编辑。首版只接受
静态 HTML/CSS、inline SVG、data URI 和当前策略允许的本地图片；脚本、runtime
canvas、iframe、网络资源、媒体、WebGL、动画、交互态及跨 slide capture 会
fail closed。输出 disposition 固定为 `native`、`rasterized`、`unsupported`、
`unresolved`；后两者以及超界绘制、隔离污染和 material delta 阻止发布。

## V0.5.2 回归基线

支持：从 Contract 1.2 checked Author HTML 新建 PPTX；可编辑的文本框、闭合
形状几何、data-URI 图片、合法矩形 rowspan/colspan 合并表格、冻结的文本
段落/run 矩阵，以及显式 authored 的 native `column`、`bar`、`line`、`pie`
和 `doughnut` charts。图表只接受 `capabilities --json` 发布的严格 JSON
protocol、数据 limits、presentation tokens 和 private doughnut default。

不支持：编辑已有 PPTX、任意网页/CSS、外部图片 URL、chart fallback、
SmartArt、动画、音视频以及 master/layout/theme 的完整保真。未知 chart
field/type、arbitrary Office format strings、authored `holeSize` 和其他
chart families 会在 check/build 前 fail closed。

本包是实验性交付，不承诺向后兼容。出现问题时请保留输入 HTML、完整 Evidence
Bundle、`doctor --json` 输出和产品版本号。

## 常见排查

- `officecli_version_mismatch`：安装或选择 OfficeCLI `1.0.151` 或更新版本；
- `missing_playwright`：确认在同一虚拟环境中安装了本 wheel；
- `missing_chromium` / `chromium_revision_mismatch`：在同一虚拟环境执行
  `python -m playwright install chromium`；
- `unsupported_platform`：当前操作系统尚未通过 Platform Acceptance Track。诊断信息会
  列出受支持的平台；不要通过改代码绕过，先补验收证据；
- `BLOCK` from `check`：按 diagnostics 修复 Candidate HTML，不要绕过 Contract；
- output collision：选择新输出名，不要删除或覆盖已有 Artifact Pair；
- `REVISION_REQUIRED`：根据 major findings 修改 HTML，重新 `check` 和 `build`；
- Linux 上 `build` 在证据阶段以 exit code `4` / `build_failed` 结束，报
  "OfficeCLI did not create screenshot"：OfficeCLI 找不到无头浏览器。激活虚拟环境
  （或装系统 Chromium），结束残留 resident 进程后重试；
- Linux 上 `doctor` 通过但 PPTX 出现折行／重叠：构建机缺字体或缺该字重字面，
  见「在 Linux 上部署」第 3 条。
