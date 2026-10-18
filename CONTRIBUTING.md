# 贡献指南

欢迎改进安装说明、报告真实阅读问题、修复错误或提交代码。项目面向个人科研阅读；贡献应帮助读者理解并核对论文，同时避免不必要的模型费用。

## 反馈与建议

先阅读 [故障排查](docs/troubleshooting.md) 并搜索已有 Issue。用仓库的故障/建议表单说明复现过程和期望结果。文档更正也欢迎直接提 PR，不要求先开 Issue。

不要上传 API Key、整个 `data/`、Zotero 数据库或受版权保护的论文全文。示例尽量使用自己编写的最小文字、合成图像或有明确开放许可的材料。

## 开发环境

目前在 Windows 开发、验证，Python 3.11+。按 [安装指南](docs/installation.md) 创建 `.venv` 并安装依赖。只有需要查看自己的文献库时才需连接 Zotero；自动测试使用临时数据和模拟响应，不要求提供真实文献或 API Key。

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
```

前端公式/来源渲染检查额外需要 [Node.js LTS](https://nodejs.org/)：

```powershell
node tests/test_deep_math.cjs
```

不需要 `npm install`。测试使用仓库自带资源，不应调用任何付费模型服务。改动启动器时，请额外用 `start.ps1 -Check` 和一个未使用端口试启动；不要关闭开发者已有的服务。

仓库的 Windows GitHub Actions 工作流会执行环境检查和以上测试，不需要 Zotero 库、Poppler 或模型密钥；可选组件缺失只会在环境检查中提示。自动测试通过不等于已验证真实模型或所有 PDF。

## 代码在哪里

| 目录 | 职责 |
| --- | --- |
| `scripts/server.py` | 本地 HTTP 服务、Zotero 只读访问、模型配置与功能入口 |
| `scripts/deep_reading.py`、`term_reading.py`、`figure_reading.py` | 论文、术语、图表的讲解结构与缓存处理 |
| `scripts/translation.py` | 专业术语约定、翻译与缓存 |
| `scripts/model_output.py`、`generation.py` | 答复格式处理和生成参数 |
| `scripts/request_jobs.py` | 生成任务取消、连接中断 |
| `scripts/journal_metrics.py`、`reading_priority.py` | 期刊数据匹配和个人阅读优先级 |
| `web/` | 无构建步骤的原生 HTML/CSS/JavaScript 页面 |
| `web/vendor/` | 已分发的 PDF.js、KaTeX 等第三方文件和许可证 |
| `tests/` | 可在本机运行的自动测试 |
| `docs/` | 面向使用者的安装、操作、排错及实现边界 |
| `references/` | 历史阶段记录、调研与数据版本；旧阶段文档不是当前安装入口 |

## 修改时保持的行为

- 只读访问 Zotero，不自动修改或删除原库内容。
- 浏览、查看缓存和免费格式整理不调用模型；只有明确生成操作才发起付费请求。
- 关闭/切换解析后取消任务；迟到的结果不能覆盖用户正在看的其他文献。
- 格式失败时保留原始答复和已有成功结果；不能通过自动重试悄悄增加费用。
- 解释区分原文事实、教学背景与推断；引用定位不等于内容已被证明。
- 按需处理文献材料，不能将 Key 发送到前端或写入日志、截图、测试样例。
- 不去除第三方许可，不将期刊数据或私人缓存提交进仓库。

## 提交 PR

Fork 仓库并在分支修改；提交前检查 `git diff --check`（第三方原始文件不要求重新排版）、运行相关测试。说明具体问题、最终行为、验证方式和已知限制；界面改动可附不含私人文献的截图。

文档或小范围样式改动无需为了覆盖率添加重复实现的测试。行为修改请提供能验证实际风险的检查。尚未实现或未验证的平台不要写成已经支持。

提交原创贡献即表示你同意这些贡献按本项目 [MIT 许可证](LICENSE) 提供；引用其他代码需说明来源并保留其兼容许可。
