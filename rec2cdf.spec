# -*- mode: python ; coding: utf-8 -*-

#import os
#from PyInstaller.utils.hooks import collect_data_files # this is very helpful


#bins = "c:\\users\\wilkinsmc\\documents\\venvs\\rec2cdf\\lib\\site-packages\\osgeo"

# these binary paths might be different on your installation. 
# modify as needed. 
# caveat emptor
#binaries = [
#    (os.path.join(bins,'geos_c.dll'), '.'),
#    ("c:\\users\\wilkinsmc\\documents\\venvs\\rec2cdf\\lib\\site-packages\\Shapely.libs", '.'),
#]


#paths = [
#    os.getcwd(),
#    os.path.join(os.getcwd(), 'bin'),
#    bins,
#    "c:\\users\\wilkinsmc\\documents\\venvs\\rec2cdf\\lib\\site-packages\\Shapely.libs"
#]


#hidden_imports = [
#    'ctypes',
#    'ctypes.util',
#    'fiona',
#    'gdal',
#    'geos',
#    'shapely',
#    'shapely.geometry',
#    'pyproj',
#    'rtree.index',
#    'geopandas.datasets',
#    'pytest',
#    'pandas._libs.tslibs.timedeltas',
#]

from PyInstaller.utils.hooks import copy_metadata
tzdatas = copy_metadata("pytz")

block_cipher = None

a = Analysis(['bin\\rec2cdfgui.pyw'],
             pathex=[],
             binaries=[],
             datas=[('bin/rec2cdf.py', '.'), ('bin/smap.py', '.'), ('bin/attr_info.jinja', '.'), ('bin/map.html', '.'), ('bin/version.txt', '.'), ('bin/help.html', '.'), ('etc/rec2cdf.ico', '.'), tzdatas[0]],
             hiddenimports=['pytz', 'cftime', 'netCDF4', 'telnetlib', 'tenacity', 'fiona'],
             hookspath=[],
             hooksconfig={},
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)

exe = EXE(pyz,
          a.scripts, 
          [],
          exclude_binaries=True,
          name='rec2cdf',
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          console=False,
          disable_windowed_traceback=False,
          target_arch=None,
          codesign_identity=None,
          entitlements_file=None , icon='etc\\rec2cdf.ico')
coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas, 
               strip=False,
               upx=True,
               upx_exclude=[],
               name='rec2cdf')
