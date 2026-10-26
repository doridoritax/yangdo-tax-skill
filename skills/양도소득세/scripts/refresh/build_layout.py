import re, json, sys
lines = open('spec/spec517.txt', encoding='utf-8').read().split('\n')
tabs = {}; cur = None
for l in lines:
    m = re.match(r'<<TABLE (\d+)>>', l)
    if m: cur = int(m.group(1)); tabs[cur] = []; continue
    if l == '<<END>>': cur = None; continue
    if cur: tabs[cur].append(l.split(' | '))
REC = {"01": (51, "C116300", 350), "02": (54, "C116300", 400), "03": (55, "C116300", 450),
       "04": (67, "C116300", 150), "05": (68, "C116400", 700), "07": (80, "C116600", 200)}
CLASSES = {"AMT", "AMT+", "RATE", "SEQ", "CODE", "LIST", "FIX", "SPACE", "DATE", "ID", "USERID"}
out = {"규격": {"판": "V5.17", "문서": "양도소득세 전자신고 파일설명서_V5.17_(20260428).doc"}, "레코드": {}}
for no, (t, form, total) in REC.items():
    fields = []; pos = 0
    for r in tabs[t][1:]:
        if r[0].strip() == '삭제': continue
        idx = next((i for i, c in enumerate(r) if c.strip() in ('CHAR', 'NUMBER')), None)
        if idx is None: continue
        name = r[idx - 1].strip().replace("–", "-").replace(" ", "")
        name = re.sub(r'\s*-\s*', '-', name) if '감면소득금액' in name else name
        ln = r[idx + 1].strip(); cum = int(r[idx + 2].strip())
        dec = 0
        if ',' in ln: ln, dec = ln.split(','); dec = int(dec)
        ln = int(ln)
        if pos + ln != cum: print('CUM MISMATCH', no, name, pos, ln, cum, file=sys.stderr)
        pos = cum
        cls = r[-1].strip()
        f = {"name": name, "type": "N" if r[idx].strip() == 'NUMBER' else "C", "len": ln, "dec": dec,
             "class": cls if cls in CLASSES else "", "start": cum - ln,
             "null": "null" in r[idx + 3].lower().replace(" ", "") and "not" not in r[idx + 3].lower()}
        if name == '자료구분': f["check"] = no
        if name == '서식코드': f["check"] = form
        fields.append(f)
    if pos != total: print('TOTAL MISMATCH', no, pos, total, file=sys.stderr)
    out["레코드"][no] = {"서식코드": form, "길이": total, "필드": fields}
for f in out["레코드"]["03"]["필드"]:
    if f["name"] == "주민세_세율": f["check"] = "01000"
json.dump(out, open(sys.argv[1], 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
for no, r in out["레코드"].items():
    print(no, [ (f["name"], f["type"], f["len"], f["dec"]) for f in r["필드"]][:3], '...', len(r["필드"]))
