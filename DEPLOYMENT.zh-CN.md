# officecli-html-to-pptx V0.2 实验版部署与使用指南

## 交付范围

本 ZIP 是 Windows 客户试用包，包含：

- `core/officecli_html_to_pptx-0.2.0-py3-none-any.whl`：Python Core Product；
- `plugins/officecli-html-to-pptx/`：skills-only Codex Plugin；
- `.agents/plugins/marketplace.json`：本地 Plugin marketplace 清单；
- 本部署与使用指南、README 和 MIT License。

ZIP 不内嵌 Python、Node.js、OfficeCLI、Chromium 或 Python 第三方依赖。
部署机器需要能够从获准的软件源安装这些依赖。

## 环境要求

- Windows 10 或 Windows 11；
- Python `>=3.10,<3.15`，推荐 Python 3.12；
- Node.js `>=20,<23`；
- OfficeCLI `>=1.0.147`，且 `officecli` 命令已加入 `PATH`；
- Playwright `1.62.0` 及其 Chromium revision `1234`；
- 如需 Agent 工作流：支持 Plugin marketplace 的 Codex Desktop/CLI。

OfficeCLI、Python、Node.js 和 Codex 的安装来源由部署方管理。本产品只检查环境，
不会自动安装、升级或改写系统配置。

## 安装 Core Product

在 ZIP 解压目录中打开 PowerShell：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install .\core\officecli_html_to_pptx-0.2.0-py3-none-any.whl
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
OfficeCLI 低于 `1.0.147`、Playwright/Chromium 不匹配、Node.js 或路径缺失都会返回
exit code `2` 和可操作的诊断。

## 安装 Codex Plugin

ZIP 根目录本身是一个本地 marketplace。使用支持 Plugin marketplace 的 Codex CLI：

```powershell
codex plugin marketplace add "<ZIP解压目录>"
codex plugin add officecli-html-to-pptx@officecli-v02-local
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

## V0.2 实验版边界

支持：从 Contract-checked Author HTML 新建 PPTX；可编辑的文本框、常用形状、
data-URI 图片和无合并单元格的原生表格。

不支持：编辑已有 PPTX、任意网页/CSS、外部图片 URL、合并单元格、原生图表、
SmartArt、动画、音视频以及 master/layout/theme 的完整保真。

本包是实验性交付，不承诺向后兼容。出现问题时请保留输入 HTML、完整 Evidence
Bundle、`doctor --json` 输出和产品版本号。

## 常见排查

- `officecli_version_mismatch`：安装或选择 OfficeCLI `1.0.147` 或更新版本；
- `missing_playwright`：确认在同一虚拟环境中安装了本 wheel；
- `missing_chromium` / `chromium_revision_mismatch`：在同一虚拟环境执行
  `python -m playwright install chromium`；
- `BLOCK` from `check`：按 diagnostics 修复 Candidate HTML，不要绕过 Contract；
- output collision：选择新输出名，不要删除或覆盖已有 Artifact Pair；
- `REVISION_REQUIRED`：根据 major findings 修改 HTML，重新 `check` 和 `build`。

## 主机字体与渲染器前置检查

`build` 在编译之前先验证两个主机条件，两者的结果都会写入 Evidence Bundle 的
`result.json` 的 `preflight` 字段。

### 字体

Author HTML 声明的字体族和字重面必须由构建主机真实提供。Chromium 是测量的权威，
因此检查直接询问 Chromium 本身：`FontFace(local(...))` 判断字体族是否存在，
DevTools Protocol 的 `CSS.getPlatformFontsForNode` 报告 Chromium 实际绘制的字重面。

| diagnostic | 级别 | 含义 |
| --- | --- | --- |
| `declared_font_family_absent` | **阻断** | 主机缺少声明的字体族，Chromium 已用替代字体测量。此时量出的文本框尺寸与 PPTX 声明的字体不一致，属于静默错误。 |
| `font_weight_face_substituted` | 提示 | 字体族存在，但请求的字重落到了更轻的字重面。PPTX 声明的是字体族，PowerPoint 会做同样的替代，因此不阻断。 |
| `declared_font_family_skipped` | 提示 | 声明了主机没有的字体族，但 Chromium 跳过了它并落到 PPTX 实际声明的那一族，几何是正确的。 |

### 渲染器

Evidence Bundle 的 PPTX 面板依赖 `officecli view <pptx> screenshot --render html`，
它需要一个可被 OfficeCLI 发现的无头浏览器。检查会用一次性文档真实截一次图，并且
**只认生成的 PNG 文件**——OfficeCLI 在没有渲染出任何内容时仍然返回退出码 `0`。

| diagnostic | 级别 | 含义 |
| --- | --- | --- |
| `renderer_browser_missing` | **阻断** | 主机上完全没有找到浏览器。 |
| `renderer_browser_unreachable` | **阻断** | 主机上存在浏览器，但 OfficeCLI 找不到它。这是更常见的情况，修复方式不同。 |

修复方式：在 `PATH` 中提供带 Playwright 的 `python3`，或把系统 Chromium
（`chromium` / `google-chrome` / `chromium-browser`）暴露到 `PATH`，然后直接重试。
探测使用一次性文档并在 `finally` 中关闭 resident，因此修正环境后不需要手工清理
resident 就能成功。

### 字体供应

文本几何由构建主机上的 Chromium 测量，PPTX 则声明 Author HTML 解析出的字体族。
主机缺少该字体族时 Chromium 会静默替代，量出的文本框按替代字体定尺寸，成品在
每一条命令都报告成功的情况下依然是错的。同理，字体族存在但缺少所需字重面时
（例如 `Arial` 没有 900 面时要在 `Arial Black` 与合成粗体之间取舍），会产生逐页漂移。

因此请在构建主机上安装 Author HTML 实际使用的字体。产品只做诊断，不安装字体
（ADR-0016）。
