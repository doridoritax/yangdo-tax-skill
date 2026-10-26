# -*- coding: utf-8 -*-
"""양도소득세 전자신고(변환신고) 파일 C116300 을 쓴다. 공개본에서 빠진 부분을 사무소에서 덧붙인 모듈이다.

규격: 국세청 「양도소득세 전자신고 파일설명서 V5.17(2026-04-28)」. 레코드 칸 목록은 efile/layout_c116300.json
(scripts/refresh/build_layout.py 가 설명서 표에서 뽑았다. 칸 길이 누적이 설명서 누적길이와 모두 맞는지 그때 검사한다).

쓰는 레코드: 01 HEADER, 02 기본사항, 03 세율별내역, 04 양수인내역, 05 양도소득금액 계산명세(C116400),
07 취득가액및필요경비 상세명세(C116600). 06(주식)·08~30(첨부서식)은 쓰지 않는다.

값의 출처:
  01  신고값 「신고」 절(구분코드·유형·과세기간·서식종류·작성일·양도일자), 「신고인」 절(주민등록번호·성명),
      세무대리인 JSON(사용자ID·전화·사업자번호·관리번호·성명·생년월일·세무프로그램코드)
  02  신고값 「신고인」 절(주소·법정동코드·전화·전자메일·내외국인·거주구분·거주지국·국적)
  03  신고값 「전자신고.세율별」(return_values.efile_rates) 를 아래 「03 행 규칙」으로 고쳐 쓴다
  04  신고값 「양수인」 절
  05  신고값 「전자신고.계산명세」
  07  신고값 「전자신고.필요경비명세」(레이아웃 칸 이름과 다른 키는 return_values.EXPENSE_RENAMES)

03 행 규칙(국세청 형식검증을 통과해 실제로 접수된 사무소 파일 118건이 모두 같은 꼴이다. 설명서와 다른 곳은 「설명서」로 적었다):
  - 차례: 세율구분 행들, 국내 소계(1·00), 합계(Z·00), 지방소득세(Z·98)
  - 지방소득세 행(Z·98)을 넣고 금액 칸은 모두 0(설명서 4번: 2020.1.1 이후 신고는 0)
  - 주민세_세율 01000 을 모든 행에 적는다(설명서 31번은 합계 행만이라고 적는다)
  - 농어촌특별세_세율 02000 을 세율구분 행에 적는다(설명서 23번 「20%」, 소계·합계는 00000)
  - 합계 행의 주민세_소득세자진납부할세액은 과세표준, 주민세_산출세액·주민세_자진납부세액은 지방소득세 신고서 합계 열의
    산출세액·납부할 세액(설명서 30번은 「19.자진납부세액과 일치」라고 적는다)

05 행 규칙(같은 118건의 꼴): calc_rows 설명. Null 허용 숫자 칸에 값이 없으면 공백.

숫자 칸: 왼쪽 0 채움. 소수 칸(5,2 / 11,3)은 소수점 없이 자릿수만큼 곱한 정수(53.05 → 05305). 음수는 '-' 다음 0 채움.
문자 칸: 왼쪽부터 KS X 1001(cp949) 바이트로 채우고 남는 자리는 공백. 칸보다 길면 ValueError(칸 이름만 적는다).
줄 끝은 CR/LF(설명서 「LINE SEQUENTIAL」).
"""
import json
import os
from decimal import ROUND_DOWN, Decimal

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAYOUT_PATH = os.path.join(SKILL_DIR, "efile", "layout_c116300.json")
ENCODING = "cp949"
EOL = b"\r\n"

