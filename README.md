# 工程造价数据库管理平台

面向个人工程造价师的 AI 驱动、本地优先的工程造价数据管理与清单编制工作台。

项目当前为技术预览版（V0.1）：已覆盖从历史 Excel 数据导入、清洗治理、检索比对到清单编制辅助的核心闭环；由于尚未使用真实脱敏广联达样本完成准确率验收，暂不标记为正式 V1。

## 核心能力

- **历史数据入库**：导入 Excel，识别工作表与字段映射，保留源文件、来源行号与导入问题。
- **数据治理**：项目画像、版本发布、口径与可比性提示、质量报告、单位换算及规范化规则。
- **多库检索**：在项目库、指标库、资源库、定额库中搜索，并支持跨项目工作台检索与来源追溯。
- **比对与分析**：工程量清单比对、候选匹配、项目指标计算和同类项目基准参考。
- **清单编制辅助**：维护清单记录，导出参考价格与导入质量报告。
- **可控 AI 增强**：支持 DeepSeek 的自然语言检索、候选审阅和导入映射建议；API Key 存于 macOS Keychain，未配置 AI 也不影响确定性功能。
- **本地数据保护**：业务数据默认保存在本机，支持自动/手动备份与恢复。

## 技术栈

- 后端：Python 3.13、FastAPI、SQLAlchemy、SQLite
- 前端：React 19、TypeScript、Vite
- 数据处理：openpyxl
- 打包：PyInstaller（macOS arm64）

## 本地运行

要求 Apple Silicon Mac、Python 3.13、[uv](https://docs.astral.sh/uv/)、Node.js 22 和 pnpm 10。

```bash
make install
make dev
```

打开 `http://127.0.0.1:5173`。生产构建由 FastAPI 同源提供：

```bash
make build
cd backend && uv run python -m cost_data.launcher
```

业务数据默认位于 `~/Library/Application Support/cost-data/`。

## 验证与打包

```bash
make test
./packaging/build-macos.sh
```

人工测试可使用 `backend/.venv/bin/python scripts/generate_sample.py` 生成样本文件；仓库不包含客户数据。

## 文档

- [产品需求文档 V0.1](docs/产品需求文档-V0.1.md)
- [技术架构调研与选型 V0.1](docs/技术架构调研与选型-V0.1.md)
- [数据字典与解析规则 V0.1](docs/数据字典与解析规则-V0.1.md)
- [金样本验收台账模板 V1](docs/金样本验收台账模板-V1.md)
- [业务审视报告：从历史数据库到清单编制工作台 V0.1](docs/业务审视报告-从历史数据库到清单编制工作台-V0.1.md)

## 当前状态

- 已完成历史项目数据治理、多库检索与清单编制工作台的技术预览闭环。
- 待以真实 Excel 脱敏样本校准解析器，并完成正式 V1 的准确率验收。
