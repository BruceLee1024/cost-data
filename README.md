# 工程造价数据库

面向个人工程造价师的 AI 驱动造价数据管理工具。

当前仓库已实现本地技术预览版。由于尚无真实广联达脱敏样本，不能标记为正式 V1。

- [产品需求文档 V0.1](docs/产品需求文档-V0.1.md)
- [技术架构调研与选型 V0.1](docs/技术架构调研与选型-V0.1.md)

## 本地运行

要求 Apple Silicon Mac、Python 3.13、uv、Node 22 和 pnpm 10。

```bash
make install
make dev
```

浏览器打开 `http://127.0.0.1:5173`。生产构建由 FastAPI 同源提供：

```bash
make build
cd backend && uv run python -m cost_data.launcher
```

业务数据默认位于 `~/Library/Application Support/cost-data/`。DeepSeek API Key 只保存到 macOS Keychain；不配置 AI 不影响导入、查询、匹配、指标和备份。

## 验证与打包

```bash
make test
./packaging/build-macos.sh
```

人工测试文件可运行 `backend/.venv/bin/python scripts/generate_sample.py` 生成，不包含客户数据。

## 当前状态

- 已完成首轮需求访谈
- 已明确第一版产品目标与核心边界
- 已完成第一轮技术架构调研与选型
- 已完成确定性核心闭环、DeepSeek 适配器、备份与 arm64 `onedir` 配置
- 待通过真实 Excel 样本校准解析器和完成正式 V1 准确率验收
