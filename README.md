# AI Market Insight Copilot

**AI市场情报与产品营销助手**：把公开、授权或模拟的工业品资料转换为带证据的竞品对比、产品价值说明与销售问答，再由人审核、导出。独立作品集，无企业官方身份或认可暗示。

## 安装与启动

需要 Python 3.11+（交付环境验证 Python 3.12.10）。在本项目目录执行：

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m streamlit run app.py --server.address 127.0.0.1
```

macOS/Linux 激活命令：`source .venv/bin/activate`。打开 `http://127.0.0.1:8501`。如在本次交付电脑上运行，可直接双击 `start-local.cmd` 使用已经准备好的工作区 Python；此脚本仅用于当前目录布局。

`requirements.txt` 固定直接依赖；`requirements-lock.txt` 保存本次 Windows/Python 3.12.10 测试环境的全部依赖版本。在相同Python版本复现可使用 `python -m pip install -r requirements-lock.txt`。其他Python版本使用直接依赖文件，由pip选择兼容的间接依赖。

## 无密钥演示

点击侧栏 **加载演示项目** → 信息提取页点击 **开始分析所选资料** → 对比页确认口径 → 生成价值说明与问答 → 审核与导出。

所有样例均为模拟数据，含三家虚构供应商、冲突补充说明、客户需求及行业简报。样例中 NorthMist 使用英文标签。演示规则只识别 `字段：值 | 条件：...`（或对应英文标签）；不声称理解任意自由文本，也不声称是实时模型生成。可上传同格式 TXT/DOCX/PDF，CSV 每行保留表头和值用于预览。任意布局、多列产品表格提取建议使用模型模式并逐项检查。`DEMO.md` 是三分钟演示脚本。

## 模型模式

```powershell
$env:OPENAI_API_KEY = '填写你的密钥'
$env:OPENAI_MODEL = '填写有权限且支持Responses结构化输出的模型名称'
python -m streamlit run app.py --server.address 127.0.0.1
```

`.env.example` 仅是环境变量模板，应用不会自动读取 `.env`。密钥只从环境变量读取；不进入数据库、缓存键或日志。模型名不在业务逻辑写死。模型提取及营销文案调用 OpenAI；竞品表始终由透明规则生成。通过 `Provider` 协议可替换实现。

使用官方 [Structured Outputs 文档](https://developers.openai.com/api/docs/guides/structured-outputs) 的 Python `client.responses.parse(..., text_format=PydanticModel)`，采用 Responses API，`store=False`。本地已检查 SDK 方法签名；未配置真实API时不声称验证了账号访问、计费或模型效果。

只有点击“开始分析所选资料”或“生成产品价值说明和销售问答”才调用。界面会提示发送范围；提取阶段发送选中文字和来源元数据，文案阶段发送事实（含摘录）与客户输入。每次40,000字符、6,000输出token、60秒、无自动重试，每项目最多20次调用（失败也计数）。超限拒绝，不截断、不分块，避免隐含费用和定位丢失。失败不切换演示模式，旧工作保留。

## 数据与隐私

默认保存至 `data/copilot.sqlite3`，SQLite存储项目、来源元数据、定位文本、上传二进制、生成批次和审核记录。可用 `COPILOT_DATA_DIR` 指定目录。删除单份资料移除当前来源及二进制，旧批次保留证据快照和“需复核”状态用于审计；需要彻底清除其历史内容时删除整个项目。界面删除项目会清除该项目记录与文件，不影响其他项目。备份是复制停止运行后的SQLite文件；手工备份需自行管理。

本地演示不外发内容；模型模式才发送到服务商。`store=False` 不等同于服务商零保留承诺；资料发送需符合授权。应用不打印完整文本或API错误响应。上传内容不执行；URL只是元数据，无抓取。默认仅监听127.0.0.1，不支持多用户，勿直接开放公网。

## 功能范围与限制

- PDF、DOCX、UTF-8 TXT/CSV；10MB、PDF 200页、本地文本120,000字符上限。PDF实际页序、DOCX段落/表行、TXT非空行的原始段落序号、CSV逻辑行号。不虚构页码。
- 不做OCR；扫描页明确提示未处理，纯扫描PDF拒绝。图片、文本框、页眉页脚、嵌入对象不在覆盖范围。复杂PDF阅读顺序需人复核。
- 来源事实、推断、营销建议、待确认问题分开；“引用定位有效”只检查ID/定位及空白规范化后的精确子串，不证明语义正确。
- 仅W/kW自动换算，不排序、不选最佳；多值全部保留并提示冲突或口径差异；缺失不等于不具备。
- 确认需要人工核对语义。编辑先回到待审核，原文不覆盖；再次提交确认才能批准。无证据内容不能作为已确认事实导出。当前版本不自动判断人工新文字是否被原文支持，责任明确交给审核人。
- 资料/范围/比较口径/文案条件变化使结果失效。不同批次保留；全部导出含历史批次，按批次及需复核状态区分。仅确认导出排除失效批次，证据上下文保留原状态；不输出旧修改草稿。
- 导出CSV含UTF-8 BOM并防公式注入；JSON包含结构、证据与审核记录；Markdown含范围、模式、日期、来源、原文、待确认项及状态。
- 不提供账号权限、爬虫、CRM、邮件、自动发布、自动政策更新、向量库、复杂Agent和PPTX。

## 架构

`app.py`：五步Streamlit工作台；`copilot/models.py`：Pydantic结构；`ingest.py`：格式验证和文字定位；`store.py`：SQLite持久化；`engine.py`：确定性提取、比较、文案、引用与审核业务；`provider.py`：可替换模型适配；`exporting.py`：三种导出；`demo.py` + `samples/`：演示项目。

缓存键包含资料哈希、项目修订、输入条件、提示词版本、模式、模型及调用配置。批次保存缓存键；同样提取/文案不重复调用。审核历史包含修改前后、备注、时间、来源与生成批次。

## 测试与评估

```powershell
python -m pytest -q
python evaluate.py
# 主动发送模拟评估集至真实API，最多两次调用；不会自动执行
python evaluate.py --real --output evaluation/real-results.json
```

`evaluation/labels.json` 是人工标注的模拟字段基准。`demo-results.json` 只描述规则模式；不能当作模型准确率。字段精确匹配指标分母为5个指定字段，不代表所有字段召回或精度。引用定位有效率单独报告；缺失/不可比/冲突、无依据成本措辞、恶意指令、修改状态及端到端导出另列。无依据主张检查是有限措辞检查，不能替代人工语义评估。真实API未执行时不生成伪造分数。

人工效率测量请填写 `evaluation/human-efficiency-template.csv`；尚无实测数据，不宣称提效百分比。

## 已知问题与下一步

当前适合单人本地作品演示，SQLite项目快照设计易审计但不适合多人并发。复杂文档结构、表格跨页及人工修改后的语义支持需要审核人判断。模型可能漏提或误解资料；程序只严格验证引用位置，不能保证结论。下一步优先增加真实授权资料评估、细粒度证据支持标注与文档布局解析；不以未经测量的数据宣传商业效果。