PROGRAM_OTHER = "9000"              # 세무프로그램코드 「기타」(설명서 23번 표). 국세청에 코드를 받지 않은 프로그램은 이 값
TAXPAYER_KIND = {"Y": "01", "N": "09"}  # 납세자구분: 내국인 01 정상, 외국인 09(설명서 01 레코드 4번)
LOCAL_ROW = ("Z", "98")             # 지방소득세 행(설명서 03 레코드 3·4번)
RESIDENT_RATE = "10.00"             # 주민세_세율 10%(01000)
RURAL_RATE = "20.00"                # 농어촌특별세_세율 20%(02000)
# 07 행에서 레이아웃 칸 이름과 다른 신고값 키(return_values.EXPENSE_RENAMES 와 같은 표)
EXPENSE_RENAMES = {"필요경비신고자료일련번호": "일련번호", "구분코드": "전자코드", "사업자등록번호": "사업자번호"}
# 신고인 주소의 도로명주소 선택 키(신고인 JSON 신고인.주소) → 02 레코드 칸. 법정동 주소(법정동코드·번지)는 그대로 필수다
ROAD_FIELDS = {"도로명코드": "도로명_도로명코드", "도로명": "도로명_도로명", "지하": "도로명_지하만있는건물구분",
               "건물본번": "도로명_건물번호(본번)", "건물부번": "도로명_건물번호(부번)", "도로명아파트동": "도로명_아파트동(도로명)",
               "도로명아파트호": "도로명_아파트호(도로명)", "읍면동일련번호": "도로명_읍면동일련번호"}
# 건물번호는 NUMBER 칸이지만 접수된 파일은 모두 왼쪽부터 적고 남는 자리를 공백으로 둔다('80   ')
ROAD_NUMBER_TEXT = ("도로명_건물번호(본번)", "도로명_건물번호(부번)")


class RoadNumber(str):
    """왼쪽부터 적는 건물번호(숫자만)."""


def road_text(a, short=0):
    """도로명주소 글자. a 는 {시도, 시군구, 읍면동, 도로명, 건물본번, 건물부번, 아파트명, 아파트동, 아파트호}.
    「경상남도 창원시 마산회원구 양덕서5길 15, 104동 1402호 (양덕동, 양덕코오롱하늘채)」(도로명주소 표기 방법).
    short 1 은 괄호 참고항목을 빼고, 2 는 시도도 뺀다(좁은 칸)."""
    no = str(a.get("건물본번") or "")
    if a.get("건물부번") not in (None, "", "0", 0):
        no += "-%s" % a["건물부번"]
    head = [a.get("시군구"), a.get("도로명"), no] if short >= 2 else [a.get("시도"), a.get("시군구"), a.get("도로명"), no]
    text = " ".join(str(x) for x in head if x)
    unit = []
    dong, ho = a.get("도로명아파트동") or a.get("아파트동"), a.get("도로명아파트호") or a.get("아파트호")
    if dong:
        unit.append(dong if str(dong).endswith("동") else "%s동" % dong)
    if ho:
        unit.append(ho if str(ho).endswith("호") else "%s호" % ho)
    if unit:
        text += ", " + " ".join(unit)
    ref = [x for x in (a.get("읍면동"), a.get("아파트명")) if x]
    if ref and not short:
        text += " (%s)" % ", ".join(ref)
    return text


def road_text_fit(a, size):
    """칸(바이트)에 들어가는 가장 긴 도로명주소 글자. 어느 것도 안 들어가면 ValueError."""
    for s in (0, 1, 2):
        t = road_text(a, s)
        if len(t.encode(ENCODING)) <= size:
            return t
    raise ValueError("도로명주소가 05 소재지 칸(%d바이트)보다 길다" % size)


LAND_KIND = "01"                    # 05 자산의종류 토지
WHOLE_SHARE = 100                 # 단독 소유(분자 = 분모) 지분은 100/100 으로 적는다(접수된 파일 꼴)
NO_EXEMPT_BLANK = ("1세대1주택비과세_보유기간", "1세대1주택_비과세_거주기간")
AGENT_KEYS = {"사용자ID", "전화", "사업자번호", "관리번호", "성명", "생년월일", "대표자성명", "대표자주민등록번호",
              "세무프로그램코드", "파일설명"}


def load_layout(path=None):
    with open(path or LAYOUT_PATH, encoding="utf-8") as f:
        return json.load(f)


