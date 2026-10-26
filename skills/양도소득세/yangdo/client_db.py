# -*- coding: utf-8 -*-
"""양도소득세 고객 DB(JSON 누적). 사무소에서 덧붙인 모듈이다(공개본에 없음).

폴더 구조(DB 경로는 efile/사무소설정.json 의 「고객DB」, 없으면 DEFAULT_ROOT):
  색인.json              고객번호·성명·주민번호 끝 7자리 가림·전화·물건 수·신고 수, 다음 고객번호·신고 일련번호
  고객/<고객번호>.json    고객 한 사람의 모든 것(아래 모양)
  자료/<신고번호>/        그 신고의 사실관계.json·신고인.json·전자신고 파일 사본

고객 JSON:
  고객번호, 등록일자, 수정일자
  인적사항   성명·주민등록번호·내외국인·국적·거주구분·거주지국·전화·휴대전화·이메일·주소(법정동·도로명)
  관할       관할세무서·세무서코드·지방세관할
  환급계좌   은행·계좌번호
  물건[]     물건번호(고객 안 일련번호), 종류, 소재지(시도·시군구·읍면동·번지·호·아파트명·동·호·법정동코드), 면적, 지분,
             취득(일자·원인·가액·상대방), 양도(일자·원인·가액·양수인), 출처(매매계약서 등 증빙 문서명)
  신고[]     신고번호(DB 전체 일련번호 YYYY-NNNN), 양도구분, 신고구분, 작성일(신고일자), 신고기한(납부기한), 물건번호[],
             세액(산출세액·지방소득세·가산세·분납), 파일(사실관계·신고인·전자신고·신고서 PDF 경로), 기준정보판, 상태
  세대       마지막으로 받은 세대 주택 목록(다음 신고 때 다시 묻지 않고 확인만 받는다)
  메모[]     {일자, 내용}
  이력[]     {일시, 내용} 이 파일을 바꾼 기록

같은 사람 찾기: 주민등록번호가 같으면 같은 고객. 같은 물건 찾기: 법정동코드·번지·호·아파트동·아파트호가 같으면 같은 물건.
쓰기는 임시 파일에 쓴 뒤 바꿔 끼운다. 주민등록번호가 들어 있으므로 DB 폴더는 공유하지 않는다.
"""
import copy
import datetime
import json
import os
import shutil

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETTINGS = os.path.join(SKILL_DIR, "efile", "사무소설정.json")
DEFAULT_ROOT = os.path.join(os.path.expanduser("~"), "Documents", "양도세_고객DB")
INDEX = "색인.json"
PEOPLE = "고객"
KEEP = "자료"
# 고객정보 JSON(신고인 JSON 에 없는 양도인 인적사항 칸)에서 받는 키 → 고객 JSON 자리
EXTRA_KEYS = {
    "고객번호": None, "휴대전화": ("인적사항", "휴대전화"), "이메일": ("인적사항", "이메일"),
    "관할세무서": ("관할", "관할세무서"), "세무서코드": ("관할", "세무서코드"), "지방세관할": ("관할", "지방세관할"),
    "환급은행": ("환급계좌", "은행"), "환급계좌": ("환급계좌", "계좌번호"), "양도구분": None, "메모": None,
}
TRANSFER_KINDS = ("부동산", "주식", "파생상품", "국외자산", "토지등매매차익")
STATES = ("작성", "제출", "취소")


def _now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def _today():
    return datetime.date.today().isoformat()


def root(path=None):
    if path:
        return path
    try:
        with open(SETTINGS, encoding="utf-8") as f:
            return json.load(f).get("고객DB") or DEFAULT_ROOT
    except (OSError, ValueError):
        return DEFAULT_ROOT


