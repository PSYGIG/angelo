# -*- mode: python -*-

block_cipher = None

import os
import importlib

package_imports = [['supervisor', ['version.txt']]]

datas = []
for package, files in package_imports:
    proot = os.path.dirname(importlib.import_module(package).__file__)
    datas.extend((os.path.join(proot, f), package) for f in files)


a = Analysis(['bin/angelo'],
             pathex=['.'],
             binaries=[],
             datas=datas,
             hiddenimports=[],
             hookspath=[],
             runtime_hooks=[],
             excludes=['pycrypto', 'PyInstaller'],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)
exe = EXE(pyz,
          a.scripts,
          a.binaries,
          a.zipfiles,
          a.datas,
          [
            (
                'angelo/config/config_schema_v1.0.json',
                'angelo/config/config_schema_v1.0.json',
                'DATA'
            ),
          ],
          name='angelo',
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          runtime_tmpdir=None,
          console=True )
