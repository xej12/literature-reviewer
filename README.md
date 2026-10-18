# Literature Reviewer · 文献梳理工具

**把 Zotero 中的论文，变成可以对照原文、逐步理解的阅读笔记。**

面向个人科研阅读的本地网页工具：不只给摘要，还能按需讲解研究方法、公式、专业术语和图表。解读保存在你的电脑上，再次查看可直接复用。

[新手安装](docs/installation.md) · [使用指南](docs/usage.md) · [常见问题](docs/troubleshooting.md) · [English](README.en.md)

> 当前提供 Windows 源码版，需要 Python 3.11+ 和本机 Zotero。尚未提供安装包，也未支持 macOS/Linux。普通使用无需安装 Codex、Node.js 或 Zotero 插件。项目仍在迭代中。

## 可以帮你做什么

| 你的需求 | 对应功能 |
| --- | --- |
| 从自己的文献库开始读 | 读取 Zotero 集合、元数据及本地 PDF；原始 PDF 可直接打开 |
| 理解论文在做什么 | 按章节生成阅读导览、方法拆解、公式讲解、实验与结论、局限与自检 |
| 不认识专业名词 | 专业术语表、结合本文的术语精讲、PDF 划词翻译 |
| 看不懂图表 | 左侧 PDF、右侧讲解；支持框选区域、翻页和放大 |
| 回到原文核实 | 来源片段与 PDF 页码定位，公式可展开原文对照 |
| 安排阅读顺序 | 本地阅读进度、研究目标、缓存的阅读优先级；可选导入中科院/JCR 指标 |
| 少花重复费用 | 已存结果直接读取；重新生成需确认；关闭解析窗口会发出取消请求 |

中科院/JCR 指标是第三方整理的指定年度数据，首次需单独导入。阅读等级围绕个人研究目标，不代表论文质量定论。

## 第一次使用，从这里开始

1. **准备 Zotero。** 在 Zotero 中确认至少一篇论文的 PDF 能打开。仅有云端附件时，先把 PDF 下载到本机。
2. **下载项目。** 点击本页上方 **Code → Download ZIP**，解压到普通可写文件夹，例如 `D:\tools\literature-reviewer`。不要直接在压缩包内运行。
3. **安装 Python 3.11 或更高版本。** 从 [Python 官网](https://www.python.org/downloads/windows/)下载安装，安装时勾选 **Add python.exe to PATH**，随后重新打开 PowerShell。
4. **安装项目依赖。** 在解压后的项目文件夹打开 PowerShell，依次执行：

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1
   ```

5. **打开网页。** 浏览器访问 <http://127.0.0.1:8765>。启动窗口需要保持打开；以后双击项目根目录的 `start.cmd` 即可启动。
6. **先验证文献，再配置模型。** 能看见文献并打开 PDF 后，点击右上角“模型设置”，填写自己的 API 地址、模型名称和 Key。图表解析还需要 [安装 Poppler](docs/installation.md#安装-poppler图表功能需要) 和支持图片输入的模型。

如果 `python` 命令找不到、Zotero 目录没有被识别，或不知道 API 地址怎么填，请跟着 [完整安装指南](docs/installation.md) 操作。上面命令无需激活虚拟环境，也无需管理员权限。

## 费用、隐私和能力边界

- **本地运行：** 默认只监听 `127.0.0.1`。别人下载的是程序，需要在自己的电脑上连接自己的 Zotero；GitHub 不会托管你的文献网页。
- **模型费用自付：** 浏览、查缓存和免费整理已有答复不调用模型。主动生成、非术语表命中的翻译以及连接测试可能消耗你的 API 额度；模型服务通常单独计费。
- **外部模型会接收材料：** 生成时相关论文文字或所选页面图片会发送到你填写的服务。API Key 和阅读记录保存在本机 `data/`；Key 以明文存储，请勿分享该目录。
- **忠于原文仍需核对：** 来源定位只帮助核实，不能保证模型解释正确。扫描件暂不支持 OCR，损坏的公式提取和图片识别可能出错。
- **取消存在服务商边界：** 关闭解析窗口会中断本机请求和上游连接；已产生的用量不能撤回，远端是否立即停算由服务商决定。

数据存储、备份与 Token 规则见 [使用指南](docs/usage.md)，具体材料覆盖和兼容限制见 [功能细节](docs/advanced.md)。服务尚无登录及多用户隔离，请保持本地使用。

## 获取帮助与参与改进

- 遇到问题：先看 [故障排查](docs/troubleshooting.md)，再用 [故障反馈表](https://github.com/xej12/literature-reviewer/issues/new?template=bug_report.yml) 提交复现步骤。
- 建议功能：使用 [功能建议表](https://github.com/xej12/literature-reviewer/issues/new?template=feature_request.yml)，说明阅读场景及期望效果。
- 想贡献代码或文档：阅读 [贡献指南](CONTRIBUTING.md)。不需要调用付费模型即可运行现有测试。
- 发现密钥或隐私泄露：请参照 [安全说明](SECURITY.md)，不要把密钥、全文或私人文献库贴进公开 Issue。

## 开源与致谢

本项目自行编写的代码与文档采用 [MIT 许可证](LICENSE)。内置的 PDF.js、KaTeX 及字体等保留各自许可证；期刊指标数据不随仓库分发，也不由本项目的 MIT 许可授权。依赖、设计参考与数据来源见 [第三方说明](THIRD_PARTY_NOTICES.md)。

项目当前没有官方付费服务、公共演示库或模型代理。欢迎反馈真实使用中的问题，让后续改进更贴近科研阅读。
