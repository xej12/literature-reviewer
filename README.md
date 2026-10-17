# 文献梳理工具

一个面向个人科研使用的本地 Zotero 文献梳理工具。它读取本机 Zotero 文献库，以网页界面展示元数据和 PDF，并提供论文解读、专业术语提取和逐页图表解析。

## 特点

- 只读访问本机 Zotero SQLite 数据库和 PDF 附件；
- 模型地址、模型名称和 API Key 在网页中配置，保存在本机；
- 论文解读、术语和图表结果按文献缓存到本机，重复打开不会重复消耗 Token；
- 服务默认只监听 `127.0.0.1:8765`，不会自动暴露到局域网或公网。
- 显示中科院大类与各小类分区、JCR 各学科分区、影响因子及数据表年份；
- 按研究目标评估并缓存阅读优先级，支持“夯 → 顶级 → 人上人 → NPC → 拉”排序与手动调整。

## Windows 使用

1. 安装 Zotero，并确认 Zotero 数据目录中存在 `zotero.sqlite`。
2. 安装 Python 3.11 或更高版本，并安装依赖：

   ```powershell
   python -m pip install -r requirements.txt
   ```

3. 安装 Poppler，并将包含 `pdftoppm.exe` 和 `pdfinfo.exe` 的目录加入 PATH。PDF 页面预览和图表解析需要它。
4. 启动服务：

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1
   ```

5. 打开 <http://127.0.0.1:8765>，点击右上角“模型设置”填写兼容 OpenAI Chat Completions API 的地址、模型和 Key。

如果 Zotero 数据目录不在默认位置，可以先设置环境变量：

```powershell
$env:ZOTERO_DATA_DIR = "D:\你的 Zotero 数据目录"
```

## 数据与隐私

`data/settings.json`、`data/analysis/`、`data/journals/`、`data/research.json`、`data/reading-priority/` 和本机 Zotero 数据不会提交到 Git。使用外部模型时，只有主动发起解读、术语提取、图表解析或阅读优先级评估时，相关文本或页面图片才会发送到你配置的模型服务。

## 期刊数据与阅读优先级

数据参考 [ShowJCR](https://github.com/hitfyd/ShowJCR)，固定版本为中科院 2025 / JCR 2025 CSV。匹配适配器独立实现，未复制上游 GPL 插件代码。第三方数据保留在本机，不随本仓库重新分发；使用前请了解上游数据来源及适用条件。其他调研参考：[cas-journal-mcp](https://github.com/Cuberskyleaf/cas-journal-mcp)、[zotero-style](https://github.com/MuiseDestiny/zotero-style)、[zotero-publication-rankings](https://github.com/ben-AI-cybersec/zotero-publication-rankings)。其中 SJR 分区不能替代 JCR。

首次使用可导入数据（固定提交、文件名和 SHA256 见 `references/journal-data.json`）：

```powershell
python scripts/import_journals.py
```

已有上述两份 CSV 时可运行 `python scripts/import_journals.py --from-dir "CSV所在目录"`。校验不符则拒绝导入。数据未载入时网页会提示，其他功能仍可使用。

页面标注的是**数据表年度**，不是论文发表时的指标，也不是直接连接官方实时服务。ISSN 优先，其次精确匹配规范刊名；未匹配的 ISSN 不回退到可能冲突的刊名。歧义、不适用和未收录分别呈现，全部学科分区可在详情展开查看。

文献列表提供“有分区信息”和“暂无分区信息”两类切换，并显示篇数。存在有效中科院大类/小类 1–4 区，或 JCR 学科 Q1–Q4 即归入前者；只有 IF、刊名匹配但没有分区的归入后者。分类是本工具的视图，不改写 Zotero 集合，支持与搜索、分析状态、等级筛选和排序组合使用。

先在网页设置研究目标与中英文关键词。关键词只作相关性线索，不自动判定必读。点击“评估阅读优先级（消耗 Token）”才调用模型，材料包括元数据、摘要、可提取 PDF 前 12 页（最多 40000 字符）与已保存解读，不保证覆盖全文。模型必须提供可在原文核对的引文，并说明材料限制。相关性占 60 分，内容价值占 30 分，期刊参考最多 10 分；缺少指标时按内容得分归一化，不因无 IF 自动降级。材料不足保持待评估。

结果按文献内容和研究目标版本缓存，浏览和排序不调用模型。修改目标或文献摘要/解读后旧结果保留但不套用。支持免费手动设定等级和理由；重新模型评估会替换当前等级，按钮提示 Token 消耗。未评估文献放在已评估等级后，按相关主题线索辅助排序。等级仅指对个人研究目标的阅读优先级，不是论文质量定论。

评估时将原文片段编号，模型引用片段 ID 后由程序还原引文，避免抄写和翻译造成匹配失败。兼容旧式字符串或引文对象，以及 PDF 断行、断词、连字等格式差异；不接受修改词义、数字或否定词的模糊匹配。部分引文有效时仅保留有效部分；没有可核实引文时仍缓存模型答复，标为“待评估”，不采用其分数，也不自动再次调用模型。可以查看已保存答复或免费手动调整。

## 项目状态

这是一个逐步构建中的个人工具。接口和页面仍可能调整，欢迎通过 Issue 提交使用反馈。
