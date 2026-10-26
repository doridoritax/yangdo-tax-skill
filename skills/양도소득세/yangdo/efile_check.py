# -*- coding: utf-8 -*-
"""전자신고 파일(C116300) 자체 형식검증. 사무소에서 덧붙인 모듈이다(공개본에 없음).

홈택스 「파일변환신고」 형식검증에서 걸릴 만한 것을 파일을 내보내기 전에 본다. 기준은 국세청 파일설명서 V5.17 의
칸 정의·점검내용이고, 오류와 경고의 경계는 홈택스에 실제로 접수된 사무소 파일 118건으로 맞췄다.
  오류: 설명서가 막는 형식(길이·숫자·날짜·코드·필수 칸·합계)이면서 접수된 파일이 한 건도 어기지 않은 것. 오류가 있으면 파일을 내지 않는다
  경고: 설명서와 다르지만 접수된 파일에서 받아들여진 것(07 필수 구분의 사업자번호 공란 등). 알림으로만 낸다
사무소 규칙: 신고인 주소는 도로명(도로명·건물본번)이 있어야 한다(오류).

check(data) → (오류 목록, 경고 목록). data 는 파일 바이트.
"""
import datetime
import json
import os

from . import bjd as bjd_mod
from . import filing

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAYOUT = os.path.join(SKILL_DIR, "efile", "layout_c116300.json")
CODES = os.path.join(SKILL_DIR, "efile", "codes_c116300.json")
ORDER = ("01", "02", "03", "04", "05", "07")
# 설명서는 Not Null 이지만 접수된 파일에서 공란이 받아들여진 칸(경고)
ACCEPTED_BLANK = {("07", "상호"), ("04", "양수인_주민등록번호"), ("05", "1세대1주택비과세_보유기간"), ("05", "1세대1주택_비과세_거주기간"),
                  ("04", "양수인_전화번호"), ("02", "전화번호")}
DATE_FIELDS = {("01", "작성일자"), ("01", "양도일자"), ("01", "세무대리인생년월일"), ("05", "거래일자_양도일자"),
               ("05", "거래일자_취득일자"), ("07", "지급일자")}
AMT_SUM = ("양도소득금액", "양도소득기본공제", "과세표준", "산출세액", "감면세액", "자진납부할세액", "가산세-계")
TAXPAYER_KINDS = {"00", "01", "02", "03", "04", "05", "06", "07", "08", "09", "99"}
REPORT_TYPES = {"1", "2", "3", "4", "5", "6", "7", "9"}


def _date_ok(s):
    try:
        datetime.date(int(s[:4]), int(s[4:6]), int(s[6:8]))
        return len(s) == 8
    except ValueError:
        return False


