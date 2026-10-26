# -*- coding: utf-8 -*-
"""양도소득세 고객 DB 명령(사무소 추가). 모양은 yangdo/client_db.py 설명.

  python scripts/client_db.py 저장 --신고인 신고인.json [--고객정보 고객정보.json] [--고객번호 N]
  python scripts/client_db.py 기록 --사실관계 facts.json --신고인 신고인.json [--고객번호 N] [--증빙목록 증빙_목록.json] [--상태 작성]
  python scripts/client_db.py 조회 (--고객번호 N | --이름 홍길동 | --주민번호 13자리)
  python scripts/client_db.py 같은해 --고객번호 N --연도 2026
  python scripts/client_db.py 상태 --고객번호 N --신고번호 2026-0001 --상태 제출
  python scripts/client_db.py 목록

신고서·전자신고 파일을 만드는 make_efile.py 는 실행할 때마다 저장과 기록을 스스로 한다. 화면 출력에는 주민등록번호를 가려 적는다.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
if SKILL not in sys.path:
    sys.path.insert(0, SKILL)

from yangdo import client_db  # noqa: E402


def _read(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def evidence_names(path):
    """증빙_목록.json(evidence inventory) → 문서 파일 이름 목록."""
    if not path:
        return []
    inv = _read(path)
    return [d.get("파일") for d in inv.get("문서") or [] if d.get("파일")]


def summary(c):
    p = c["인적사항"]
    lines = ["고객번호 %s  %s  %s  등록 %s" % (c["고객번호"], p.get("성명"), client_db._mask(p.get("주민등록번호")), c["등록일자"])]
    for x in c["물건"]:
        loc = x["소재지"]
        place = " ".join(str(loc.get(k)) for k in ("시도", "시군구", "읍면동", "번지") if loc.get(k))
        if loc.get("아파트명"):
            place += " %s %s동 %s호" % (loc["아파트명"], loc.get("아파트동") or "", loc.get("아파트호") or "")
        lines.append("  물건 %d  %s  %s  취득 %s  양도 %s" % (x["물건번호"], x.get("종류"), place, x["취득"].get("일자"), x["양도"].get("일자")))
    for f in c["신고"]:
        tax = f.get("세액") or {}
        lines.append("  신고 %s  %s  작성 %s  기한 %s  물건 %s  산출세액 %s  %s" % (
            f["신고번호"], f.get("신고구분"), f.get("작성일"), f.get("신고기한"), f.get("물건번호"),
            "{:,}".format(tax["산출세액"]) if tax.get("산출세액") is not None else "-", f["상태"]))
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="양도소득세 고객 DB")
    ap.add_argument("명령", choices=("저장", "기록", "조회", "같은해", "상태", "목록"))
    ap.add_argument("--고객DB")
    ap.add_argument("--고객번호", type=int)
    ap.add_argument("--신고인")
    ap.add_argument("--고객정보")
    ap.add_argument("--사실관계")
    ap.add_argument("--증빙목록")
    ap.add_argument("--상태", default="작성")
    ap.add_argument("--신고번호")
    ap.add_argument("--이름")
    ap.add_argument("--주민번호")
    ap.add_argument("--연도", type=int)
    a = ap.parse_args(argv)
    db = client_db.Db(a.고객DB)
    if a.명령 == "목록":
        for k, v in sorted(db.index["고객"].items(), key=lambda x: int(x[0])):
            print("%s  %s  %s  물건 %s  신고 %s  마지막 %s" % (k, v["성명"], v["주민번호"], v["물건수"], v["신고수"], v["마지막신고"]))
        return 0
    if a.명령 == "조회":
        for no in db.find(rrn=a.주민번호, name=a.이름, no=a.고객번호):
            print(summary(db.load(no)))
        return 0
    if a.명령 == "같은해":
        print(json.dumps(db.same_year(a.고객번호, a.연도), ensure_ascii=False, indent=1))
        return 0
    if a.명령 == "상태":
        db.set_state(a.고객번호, a.신고번호, a.상태)
        print("신고 %s 상태를 %s 로 바꿨다" % (a.신고번호, a.상태))
        return 0
    filer = _read(a.신고인)
    extra = _read(a.고객정보) if a.고객정보 else None
    no, new = db.upsert(filer, extra, a.고객번호)
    print("고객번호 %s %s (%s)" % (no, "등록" if new else "갱신", db.path(no)))
    if a.명령 == "기록":
        fid = db.record(no, _read(a.사실관계), filer, evidence=evidence_names(a.증빙목록), state=a.상태)
        print("신고 %s 기록" % fid)
    return 0


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except AttributeError:
            pass
    sys.exit(main())
