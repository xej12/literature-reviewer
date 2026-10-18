# 第三方组件、参考项目与数据

[返回首页](README.md)

项目自有代码和文档采用 MIT。以下组件和数据保留各自条款；仓库根目录的 MIT 不替代它们的许可证。

## 实际随仓库分发的组件

| 组件 | 版本与上游 | 用途 | 随附许可位置 |
| --- | --- | --- | --- |
| KaTeX | [0.16.22](https://github.com/KaTeX/KaTeX/releases/tag/v0.16.22) | 本地数学公式排版及字体 | [web/vendor/katex/LICENSE](web/vendor/katex/LICENSE)（MIT） |
| PDF.js | [pdfjs-dist 5.4.149](https://www.npmjs.com/package/pdfjs-dist/v/5.4.149) / [源码](https://github.com/mozilla/pdf.js) | 原始版式 PDF 阅读、可选择文字层 | [web/vendor/pdfjs/LICENSE](web/vendor/pdfjs/LICENSE)（Apache-2.0） |
| PDF.js 附带资源 | 随上述分发版本 | 字体、字符映射、色彩及图像解码 | 见下方资源许可 |
| markdown-it | [15.0.3](https://www.npmjs.com/package/markdown-it/v/15.0.3) / [源码](https://github.com/markdown-it/markdown-it) | 本地笔记 Markdown 预览 | [web/vendor/markdown-it/LICENSE](web/vendor/markdown-it/LICENSE)（MIT） |

PDF.js 资源原许可保留于：

- [字符映射](web/vendor/pdfjs/cmaps/LICENSE)
- [ICC 色彩资源](web/vendor/pdfjs/iccs/LICENSE)
- [Foxit 字体](web/vendor/pdfjs/standard_fonts/LICENSE_FOXIT)
- [Liberation 字体](web/vendor/pdfjs/standard_fonts/LICENSE_LIBERATION)
- [OpenJPEG](web/vendor/pdfjs/wasm/LICENSE_OPENJPEG) 与 [PDF.js OpenJPEG 适配](web/vendor/pdfjs/wasm/LICENSE_PDFJS_OPENJPEG)
- [QCMS](web/vendor/pdfjs/wasm/LICENSE_QCMS) 与 [PDF.js QCMS 适配](web/vendor/pdfjs/wasm/LICENSE_PDFJS_QCMS)

更新第三方组件时请同时保留/更新其版权和许可文件。不要仅复制压缩后的 JS 或字体而丢弃这些文件。

## 运行时另行安装的依赖

Python 依赖由 [requirements.txt](requirements.txt) 声明：

- [pypdf](https://github.com/py-pdf/pypdf)：PDF 文字提取，BSD-3-Clause。
- [pdf2image](https://github.com/Belval/pdf2image)：调用 Poppler 渲染 PDF，MIT。
- [Pillow](https://github.com/python-pillow/Pillow)：图像处理，HPND 等条款，以安装版本随附许可为准。
- [Poppler](https://poppler.freedesktop.org/)：用户另行安装的 PDF 渲染工具，本项目不捆绑其可执行文件；其 GPL 等许可不由根 MIT 替代。[Windows 构建](https://github.com/oschwartz10612/poppler-windows)是第三方分发。

## 本机单独导入的数据

中科院/JCR 表来自 [ShowJCR](https://github.com/hitfyd/ShowJCR) 的固定提交，文件名、数据年度、上游提交与 SHA256 见 [数据清单](references/journal-data.json)。本仓库不分发这些表，也不授予其使用或再分发权；使用者应了解数据来源和适用条件。匹配适配器自行编写，未复制上游 GPL 插件代码。

PDF、Zotero 元数据、个人术语表和模型生成记录由使用者提供或生成，不作为项目自带开放数据分发。能在本机阅读一篇论文，不自动代表有权把全文公开上传。

## 设计与工作流参考

- [Better Notes for Zotero](https://github.com/windingwind/zotero-better-notes)：参考关联文献、模板与导出流程；未复制 AGPL 插件代码或模板。笔记模板由本项目自行编写。
- [Vditor](https://github.com/Vanessa219/vditor)：参考编辑/预览与工具栏交互；当前没有集成其完整编辑器。见 [笔记调研](references/notes-research.md)。

- [DeepPaperNote](https://github.com/917Dhj/DeepPaperNote)：参考证据组织、机制解释和材料覆盖的思路，在本应用中独立实现。
- [Translate for Zotero](https://github.com/windingwind/zotero-pdf-translate)、[NextAI Translator](https://github.com/nextai-translator/nextai-translator)：参考手动触发、术语优先和原译文对照的交互，没有复制其源码。
- [PDFMathTranslate](https://github.com/PDFMathTranslate/PDFMathTranslate)：全文双语翻译的调研对象，当前未集成。
- [cas-journal-mcp](https://github.com/Cuberskyleaf/cas-journal-mcp)、[zotero-style](https://github.com/MuiseDestiny/zotero-style)、[zotero-publication-rankings](https://github.com/ben-AI-cybersec/zotero-publication-rankings)：期刊指标相关调研参考，未以 SJR 替代 JCR。

更详细的翻译方案选择见 [调研记录](references/translation-research.md)。上述链接是来源说明，不代表与上游存在合作、官方授权或兼容保证。
