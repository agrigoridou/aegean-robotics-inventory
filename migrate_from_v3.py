"""Offline, opt-in migration from an older app directory.

Stop both old and new server first. Existing destination DB is NEVER overwritten.
"""
from pathlib import Path
import sqlite3,shutil,sys
ROOT=Path(__file__).resolve().parent
if len(sys.argv)!=2:
    sys.exit('Usage: python migrate_from_v3.py "C:\\path\\to\\previous\\app"')
old=Path(sys.argv[1]).expanduser().resolve()
src=old/'data'/'inventory.db'
new=ROOT/'data'/'inventory.db'
if not src.is_file():sys.exit('ERROR: No data/inventory.db in previous project directory.')
if new.exists():sys.exit('SAFETY: Current data/inventory.db already exists. Nothing copied. Back up / choose fresh installation directory.')
new.parent.mkdir(parents=True,exist_ok=True)
try:
    with sqlite3.connect(f'file:{src.as_posix()}?mode=ro',uri=True) as con_old,sqlite3.connect(str(new)) as con_new:
        con_old.backup(con_new)
    if (old/'data'/'photos').is_dir():shutil.copytree(old/'data'/'photos',ROOT/'data'/'photos',dirs_exist_ok=True)
    if (old/'.env').is_file() and not (ROOT/'.env').exists():shutil.copy2(old/'.env',ROOT/'.env')
except Exception:
    if new.exists():new.unlink()
    raise
print('SUCCESS: Existing inventory, photos and optional .env migrated. Run START_WINDOWS.bat.')
