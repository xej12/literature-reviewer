# Windows 新手安装指南

[返回首页](../README.md) · [使用指南](usage.md) · [故障排查](troubleshooting.md)

目标：先在自己的电脑上看见 Zotero 文献并打开 PDF，然后配置模型，最后按需开启图表和期刊指标。

## 1. 准备软件与文献

| 项目 | 是否必需 | 说明 |
| --- | --- | --- |
| Windows、现代浏览器 | 必需 | 当前服务使用 Windows 注册表检测 Zotero 版本，其他系统尚不支持 |
| Python 3.11+ | 必需 | 推荐 Python 3.11 或 3.12；无需安装 Codex |
| Zotero 桌面版 | 必需 | 需要本电脑 `zotero.sqlite`，PDF 附件也应下载到本电脑 |
| 自己的模型 API | AI 功能需要 | 兼容 OpenAI **Chat Completions**；订阅聊天网站不等于拥有 API 额度 |
| Poppler | 自动配置 | Windows x64 新手 ZIP 已包含；`setup.cmd` 校验并解压，无需手动改 PATH |
| Git、Node.js | 普通使用不需要 | Git 用于克隆/协作；Node.js 只用于开发时的前端测试 |

从 [Zotero 官网](https://www.zotero.org/download/) 安装桌面版。在 Zotero 里打开一篇带 PDF 的论文，确认附件确实在本电脑。不需要开放 Zotero 本地 API，也不需要安装配套插件；本项目直接只读访问本电脑数据库。

## 2. 下载并解压项目

推荐下载 [Windows x64 新手 ZIP（内含 Poppler）](https://github.com/xej12/literature-reviewer/releases/latest/download/literature-reviewer-windows-x64.zip)，右键解压。也可打开 [Releases](https://github.com/xej12/literature-reviewer/releases/latest)，在 Assets 选择 `literature-reviewer-windows-x64.zip`，不是自动生成的 Source code ZIP。进入解压后含 `setup.cmd`、`README.md` 和 `scripts` 的那一层文件夹。

建议放在自己的普通可写目录，例如 `D:\tools\literature-reviewer`。实际解压目录可能叫 `literature-reviewer-main`，没有关系。不要放在 `Program Files` 或直接在 ZIP 中运行。

熟悉 Git 的用户也可选择：

```powershell
git clone https://github.com/xej12/literature-reviewer.git
cd literature-reviewer
```

**Code → Download ZIP** 或 Git 克隆也可使用；这两种源码下载不含 Poppler 二进制，安装脚本会自动联网补齐。ZIP 用户不需要另外安装 Git。

安装好 Python 后，在项目根目录双击 **`setup.cmd`**：自动创建虚拟环境、联网安装 Python 依赖、校验并解压 Poppler，然后直接启动网站。使用新手 ZIP 时 Poppler 无需再下载；使用源码时会下载约 42 MiB 的固定版本并核验 SHA256。无需管理员权限或手动配置 PATH。普通 `start.cmd` 不会自动联网安装。

## 3. 安装 Python 与依赖

从 [Python Windows 下载页](https://www.python.org/downloads/windows/) 安装 Python 3.11+。安装时勾选 **Add python.exe to PATH**。安装后关闭旧终端，重新打开 PowerShell。

**推荐：直接双击 `setup.cmd`，等待安装完成即可继续第 4 步。** 首次安装仍需联网获取 Python 依赖，因此新手包并非完全离线安装包。

如需手动安装，在项目文件夹空白处右键选择“在终端中打开”；以下命令在项目根目录执行：

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install-poppler.ps1 -Download
```

第一行应显示 `Python 3.11` 或更高版本；依赖安装结束且没有报错后继续。若只有 `py` 命令可用，可把前两行的 `python` 换为 `py -3`，第三行保持原样。无需运行 `Activate.ps1`。

虚拟环境 `.venv` 将依赖留在当前项目中。下载新版本后请保留它，或者按上述命令重新创建；不要从别人的电脑复制虚拟环境。

## 4. 检查并启动

先运行只读检查：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1 -Check
```

`[FAIL]` 表示应先修复的问题；缺少 Poppler 或未找到 Zotero 会显示 `[WARN]`。检查不会调用模型、联网或输出 API Key。它只检查依赖能否被找到，不代替后面的实际 PDF 试用。

启动：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

看到 `Literature Reviewer running at http://127.0.0.1:8765` 后，在浏览器打开该地址。它是自己电脑上的服务地址，并不代表对外公开的网站。

保留启动窗口。停止时在该窗口按 **Ctrl+C**；下次直接双击项目根目录的 `start.cmd`。启动器优先选项目 `.venv`，其次系统 Python，再兼容已有的 Codex 内置 Python。

### 先试用示例模式（可选）

如果暂时没有 Zotero，或想先检查网页界面，可以运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1 -Demo
```

示例模式包含一篇随项目分发的短示例 PDF，明确标记为“示例模式”，不会读取 Zotero、不会读取个人文件，也不会发送模型请求。可以用它体验 PDF 打开、页码导航和笔记；点击生成解读时会被明确拦截。关闭窗口后，按上面的普通启动命令运行即可回到自己的文献库。

虚拟环境缺依赖时，启动器会提示使用选中的 Python 安装依赖；不要在另一个 Python 环境中重复安装。

## 5. 找不到 Zotero 时，指定数据目录

在 Zotero 的 **设置/首选项 → 高级 → 文件和文件夹 → 数据存储位置** 中查看实际数据目录（版本不同，文字可能略有差别）。要选的是**直接包含 `zotero.sqlite` 的文件夹**，不是 Zotero 安装目录，也不是里面的 `storage` 文件夹。

在同一个 PowerShell 窗口执行，替换示例路径：

```powershell
$env:ZOTERO_DATA_DIR = "D:\我的文献\Zotero"
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

这次设置仅对当前终端及其启动的服务生效。如果希望之后双击 `start.cmd` 也能识别，可在 Windows 搜索“编辑账户的环境变量”，新增**用户变量** `ZOTERO_DATA_DIR`，值填真实目录；重新打开终端或文件管理器后再启动。

网页能显示文献、集合和 PDF 附件，就说明基本连接成功；此时还不需要填写 API。

## 6. 在网页填写模型 API

点击右上角 **模型设置**，填写：

| 字段 | 怎么填 |
| --- | --- |
| API 地址 | 服务商提供的 Chat Completions 基础地址，例如 `https://api.openai.com/v1`。不要填写聊天网页地址，也不要在末尾重复加 `/chat/completions` |
| 模型名称 | 服务商文档中你有权限使用的准确模型 ID，不是自己起的名称 |
| API Key | 从该服务商的 API 控制台创建的密钥；不要发到 Issue 或截图中 |
| 输出预算、思考模式 | 第一次先保留默认；并非每个兼容服务都支持相同参数 |

模型设置中的“快速选择服务商”可以自动填写 OpenAI、DeepSeek、Ollama 或 LM Studio 的常见地址和示例模型。它只是填表快捷方式，最终仍应以服务商文档提供的地址和模型 ID 为准；其他服务选择“自定义 OpenAI 兼容服务”。本地 Ollama/LM Studio 通常不需要 API Key，但必须先在本机启动对应服务。

先点击**测试连接**检查服务的 `/models` 接口。此检查不会发送论文内容，也不会调用生成模型；部分兼容服务不提供该接口，会提示“地址可达但无法确认模型”。确认后再点击**保存配置**。保存后的 API Key 使用 Windows 当前账户的 DPAPI 加密，不再明文写入 `data/settings.json`；旧版本留下的明文 Key 会在下一次保存时迁移。仅浏览和保存配置不会生成解读。

图表功能要使用支持图片输入的模型。只有文字能力的服务仍可用于文字功能；以后切换配置时，已存讲解不会因此自动付费重生成。

环境变量 `LITERATURE_REVIEWER_*` 或 `OPENAI_*` 可以覆盖网页里的模型地址、Key 和名称。普通用户无需设置它们；“保存后仍用旧配置”时检查是否遗留了这些变量。

## 安装 Poppler（图表功能需要）

**运行过 `setup.cmd` 就已经配置好，不需要另装或编辑 PATH。** 固定版本、来源与 SHA256 在 [manifest.json](../vendor/poppler/manifest.json)；许可证与源码入口见 [Poppler 说明](../vendor/poppler/README.md)。支持 Windows x64，不支持 ARM64。

目录中 `vendor/poppler/windows-x64.zip` 是上游原始压缩包，安装时校验后解压到 `vendor/poppler/runtime/`。服务和环境检查会自动找到该目录，只调整当前进程的 PATH。终端直接输入 `pdfinfo` 找不到命令也不代表项目安装失败，应使用第 4 步环境检查。

已有环境只想补装 Poppler，可执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install-poppler.ps1 -Download
```

有包时直接解压，不下载；已有完整安装时只验证可执行文件。若下载失败，可下载新手 ZIP，或从清单中的固定上游地址获取原始 ZIP，放为 `vendor/poppler/windows-x64.zip` 后重试。校验失败时请重新下载，不要关闭校验。安装完成后重启网站。

进阶用户仍可自行安装 Poppler 并配置用户 PATH；项目内没有运行时时才使用 PATH 中的版本。`pip install pdf2image` 本身不会安装 Poppler。

## 7. 可选：导入期刊分区数据

不需要影响因子/分区时可以跳过，其他功能照常使用。导入的是第三方整理的指定年度数据，需要能连接 GitHub；不会调用模型。

```powershell
.\.venv\Scripts\python.exe scripts/import_journals.py
```

来源、固定版本、校验规则及离线导入方式见 [功能细节](advanced.md#期刊数据与阅读优先级)。中科院分区与 JCR 是两种口径，数据年度不等于论文发表时的指标。

## 8. 完成首次试用

打开一篇有本地 PDF 的论文 → 验证原文能打开 → 进入论文深度解读 → 只生成“阅读导览” → 关掉后再打开，确认可直接读取已保存结果。第一次生成会产生模型费用，第二次读缓存不会。

之后按照 [使用指南](usage.md) 按需体验术语、翻译和图表。若报错，对照 [故障排查](troubleshooting.md)，无需从头重装全部软件。
