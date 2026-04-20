"""
軽量開発サーバー — 静的ファイル配信 + /api/reviews エンドポイント
依存: requests, beautifulsoup4  (pip install requests beautifulsoup4)
起動: python server.py
アクセス: http://localhost:8080
"""

import re, time, json, threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
try:
    import requests
    from bs4 import BeautifulSoup
    DEPS_OK = True
    DEPS_ERR = ""
except ImportError as e:
    DEPS_OK = False
    DEPS_ERR = str(e)

POSITIVE_WORDS = [
    "良い","良かった","いい","よかった","綺麗","きれい","可愛い","かわいい","素敵","すてき",
    "丁寧","ていねい","迅速","早い","はやい","満足","大満足","完璧","最高","おすすめ",
    "品質","高品質","しっかり","丈夫","使いやすい","安心","リピート","コスパ","ピッタリ",
    "ぴったり","想像以上","期待以上","また買","再購入","気に入","好き","嬉しい","うれしい",
    "便利","お得","値段以上","とても良","とてもよ","大変良",
]
NEGATIVE_WORDS = [
    "悪い","わるい","残念","がっかり","失敗","壊れ","こわれ","傷","きず","汚れ","汚い",
    "遅い","おそい","届かない","雑","ざつ","薄い","うすい","臭い","返品","クレーム",
    "問題","不良","欠陥","説明と違","写真と違","イメージと違","使いにくい","ゆるい",
    "すぐ壊","粗末","微妙","イマイチ","期待外れ","ひどい","最悪","ほつれ","色が違",
    "サイズが違","においが","ガタガタ",
]
TEXT_SELECTORS = [
    ".revRvwUserFreetext", ".review-text",
    "[class*='freetext']", "[class*='review-body']", "[class*='reviewBody']",
]
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "ja-JP,ja;q=0.9",
}

def scrape_reviews(items):
    print(f"[SCRAPE] items受信: {len(items)}件 / 先頭={items[:1]}")
    pos_freq, neg_freq, total, star_dist = {}, {}, 0, [0,0,0,0,0]
    for item in items[:5]:
        code = item.get("itemCode", "")
        if not code:
            continue
        url = f"https://review.rakuten.co.jp/item/1/{code}/1.1/"
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            r.encoding = "utf-8"
            soup = BeautifulSoup(r.text, "html.parser")
            print(f"[SCRAPE] {url} → status={r.status_code} len={len(r.text)}")
            # 実際のクラス名を調べる
            all_classes = set()
            for tag in soup.find_all(class_=True):
                for c in tag.get("class", []):
                    if "rev" in c.lower() or "review" in c.lower() or "text" in c.lower():
                        all_classes.add(c)
            print(f"[SCRAPE] 関連クラス: {sorted(all_classes)[:20]}")
            els = []
            for sel in TEXT_SELECTORS:
                els = soup.select(sel)
                if els:
                    print(f"[SCRAPE] セレクタ '{sel}' → {len(els)}件")
                    break
            if not els:
                els = [p for p in soup.find_all("p") if len(p.get_text(strip=True)) > 20]
                print(f"[SCRAPE] pタグfallback → {len(els)}件")
            for el in els:
                text = el.get_text(strip=True)
                if len(text) < 5:
                    continue
                total += 1
                for w in POSITIVE_WORDS:
                    if w in text:
                        pos_freq[w] = pos_freq.get(w, 0) + 1
                for w in NEGATIVE_WORDS:
                    if w in text:
                        neg_freq[w] = neg_freq.get(w, 0) + 1
            for sel in soup.select("[class*='Star'],[class*='star'],[data-rating]"):
                rating = sel.get("data-rating")
                if rating:
                    try:
                        s = round(float(rating))
                        if 1 <= s <= 5:
                            star_dist[s-1] += 1
                    except ValueError:
                        pass
                for c in sel.get("class", []):
                    m = re.search(r"[Ss]tar[-_]?(\d)", c)
                    if m:
                        s = int(m.group(1))
                        if 1 <= s <= 5:
                            star_dist[s-1] += 1
            time.sleep(0.8)
        except Exception:
            continue
    return {
        "positive": sorted(pos_freq.items(), key=lambda x: -x[1])[:10],
        "negative": sorted(neg_freq.items(), key=lambda x: -x[1])[:10],
        "star_dist": star_dist,
        "total_reviews": total,
    }


