import json
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from openpyxl import Workbook

from cost_data.config import get_settings
from cost_data.main import app


def golden_workbook() -> bytes:
    workbook = Workbook()
    bill = workbook.active
    bill.title = "分部分项清单计价表"
    bill.append(["项目编码", "项目名称", "项目特征描述", "计量单位", "工程量", "综合单价", "合价"])
    bill.append(["010502001001", "现浇混凝土矩形柱", "混凝土强度等级 C30", "m3", 100, 685.25, 68525])
    bill.append(["010515001001", "现浇构件钢筋", "HRB400", "t", 12.5, 5320, 66500])
    resources = workbook.create_sheet("工料机汇总表")
    resources.append(["材料编码", "材料名称", "规格型号", "单位", "数量", "市场价", "金额"])
    resources.append(["MAT001", "商品混凝土", "C30", "m3", 105, 485, 50925])
    resources.append(["MAT002", "钢筋", "HRB400", "kg", 12500, 4.5, 56250])
    analysis = workbook.create_sheet("综合单价分析表")
    analysis.append(["项目编码", "项目名称", "费用类别", "金额"])
    analysis.append(["010502001001", "人工费", "人工", 65.25])
    analysis.append(["010502001001", "材料费", "材料", 580])
    measures = workbook.create_sheet("措施项目表")
    measures.append(["费用名称", "金额"])
    measures.append(["安全文明施工费", 12000])
    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def metadata(name: str = "西安人工黄金样本") -> str:
    return json.dumps({"name": name, "region": "西安", "pricing_date": "2026-06", "specialty": "土建", "pricing_mode": "内地清单定额", "result_stage": "结算", "area": "1000"}, ensure_ascii=False)


def test_import_publish_search_match_metrics_backup() -> None:
    client = TestClient(app)
    token = client.get("/api/v1/health").json()["session_token"]
    headers = {"X-Cost-Data-Token": token}
    workbook = golden_workbook()
    response = client.post("/api/v1/imports", headers=headers, data={"metadata_json": metadata()}, files=[("files", ("黄金样本.xlsx", workbook, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))])
    assert response.status_code == 202, response.text
    job = response.json()
    current = client.get(f"/api/v1/imports/{job['id']}").json()
    assert current["status"] == "review"
    assert current["processed_files"] == 1
    issues = client.get(f"/api/v1/imports/{job['id']}/issues").json()
    assert not [issue for issue in issues if issue["severity"] == "error"]

    published = client.post(f"/api/v1/imports/{job['id']}/publish", headers=headers)
    assert published.status_code == 200, published.text
    version_id = published.json()["id"]
    found = client.get("/api/v1/cost-items/search", params={"query": "混凝土"})
    assert found.status_code == 200, found.text
    assert found.json()["total"] == 1
    item = found.json()["items"][0]
    assert item["unit_price"]["value"] == "685.25"
    assert item["source"]["file_name"] == "黄金样本.xlsx"
    assert len(item["components"]) == 2

    match = client.post("/api/v1/match-sessions", headers=headers, json={"name": "测试匹配", "items": [{"name": "现浇混凝土柱", "unit": "m3"}]})
    assert match.status_code == 201, match.text
    assert match.json()["results"][0]["candidates"][0]["total_score"] > 0
    metrics = client.get(f"/api/v1/metrics/projects/{version_id}").json()
    assert {metric["code"] for metric in metrics} == {"cost_per_area", "steel_per_area", "concrete_per_area"}

    backup_dir = get_settings().data_home / "test-backups"
    backup = client.post("/api/v1/backups", headers=headers, json={"target_directory": str(backup_dir), "kind": "manual"})
    assert backup.status_code == 201, backup.text
    assert Path(backup.json()["path"], "manifest.json").exists()

    duplicate = client.post("/api/v1/imports", headers=headers, data={"metadata_json": metadata(), "project_id": job["project_id"]}, files=[("files", ("黄金样本.xlsx", workbook, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))])
    assert duplicate.status_code == 409


def test_security_and_validation_contract() -> None:
    client = TestClient(app)
    denied = client.post("/api/v1/projects", json={})
    assert denied.status_code == 403
    response = client.post("/api/v1/projects", headers={"X-Cost-Data-Token": "test-session-token"}, json={})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
