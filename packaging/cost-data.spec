from pathlib import Path

root = Path(SPEC).resolve().parents[1]
frontend = root / "frontend" / "dist"

a = Analysis(
    [str(root / "backend" / "src" / "cost_data" / "launcher.py")],
    pathex=[str(root / "backend" / "src")],
    binaries=[],
    datas=[
        (str(frontend), "frontend/dist"),
        (str(root / "backend" / "alembic.ini"), "."),
        (str(root / "backend" / "migrations"), "migrations"),
    ],
    hiddenimports=["uvicorn.logging", "uvicorn.loops.auto", "uvicorn.protocols.http.auto", "uvicorn.protocols.websockets.auto", "uvicorn.lifespan.on"],
    excludes=["tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="cost-data", console=False, target_arch="arm64")
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="cost-data")
