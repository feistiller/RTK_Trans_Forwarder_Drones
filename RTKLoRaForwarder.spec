# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from pathlib import Path

block_cipher = None

# 将项目根目录加入搜索路径，增强可移植性
# 注意：在某些 PyInstaller 版本/环境中，执行 spec 时 `__file__` 可能未定义。
# 因此这里使用 `os.getcwd()` 作为构建时的工作目录路径。
pathex = [os.getcwd()]

# 组装额外的 Tcl/Tk 运行时（conda/Windows 常见需要）
extra_binaries = []
extra_datas = []

prefixes = []
for cand in [os.environ.get('CONDA_PREFIX'), sys.prefix, sys.base_prefix]:
    if cand and os.path.isdir(cand):
        prefixes.append(cand)

for base in prefixes:
    lib_bin = Path(base) / 'Library' / 'bin'
    for dll in ('tcl86t.dll', 'tk86t.dll', 'tcl86.dll', 'tk86.dll'):
        p = lib_bin / dll
        if p.exists():
            extra_binaries.append((str(p), '.'))

    # 尝试收集 tcl/tk 数据目录（不同安装布局）
    for rel in [
        ('Library', 'lib', 'tcl8.6'),
        ('Library', 'lib', 'tk8.6'),
        ('tcl', 'tcl8.6'),
        ('tcl', 'tk8.6'),
    ]:
        d = Path(base).joinpath(*rel)
        if d.is_dir():
            dest = 'tcl' if d.name.startswith('tcl') else 'tk'
            extra_datas.append((str(d), dest))


a = Analysis(
    ['run_app.py'],
    pathex=pathex,
    binaries=extra_binaries,
    datas=[('README.md', '.'), ('config.json', '.')] + extra_datas,
    hiddenimports=[
        'serial',
        'serial.tools.list_ports',
        'tkinter',
        'tkinter.ttk',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# one-file 模式：产出单一 EXE；如需 one-folder，请参考下方注释的 COLLECT 版本
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name='RTKLoRaForwarder',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # GUI 程序，无控制台窗口
    disable_windowed_traceback=False,
    target_arch=None,
    uac_admin=False,
    uac_uiaccess=False,
    # icon='app.ico',  # 如有图标，可解除注释并填入路径
)

# 如需 one-folder（便于调试），请改用以下 COLLECT（并将上面的 EXE exclude_binaries=True，见 PyInstaller 默认生成模板）：
# exe = EXE(
#     pyz,
#     a.scripts,
#     [],
#     exclude_binaries=True,
#     name='RTKLoRaForwarder',
#     debug=False,
#     bootloader_ignore_signals=False,
#     strip=False,
#     upx=True,
#     console=False,
# )
# coll = COLLECT(
#     exe,
#     a.binaries,
#     a.zipfiles,
#     a.datas,
#     strip=False,
#     upx=True,
#     upx_exclude=[],
#     name='RTKLoRaForwarder'
# )
