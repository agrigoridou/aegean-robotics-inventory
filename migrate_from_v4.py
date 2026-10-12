"""One-time migration from a STOPPED 4.0 / 4.0.1 installation.
Never replaces the target DB. Uses sqlite3's consistent backup operation.
"""
from pathlib import Path
import sqlite3
import shutil
import sys

ROOT=Path(__file__).resolve().parent

def main():
    print('IMPORT 4.0/4.0.1 -> 4.2 LOGIN. Κλείσε πρώτα και τις δύο εφαρμογές.')
    old=Path(input('Πλήρης διαδρομή ΠΑΛΙΟΥ φακέλου (που περιέχει server.py): ').strip().strip('"')).resolve()
    if old==ROOT or not (old/'server.py').is_file():
        print('Λανθασμένος φάκελος. Επίλεξε τον ΠΑΛΙΟ φάκελο της εφαρμογής.');return 1
    source=old/'data'/'inventory.db'
    target=ROOT/'data'/'inventory.db'
    if not source.is_file():print('Δεν βρέθηκε παλιά βάση δεδομένων:',source);return 1
    if target.exists():
        print('Η νέα βάση υπάρχει ήδη. Δεν θα αντικατασταθεί ούτε θα συγχωνευτεί.')
        print('Αν έχεις ήδη χρησιμοποιήσει τη νέα έκδοση, κράτησε αντίγραφα και ζήτησε ελεγχόμενη συγχώνευση.')
        return 1
    with sqlite3.connect(f'file:{source}?mode=ro',uri=True) as con:
        if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='items'").fetchone():
            print('Η επιλεγμένη βάση δεν περιέχει inventory items.');return 1
    confirm=input('Εισαγωγή παλιάς βάσης και φωτογραφιών στη νέα εγκατάσταση; γράψε YES: ').strip()
    if confirm!='YES':print('Ακυρώθηκε.');return 1
    target.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(f'file:{source}?mode=ro',uri=True) as old_con,sqlite3.connect(target) as new_con:
        old_con.backup(new_con)
    photos=old/'data'/'photos'
    if photos.is_dir():
        shutil.copytree(photos,ROOT/'data'/'photos',dirs_exist_ok=True)
    env=old/'.env'
    if env.is_file() and not (ROOT/'.env').exists():
        shutil.copy2(env,ROOT/'.env')
    print('Η μεταφορά ολοκληρώθηκε. Τώρα τρέξε RUN_ME_WINDOWS.bat και δημιούργησε τον πρώτο Administrator.')
    return 0

if __name__=='__main__':sys.exit(main())
