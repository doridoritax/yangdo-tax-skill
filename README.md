# 양도소득세 스킬 + 홈택스 전자신고 파일 생성기 (Claude Code)

부동산 양도소득세를 계산하고, 신고서 PDF와 **홈택스 「파일변환신고」용 전자신고 파일(C116300)** 까지 만드는 Claude Code 스킬입니다.

계산 엔진과 신고서 PDF는 [hany202507/finance-ai-skills](https://github.com/hany202507/finance-ai-skills)의 `양도소득세` 스킬(MIT)을 그대로 쓰고, 공개본에 없는 아래 기능을 덧붙였습니다.

| 덧붙인 것 | 파일 | 내용 |
|---|---|---|
| 전자신고 파일 생성 | `scripts/make_efile.py`, `yangdo/efile_writer.py`, `efile/layout_c116300.json` | 국세청 「양도소득세 전자신고 파일설명서 V5.17」(2026-04-28) 레이아웃으로 01·02·03·04·05·07 레코드를 쓴다 |
| 자체 형식검증 | `yangdo/efile_check.py` | 파일을 쓴 직후 길이·숫자·날짜·코드·필수 칸·합계를 검사한다. 오류가 있으면 파일을 지운다 |
| 전액 비과세 신고 | `scripts/make_efile.py` | 1세대1주택 전액 비과세 건도 신고서와 전자신고 파일을 만든다 |
| 도로명주소 | `yangdo/efile_writer.py` | 신고인 주소(02 도로명 칸)와 양도 물건 소재지(05 소재지 칸)를 도로명주소로 적는다 |
| 고객 DB | `yangdo/client_db.py`, `scripts/client_db.py` | 고객·양도 물건·신고 이력을 JSON 으로 쌓는다(신고번호 YYYY-NNNN) |

홈택스 형식검증에서 과세 건, 전액 비과세 건, 도로명주소 반영 건이 오류 없이 통과하는 것을 확인했습니다(2026-10). 그래도 **결과는 검토용 초안**입니다. 신고 전 최종 판단은 세무 전문가가 하세요.

## 설치

```bash
git clone https://github.com/doridoritax/yangdo-tax-skill.git
```

`skills/양도소득세` 폴더를 `~/.claude/skills/양도소득세` 로 복사하고, 파이썬 패키지를 설치합니다(Python 3.10 이상).

```bash
pip install -r ~/.claude/skills/양도소득세/requirements.txt
```

## 설정(선택)

| 파일 | 쓰는 때 |
|---|---|
| `efile/세무대리인.json` | 세무대리인 명의로 신고할 때. `efile/세무대리인_양식.json` 을 복사해 채웁니다. 없으면 납세자 직접 신고로 보고 전자신고세액공제를 넣습니다 |
| `efile/사무소설정.json` | 고객 DB 폴더를 바꿀 때. `efile/사무소설정_양식.json` 을 복사합니다(기본: `문서\양도세_고객DB`) |

두 파일과 고객 DB 에는 인적사항이 들어가므로 `.gitignore` 로 저장소에 올리지 않습니다.

## 사용

Claude Code 에서 「양도세 계산해줘」, 「계약서 올릴게」처럼 말하면 스킬이 사실관계를 모아 계산합니다. 신고서와 전자신고 파일은:

```bash
python scripts/make_efile.py --사실관계 facts.json --신고인 신고인.json --출력 <폴더>
```

자세한 절차는 `skills/양도소득세/SKILL.md`(6~8절이 덧붙인 기능)에 있습니다.

## 다루지 않는 것

조세특례제한법 감면, 양도차손 통산이 필요한 여러 자산 건, 같은 날 주택 여러 채 양도, 입주권·분양권, 수용·교환·부담부증여, 기한후·수정신고. 이런 건은 계산하지 않고 「다루지 않음」으로 멈춥니다(`references/적용한계.md`).

## 라이선스

MIT. 원저작물 저작권 표시는 `LICENSE` 에 그대로 두었습니다.
