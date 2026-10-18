# 文献发现：调研与分阶段实现

调研日期：2026-10-18。第一阶段从一篇已导入论文寻找库外文献；第二阶段增加 2–5 篇联合推荐、研究问题和已存检索管理；第三阶段增加勾选并导出 RIS、BibTeX、Markdown。不包含关系图或 Zotero 写入。

| 项目 | 核对内容 | 本项目采用方式 |
| --- | --- | --- |
| [Local Citation Network](https://github.com/LocalCitationNetwork/LocalCitationNetwork.github.io) | README 与 GPL-3.0 LICENSE；种子论文、参考文献和后续引用网络 | 参考三种关系的组织方式，未复制源码 |
| [semanticscholar](https://github.com/danielnsilva/semanticscholar) | README、MIT LICENSE、`get_recommended_papers` 与多篇正反例推荐接口 | 核对 Semantic Scholar API 能力；独立编写标准库 HTTP 适配器，未引入或复制 SDK |
| [PyAlex](https://github.com/J535D165/pyalex) | README、MIT LICENSE；DOI 查询、`search.semantic`、引用关系和 Key 配置 | 核对 OpenAlex API 用法；独立编写 HTTP 适配器，未引入或复制 SDK |
| [Zotero Research Assistant](https://github.com/qiobn/zotero-research-assistant) | README、MIT LICENSE、`research_core/tools/find_related.py` | 参考多源候选合并、库内标记及匹配失败时不虚构结果的流程；未安装完整 RAG/MCP 系统 |
| [Inciteful Zotero Plugin](https://github.com/inciteful-xyz/inciteful-zotero-plugin) | README、AGPL-3.0 LICENSE；从单篇/集合发起图谱搜索 | 参考入口设计，未复制插件代码 |

核对时的上游提交：Local Citation Network `6a21efc4b946b3ec098bb29e7d039731848e93a6`；semanticscholar `6041eed87ea0e9ca59aa8805ddcccffd02cfdc74`；PyAlex `875c708cbb6e449feebc46d2a7a26af8ed8b2fdd`；Zotero Research Assistant `8bebcc2b072ea243d43c7decd49fcf08ba4f7d15`；Inciteful 插件 `694c68b26bfb9cbf8cdf98a69134dbfe53d37fe8`。

## 实现范围与依据

- OpenAlex：DOI 精确定位；语义相似检索不可用时降级标题关键词检索并标明；部分参考文献与近期被引文献。
- Semantic Scholar：DOI/arXiv 定位、推荐 API、参考文献与被引文献。推荐池默认偏近期，不能等同于全学科全历史覆盖。
- 不调用大模型，不上传 PDF；按需向学术服务发送标识符、标题和摘要。检索服务独立于模型配置。
- 首次打开只读取本电脑缓存；用户点开始查找/刷新才联网。每源每类最多取 20 条，OpenAlex 参考文献先取原记录的前 30 个标识符；合并后展示最多 20 篇，并为每类保留候选。此范围并非完整引文列表或系统综述检索。
- 同 DOI 合并证据；冲突 DOI 不按相同标题合并。无 DOI 的标题匹配要求长标题一致、年份一致并有共同作者，否则请用户核对候选。确认候选后只查询该数据源，后续刷新复用该确认。
- 排序以数据源名次的倒数融合，兼顾三类关系；不以被引次数、影响因子或虚构的相关性百分比作为排序依据。推荐依据仅描述 API 关系，不评价未读全文。
- 搜索缓存保存在 `data/discovery/`，Key 保存在 `data/discovery-settings.json`，均不进 Git；读取缓存时重新核对库内状态。文献信息变化会提示过期，不自动发起刷新；无可用结果的失败刷新保留旧结果。
- 通过已有请求取消机制中止两个检索工作线程；停止/离开页面时发送取消请求，取消成功后不继续请求或覆盖缓存。已经完成的请求仍会计入服务方额度。

## 服务规则与实测边界

第三阶段使用标准书目格式独立实现缓存导出，不增加生产依赖。单篇旧缓存读取时补充与联合检索一致的稳定结果编号；服务端仅允许导出指定已存结果中的已选编号，不会接收浏览器编造的论文元数据，不触发查询。RIS/BibTeX 使用通用类型，保留已有作者姓名，不推断出版类型或缺失字段。Markdown 记录研究问题和关联依据，并提供手写阅读模板。选择仅在当前页面保留，跨筛选显示隐藏数量，不感兴趣项自动移除；下载不会自动导入 Zotero。

导出验证使用独立测试目录中的 rispy 0.10.0、bibtexparser 1.4.3 解析真实浏览器下载文件，检查篇数、DOI、完整作者、中文和特殊符号；它们不随项目分发，也不是运行依赖。测试未向个人 Zotero 库实际导入记录。

第二阶段复用上述公开接口：Semantic Scholar 多篇正例推荐使用 JSON POST `positivePaperIds`；研究问题通过 OpenAlex 语义检索（失败后明确降级为关键词）和 Semantic Scholar 搜索检索。问题结果与每篇独立关联结果保守去重，不把联合模型推荐虚构成与每篇均有关联。中文专业词使用本电脑术语表和用户研究方向的同义词展开，支持显式英文检索词覆盖，不调用 LLM。

每组最多展示 60 篇候选，研究问题命中、字面词命中、独立关联篇数和倒数排名按序排序，不保证学术相关性或完整性。筛选依赖数据源的年份、Review/type 和开放获取元数据，未知字段不通过严格筛选；旧单篇缓存未包含这些字段时需主动更新。组记录及可恢复的反馈保存在 `data/discovery/groups/`，组 ID 与种子选择顺序无关；仅浏览和筛选不联网。每次检索最多两个种子工作线程，各自最多两个来源；复用已有单篇缓存。取消上下文传递到每个线程，写入前核对取消状态。

API 官方入口：[OpenAlex 文档](https://docs.openalex.org/)、[Semantic Scholar API](https://api.semanticscholar.org/api-docs/)。OpenAlex 客户端 README 与其 GitHub 文档的部分鉴权/额度说明存在版本差异，不硬编码免费额度承诺。网页可保存独立 Key，按实际 HTTP 401/403/429 提示处理，不自动无限重试。

无 Key 联网抽查：以 DOI `10.1051/0004-6361/201935251`（SPHERE 仪器论文）准确定位 OpenAlex 记录，返回 20 条合并候选；语义检索不可用时关键词降级有效；Semantic Scholar 当次返回限流。只证明当次公共接口和该论文可用，不保证所有论文均收录，也不证明所有推荐都适合用户的研究问题。测试缓存使用临时目录，不写入个人文献或笔记。

第二阶段无 Key 联网抽查：结合上述 SPHERE 论文与 `10.1073/pnas.1304215111`（Gemini Planet Imager 首光），使用 `coronagraph wavefront control` 研究问题检索，OpenAlex 准确定位两篇论文并返回合并后的 60 篇候选，含来源提供的年份与开放获取元数据；Semantic Scholar 当次限流，因此未声称其真实多篇推荐成功。其 JSON POST 格式、多个正例与独立关联计数通过模拟接口验证。临时目录中的测试数据不进入个人检索记录。
