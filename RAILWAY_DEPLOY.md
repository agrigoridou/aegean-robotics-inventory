# Aegean Robotics Smart Inventory 4.2 — Railway Pilot

Αυτό είναι **πιλοτικό πακέτο προσαρμοσμένο για Railway**, ΟΧΙ επαληθευμένη production εγκατάσταση.
Δεν έχει ανέβει σε cloud ούτε έχει πραγματοποιηθεί ανεξάρτητος έλεγχος ασφαλείας.

## 1. GitHub

Δημιούργησε **private** repository (π.χ. `aegean-robotics-inventory`) και ανέβασε **τα αρχεία αυτού του φακέλου στη ρίζα του repository** (το `server.py` πρέπει να βρίσκεται στη ρίζα). Ποτέ μην ανεβάζεις `.env`, `inventory.db` ή φωτογραφίες πραγματικών χρηστών στο GitHub.

## 2. Railway

1. https://railway.com → New Project → Deploy from GitHub Repo → διάλεξε το private repo.
2. Railway service → Settings → Deploy → Start Command: `sh start_railway.sh` (αν δεν αναγνωριστεί αυτόματα).
3. Service → **Add Volume**, mount path: `/data` (ΠΡΙΝ χρησιμοποιηθεί πραγματικά η εφαρμογή).
4. Variables:
   - `INVENTORY_DATA_DIR=/data`
   - `AUTH_SECURE_COOKIE=1` (χρησιμοποίησε την εφαρμογή μόνο μέσω HTTPS)
   - `GEMINI_API_KEY=` το δικό σου κλειδί, **μόνο στο Railway Variables**.
   - `GEMINI_MODEL=` μοντέλο διαθέσιμο για το κλειδί σου, εφόσον χρειάζεται αλλαγή.
5. Deploy/redeploy. **ΜΗ δημιουργήσεις δημόσιο domain ακόμη.** Ο server αρχικοποιεί `/data/inventory.db` στον πρώτο κύκλο εκκίνησης.
6. Άνοιξε Railway CLI από τον δικό σου υπολογιστή, κάνε login/link στο project, και μετά `railway ssh`. Μέσα στο shell του Railway τρέξε `python auth.py init-admin --db /data/inventory.db`. Διάλεξε νέο μοναδικό κωδικό >=12 χαρακτήρες. Έλεγξε ότι υπάρχει ενεργός διαχειριστής με `python auth.py status --db /data/inventory.db`.
7. Εφόσον ολοκληρωθούν οι έλεγχοι ασφαλείας, Service → Settings → Networking → **Generate Domain**. Μετά όρισε στο Railway Variables `PUBLIC_BASE_URL=https://<ακριβές-domain-που-δόθηκε>` και κάνε redeploy. Άνοιξε `https://<domain>/login` και δοκίμασε σύνδεση, εξαγωγή xlsx, αποθήκευση φωτογραφίας και restart για να επιβεβαιώσεις τη διατήρηση.
8. WordPress Admin → Εμφάνιση → Μενού (ή Editor/Navigation) → Προσαρμοσμένος σύνδεσμος προς το URL, όνομα «Lab Inventory».

## Χρήσιμα

- Η εφαρμογή δεν έχει ενσωμάτωση login με WordPress. Είναι ανεξάρτητοι λογαριασμοί.
- Το WordPress Admin δεν εγκαθιστά Python backend στον server του Πανεπιστημίου.
- Το `/data` περιέχει τη ζωντανή SQLite βάση και τις φωτογραφίες. **Ρύθμισε backups** ανεξάρτητα από το Excel export (το Excel δεν υποκαθιστά ολόκληρο backup της βάσης).
- Για πραγματική λειτουργία με μέλη εργαστηρίου, χρειάζονται έλεγχος ασφάλειας, σωστή ρύθμιση hosting, προστασία δεδομένων (όνομα δανειζόμενων, φωτογραφίες), κόστος/όρια Gemini και συμφωνία με την πολιτική του Πανεπιστημίου.
- Η εφαρμογή χρησιμοποιεί τον ενσωματωμένο HTTP server της Python (`ThreadingHTTPServer`). Δεν είναι ελεγμένη για production με άμεση έκθεση στο Internet. Συνιστάται hardening ή μετάβαση σε production-grade web server/framework και προστασία πρόσβασης.
- Η υπηρεσία ενδέχεται να έχει χρέωση. Ο δωρεάν χώρος μπορεί να μην αρκεί για φωτογραφίες/συνεχόμενη λειτουργία.
- Μη χρησιμοποιήσεις `RUN_ME_WINDOWS.bat` στο Railway.

## Τοπικός έλεγχος Linux/Mac

```
python -m pip install -r requirements.txt
INVENTORY_DATA_DIR=/tmp/aegean-inventory-pilot python server.py --host 127.0.0.1 --port 8989
```

Πρώτα δημιούργησε admin στη βάση του pilot:

```
INVENTORY_DATA_DIR=/tmp/aegean-inventory-pilot python auth.py init-admin --db /tmp/aegean-inventory-pilot/inventory.db
```
