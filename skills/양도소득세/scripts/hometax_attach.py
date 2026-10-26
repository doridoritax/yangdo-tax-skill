# -*- coding: utf-8 -*-
"""홈택스 「신고부속서류 제출」에 올릴 파일을 어사이드 세션 업로드 폴더에 모은다(양도세·증여세 공용).

  python -I -X utf8 scripts/hometax_attach.py --이름 1_수증자A 파일1 파일2 ... [--합본 "임대차계약서_501~514호.pdf" a.pdf b.jpg ...] [--세션 <폴더>]

- 어사이드는 세션 폴더 밖의 파일을 브라우저에 올리지 못한다. 그래서 <세션>/upload/<이름>/ 으로 복사한다.
  --세션 을 주지 않으면 ~/.aside/u/0/sessions 에서 가장 최근에 바뀐 세션을 쓴다. 어사이드 repl 의 `pwd` 와 같은지 확인한다.
- 홈택스 부속서류 팝업은 「파일선택」 한 번에 5개까지만 받고, 한 번 제출은 50MB 까지다(2026-10-26 확인).
  5개를 넘으면 종료코드 2 로 멈춘다 — 같은 종류(예: 호실별 임대차계약서)를 --합본 으로 PDF 하나로 묶는다(이미지는 PDF 쪽으로 바꿔 붙임).
- jpg·png 는 그대로 둬도 된다(홈택스가 PDF 로 바꿔 받는다).
종료코드: 0 완료, 2 입력 오류(파일 없음·개수·크기 초과).
"""
import argparse
import glob
import os
import shutil
import sys

MAX_FILES = 5
MAX_BYTES = 50 * 1024 * 1024
SESSIONS = os.path.join(os.path.expanduser("~"), ".aside", "u", "0", "sessions")


def latest_session():
    ds = [d for d in glob.glob(os.path.join(SESSIONS, "*")) if os.path.isdir(d)]
    return max(ds, key=os.path.getmtime) if ds else None


def merge(paths, out):
    import pymupdf
    doc = pymupdf.open()
    for p in paths:
        src = pymupdf.open(p) if p.lower().endswith(".pdf") else pymupdf.open("pdf", pymupdf.open(p).convert_to_pdf())
        doc.insert_pdf(src)
    doc.save(out, garbage=3, deflate=True)
    return doc.page_count


def main(argv=None):
    ap = argparse.ArgumentParser(description="홈택스 부속서류 업로드 준비(어사이드 세션 폴더)")
    ap.add_argument("파일", nargs="*")
    ap.add_argument("--이름", required=True, help="업로드 하위 폴더 이름(예: 1_수증자A)")
    ap.add_argument("--합본", nargs="+", action="append", default=[], metavar=("이름.pdf", "파일"))
    ap.add_argument("--세션")
    ap.add_argument("--최대", type=int, default=MAX_FILES)
    a = ap.parse_args(argv)
    sess = a.세션 or latest_session()
    if not sess or not os.path.isdir(sess):
        print("어사이드 세션 폴더를 찾지 못했다 — 어사이드 repl 에서 pwd 를 확인해 --세션 으로 준다")
        return 2
    missing = [p for p in a.파일 + [x for g in a.합본 for x in g[1:]] if not os.path.isfile(p)]
    if missing:
        print("없는 파일: " + ", ".join(missing))
        return 2
    count = len(a.파일) + len(a.합본)
    if count > a.최대:
        print("파일 %d개 — 홈택스는 한 번에 %d개까지 받는다. 같은 종류를 --합본 \"이름.pdf\" 파일들 로 묶는다" % (count, a.최대))
        return 2
    dst = os.path.join(sess, "upload", a.이름)
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    os.makedirs(dst)
    for p in a.파일:
        shutil.copy2(p, dst)
    for g in a.합본:
        name = g[0] if g[0].lower().endswith(".pdf") else g[0] + ".pdf"
        pages = merge(g[1:], os.path.join(dst, name))
        print("합본 %s: %d개 파일, %d쪽" % (name, len(g) - 1, pages))
    files = sorted(os.listdir(dst))
    total = sum(os.path.getsize(os.path.join(dst, f)) for f in files)
    for f in files:
        print("  %s (%s KB)" % (f, format(os.path.getsize(os.path.join(dst, f)) // 1024, ",")))
    print("업로드 폴더: %s  (%d개, %.1f MB)" % (dst, len(files), total / 1048576))
    if total > MAX_BYTES:
        print("50MB 를 넘는다 — 두 번으로 나눠 제출한다(제출내역의 「부속서류 추가 제출」)")
        return 2
    return 0


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except AttributeError:
            pass
    sys.exit(main())