def load_agent(path):
    """세무대리인 JSON. _ 로 시작하는 키는 설명이라 읽지 않는다. 모르는 키가 있으면 ValueError."""
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    d = {k: v for k, v in d.items() if not k.startswith("_")}
    unknown = set(d) - AGENT_KEYS
    if unknown:
        raise ValueError("세무대리인 파일에 모르는 키: %s" % ", ".join(sorted(unknown)))
    if not d.get("성명"):
        raise ValueError("세무대리인 파일에 성명이 없다(01 레코드 세무대리인성명 필수)")
    if not (d.get("관리번호") or d.get("생년월일")):
        raise ValueError("세무대리인 파일에 관리번호나 생년월일 중 하나가 있어야 한다(설명서 01 레코드 22·27번)")
    return d


def _digits(v):
    return "".join(ch for ch in str(v or "") if ch.isdigit())


def _cell(f, v):
    """레이아웃 칸 하나를 바이트로."""
    n, name = f["len"], f["name"]
    if f["type"] == "N" and f.get("null") and v in (None, ""):
        return b" " * n                 # Null 허용 숫자 칸에 값이 없으면 공백(도로명 건물번호 등)
    if isinstance(v, RoadNumber):
        if not v.isdigit() or len(v) > n:
            raise ValueError("%s 칸에는 %d자리 이하 숫자만 적는다" % (name, n))
        return v.encode("ascii") + b" " * (n - len(v))
    if f["type"] == "N":
        d = Decimal(str(v if v not in (None, "") else 0))
        scaled = int((d * (Decimal(10) ** f["dec"])).to_integral_value(rounding=ROUND_DOWN))
        text = ("-" + str(-scaled).zfill(n - 1)) if scaled < 0 else str(scaled).zfill(n)
        if len(text) > n:
            raise ValueError("%s 칸(%d자리)에 숫자가 넘친다" % (name, n))
        return text.encode("ascii")
    if isinstance(v, bool):
        raise ValueError("%s 칸에 참·거짓 값이 왔다" % name)
    if isinstance(v, int):
        text = str(v).zfill(n)
    else:
        text = "" if v is None else str(v)
    try:
        b = text.encode(ENCODING)
    except UnicodeEncodeError:
        raise ValueError("%s 칸에 KS X 1001 로 쓸 수 없는 글자가 있다" % name)
    if len(b) > n:
        raise ValueError("%s 칸(%d바이트)보다 값이 길다" % (name, n))
    return b + b" " * (n - len(b))


def record(layout, no, values):
    """레코드 한 줄(줄 끝 제외). 자료구분·서식코드는 레이아웃의 check 값, 공란은 공백. 모르는 키가 있으면 ValueError."""
    rec = layout["레코드"][no]
    names = {f["name"] for f in rec["필드"]}
    unknown = set(values) - names
    if unknown:
        raise ValueError("%s 레코드에 없는 칸: %s" % (no, ", ".join(sorted(unknown))))
    out = b""
    for f in rec["필드"]:
        if f["name"] in ("자료구분", "서식코드"):
            v = f["check"]
        elif f["name"] == "공란":
            v = ""
        else:
            v = values.get(f["name"])
        out += _cell(f, v)
    if len(out) != rec["길이"]:
        raise ValueError("%s 레코드 길이 %d ≠ %d" % (no, len(out), rec["길이"]))
    return out


# ------------------------------------------------------------ 레코드별 값

