#!/usr/bin/env python3
"""이안스튜디오 홈페이지 자체 점검 (표준 라이브러리만 사용)

사용법:
    python3 verify.py            # 로컬 파일만 점검 (빠름)
    python3 verify.py --live     # 배포된 라이브 페이지까지 점검 (50초 정도 소요)

종료 코드: 0 = 모두 통과, 1 = 실패 있음
"""
import os
import re
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
BOTH, LOCAL, LIVE = 0, 1, 2          # 점검 범위 (BOTH=어디서든, LOCAL=로컬만, LIVE=라이브만)

results = []


def check(scope, name, cond, detail=""):
    results.append((scope, name, bool(cond), detail))


def read(fn):
    p = os.path.join(ROOT, fn)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return f.read()


def section(html, sec_id):
    """<section id="x"> ... </section> 또는 <div class="tab-panel" id="x"> 내용만 뽑기"""
    m = re.search(r'id="%s"' % re.escape(sec_id), html)
    if not m:
        return ""
    rest = html[m.end():]
    nxt = re.search(r'id="(?!%s)[a-zA-Z\-]+"' % re.escape(sec_id), rest)
    return rest[:nxt.start()] if nxt else rest


def build_checks(idx):
    # ---------- 구조 ----------
    order = re.findall(r'<section[^>]*class="([^"]+)"', idx)
    order = [c.split()[0] for c in order]
    check(BOTH, "섹션 순서 (히어로→…→예약→오시는길)",
          order == ["hero", "about", "services", "gallery", "insta-feed", "pricing",
                    "snap-pricing", "reserve", "visit"], " / ".join(order))
    check(BOTH, "리뷰 이벤트 섹션 제거됨", 'class="event"' not in idx)
    check(BOTH, "촬영 준비사항 섹션 제거됨", "촬영 전 준비사항" not in idx and 'id="prep"' not in idx)

    # ---------- 서비스 카드 → 가격 이동 ----------
    ctas = re.findall(r'class="service".*?</div>', idx, re.S)
    hrefs = re.findall(r'class="more">가격 보기 →', idx)
    check(BOTH, "서비스 카드 6개가 '가격 보기'", len(hrefs) == 6, "%d개" % len(hrefs))
    check(BOTH, "문의하기 카드 링크 없음", 'class="more">문의하기' not in idx)
    for aid in ("price-family", "price-portrait", "price-doc"):
        check(BOTH, "가격 앵커 #%s 존재" % aid, 'id="%s"' % aid in idx)

    # ---------- 가격표: 가족사진 ----------
    fam = section(idx, "price-family")
    check(BOTH, "가족사진 4단 유지", len(re.findall(r'class="price-item', fam)) == 4,
          "%d단" % len(re.findall(r'class="price-item', fam)))
    check(BOTH, "가족사진 '스페셜' 제거", "스페셜" not in fam and "인당 2만원" not in fam)

    # ---------- 스냅 상품: 탭별 카드 (이름, 가격) ----------
    expect = {
        "dol": [("돌스냅 · 데이터형", "33만원"), ("돌스냅 · 액자형", "43만원"),
                ("압축앨범형", "50만원"), ("화보앨범형", "60만원"), ("아이폰스냅 추가", "25만원")],
        "chilsun": [("칠순잔치 · BASIC", "33만원"), ("칠순잔치 · STANDARD", "60만원"),
                    ("아이폰스냅 추가", "25만원")],
        "wedding-package": [("베이직 패키지", "105만원"), ("스탠다드 패키지", "125만원"),
                            ("스냅 + 영상 + 아이폰", "130만원")],
    }
    for tab, cards in expect.items():
        body = section(idx, tab)
        names = re.findall(r'class="snap-name">([^<]+)', body)
        prices = re.findall(r'class="snap-price">([^<]+)', body)
        for (nm, pr), got_nm in zip(cards, names):
            check(BOTH, "[%s] %s 이름" % (tab, nm), got_nm.startswith(nm), got_nm)
        for (nm, pr), got_pr in zip(cards, prices):
            check(BOTH, "[%s] %s 가격 %s" % (tab, nm, pr), got_pr == pr, got_pr)

    # ---------- 개별 문구 ----------
    dol = section(idx, "dol")
    check(BOTH, "돌스냅 화보앨범 11×14 40p", "11×14 40p 화보앨범" in dol and "11x14" not in idx)
    chil = section(idx, "chilsun")
    check(BOTH, "칠순 BASIC 온라인 데이터 전달", "온라인 데이터 전달" in chil and "고급 인화" not in idx)
    check(BOTH, "칠순 보정 20컷 ×2", chil.count("전문 보정 20컷") == 2 and "보정 30컷" not in chil)
    wpack = section(idx, "wedding-package")
    check(BOTH, "웨딩 베이직 라벨", "베이직 패키지 <em>스냅+영상 데이터형</em>" in wpack)
    check(BOTH, "웨딩 스탠다드 라벨", "스탠다드 패키지 <em>앨범+영상 데이터형</em>" in wpack)

    # ---------- 갤러리: nums 배열 == 실제 파일 (404 방지) ----------
    gal_dir = os.path.join(ROOT, "images", "gallery")
    if os.path.isdir(gal_dir):
        files = os.listdir(gal_dir)
        for cid, pref, nums in re.findall(
                r"id:\s*'(\w+)',\s*prefix:\s*'(\w+)_',\s*nums:\s*\[([^\]]*)\]", idx):
            want = sorted(int(x) for x in nums.split(",") if x.strip())
            have = sorted(int(n) for n in re.findall(pref + r"_(\d+)\.jpg", " ".join(files)))
            check(BOTH, "갤러리 %s 번호 일치" % cid, want == have,
                  "html %d / 파일 %d" % (len(want), len(have)))

    # ---------- 예약 QR ----------
    page = section(idx, "reserve")
    check(BOTH, "예약 QR 섹션 존재", 'id="reserve"' in idx and ".reserve-qr" in idx)
    check(BOTH, "예약 카드 링크", 'href="consent.html"' in page)
    check(BOTH, "헤더 예약 버튼 → #reserve", 'href="#reserve" class="cta"' in idx)
    check(BOTH, "예약 QR 이미지 파일 존재",
          os.path.exists(os.path.join(ROOT, "images", "reserve-qr.png")))

    # ---------- 예약 카드(consent) ----------
    con = read("consent.html")
    if con:
        check(BOTH, "예약카드 가족사진 옵션 4개(스페셜 제외)",
              "sub:['시그니처','프리미엄','스탠다드','베이직']" in con and "'스페셜'" not in con)
    else:
        check(LOCAL, "consent.html 존재", False)

    # ---------- 웹앱(frame) ----------
    fr = read("frame.html")
    if fr:
        check(BOTH, "앨범액자 웹: 웹용 작업 존재", '"웹용":"web"' in fr)
        check(BOTH, "앨범액자 웹: 미리보기 넘기기", 'id="prevNav"' in fr)
    else:
        check(LOCAL, "frame.html 존재", False)


