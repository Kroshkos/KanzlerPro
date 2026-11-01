# -*- mode: python ; coding: utf-8 -*-
# Spec для сборки дистрибутива PyInstaller (BACKLOG D-3).
# Сборка из корня репозитория:  pyinstaller kanzler.spec
# Результат: dist/kanzler_pro/  (запускать kanzler_pro / kanzler_pro.exe)

block_cipher = None

a = Analysis(
    ["main.py"],
    pathex=["app"],  # модули приложения лежат в app/ и импортируются плоско
    binaries=[],
    datas=[("app", "app")],  # на случай ленивой загрузки ресурсов из app/
    hiddenimports=[
        "flet_web",  # flet определяет платформу динамически
        "openpyxl",
        "docx",
        "dotenv",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib"],
    win_no_prefer_redirects=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="kanzler_pro",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # GUI-приложение: консоль не показываем; для диагностики
                     # запускайте собранное приложение через `kanzler_pro.exe`
                     # с переменной KANZLER_DEBUG=1
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="kanzler_pro",
)
