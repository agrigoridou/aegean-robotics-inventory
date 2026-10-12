"""Dependency-free Excel 2007+ (.xlsx) snapshot writer. Does not edit source workbook.

Outputs a conventional OOXML file with shared styles, auto-filter, freeze panes,
fixed column widths and data type safety. Generated from *live SQLite* when requested.
"""
from __future__ import annotations
import io, re, zipfile
from datetime import datetime, date
from xml.sax.saxutils import escape

EXCEL_MAX_TEXT=32767
INVALID_XML=re.compile(r'[\x00-\x08\x0b-\x0c\x0e-\x1f]')
DANGEROUS_PREFIX=('=', '+', '-', '@', '\t', '\r', '\n')

def clean(v):
    txt=INVALID_XML.sub('',str(v if v is not None else ''))[:EXCEL_MAX_TEXT]
    if txt.startswith(DANGEROUS_PREFIX): txt="'"+txt
    return escape(txt, {'"':'&quot;'})

def col(n):
    result=''
    while n:
        n,rest=divmod(n-1,26)
        result=chr(65+rest)+result
    return result

def sheet_xml(headers, rows, widths=None):
    headers=list(headers);n=len(headers);rows=list(rows);widths=widths or []
    buff=['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
       '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
       '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/><selection pane="bottomLeft" activeCell="A2" sqref="A2"/></sheetView></sheetViews>',
       '<sheetFormatPr defaultRowHeight="18"/>','<cols>']
    for i,h in enumerate(headers,1):
        w=widths[i-1] if i<=len(widths) else min(42,max(14,len(str(h))+5))
        buff.append(f'<col min="{i}" max="{i}" width="{w}" customWidth="1"/>')
    buff.append('</cols><sheetData>')
    all_rows=[headers]+rows
    for rid,values in enumerate(all_rows,1):
        buff.append(f'<row r="{rid}" ht="{26 if rid==1 else 20}" customHeight="1">')
        for j,v in enumerate(values[:n],1):
            if v is None: continue
            addr=f'{col(j)}{rid}'
            style=1 if rid==1 else (2 if rid%2==0 else 0)
            if isinstance(v,(float,int)) and not isinstance(v,bool):
                buff.append(f'<c r="{addr}" s="{style}"><v>{v}</v></c>')
            else:
                buff.append(f'<c r="{addr}" t="inlineStr" s="{style}"><is><t xml:space="preserve">{clean(v)}</t></is></c>')
        buff.append('</row>')
    buff.append('</sheetData>')
    if n: buff.append(f'<autoFilter ref="A1:{col(n)}{max(1,len(all_rows))}"/>')
    buff.append('<pageMargins left="0.3" right="0.3" top="0.5" bottom="0.5" header="0.2" footer="0.2"/></worksheet>')
    return ''.join(buff).encode('utf8')

def workbook_bytes(sheets):
    """sheets: list[(name, headers, rows, optional widths)]"""
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        z.writestr('[Content_Types].xml', '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
           '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'+
           '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'+
           '<Default Extension="xml" ContentType="application/xml"/>'+
           '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'+
           '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'+
           ''.join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(1,len(sheets)+1))+'</Types>')
        z.writestr('_rels/.rels','<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr('xl/workbook.xml','<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><bookViews><workbookView/></bookViews><sheets>'+''.join(f'<sheet name="{clean(row[0][:31])}" sheetId="{i}" r:id="rId{i}"/>' for i,row in enumerate(sheets,1))+'</sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels','<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'+''.join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1,len(sheets)+1))+f'<Relationship Id="rId{len(sheets)+1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
        z.writestr('xl/styles.xml','<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="2"><font><sz val="11"/><color rgb="FF163044"/><name val="Aptos"/></font><font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Aptos"/></font></fonts><fills count="4"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF163C53"/><bgColor indexed="64"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFF1F7FA"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFill="1" applyFont="1"/><xf numFmtId="0" fontId="0" fillId="3" borderId="0" xfId="0" applyFill="1"/></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>')
        for i,(_,hdr,rows,*extra) in enumerate(sheets,1):
            z.writestr(f'xl/worksheets/sheet{i}.xml',sheet_xml(hdr,rows,extra[0] if extra else None))
    return output.getvalue()