def build_live_checks(live):
    check(LIVE, "HTTP 응답", live is not None)
    if not live:
        return
    check(LIVE, "리뷰이벤트 없음", 'class="event"' not in live)
    check(LIVE, "준비사항 없음", "촬영 전 준비사항" not in live)
    check(LIVE, "가족사진 스페셜 없음", "인당 2만원" not in live)
    check(LIVE, "예약 QR 섹션", 'id="reserve"' in live)
    check(LIVE, "헤더 CTA → #reserve", 'href="#reserve" class="cta"' in live)
    for tab, pairs in (("dol", [("압축앨범형", "50만원"), ("화보앨범형", "60만원")]),
                       ("chilsun", [("칠순잔치 · BASIC", "33만원")]),
                       ("wedding-package", [("베이직 패키지", "105만원")])):
        body = section(live, tab)
        for nm, pr in pairs:
            check(LIVE, "[%s] %s %s" % (tab, nm, pr), nm in body and pr in body)


def main():
    live_wanted = "--live" in sys.argv
    idx = read("index.html")
    if idx is None:
        print("index.html 이 없습니다 (저장소 루트에서 실행하세요)")
        return 1
    build_checks(idx)

    live = None
    if live_wanted:
        try:
            url = "https://ianstudio-yulha.github.io/?cb=%d" % int(time.time())
            with urllib.request.urlopen(url, timeout=25) as r:
                live = r.read().decode("utf-8", "replace")
        except Exception as e:                                  # noqa: BLE001
            print("(라이브 접속 실패: %s)" % e)
    if live_wanted:
        build_live_checks(live)

    fails = [r for r in results if not r[2]]
    for scope, name, ok, detail in results:
        tag = {BOTH: "  ", LOCAL: "로컬", LIVE: "라이브"}[scope] if scope else "  "
        line = "%s %s %s" % ("PASS" if ok else "FAIL", tag, name)
        if detail and not ok:
            line += "  →  %s" % detail
        print(line)

    print("\n%d / %d 통과%s" % (len(results) - len(fails), len(results),
                                "" if not live_wanted else "  (라이브 포함)"))
    if fails:
        print("\n실패 목록:")
        for _, name, _, detail in fails:
            print("  - %s %s" % (name, ("→ " + detail) if detail else ""))
        return 1
    print("모두 정상입니다 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
