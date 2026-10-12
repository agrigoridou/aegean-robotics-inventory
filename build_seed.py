"""One-time, reproducible extract of SUB.2 Inventory ONLY from original workbook."""
from artifact_tool import Blob, SpreadsheetFile
from datetime import datetime, timedelta
from collections import Counter
import json, re

SRC = '/mnt/data/Aegean Robotics Inventory.xlsx'
DEST = '/mnt/data/aegean-smart-inventory/data/seed_sub2.json'
wb = SpreadsheetFile.import_xlsx(Blob.load(SRC))
sheet = wb.worksheets.get_item('SUB.2 Inventory')
rows = sheet.get_range('A3:H350').values

RULES = [
    ('Υποβρύχια & Καλυψώ', ['kalypso','καλυψ','underwater','under water','thruster','truster','watertight','wetlink','subsea','oxygen','sonar','water pressure','marine','προπέλα','αδιάβροχ','υποβρύχ','enclosure dome','fiber glass']),
    ('Μπαταρίες & φόρτιση', ['battery','batteries','μπαταρ','lipo','charger','charging','balance charger','tattu','gens ace','bashing','king max','battery holders','pi juice','pijuice']),
    ('Κινητήρες & Servo', ['motor','servo','stepper','steper','μοτέρ','κινητήρ','motor drive','motord','τροχ','ρόδες','gear motor','φεετεch','feetech','dss','fr0115','mg90','mg995','gripper']),
    ('Κάμερες & οθόνες', ['camera','cammera','cam','kinect','lcd','screen','display','hdmi','matrix','οθόνη','led strip','leds','video','low light','light module']),
    ('Αισθητήρες', ['sensor','sensore','imu','mpu','lidar','rplidar','gps','ultrasonic','pressure','humidity','dht11','bitalino','bitaliano','gy-','bar pressure','rfid','bmx160']),
    ('Υπολογιστές & Μικροελεγκτές', ['arduino','raspberry','pico','tinker board','banana pi','micro:bit','microbit','esp','8266','olimex','lollin','pi4','pi5','pi 4','pi 5','rpi','motherboard','pc ', 'computer','laptop','microcontroller','adfruit qt py','adafruit qt py','col ai']),
    ('Εργαλεία & Ασφάλεια', ['solder','κολλητ','glue gun','πολυμετρο','multimeter','εργαλε','dremel','drill','κατσαβίδ','κατσαβιδ','τσίμπ','τσιμπ','πενσ','κοπτά','stripper','stripping','caliper','μέτρο','μάσκε','γυαλιά','screwdriver','drill press','precision','ηλεκτρικό κατσαβίδι']),
    ('Καλώδια & Συνδέσεις', ['cable','καλώδι','jumper','connector','βύσμα','βισμα','micro hdmi','ethernet','adapter','adaptor','fiber','uart','usb c','usb-c','usb power','ribbon','breadboard','proto board']),
    ('Τροφοδοσία & Ηλεκτρονικά', ['power','τροφοδο','voltage','volt','relay','ρελέ','mosfet','resistor','αντίστασ','capacitor','πυκνωτ','step down','dc-dc','shield','hat','driver','converter','diode','διακόπτ','switch','transistor','πλακέτ','potentiometer','ποντεσιο','module','hardware','fl-2','shunt','fuse','led','buzzer','buzzers','χρονόμετρο']),
    ('Δικτύωση & Επικοινωνίες', ['antenna','wifi','lora','network','ethernet','router','communication','επικοινων','modem','gps hat','rf ']),
    ('Αναλώσιμα & Μηχανικά', ['βίδ','παξιμάδ','spacer','o ring','φλάντζ','συγκόλλ','tape','ταινί','γράσο','βαζελίν','λιπαντ','μπογιά','adhesive','screw','nut','gear','γρανάζ','3d print','filament','filament','πλαστικ','κόλλα','silicone','threaded','σακουλάκι']),
]

def classify(name):
    normalized = str(name or '').casefold().strip()
    for cat,words in RULES:
        if any(word in normalized for word in words): return cat
    return 'Λοιπά'

def loc_code(raw):
    if raw is None or raw=='': return None
    if isinstance(raw,(int,float)):
        d=datetime(1899,12,30)+timedelta(days=int(raw))
        # Original Excel's d.m date format represents spatial indices, not calendar dates.
        if 1<=d.day<=31 and 1<=d.month<=12:
            return f'C{d.day:02d}-S{d.month:02d}'
    m=re.fullmatch(r'\s*(\d{1,2})[.\-/](\d{1,2})\s*',str(raw))
    if m:return f'C{int(m.group(1)):02d}-S{int(m.group(2)):02d}'
    return None

items=[]
for index,values in enumerate(rows,start=3):
    name,_,qty,raw,notes,_,_,_=values
    if not isinstance(name,str) or not name.strip() or name.strip().upper() == 'MOTORS':continue
    qty_clean = int(qty) if isinstance(qty,(int,float)) and not isinstance(qty,bool) and qty>=0 else None
    items.append({
        'sku':f'AR-{index:04d}', 'source_row':index,'name':name.strip(),
        'category':classify(name),'quantity':qty_clean,'quantity_unknown':qty_clean is None,
        'location_id':loc_code(raw), 'notes':str(notes or '').strip(),
    })

locations=[]
for code in sorted({x['location_id'] for x in items if x['location_id']}):
    m=re.fullmatch(r'C(\d+)-S(\d+)',code)
    cab,shelf=map(int,m.groups())
    locations.append({'id':code,'cabinet':cab,'slot':shelf,'label':f'Ντουλάπα {cab} · Θέση {shelf}'})

with open(DEST,'w',encoding='utf-8') as f:json.dump({'source_sheet':'SUB.2 Inventory','items':items,'locations':locations},f,ensure_ascii=False,indent=2)
print('items:',len(items),'locations:',len(locations),'known stock:',sum(x['quantity'] or 0 for x in items),'quantity unknown:',sum(x['quantity_unknown'] for x in items))
print('categories',Counter(x['category'] for x in items))
print('no location:',sum(x['location_id'] is None for x in items))
