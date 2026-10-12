"""Offline photo-example matching; score means visual resemblance, NOT model certainty."""
from __future__ import annotations
import base64, io, json, math, os, re
from pathlib import Path
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_BYTES=5_000_000
Image.MAX_IMAGE_PIXELS=14_000_000

def prepare_image(data_url: str):
    if not isinstance(data_url,str) or not re.match(r'^data:image/(?:jpeg|jpg|png|webp);base64,',data_url,re.I):
        raise ValueError('Δώσε φωτογραφία JPEG, PNG ή WebP.')
    encoded=data_url.split(',',1)[1]
    if len(encoded)>MAX_BYTES*4//3+64:raise ValueError('Η φωτογραφία είναι πολύ μεγάλη (όριο 5 MB).')
    try:
        data=base64.b64decode(encoded,validate=True)
        if len(data)>MAX_BYTES:raise ValueError('Η φωτογραφία ξεπερνά τα 5 MB.')
        pic=Image.open(io.BytesIO(data))
        pic.load()
        if pic.format not in ('JPEG','PNG','WEBP'):raise ValueError('Μη υποστηριζόμενη μορφή.')
        pic=ImageOps.exif_transpose(pic).convert('RGB')
    except (UnidentifiedImageError,OSError,ValueError) as ex:
        raise ValueError('Δεν ήταν δυνατή η ανάγνωση της φωτογραφίας: '+str(ex))
    pic.thumbnail((1200,1200),Image.Resampling.LANCZOS)
    output=io.BytesIO();pic.save(output,format='JPEG',quality=84,optimize=True)
    return output.getvalue(),feature(pic)

def bit_hash(values):
    m=sum(values)/len(values)
    return sum((v>=m)<<i for i,v in enumerate(values))

def feature(image):
    gray=ImageOps.grayscale(image)
    gray8=gray.resize((16,16),Image.Resampling.LANCZOS)
    ah=bit_hash(list(gray8.getdata()))
    gray9=gray.resize((9,8),Image.Resampling.LANCZOS)
    a=list(gray9.getdata());dh=sum((a[y*9+x]>a[y*9+x+1])<<(y*8+x) for y in range(8) for x in range(8))
    small=image.resize((80,80),Image.Resampling.BILINEAR)
    hist=[0]*64
    for r,g,b in small.getdata():hist[(r//64)*16+(g//64)*4+b//64]+=1
    hist=[x/6400 for x in hist]
    return {'a':str(ah),'d':str(dh),'h':hist}

def resemblance(left,right):
    try:
        d1=(int(left['a'])^int(right['a'])).bit_count()/256
        d2=(int(left['d'])^int(right['d'])).bit_count()/64
        d3=sum(abs(a-b) for a,b in zip(left['h'],right['h']))/2
    except (ValueError,TypeError,KeyError):return 0.
    # Same photo/near-identical views rank highly; different orientations may score poorly.
    score=1-(.30*d1+.43*d2+.27*d3)
    return round(max(0,min(1,score))*100,1)