class _Check:
    def __init__(self, layout=None, codes=None, bjd=None):
        with open(layout or LAYOUT, encoding="utf-8") as f:
            self.L = json.load(f)
        with open(codes or CODES, encoding="utf-8") as f:
            self.C = json.load(f)
        self.bjd = bjd or bjd_mod.load()
        self.exp = {v["전자코드"]: v for v in self.C["필요경비구분"].values()}
        self.err, self.warn = [], []

    def e(self, s):
        if s not in self.err:
            self.err.append(s)

    def w(self, s):
        if s not in self.warn:
            self.warn.append(s)

    def parse(self, i, line):
        no = line[:2].decode("ascii", "replace")
        rec = self.L["레코드"].get(no)
        if rec is None:
            self.e("줄%d 알 수 없는 자료구분 %r" % (i, no))
            return no, None
        if len(line) != rec["길이"]:
            self.e("줄%d %s 레코드 길이 %d ≠ %d" % (i, no, len(line), rec["길이"]))
            return no, None
        out = {}
        for f in rec["필드"]:
            raw = line[f["start"]:f["start"] + f["len"]]
            try:
                v = raw.decode("cp949")
            except UnicodeDecodeError:
                self.e("줄%d %s.%s KS X 1001 로 읽을 수 없는 바이트" % (i, no, f["name"]))
                v = raw.decode("cp949", "replace")
            name = f["name"]
            if f.get("check") and v.strip() != f["check"]:
                self.e("줄%d %s.%s 값 %r ≠ %r" % (i, no, name, v.strip(), f["check"]))
            if f["type"] == "N" and not name.startswith("도로명_"):
                s = v.strip()
                if not s:
                    if not f.get("null"):
                        # 연금계좌세액공제는 V5.15(2025-06-18)에 생긴 칸이라 그 전 파일은 비어 있다
                        (self.w if name == "연금계좌세액공제" else self.e)("줄%d %s.%s 숫자 칸이 비었다(0 으로 채운다)" % (i, no, name))
                    out[name] = 0
                    continue
                body = s[1:] if s.startswith("-") else s
                if not body.isdigit() or len(s) != f["len"]:
                    self.e("줄%d %s.%s 숫자 형식 오류 %r" % (i, no, name, v))
                    out[name] = 0
                    continue
                out[name] = int(s)
                if f["dec"]:
                    out[name] = int(s) / 10 ** f["dec"]
            elif name.startswith("도로명_건물번호"):
                s = v.strip()
                if s and not s.isdigit():
                    self.e("줄%d %s.%s 숫자가 아니다 %r" % (i, no, name, s))
                out[name] = s
            else:
                s = v.rstrip()
                out[name] = s
                if (not f.get("null") and f["class"] != "SPACE" and name not in ("공란",) and not s.strip()
                        and name not in ("사업자등록번호", "지급일자")):
                    (self.w if (no, name) in ACCEPTED_BLANK else self.e)("줄%d %s.%s 필수 칸이 비었다" % (i, no, name))
                if (no, name) in DATE_FIELDS and s.strip() and not _date_ok(s.strip()):
                    self.e("줄%d %s.%s 날짜 형식 오류 %r" % (i, no, name, s))
        return no, out

    # ------------------------------------------------------------ 레코드별

    def header(self, h, r05):
        if h["납세자구분"] not in TAXPAYER_KINDS:
            self.e("01 납세자구분 %r 이 코드표에 없다" % h["납세자구분"])
        if h["신고구분코드"] not in ("01", "03"):
            self.e("01 신고구분코드 %r" % h["신고구분코드"])
        if h["신고유형"] not in REPORT_TYPES:
            self.e("01 신고유형 %r" % h["신고유형"])
        if h["신고구분상세코드"] not in ("01", "03"):
            self.e("01 신고구분상세코드 %r" % h["신고구분상세코드"])
        if h["신고서종류코드"] not in ("D01", "D02", "D03"):
            self.e("01 신고서종류코드 %r" % h["신고서종류코드"])
        if len(h["납세자ID"].strip()) != 13 or not h["납세자ID"].strip().isdigit():
            self.e("01 납세자ID(주민등록번호)가 숫자 13자리가 아니다")
        if r05:
            sold = max(r["거래일자_양도일자"] for r in r05)
            if h["양도일자"] != sold:
                self.e("01 양도일자 %s ≠ 05 의 가장 늦은 양도일 %s(설명서 25번)" % (h["양도일자"], sold))
            if h["과세기간_년월"] != sold[:4] + "01":
                self.e("01 과세기간 %s ≠ 양도연도+01" % h["과세기간_년월"])
            if h["작성일자"] < sold:
                self.w("01 작성일자 %s 가 양도일 %s 보다 앞선다" % (h["작성일자"], sold))
        if h["제출년월"] != h["작성일자"][:6]:
            self.e("01 제출년월 %s ≠ 작성일자의 연월" % h["제출년월"])
        if h["세무대리사업자등록번호"].strip():
            if not filing.biz_ok(h["세무대리사업자등록번호"].strip()):
                self.e("01 세무대리 사업자등록번호 검증번호가 맞지 않는다")
            if not (h["세무대리인관리번호"].strip() or h["세무대리인생년월일"].strip()):
                self.e("01 세무대리인관리번호·생년월일 중 하나는 있어야 한다(설명서 22·27번)")
            if not h["세무대리인성명"].strip():
                self.e("01 세무대리인성명이 없다(설명서 26번 필수)")

    def basics(self, b):
        code = b["주소_법정동코드"].strip()
        if not self.bjd.exists(code):
            self.e("02 신고인 법정동코드 %s 가 법정동코드표에 없다" % code)
        if not b["도로명_도로명"].strip() or not b["도로명_건물번호(본번)"]:
            self.e("02 신고인 주소에 도로명주소(도로명·건물본번)가 없다(사무소 규칙)")
        if b["도로명_지하만있는건물구분"].strip() not in ("", "0", "1"):
            self.e("02 지하만있는건물구분은 0 또는 1")
        if b["내외국인여부"] not in ("Y", "N") or b["거주구분"] not in ("Y", "N"):
            self.e("02 내외국인여부·거주구분은 Y/N")
        if b["거주구분"] == "N" and b["거주지국코드"].strip() != "KR":
            self.e("02 거주자인데 거주지국코드가 KR 이 아니다(설명서 16번)")
        if b["내외국인여부"] == "Y" and b["국적코드"].strip() != "KR":
            self.e("02 내국인인데 국적코드가 KR 이 아니다(설명서 26번)")
        tel = b["전화번호"].strip()
        if tel and not tel.isdigit():
            self.e("02 전화번호에 숫자 아닌 글자가 있다")

    def rates(self, r03, r05):
        by = {(r["국내외분"], r["세율구분"]): r for r in r03}
        tot = by.get(("Z", "00"))
        if tot is None:
            self.e("03 합계(Z·00) 행이 없다")
            return
        body = [r for k, r in by.items() if k[1] not in ("00", "98")]
        sub = by.get(("1", "00"))
        for k in AMT_SUM:
            if sum(r[k] for r in body) != tot[k]:
                self.e("03 %s: 세율구분 행 합 %s ≠ 합계 %s(설명서 5~19번)" % (k, sum(r[k] for r in body), tot[k]))
            if sub is not None and sub[k] != tot[k]:
                self.e("03 %s: 국내 소계 %s ≠ 합계 %s" % (k, sub[k], tot[k]))
        for r in body + [tot]:
            base = r["양도소득금액"] + r["기신고,결정,경정된양도소득금액합계"] - r["소득감면대상소득금액"] - r["양도소득기본공제"]
            if r["양도소득금액"] > 0 and r["과세표준"] != max(base, 0):
                self.w("03 %s%s 과세표준 %s ≠ 소득금액-기본공제 %s" % (r["국내외분"], r["세율구분"], r["과세표준"], base))
            due = (r["산출세액"] - r["감면세액"] - r["외국납부세액공제"] - r["예정신고납부세액공제"] - r["원천징수세액공제"]
                   - r["전자신고세액공제"] - r["연금계좌세액공제"] + r["가산세-계"] - r["기신고,결정,경정세액"])
            if max(due, 0) != r["자진납부할세액"]:
                self.e("03 %s%s 자진납부할세액 %s ≠ 산출-공제+가산세 %s" % (r["국내외분"], r["세율구분"], r["자진납부할세액"], due))
            if r["가산세-계"] != r["가산세-신고불성실"] + r["가산세-납부불성실"] + r["가산세-기장불성실등"]:
                self.e("03 %s%s 가산세-계가 세 가산세의 합이 아니다" % (r["국내외분"], r["세율구분"]))
            if r["전자신고세액공제"] > 20000:
                self.e("03 전자신고세액공제가 2만원을 넘는다")
        if tot["양도소득기본공제"] > 2500000:
            self.e("03 기본공제 %s 가 250만원을 넘는다" % tot["양도소득기본공제"])
        due, inst = tot["자진납부할세액"], tot["분납할세액"]
        lim = 0 if due <= 10000000 else (due - 10000000 if due <= 20000000 else due // 2)
        if inst > lim:
            self.e("03 분납할세액 %s 가 한도 %s 를 넘는다(설명서 20번)" % (inst, lim))
        if tot["자진납부세액"] != due - inst:
            self.e("03 자진납부세액 ≠ 자진납부할세액 - 분납할세액")
        for r in body + ([sub] if sub else []):
            if r["분납할세액"] or r["자진납부세액"]:
                self.e("03 분납할세액·자진납부세액은 합계 행에만 적는다(설명서 20·21번)")
        rates05 = {}
        for r in r05:
            rates05[r["세율구분"]] = rates05.get(r["세율구분"], 0) + r["양도소득금액"]
        for s, amt in rates05.items():
            row = by.get((r05[0]["국내외분(소재지)"], s))
            if row is None:
                self.e("03 05 의 세율구분 %s 행이 없다" % s)
            elif row["양도소득금액"] != max(amt, 0) and row["양도소득금액"] != amt:
                self.e("03 %s 양도소득금액 %s ≠ 05 세율구분 합 %s" % (s, row["양도소득금액"], amt))

    def buyers(self, r04):
        rel = set(self.C["양수인관계목록"]) if isinstance(self.C.get("양수인관계목록"), dict) else None
        for x in r04:
            n, kind = x["양수인_주민등록번호"].strip(), x["양수인_주민사업자구분"]
            if kind not in ("1", "2"):
                self.e("04 주민사업자구분 %r" % kind)
            elif kind == "1" and (len(n) != 13 or not n.isdigit()):
                self.w("04 양수인(%s) 구분 1(주민)인데 번호가 주민번호 13자리가 아니다" % x["양수인_성명"].strip()[:10])
            elif kind == "2" and (len(n) != 10 or not filing.biz_ok(n)):
                self.w("04 양수인 구분 2(사업자)인데 번호가 사업자등록번호가 아니다")
            if x["양수인_내외국인_구분코드"] not in ("1", "9"):
                self.e("04 내외국인구분코드 %r" % x["양수인_내외국인_구분코드"])
            a, b = x["양수인_지분(분자)"], x["양수인_지분(분모)"]
            if not b or a <= 0 or a > b:
                self.e("04 양수인 지분 %s/%s 이 맞지 않는다" % (a, b))
            if rel is not None and x["양수인_양도자와의관계"] not in rel:
                self.e("04 양도자와의관계 코드 %r 이 코드표에 없다" % x["양수인_양도자와의관계"])

    def calcs(self, r05, r07):
        kinds = {v["코드"] for v in self.C["자산종류"].values() if v.get("코드")}
        purposes = set(self.C["등기목적목록"])
        for r in r05:
            tag = "05 #%s" % r["일련번호"]
            if not self.bjd.exists(r["소재지_법정동코드"].strip()):
                self.e("%s 소재지 법정동코드 %s 가 법정동코드표에 없다" % (tag, r["소재지_법정동코드"]))
            if r["자산의종류"] not in kinds:
                self.e("%s 자산의종류 %r 이 코드표에 없다" % (tag, r["자산의종류"]))
            for side in ("양도", "취득"):
                p, c = r["거래일자_%s등기목적" % side], r["거래일자_%s등기원인" % side].strip()
                if p not in purposes:
                    self.e("%s %s등기목적 %r 이 코드표에 없다" % (tag, side, p))
                elif c and self.C["등기원인목록"].get(p) and c not in self.C["등기원인목록"][p]:
                    self.e("%s %s등기원인 %s 은 등기목적 %s 에 쓰지 않는 코드" % (tag, side, c, p))
            if r["거래일자_취득일자"] > r["거래일자_양도일자"]:
                self.e("%s 취득일자가 양도일자보다 늦다" % tag)
            if r["취득가액종류"] not in ("01", "02", "03", "04", "05", "11", "12", "13", "14"):
                self.e("%s 취득가액종류 %r" % (tag, r["취득가액종류"]))
            g = r["거래금액_양도가액"] - r["거래금액_취득가액"] - r["기타필요경비"] - r["기납부토지초과이득세"]
            if r["과세구분"] != "01" and g != r["양도차익_전체양도차익"]:
                self.e("%s 전체양도차익 %s ≠ 양도가액-취득가액-기타필요경비 %s" % (tag, r["양도차익_전체양도차익"], g))
            if r["양도차익_전체양도차익"] - r["양도차익_비과세양도차익"] != r["양도차익_과세대상양도차익"]:
                self.e("%s 과세대상양도차익 ≠ 전체-비과세" % tag)
            if r["양도차익_과세대상양도차익"] - r["장기보유특별공제"] != r["양도소득금액"]:
                self.e("%s 양도소득금액 ≠ 과세대상양도차익-장기보유특별공제" % tag)
            cut = r["감면소득금액-세액감면대상"] + r["감면소득금액-소득금액감면대상"]
            if cut and r["양도소득금액"] < cut:
                self.e("%s 양도소득금액 < 감면소득금액 합(설명서 오류 조건)" % tag)
            for ar, sh in (("토지", "토지"), ("건물", "건물")):
                if r["거래자산면적_총면적_%s_지분(분자)" % sh] > r["거래자산면적_총면적_%s_지분(분모)" % sh]:
                    self.e("%s %s 지분 분자가 분모보다 크다" % (tag, ar))
            seq = r["필요경비신고자료일련번호"]
            mine = [x for x in r07 if seq and int(x["필요경비신고자료일련번호"] or 0) == seq]
            if seq and not mine:
                self.e("%s 필요경비신고자료일련번호 %s 인데 07 행이 없다(설명서 61번)" % (tag, seq))
            if mine and r["취득가액종류"] == "01":
                acq = sum(-x["지급금액"] if x["구분코드"] == "14101" else x["지급금액"] for x in mine if x["구분코드"][:1] == "1")
                oth = sum(x["지급금액"] for x in mine if x["구분코드"][:1] == "2")
                if abs(acq - r["거래금액_취득가액"]) > 3:      # 접수된 입주권 파일에 있었다(경고)
                    self.w("%s 07 취득가액 명세 합 %s ≠ 05 취득가액 %s" % (tag, acq, r["거래금액_취득가액"]))
                if abs(oth - r["기타필요경비"]) > 3:
                    self.w("%s 07 기타필요경비 명세 합 %s ≠ 05 기타필요경비 %s" % (tag, oth, r["기타필요경비"]))
        seqs = {r["필요경비신고자료일련번호"] for r in r05}
        evid = set(self.C["증빙종류목록"]) | {"ZZ"}
        for x in r07:
            code, e = x["구분코드"], self.exp.get(x["구분코드"])
            tag = "07 %s(%s)" % (code, x["상호"].strip()[:10])
            if int(x["필요경비신고자료일련번호"] or 0) not in seqs:
                self.e("%s 필요경비신고자료일련번호가 05 에 없다" % tag)
            if e is None:
                self.e("%s 구분코드가 코드표에 없다" % tag)
                continue
            if x["증빙종류코드"] not in evid:
                self.e("%s 증빙종류코드 %r 이 코드표에 없다" % (tag, x["증빙종류코드"]))
            if e["필수"] and x["지급금액"]:
                miss = [k for k in ("사업자등록번호", "지급일자") if not x[k].strip()]
                if x["증빙종류코드"] == "ZZ":
                    miss.append("증빙종류")
                if miss:
                    self.w("%s 필수 구분인데 %s 이 없다(접수된 파일에서는 받아들여졌다)" % (tag, "·".join(miss)))
            elif x["증빙종류코드"] != "ZZ":
                self.w("%s 필수 구분이 아닌 행의 증빙종류는 ZZ(설명서 10번)" % tag)
            b = x["사업자등록번호"].strip()
            if b and (len(b) != 10 or not filing.biz_ok(b)):
                self.e("%s 사업자등록번호 검증번호가 맞지 않는다" % tag)

    def run(self, data):
        if not data.endswith(b"\r\n"):
            self.e("파일 끝에 CR/LF 가 없다")
        if b"\r\n" not in data or data.replace(b"\r\n", b"").find(b"\n") >= 0:
            self.e("줄 끝은 CR/LF 여야 한다(LINE SEQUENTIAL)")
        lines = [x for x in data.split(b"\r\n") if x]
        recs = {k: [] for k in ORDER}
        last = -1
        for i, line in enumerate(lines, 1):
            no, r = self.parse(i, line)
            if no in ORDER:
                pos = ORDER.index(no)
                if pos < last:
                    self.e("줄%d %s 레코드 순서가 틀렸다(01·02·03·04·05·07 차례)" % (i, no))
                last = max(last, pos)
            if r is not None:
                recs[no].append(r)
        if len(recs["01"]) != 1 or len(recs["02"]) != 1:
            self.e("01·02 레코드는 한 줄씩이어야 한다")
            return self.err, self.warn
        if not recs["05"] or not recs["03"] or not recs["04"]:
            self.e("03·04·05 레코드가 있어야 한다")
            return self.err, self.warn
        self.header(recs["01"][0], recs["05"])
        self.basics(recs["02"][0])
        self.rates(recs["03"], recs["05"])
        self.buyers(recs["04"])
        self.calcs(recs["05"], recs["07"])
        return self.err, self.warn


def check(data, bjd=None):
    """(오류 목록, 경고 목록)."""
    return _Check(bjd=bjd).run(data)
