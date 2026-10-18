# 阅读笔记与侧栏改进调研（2026-10-18）

目标是让读者留下自己的理解、疑问及原文位置，先完成本地笔记和导出的使用闭环。

| 项目 | 核对到的能力 | 本次采用方式 |
| --- | --- | --- |
| [Better Notes for Zotero](https://github.com/windingwind/zotero-better-notes) | README 展示笔记关联、模板、Markdown 同步与多格式导出；当前 LICENSE 为 AGPL-3.0 | 参考“笔记关联论文 → 模板提问 → 导出”的流程。本次没有复制插件代码或模板，没有安装插件，也没有实现 Zotero 笔记回写/双向同步。 |
| [Vditor](https://github.com/Vanessa219/vditor) | 浏览器 Markdown 编辑器，支持富文本、即时渲染及分屏预览，README 标注 MIT | 参考格式工具栏与编辑/预览交互。当前先提供文本编辑与预览，没有引入其整套编辑器，也没有把富文本编辑列为已实现功能。 |
| [markdown-it](https://github.com/markdown-it/markdown-it) | CommonMark 解析、可扩展规则和浏览器构建；MIT | 实际集成本地浏览器构建 15.0.3，渲染标题、列表、引用、表格等；复用本地 KaTeX 显示公式。 |

此次核对的上游 README 提交：Better Notes `4215a882e9f3528ddd4820c20b2c29e732c14e7e`；Vditor `4535ffb0c6b70809a0d5bcb477d9568e297ae83f`；markdown-it `a8c00d474ec9b304fad9b71c16d6fa8b4909279e`。README 描述是上游能力，不代表本项目已实现其全部功能。

## 实际集成的依赖

- 来源：`https://registry.npmjs.org/markdown-it/-/markdown-it-15.0.3.tgz`
- npm tarball integrity：`sha512-+Az7Ojz3iRGu8KYMvJ6xVhvrxP3eE+vEtJX75Ow88XBpcQNV/0lGX5ZynIIBftREo4DC2jsveAMDaeltmm8QvQ==`，下载时已核验。
- `web/vendor/markdown-it/markdown-it.min.js` SHA256：`391f2aa638e75e6c7859d0a5c5650ef0956722a45998f17e05b83bc655778e1e`。
- MIT 许可保留在 `web/vendor/markdown-it/LICENSE`；浏览器日常使用不连接 CDN。

## 第一版范围

左栏新增文献库/我的笔记导航、笔记数量和最近三篇笔记。文献集合继续来自本机 Zotero。

笔记可独立创建，或从论文详情建立固定文献关联。四个模板由本项目自行编写：快速摘记、论文精读、图表研读、空白笔记。模板只是可改写的提示提纲，不自动填入模型内容。

正文使用 Markdown，提供格式按钮、编辑/对照/预览、公式显示与搜索。手写内容自动保存在 `data/notes/`；有浏览器未保存草稿保护、原子文件替换和版本冲突检查。草稿只保存在该浏览器的本地存储中，不跨设备同步；浏览器存储不可用时会提示导出。已有磁盘笔记损坏时保留原文件并提示，不静默覆盖。

导出 Markdown 带论文元数据；HTML 为独立文档，公式用浏览器 MathML 显示，不需要 CDN、脚本或外部字体。打印 PDF 使用浏览器的打印功能，不是服务端 PDF 转换。正文 HTML 不执行，图片引用不自动加载，以免预览时悄悄访问外部站点或本机接口。此版不支持图片附件、DOCX、自定义模板、协作编辑或 Zotero 双向同步。

笔记创建、保存、搜索、预览、导出均不调用模型。测试使用临时目录及模拟文献，不把测试笔记写进个人库。