def header(rv, agent):
    s, p = rv["신고"], rv["신고인"]
    a = agent or {}
    return {
        "납세자ID": _digits(p.get("주민등록번호")) or p.get("주민등록번호"),
        "납세자구분": TAXPAYER_KIND.get(p["코드"].get("내외국인여부"), "01"),
        "세목코드": "22", "신고구분코드": s["구분코드"], "신고유형": s["유형"], "과세기간_년월": s["과세기간"],
        "신고구분상세코드": s["상세코드"], "신고서종류코드": s["서식종류"], "민원종류코드": "FD001",
        "사용자ID": a.get("사용자ID") or s.get("홈택스ID"), "제출년월": s["제출년월"], "성명": p.get("성명"),
        "세무대리대표자주민등록번호": _digits(a.get("대표자주민등록번호")), "세무대리대표자성명": a.get("대표자성명"),
        "세무대리인전화번호": _digits(a.get("전화")), "세무대리사업자등록번호": _digits(a.get("사업자번호")),
        "세무대리인관리번호": (a.get("관리번호") or "").replace("-", ""),
        "세무프로그램코드": a.get("세무프로그램코드") or PROGRAM_OTHER,
        "작성일자": s["작성일"], "양도일자": s["양도일자"], "세무대리인성명": a.get("성명"),
        "세무대리인생년월일": _digits(a.get("생년월일")),
    }


def basics(rv):
    p = rv["신고인"]
    addr, code = p.get("주소") or {}, p["코드"]
    road = {field: addr.get(key) for key, field in ROAD_FIELDS.items() if addr.get(key) not in (None, "")}
    for field in ROAD_NUMBER_TEXT:
        if field in road:
            road[field] = RoadNumber(road[field])
    return dict(road, **{
        "주소_법정동코드": addr.get("법정동코드"), "주소_특수지코드": addr.get("특수지") or "0",
        "주소_번지": addr.get("번지"), "주소_호": addr.get("호") or "0", "주소_아파트명": addr.get("아파트명"),
        "주소_아파트동": addr.get("아파트동"), "주소_아파트호": addr.get("아파트호"),
        "전화번호": _digits(p.get("전화")), "전자메일주소": p.get("전자메일"),
        "내외국인여부": code.get("내외국인여부"), "거주구분": code.get("거주구분"),
        "거주지국코드": code.get("거주지국"), "거주지국명": code.get("거주지국명"), "국적코드": code.get("국적"),
    })


def rate_rows(rv):
    """03 행. 신고값 세율별 행을 모듈 설명의 「03 행 규칙」으로 고친다."""
    rows = [dict(r) for r in rv["전자신고"]["세율별"]]
    special = [r for r in rows if r["세율구분"] == "00"]
    body = [r for r in rows if r["세율구분"] != "00"]
    if not body:        # 전액 비과세 건: 과세 열이 없다. 계산명세의 세율구분마다 금액 0 인 행을 넣는다(접수된 파일 꼴)
        keys = dict.fromkeys((r["국내외분(소재지)"], r["세율구분"]) for r in rv["전자신고"]["계산명세"])
        body = [{"국내외분": d, "세율구분": s, "세율": "0.00"} for d, s in keys]
    total = next(r for r in special if r["국내외분"] == "Z")
    local_total = rv["지방"]["열"]["합계"]
    for r in body:
        r["농어촌특별세_세율"] = RURAL_RATE
        if not r.get("과세표준"):
            r["세율"] = "0.00"          # 과세표준이 0 인 행은 세율도 0(접수된 파일 꼴. 기본공제 안의 소액 차익 등)
    for r in body + special:
        r["주민세_세율"] = RESIDENT_RATE
    total["주민세_소득세자진납부할세액"] = total["과세표준"]
    total["주민세_산출세액"] = local_total["산출세액"]
    total["주민세_자진납부세액"] = local_total["납부할세액"]
    local = {"국내외분": LOCAL_ROW[0], "세율구분": LOCAL_ROW[1], "주민세_세율": RESIDENT_RATE}
    sub = [r for r in special if r["국내외분"] != "Z"]
    return body + sub + [total, local]


def buyer_rows(rv):
    out = []
    for b in rv["양수인"]:
        out.append({"일련번호": b["일련번호"], "양수인_주민사업자구분": b.get("구분"),
                    "양수인_내외국인_구분코드": b.get("내외국인"), "양수인_주민등록번호": _digits(b.get("번호")),
                    "양수인_성명": b.get("성명"), "양수인_전화번호": _digits(b.get("전화")),
                    "양수인_지분(분자)": b.get("지분분자"), "양수인_지분(분모)": b.get("지분분모"),
                    "양수인_양도자와의관계": b.get("관계")})
    return out