def scrape_ranking_search(keyword):
    if keyword:
        url = "https://ranking.rakuten.co.jp/search"
        params = {"stx": keyword, "smd": 0, "ptn": 1, "srt": 1, "vmd": 0}
    else:
        url = "https://ranking.rakuten.co.jp/"
        params = {}
    r = requests.get(url, params=params, headers=HEADERS, timeout=15)
    r.encoding = "utf-8"
    print(f"[RANKING] {r.url} status={r.status_code} len={len(r.text)}")
    soup = BeautifulSoup(r.text, "html.parser")

    items = []
    # 複数のセレクタを試す
    candidates = (
        soup.select("li.rnk-item") or
        soup.select("[class*='rankItem']") or
        soup.select("[class*='rank-item']") or
        soup.select("li[class*='item']")
    )
    print(f"[RANKING] candidates={len(candidates)}")
    for el in candidates[:30]:
        rank_el = el.select_one("[class*='rank']") or el.select_one(".num")
        name_el = el.select_one("a")
        price_el = el.select_one("[class*='price']")
        rank_text = rank_el.get_text(strip=True) if rank_el else ""
        rank_num = int(re.sub(r"[^\d]", "", rank_text)) if re.search(r"\d", rank_text) else None
        href = name_el["href"] if name_el and name_el.get("href") else ""
        # itemCode を URL から抽出（/shopCode/itemId/ 形式）
        m = re.search(r"item\.rakuten\.co\.jp/([^/]+)/([^/?]+)", href)
        item_code = f"{m.group(1)}:{m.group(2)}" if m else ""
        if item_code or name_el:
            items.append({
                "rank": rank_num,
                "name": name_el.get_text(strip=True)[:60] if name_el else "",
                "url": href,
                "itemCode": item_code,
                "price": re.sub(r"[^\d]", "", price_el.get_text()) if price_el else "",
            })

    # セレクタが全滅した場合：ページ内の全リンクからitem.rakuten.co.jpを抽出
    if not items:
        print("[RANKING] fallback: リンク抽出")
        for i, a in enumerate(soup.find_all("a", href=re.compile(r"item\.rakuten\.co\.jp")), 1):
            m = re.search(r"item\.rakuten\.co\.jp/([^/]+)/([^/?]+)", a["href"])
            if m:
                items.append({
                    "rank": i,
                    "name": a.get_text(strip=True)[:60],
                    "url": a["href"],
                    "itemCode": f"{m.group(1)}:{m.group(2)}",
                    "price": "",
                })
            if len(items) >= 30:
                break

    return {"items": items, "total": len(items)}


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"[{self.address_string()}] {fmt % args}")

    def send_json(self, code, data):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _clean_path(self):
        return self.path.split("?")[0].rstrip("/")

    def do_GET(self):
        p = self._clean_path()
        print(f"GET {self.path!r} → clean={p!r}")
        if p == "/api/ping":
            self.send_json(200, {"ok": True, "bs4": DEPS_OK, "error": DEPS_ERR})
        elif p == "/api/suggest":
            try:
                from urllib.parse import parse_qs
                qs = parse_qs(self.path.split("?",1)[1] if "?" in self.path else "")
                query = qs.get("q", [""])[0]
                url = "https://suggestqueries.google.com/complete/search"
                r = requests.get(url, params={"q": query, "hl": "ja", "client": "firefox"}, headers=HEADERS, timeout=8)
                r.encoding = "utf-8"
                data = r.json()
                words = [w for w in (data[1] if isinstance(data, list) and len(data) > 1 else []) if w != query]
                self.send_json(200, [{"word": w} for w in words])
            except Exception as e:
                print(f"[ERROR] /api/suggest: {e}")
                self.send_json(500, {"error": str(e)})
        else:
            super().do_GET()

    def do_POST(self):
        p = self._clean_path()
        if p == "/api/ranking-search":
            if not DEPS_OK:
                self.send_json(500, {"error": "beautifulsoup4 未インストール"}); return
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length))
                keyword = body.get("keyword", "")
                result = scrape_ranking_search(keyword)
                self.send_json(200, result)
            except Exception as e:
                print(f"[ERROR] /api/ranking-search: {e}")
                self.send_json(500, {"error": str(e)})
        elif p == "/api/reviews":
            if not DEPS_OK:
                self.send_json(500, {"error": f"依存ライブラリ不足: {DEPS_ERR}。pip install requests beautifulsoup4 を実行してください。"})
                return
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length))
                result = scrape_reviews(body.get("items", []))
                self.send_json(200, result)
            except Exception as e:
                print(f"[ERROR] /api/reviews: {e}")
                self.send_json(500, {"error": str(e)})
        else:
            self.send_response(404); self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()


if __name__ == "__main__":
    import os, pathlib
    os.chdir(pathlib.Path(__file__).parent)
    print(f"配信フォルダ: {os.getcwd()}")
    port = 9090
    server = HTTPServer(("", port), Handler)
    print(f"サーバー起動: http://localhost:{port}")
    print("停止するには Ctrl+C")
    server.serve_forever()
