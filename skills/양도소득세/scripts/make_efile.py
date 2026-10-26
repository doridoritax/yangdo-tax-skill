# -*- coding: utf-8 -*-
"""신고서 PDF 두 벌에 더해 홈택스 전자신고(변환신고) 파일 C116300 을 만든다. 공개본에 없는 단계를 사무소에서 덧붙였다.

  python scripts/make_efile.py --사실관계 facts.json --신고인 신고인.json --세무대리인 efile/세무대리인.json --출력 out

차례는 make_return.py 와 같다(계산 → 신고인 정보 → 신고값 → 서식 검산 → 신고서 PDF). 신고값을 만들 때 전자신고 레이아웃
(efile/layout_c116300.json)을 읽게 해 03·05·07 행을 함께 만들고, 신고서 PDF 까지 끝났으면(종료코드 0)
yangdo/efile_writer.py 로 전자신고 파일을 출력 폴더에 쓴다. 스킬의 원래 모듈은 고치지 않고 이 스크립트 안에서만 바꿔 끼운다.

--세무대리인 을 주면 세무대리인 신고다. 01 레코드에 세무대리인 칸을 채우고, 전자신고세액공제(국세·지방)는 0 으로 한다
(조특법 시행령 제104조의5①·지방세법 시행령 제116조의2①: 납세자가 직접 전자신고할 때만 공제). 신고서 PDF 도 같은 값이다.
신고인 JSON 의 세무대리인은 그대로 null 로 둔다(스킬이 대리 신고를 다루지 않음으로 멈추기 때문이다).

종료코드는 make_return.py 와 같고, 전자신고 파일을 쓰지 못하면 1 이다.
"""
import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
for p in (SKILL, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

import make_return  # noqa: E402
from yangdo import efile_check, efile_writer, filing, forms_check, forms_fmt, return_values, ruleset  # noqa: E402

ROAD_TAIL = re.compile(r"(로|길)\s?\d+(-\d+)?(,|\s\(|$)")      # 「…로 80」, 「…5길 15, 104동」 같은 도로명주소 꼴
DEFAULT_AGENT = os.path.join(SKILL, "efile", "세무대리인.json")      # 없으면 납세자 직접 신고(전자신고세액공제 적용)
CREDIT_KEYS = ("전자신고세액공제.예정", "지방.전자신고세액공제.예정")


def _patch(agent):
    layout = efile_writer.load_layout()
    # 신고인 주소·자산 지번의 도로명주소 키를 모르는 키로 알리지 않는다(02 레코드 도로명 칸, 05 소재지, 신고서 주소 칸에 쓴다)
    filing._KNOWN_KEYS["신고인.주소"] = set(filing._KNOWN_KEYS["신고인.주소"]) | set(efile_writer.ROAD_FIELDS)
    filing._KNOWN_KEYS["자산"] = set(filing._KNOWN_KEYS["자산"]) | set(efile_writer.ROAD_FIELDS)
    # 신고서 PDF 의 신고인 주소와 양도자산 소재지를 도로명주소로 적는다(도로명이 있을 때)
    address = forms_fmt._address

    def road_or_lot(a, mountain=None):
        return efile_writer.road_text(a) if isinstance(a, dict) and a.get("도로명") else address(a, mountain)
    forms_fmt._address = road_or_lot
    shorter = forms_fmt._shorter

    def road_shorter(text):
        """좁은 칸의 줄임 후보. 도로명주소(「… 15, 104동 1402호 (양덕동, …)」)는 괄호 참고항목 → 시도 약칭 → 시도 → 동·호 순으로 뺀다."""
        base = shorter(text)
        if not isinstance(text, str) or not ROAD_TAIL.search(text):
            return base
        no_ref = re.sub(r"\s*\([^)]*\)$", "", text)
        words = no_ref.split(" ")
        sido = words[0]
        cands = [text, no_ref]
        if forms_fmt.SIDO_SHORT.get(sido):
            cands.append(" ".join([forms_fmt.SIDO_SHORT[sido]] + words[1:]))
        no_sido = " ".join(words[1:])
        cands += [no_sido, no_sido.split(",")[0]]
        out = []
        for c in cands + list(base):
            if c and c not in out:
                out.append(c)
        return out
    forms_fmt._shorter = road_shorter
    place = return_values._Builder.place

    def road_place(self, a, lot, code):
        if (lot or {}).get("도로명"):
            return efile_writer.road_text(dict(a.get("소재지") or {}, **lot))
        return place(self, a, lot, code)
    return_values._Builder.place = road_place
    init = return_values._Builder.__init__

    def init_with_layout(self, *a, **k):
        init(self, *a, **k)
        self.layout = layout
    return_values._Builder.__init__ = init_with_layout

    if agent:
        value = ruleset.Ruleset.value

        def no_credit(self, key, on):
            return 0 if key in CREDIT_KEYS else value(self, key, on)
        ruleset.Ruleset.value = no_credit

    values = make_return._values

    def keep_values(rep, res, *a, **k):
        if _all_exempt(res):
            _fill_exempt(res)
            rep["확인사항"].append(EXEMPT_NOTE)
        rv = values(rep, res, *a, **k)
        rep["_신고값"] = rv
        return rv
    make_return._values = keep_values
    _patch_exempt()
    return layout


# ------------------------------------------------------------ 전액 비과세 건
# 공개본은 전액 비과세 자산뿐인 건의 신고서를 만들지 않는다(엔진이 그 자산의 취득가액·양도차익을 계산하지 않는다).
# 사무소는 1세대1주택 비과세 건도 예정신고를 하므로, 자산이 모두 전액 비과세일 때만 아래처럼 채워 신고서와 전자신고 파일을 만든다.
# 접수된 비과세 예정신고 파일의 꼴: 05 과세구분 01, 취득가액 0, 전체양도차익 = 비과세양도차익 = 양도가액,
# 장특공 적용구분 01(1세대1주택), 03 행 금액 0. 과세 자산과 섞인 건은 공개본 그대로(비과세 자산을 신고서에서 뺀다)다.

EXEMPT_NOTE = ("전액 비과세 자산뿐인 건이라 취득가액을 0, 전체양도차익과 비과세양도차익을 양도가액으로 적었다"
               "(사무소에서 접수한 비과세 예정신고 파일의 꼴). 취득가액과 필요경비는 신고서에 적지 않았다")


EXEMPT_ACQ_CODE = "01"
# 전액 비과세 자산뿐인 건에서 서식 검산이 내는 문장 가운데, 「비과세 자산은 신고서에 없다」는 공개본 전제에서 나오는 것.
# 본지에는 과세 열이 없고(세율구분 열 없음), 부표1 ⑯ 은 1세대1주택이라 01 을 적는다(엔진 판정은 「없음」)
EXEMPT_CHECK_SKIP = ("에 해당하는 본지 열이 없다", "장기보유특별공제 코드 01 ≠ 엔진 판정 없음")


def _all_exempt(res):
    rows = ((res or {}).get("계산") or {}).get("자산") or []
    return bool(rows) and all((r.get("판정") or {}).get("전액비과세") for r in rows)


def _fill_exempt(res):
    for r in res["계산"]["자산"]:
        c = r["계산"]
        # 취득가액방법은 비워 둔다(부표1 ⑫ 종류 칸 공란, 부표3 없음). 05 취득가액종류만 접수된 파일처럼 01(실지거래가액)
        c.update(취득가액=0, 필요경비=0, 양도차익=c["양도가액"], 비과세양도차익=c["양도가액"])
        c["코드"]["취득가액종류"] = c["코드"].get("취득가액종류") or EXEMPT_ACQ_CODE


def _patch_exempt():
    exempt_ids = return_values.exempt_ids

    def none_when_all_exempt(res):
        return [] if _all_exempt(res) else exempt_ids(res)
    return_values.exempt_ids = none_when_all_exempt
    make_return.return_values.exempt_ids = none_when_all_exempt

    asset = return_values._Builder.asset

    def exempt_asset(self, n, row):
        v = row["판정"]
        if not v.get("전액비과세"):
            return asset(self, n, row)
        v2 = dict(v, 전액비과세=False, 장특공="표2" if v.get("일세대일주택") else v.get("장특공"))
        rows = self.expense_rows
        self.expense_rows = lambda *a: ([], 0, 0)       # 취득가액·필요경비 명세(부표3, 07)는 쓰지 않는다
        try:
            return asset(self, n, dict(row, 판정=v2))
        finally:
            self.expense_rows = rows
    return_values._Builder.asset = exempt_asset

    # 서식 검산도 전액 비과세 자산뿐인 건은 그 자산을 신고서에 넣는 자산으로 보고 검산한다
    check_init = forms_check._Check.__init__

    def check_all(self, *a, **k):
        check_init(self, *a, **k)
        if self.exempt and not self.taxed:
            self.taxed, self.exempt = self.exempt, []
            self.is_exempt = lambda aid: False
    forms_check._Check.__init__ = check_all

    check = forms_check.check

    def check_exempt(rv, result, *a, **k):
        fails = check(rv, result, *a, **k)
        if _all_exempt(result):
            fails = [x for x in fails if not any(s in x for s in EXEMPT_CHECK_SKIP)]
        return fails
    make_return.forms_check.check = check_exempt


def make(facts, filer, out, agent_path=None, name=None, today=None, rules_dir=None, customer=None):
    """customer 는 고객 DB 기록 설정 {"번호", "정보"(고객정보 JSON 경로), "증빙"(증빙_목록.json 경로), "DB"} 또는 None(기록 안 함)."""
    agent = efile_writer.load_agent(agent_path) if agent_path else None
    layout = _patch(agent)
    missing = road_missing(facts, filer)
    if missing:     # 사무소 규칙: 신고인 주소와 건물이 있는 양도 물건 소재지는 도로명주소로 신고한다
        rep = make_return._report(out, make_return.FORMS)
        rep.update(종료코드=2, 상태="입력오류", 요약="도로명주소가 없어 신고서와 전자신고 파일을 만들지 않았다")
        rep["알림"] += missing
        rep["단계"]["전자신고 파일"] = "하지 않음"
        rep["사람이할일"] = ["신고인 JSON 에 도로명주소(도로명, 건물본번, 있으면 건물부번)를 채운 뒤 다시 실행한다"]
        if customer is not None:
            _record_customer(rep, None, facts, filer, out, customer, rules_dir)
        return rep
    rep = make_return.make(facts, filer, out, today=today, rules_dir=rules_dir)
    rv = rep.pop("_신고값", None)
    rep["단계"]["전자신고 파일"] = "하지 않음"
    try:
        if rep["종료코드"] != 0 or rv is None:
            return rep
        return _write_efile(rep, rv, out, agent, name, layout, facts, filer)
    finally:
        if customer is not None:
            _record_customer(rep, rv, facts, filer, out, customer, rules_dir)


def _record_customer(rep, rv, facts, filer, out, customer, rules_dir):
    """실행할 때마다 고객 DB 에 고객·물건·신고를 쌓는다. 실패해도 신고서 결과는 그대로 두고 알림만 단다."""
    import client_db as cli
    from yangdo import client_db, dates
    try:
        f = _read_json(facts) if not isinstance(facts, dict) else facts
        g = _read_json(filer) if not isinstance(filer, dict) else filer
        db = client_db.Db(customer.get("DB"))
        extra = _read_json(customer["정보"]) if customer.get("정보") else None
        no, new = db.upsert(g, extra, customer.get("번호"))
        s = g.get("신고") or {}
        sold = [((a.get("양도") or {}).get("잔금일") or (a.get("양도") or {}).get("대금완납일") or (a.get("양도") or {}).get("등기접수일"))
                for a in f.get("자산") or []]
        sold = [d for d in sold if d]
        burden = any((a.get("양도") or {}).get("원인") == "부담부증여" for a in f.get("자산") or [])
        due = None
        if sold and s.get("구분") in ("예정", "확정"):
            due = dates.filing_deadline(s["구분"], max(sold), ruleset.load(rules_dir), burden)[1].isoformat()
        ok = rep["종료코드"] == 0
        result = {"합계": rep.get("합계"), "판": (rep.get("기준정보") or {}).get("판") if isinstance(rep.get("기준정보"), dict) else rep.get("판"),
                  "신고기한": due, "분납기한": ((rv or {}).get("분납기한") or {}).get("기한")}
        files = {"사실관계": os.path.abspath(facts) if not isinstance(facts, dict) else None,
                 "신고인": os.path.abspath(filer) if not isinstance(filer, dict) else None,
                 "출력": [os.path.abspath(p if os.path.isabs(p) else os.path.join(out, p)) for p in rep.get("파일") or []] if ok else []}
        fid = db.record(no, f, g, result, files, cli.evidence_names(customer.get("증빙")), "작성")
        rep["알림"].append("고객 DB: 고객번호 %s(%s), 신고 %s 를 %s 에 기록했다%s" % (
            no, "새로 등록" if new else "기존 고객", fid, db.root, "" if ok else ". 신고서를 아직 만들지 못한 상태로 기록했다"))
        rep["고객번호"], rep["신고번호"] = no, fid
    except Exception as e:      # 고객 DB 는 부가 기능이다. 신고서 결과를 막지 않는다
        rep["알림"].append("고객 DB 에 기록하지 못했다(%s: %s)" % (type(e).__name__, e))


def road_missing(facts, filer):
    """도로명주소가 빠진 곳의 문장 목록. 신고인 주소는 늘, 양도 물건은 토지(건물 없는 땅)가 아니면 도로명·건물본번이 있어야 한다."""
    try:
        f = _read_json(facts) if not isinstance(facts, dict) else facts
        g = _read_json(filer) if not isinstance(filer, dict) else filer
    except (OSError, ValueError):
        return []           # 파일을 못 읽는 경우는 make_return 이 알린다
    out = []
    addr = (g.get("신고인") or {}).get("주소") or {}
    if not (addr.get("도로명") and addr.get("건물본번")):
        out.append("신고인.주소: 도로명주소(도로명, 건물본번)를 적는다(사무소 규칙, 02 레코드 도로명 칸)")
    for a in f.get("자산") or []:
        if a.get("종류") == "토지":
            continue
        lot = (g.get("자산") or {}).get(a.get("id")) or {}
        if not (lot.get("도로명") and lot.get("건물본번")):
            out.append("자산.%s: 양도 물건 소재지의 도로명주소(도로명, 건물본번)를 적는다(사무소 규칙. 건물 없는 토지만 지번으로 신고)"
                       % a.get("id"))
    return out


def _read_json(path):
    import json
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _write_efile(rep, rv, out, agent, name, layout, facts=None, filer=None):
    try:
        if facts is not None and filer is not None:     # 05 소재지에 적을 물건별 도로명주소
            f = _read_json(facts) if not isinstance(facts, dict) else facts
            g = _read_json(filer) if not isinstance(filer, dict) else filer
            rv["_도로명"] = {a["id"]: dict(a.get("소재지") or {}, **((g.get("자산") or {}).get(a["id"]) or {}))
                           for a in f.get("자산") or [] if ((g.get("자산") or {}).get(a["id"]) or {}).get("도로명")}
        path = efile_writer.write(rv, out, agent=agent, name=name, layout=layout)
    except (ValueError, KeyError) as e:
        rep["단계"]["전자신고 파일"] = "만들지 못함"
        rep["알림"].append("전자신고 파일을 만들지 못했다. %s" % e)
        rep.update(종료코드=1, 상태="전자신고실패", 요약="신고서 PDF 는 만들었지만 전자신고 파일을 만들지 못했다")
        return rep
    with open(path, "rb") as fh:
        errors, warnings = efile_check.check(fh.read())
    rep["전자신고점검"] = {"오류": errors, "경고": warnings}
    if errors:      # 홈택스 형식검증에서 걸릴 파일은 내보내지 않는다
        os.remove(path)
        rep["단계"]["전자신고 파일"] = "만들지 않음(자체 형식검증 오류 %d건)" % len(errors)
        rep["알림"] += ["전자신고 파일 자체 형식검증 오류: %s" % x for x in errors]
        rep.update(종료코드=1, 상태="전자신고검증실패", 요약="신고서 PDF 는 만들었지만 전자신고 파일이 자체 형식검증을 통과하지 못해 지웠다")
        return rep
    rep["알림"] += ["전자신고 파일 자체 형식검증 경고: %s" % x for x in warnings]
    rep["단계"]["전자신고 파일"] = "만듦(자체 형식검증 통과%s)" % (", 경고 %d건" % len(warnings) if warnings else "")
    rep["파일"].append(path)
    rep["요약"] += ", 전자신고 파일 %s 를 만들었다" % os.path.basename(path)
    if agent:
        rep["확인사항"].append("세무대리인 신고라 전자신고세액공제(국세·지방소득세)를 0 으로 했다(납세자가 직접 전자신고할 때만 공제)")
    return rep


def main(argv=None):
    ap = argparse.ArgumentParser(description="양도소득세 신고서 PDF 와 전자신고 파일(C116300)을 만든다")
    ap.add_argument("--사실관계", required=True)
    ap.add_argument("--신고인", required=True, help="신고인 JSON 파일 경로(인적사항)")
    ap.add_argument("--세무대리인", default=DEFAULT_AGENT if os.path.exists(DEFAULT_AGENT) else None,
                    help="세무대리인 JSON 파일 경로(기본: efile/세무대리인.json). 사무소 양도세 전자신고는 늘 세무대리인 명의로 낸다")
    ap.add_argument("--출력", required=True)
    ap.add_argument("--파일명", help="전자신고 파일 이름(기본: 작성일자C116300.01)")
    ap.add_argument("--오늘", type=make_return.iso_date)
    ap.add_argument("--rules")
    ap.add_argument("--고객번호", type=int, help="고객 DB 고객번호. 없으면 주민등록번호로 찾고, 처음 보는 사람이면 새 번호를 준다")
    ap.add_argument("--고객정보", help="고객정보 JSON(휴대전화·관할세무서·환급계좌·메모 등, 고객정보_양식.json)")
    ap.add_argument("--증빙목록", help="증빙_목록.json. 물건의 출처(매매계약서 등) 문서 이름으로 남긴다")
    ap.add_argument("--고객DB", help="고객 DB 폴더(기본: efile/사무소설정.json 의 고객DB)")
    ap.add_argument("--기록안함", action="store_true", help="고객 DB 에 기록하지 않는다(시험용)")
    a = ap.parse_args(argv)
    customer = None if a.기록안함 else {"번호": a.고객번호, "정보": a.고객정보, "증빙": a.증빙목록, "DB": a.고객DB}
    rep = make(a.사실관계, a.신고인, a.출력, a.세무대리인, a.파일명, today=a.오늘, rules_dir=a.rules, customer=customer)
    code = rep["종료코드"]
    print(make_return.confirm_md(rep), file=sys.stderr if code == 4 else sys.stdout)
    return code


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")
        except AttributeError:
            pass
    sys.exit(main())