def calc_rows(rv, layout):
    """05 행. 신고값 계산명세에서 두 칸을 고친다(모듈 설명의 05 행 규칙).
    - 장기보유특별공제적용구분코드: 엔진은 ZZ 를 넣는다(규칙 코드표에 「규격서에 값 설명이 없다」). 접수된 파일 118건은
      부표1 ⑯ 장특공 코드와 같은 값(01 표2, 02 표1, 03 적용배제)을 쓴다. 부표1 의 그 자산 코드를 옮긴다
    - 1세대1주택비과세_보유기간·거주기간: 1세대1주택이 아니어서 엔진이 ZZ(해당없음)를 넣은 칸은 공백으로 둔다(접수된 파일 꼴)
    - 총면적 지분: 단독 소유(분자 = 분모)는 100/100 으로 적는다(접수된 파일 꼴. 공동 소유는 1/3 처럼 그대로)"""
    names = {f["name"] for f in layout["레코드"]["05"]["필드"]}
    ltd = {s["자산"]: s.get("장특공코드") for s in rv.get("부표1") or []}
    out = []
    for r in rv["전자신고"]["계산명세"]:
        row = {k: v for k, v in r.items() if k in names}
        if ltd.get(r.get("자산")):
            row["장기보유특별공제적용구분코드"] = ltd[r["자산"]]
        road = (rv.get("_도로명") or {}).get(r.get("자산"))
        if road:            # 05 에는 도로명 칸이 없다. 자유 글 「소재지」(60바이트)에 도로명주소를 적는다
            row["소재지"] = road_text_fit(road, 60)
        for k in NO_EXEMPT_BLANK:
            if row.get(k) == "ZZ":
                row[k] = ""
        for part in ("토지", "건물"):
            num, den = ("거래자산면적_총면적_%s_지분(%s)" % (part, x) for x in ("분자", "분모"))
            if part == "건물" and r.get("자산의종류") == LAND_KIND and not r.get("거래자산면적_총면적_건물_면적"):
                row[num] = row[den] = 0         # 토지만 판 건은 건물 지분을 0/0 으로 둔다(접수된 파일 꼴)
            elif row.get(num) and row.get(num) == row.get(den):
                row[num] = row[den] = WHOLE_SHARE
        out.append(row)
    return out


def expense_rows(rv, layout):
    out = []
    for r in rv["전자신고"]["필요경비명세"]:
        row = {}
        for f in layout["레코드"]["07"]["필드"]:
            key = EXPENSE_RENAMES.get(f["name"], f["name"])
            if f["name"] in ("자료구분", "서식코드", "공란"):
                continue
            row[f["name"]] = r.get(key)
        out.append(row)
    return out


def lines(rv, agent=None, layout=None):
    """전자신고 파일 줄(bytes) 목록. 신고값에 「전자신고」 절이 없으면(레이아웃 없이 만든 신고값) ValueError."""
    layout = layout or load_layout()
    if not rv.get("전자신고"):
        raise ValueError("신고값에 전자신고 절이 없다. 레이아웃을 읽은 신고값으로 다시 만든다")
    out = [record(layout, "01", header(rv, agent)), record(layout, "02", basics(rv))]
    out += [record(layout, "03", r) for r in rate_rows(rv)]
    out += [record(layout, "04", r) for r in buyer_rows(rv)]
    out += [record(layout, "05", r) for r in calc_rows(rv, layout)]
    out += [record(layout, "07", r) for r in expense_rows(rv, layout)]
    return out


def file_name(rv, seq=1):
    """설명서 「파일명을 부여하는 방법」: 작성일자 + C116300 + . + 두 자리 순번."""
    return "%sC116300.%02d" % (rv["신고"]["작성일"], seq)


def write(rv, out_dir, agent=None, name=None, layout=None):
    data = b"".join(x + EOL for x in lines(rv, agent, layout))
    path = os.path.join(out_dir, name or file_name(rv))
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)
    return path