def _read(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return copy.deepcopy(default)


def _write(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def _mask(rrn):
    rrn = "".join(ch for ch in str(rrn or "") if ch.isdigit())
    return rrn[:6] + "-*******" if len(rrn) == 13 else ""


class Db:
    def __init__(self, path=None):
        self.root = root(path)
        self.index_path = os.path.join(self.root, INDEX)
        self.index = _read(self.index_path, {"다음고객번호": 1, "신고일련번호": {}, "고객": {}})

    def path(self, no):
        return os.path.join(self.root, PEOPLE, "%s.json" % no)

    def load(self, no):
        c = _read(self.path(no))
        if c is None:
            raise KeyError("고객번호 %s 가 DB 에 없다" % no)
        return c

    def find(self, rrn=None, name=None, no=None):
        """조건에 맞는 고객번호 목록."""
        rrn = "".join(ch for ch in str(rrn or "") if ch.isdigit())
        out = []
        for k, v in self.index["고객"].items():
            if no is not None and str(no) != k:
                continue
            if rrn and v.get("_주민") != rrn:
                continue
            if name and name not in (v.get("성명") or ""):
                continue
            out.append(k)
        return out

    def save(self, c, what):
        c["수정일자"] = _today()
        c.setdefault("이력", []).append({"일시": _now(), "내용": what})
        _write(self.path(c["고객번호"]), c)
        p = c["인적사항"]
        self.index["고객"][str(c["고객번호"])] = {
            "성명": p.get("성명"), "주민번호": _mask(p.get("주민등록번호")), "_주민": "".join(ch for ch in str(p.get("주민등록번호") or "") if ch.isdigit()),
            "전화": p.get("휴대전화") or p.get("전화"), "물건수": len(c.get("물건") or []), "신고수": len(c.get("신고") or []),
            "마지막신고": (c.get("신고") or [{}])[-1].get("신고번호"), "수정일자": c["수정일자"]}
        _write(self.index_path, self.index)

    # ------------------------------------------------------------ 고객

    def upsert(self, filer, extra=None, no=None):
        """신고인 JSON(+고객정보 JSON)으로 고객을 만들거나 고친다. (고객번호, 새로만듦 여부)."""
        p = filer.get("신고인") or {}
        extra = dict(extra or {})
        no = no or extra.pop("고객번호", None)
        found = self.find(rrn=p.get("주민등록번호")) if p.get("주민등록번호") else []
        if no is None and found:
            no = found[0]
        new = no is None or str(no) not in self.index["고객"]
        if no is None:
            no = self.index["다음고객번호"]
        no = int(no)
        self.index["다음고객번호"] = max(self.index["다음고객번호"], no + 1)
        c = self.load(no) if not new else {
            "고객번호": no, "등록일자": _today(), "인적사항": {}, "관할": {}, "환급계좌": {}, "물건": [], "신고": [],
            "세대": None, "메모": [], "이력": []}
        person = c["인적사항"]
        for k in ("성명", "주민등록번호", "내외국인", "거주구분", "거주지국", "국적", "전화", "전자메일", "주소"):
            if p.get(k) not in (None, "", {}):
                person["이메일" if k == "전자메일" else k] = copy.deepcopy(p[k])
        refund = filer.get("환급계좌") or {}
        if refund:
            c["환급계좌"].update({"은행": refund.get("은행"), "계좌번호": refund.get("계좌번호")})
        unknown = [k for k in extra if k not in EXTRA_KEYS and not k.startswith("_")]
        if unknown:
            raise ValueError("고객정보에 모르는 키: %s" % ", ".join(unknown))
        for k, v in extra.items():
            if k.startswith("_") or v in (None, ""):
                continue
            if k == "메모":
                c["메모"].append({"일자": _today(), "내용": v})
            elif k == "양도구분":
                if v not in TRANSFER_KINDS:
                    raise ValueError("양도구분은 %s 중 하나" % ", ".join(TRANSFER_KINDS))
                c["양도구분"] = v
            else:
                sec, key = EXTRA_KEYS[k]
                c[sec][key] = v
        self.save(c, "고객 %s" % ("등록" if new else "정보 갱신"))
        return no, new

    # ------------------------------------------------------------ 물건

    @staticmethod
    def _place(asset, lot, bjd=None):
        loc = dict(asset.get("소재지") or {})
        lot = lot or {}
        for k in ("특수지", "번지", "호", "아파트명", "아파트동", "아파트호", "법정동코드"):
            if lot.get(k) not in (None, ""):
                loc[k] = lot[k]
        return loc

    @staticmethod
    def _same_place(a, b):
        keys = ("법정동코드", "번지", "호", "아파트동", "아파트호")
        return all((a.get(k) or "") == (b.get(k) or "") for k in keys) and any(a.get(k) for k in keys)

    def add_property(self, c, asset, lot, buyers, evidence=None):
        """사실관계 자산 하나(+신고인 JSON 지번·양수인)를 물건 목록에 넣거나 고친다. 물건번호를 돌려준다."""
        place = self._place(asset, lot)
        sale, buy = asset.get("양도") or {}, asset.get("취득") or {}
        item = {
            "종류": asset.get("종류"), "주택유형": asset.get("주택유형"), "소재지": place, "면적": asset.get("면적"),
            "지분": asset.get("지분"),
            "취득": {"일자": min(d for d in (buy.get("잔금일"), buy.get("등기접수일"), buy.get("대금완납일")) if d)
                   if any((buy.get("잔금일"), buy.get("등기접수일"), buy.get("대금완납일"))) else None,
                   "잔금일": buy.get("잔금일"), "등기접수일": buy.get("등기접수일"), "계약일": buy.get("계약일"), "원인": buy.get("원인"),
                   "전체가액": asset.get("전체취득가액"), "상대방": (lot or {}).get("취득상대방")},
            "양도": {"일자": min(d for d in (sale.get("잔금일"), sale.get("등기접수일"), sale.get("대금완납일")) if d)
                   if any((sale.get("잔금일"), sale.get("등기접수일"), sale.get("대금완납일"))) else None,
                   "잔금일": sale.get("잔금일"), "등기접수일": sale.get("등기접수일"), "계약일": sale.get("계약일"), "원인": sale.get("원인"),
                   "전체가액": asset.get("전체양도가액"),
                   "양수인": [{"성명": b.get("성명"), "구분": b.get("구분"), "지분": b.get("지분")} for b in buyers]},
            "필요경비": asset.get("필요경비"), "출처": evidence or [],
        }
        for old in c["물건"]:
            if self._same_place(old["소재지"], place):
                keep = old["물건번호"]
                old.update({k: v for k, v in item.items() if v not in (None, [], {})})
                old["물건번호"] = keep
                return keep
        item["물건번호"] = max([x["물건번호"] for x in c["물건"]] or [0]) + 1
        c["물건"].append(item)
        return item["물건번호"]

    # ------------------------------------------------------------ 신고

    def next_filing_no(self, year):
        n = self.index["신고일련번호"].get(str(year), 0) + 1
        self.index["신고일련번호"][str(year)] = n
        return "%s-%04d" % (year, n)

    def record(self, no, facts, filer, result=None, files=None, evidence=None, state="작성", kind_of_transfer=None):
        """신고 한 건을 기록한다. 같은 작성일·같은 물건 묶음의 「작성」 기록이 있으면 새로 만들지 않고 고친다. 신고번호를 돌려준다."""
        c = self.load(no)
        s = filer.get("신고") or {}
        nos = []
        for a in facts.get("자산") or []:
            lot = (filer.get("자산") or {}).get(a.get("id"))
            buyers = [b for b in filer.get("양수인") or [] if b.get("자산") == a.get("id")]
            nos.append(self.add_property(c, a, lot, buyers, evidence))
        if facts.get("세대"):
            c["세대"] = {"기준일": s.get("작성일"), **copy.deepcopy(facts["세대"])}
        result = result or {}
        entry = {
            "양도구분": kind_of_transfer or c.get("양도구분") or "부동산", "신고구분": s.get("구분"), "작성일": s.get("작성일"),
            "신고기한": result.get("신고기한"), "분납기한": result.get("분납기한"), "물건번호": nos,
            "세액": result.get("합계"), "기준정보판": result.get("판"), "파일": files or {}, "상태": state,
        }
        same = [f for f in c["신고"] if f["상태"] == "작성" and f["작성일"] == entry["작성일"] and f["물건번호"] == nos]
        if same:
            fid = same[-1]["신고번호"]
            what = "신고 %s 다시 만듦" % fid
        else:
            fid = self.next_filing_no((s.get("작성일") or _today())[:4])
            what = "신고 %s 기록" % fid
        entry["보관"] = self.keep(fid, facts, filer, files)
        if same:
            same[-1].update({k: v for k, v in entry.items() if v not in (None, {}, [])})
        else:
            entry["신고번호"] = fid
            c["신고"].append(entry)
        self.save(c, what)
        return fid

    def keep(self, fid, facts, filer, files):
        """신고마다 자료/<신고번호>/ 에 사실관계·신고인 JSON 과 전자신고 파일 사본을 남긴다(원래 작업 폴더가 지워져도 남게)."""
        d = os.path.join(self.root, KEEP, fid)
        _write(os.path.join(d, "사실관계.json"), facts)
        _write(os.path.join(d, "신고인.json"), filer)
        kept = {"폴더": d}
        for p in (files or {}).get("출력") or []:
            if os.path.basename(p).upper().find("C116300") >= 0 and os.path.isfile(p):
                shutil.copy2(p, os.path.join(d, os.path.basename(p)))
                kept["전자신고"] = os.path.join(d, os.path.basename(p))
        return kept

    def set_state(self, no, fid, state):
        if state not in STATES:
            raise ValueError("상태는 %s 중 하나" % ", ".join(STATES))
        c = self.load(no)
        f = next((x for x in c["신고"] if x["신고번호"] == fid), None)
        if f is None:
            raise KeyError("신고번호 %s 가 고객 %s 에 없다" % (fid, no))
        f["상태"] = state
        self.save(c, "신고 %s 상태 %s" % (fid, state))

    def same_year(self, no, year):
        """그 해에 이미 기록된 신고(확정신고 합산·기본공제 확인용)."""
        c = self.load(no)
        out = []
        for f in c["신고"]:
            sold = [x["양도"]["일자"] for x in c["물건"] if x["물건번호"] in f["물건번호"] and x["양도"].get("일자")]
            if any(d.startswith(str(year)) for d in sold):
                out.append({"신고번호": f["신고번호"], "신고구분": f["신고구분"], "작성일": f["작성일"], "상태": f["상태"],
                            "양도일": sold, "세액": f.get("세액")})
        return out
