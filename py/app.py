"""
売れ行き調査 Web アプリ (Flask + matplotlib PNG生成)
"""

import io, time, threading, warnings, webbrowser, re
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.font_manager as fm
import requests
from datetime import datetime, timedelta
from flask import Flask, request, send_file, jsonify
try:
    from bs4 import BeautifulSoup
    BS4_OK = True
except ImportError:
    BS4_OK = False

warnings.filterwarnings("ignore")

app = Flask(__name__, static_folder="..", static_url_path="")

# ── レビュー感情キーワード ─────────────────────────────────
POSITIVE_WORDS_PY = [
    "良い","良かった","いい","よかった","綺麗","きれい","可愛い","かわいい","素敵","すてき",
    "丁寧","ていねい","迅速","早い","はやい","満足","大満足","完璧","最高","おすすめ",
    "品質","高品質","しっかり","丈夫","使いやすい","安心","リピート","コスパ","ピッタリ",
    "ぴったり","想像以上","期待以上","また買","再購入","気に入","好き","嬉しい","うれしい",
    "ありがとう","感謝","便利","お得","値段以上","大変良","とても良","とてもよ",
]
NEGATIVE_WORDS_PY = [
    "悪い","わるい","残念","がっかり","失敗","壊れ","こわれ","傷","きず","汚れ","汚い",
    "遅い","おそい","届かない","雑","ざつ","薄い","うすい","臭い","返品","クレーム",
    "問題","不良","欠陥","説明と違","写真と違","イメージと違","使いにくい","ゆるい",
    "すぐ壊","粗末","微妙","イマイチ","期待外れ","ひどい","最悪","壊","すぐに壊",
    "縫い目","ほつれ","色が違","サイズが違","においが","臭","ガタガタ",
]
RAKUTEN_APP_ID = "1078085414692158559"

# ── 日本語フォント ─────────────────────────────────────────
for _p in ["C:/Windows/Fonts/meiryo.ttc","C:/Windows/Fonts/msgothic.ttc","C:/Windows/Fonts/YuGothR.ttc"]:
    try:
        fm.fontManager.addfont(_p)
        plt.rcParams["font.family"] = fm.FontProperties(fname=_p).get_name()
        break
    except Exception:
        pass

# ── Google トレンド ────────────────────────────────────────
def fetch_google_trends(keyword):
    try:
        from pytrends.request import TrendReq
        pt = TrendReq(hl="ja-JP", tz=540)
        pt.build_payload([keyword], timeframe="today 4-y", geo="JP")
        df = pt.interest_over_time().drop(columns=["isPartial"], errors="ignore")
        if df.empty: raise ValueError()
        df.index = pd.to_datetime(df.index)
        df.columns = ["trend_index"]
        return df, True
    except Exception:
        dates = pd.date_range(end=datetime.today(), periods=208, freq="W")
        n = len(dates)
        base = 30 + 20 * np.sin(np.linspace(0, 8*np.pi, n))
        vals = np.clip(base + np.random.normal(0, 5, n), 0, 100)
        return pd.DataFrame({"trend_index": vals}, index=dates), False

def seasonality(df):
    m = df.copy(); m["month"] = m.index.month
    r = m.groupby("month")["trend_index"].mean().reset_index()
    r.columns = ["month","avg"]
    r["label"] = r["month"].apply(lambda x: f"{x}月")
    return r

def forecast(df):
    df = df.copy().sort_index()
    df["t"] = np.arange(len(df))
    sea = df.groupby(df.index.month)["trend_index"].mean()
    sea_n = sea / sea.mean()
    df["des"] = df["trend_index"] / df.index.month.map(sea_n)
    fn = np.poly1d(np.polyfit(df["t"], df["des"], 1))
    fd = pd.date_range(df.index[-1]+timedelta(weeks=1), periods=48, freq="W")
    fc = np.clip(fn(np.arange(len(df), len(df)+48)) * fd.month.map(sea_n), 0, 100)
    return pd.DataFrame({"forecast": fc}, index=fd)

# ── 楽天 ──────────────────────────────────────────────────
def fetch_rakuten(keyword):
    items = []
    for page in range(1, 4):
        try:
            r = requests.get(
                "https://app.rakuten.co.jp/services/api/IchibaItem/Search/20170706",
                params={"applicationId": RAKUTEN_APP_ID, "keyword": keyword,
                        "hits": 30, "page": page, "sort": "-reviewCount",
                        "formatVersion": 2},
                timeout=10)
            for it in r.json().get("Items", []):
                items.append({"name": it.get("itemName","")[:45],
                              "price": it.get("itemPrice", 0),
                              "review_count": it.get("reviewCount", 0),
                              "review_avg":   it.get("reviewAverage", 0.0),
                              "url":          it.get("itemUrl","#")})
            time.sleep(0.5)
        except Exception:
            break
    if not items:
        return pd.DataFrame(), False
    return pd.DataFrame(items).sort_values("review_count", ascending=False).reset_index(drop=True), True

# ── グラフ生成 ─────────────────────────────────────────────
def build_chart(keyword, trend_df, forecast_df, sea_df, rak_df, trend_ok, rak_ok):
    fig = plt.figure(figsize=(16, 13), facecolor="white")
    note = ("※トレンドはサンプルデータ　" if not trend_ok else "") + \
           ("※楽天はサンプルデータ" if not rak_ok else "")
    title = f"「{keyword}」売れ行き調査レポート  {datetime.now().strftime('%Y/%m/%d')}"
    fig.suptitle(title + (f"\n{note}" if note else ""), fontsize=14, fontweight="bold", y=0.99)

    # (A) トレンド推移 + 予測
    ax1 = fig.add_subplot(3, 2, (1, 2))
    ax1.fill_between(trend_df.index, trend_df["trend_index"], alpha=0.25, color="steelblue")
    ax1.plot(trend_df.index, trend_df["trend_index"], color="steelblue", lw=1.5, label="実績（Googleトレンド）")
    ax1.fill_between(forecast_df.index, forecast_df["forecast"], alpha=0.2, color="tomato")
    ax1.plot(forecast_df.index, forecast_df["forecast"], color="tomato", lw=2, ls="--", label="予測（今後12ヶ月）")
    ax1.axvline(trend_df.index[-1], color="gray", lw=1, ls=":")
    ax1.set_title("Googleトレンド推移と将来予測（日本）"); ax1.set_ylabel("トレンド指数（0〜100）")
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y/%m"))
    ax1.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    plt.setp(ax1.xaxis.get_majorticklabels(), rotation=30, ha="right")
    ax1.legend(); ax1.grid(True, alpha=0.3)

    # (B) 季節性
    ax2 = fig.add_subplot(3, 2, 3)
    colors = ["#e74c3c" if v == sea_df["avg"].max() else "#3498db" for v in sea_df["avg"]]
    bars = ax2.bar(sea_df["label"], sea_df["avg"], color=colors, edgecolor="white")
    ax2.set_title("月別平均トレンド（季節性）"); ax2.set_ylabel("平均トレンド指数")
    for b, v in zip(bars, sea_df["avg"]):
        ax2.text(b.get_x()+b.get_width()/2, b.get_height()+0.5, f"{v:.0f}", ha="center", va="bottom", fontsize=8)
    ax2.grid(True, axis="y", alpha=0.3)

    # (C) 価格分布
    ax3 = fig.add_subplot(3, 2, 4)
    prices = rak_df["price"].values
    ax3.hist(prices, bins=min(15,len(prices)), color="mediumseagreen", edgecolor="white")
    ax3.axvline(np.median(prices), color="red", lw=2, ls="--", label=f"中央値 ¥{int(np.median(prices)):,}")
    ax3.axvline(np.mean(prices),   color="orange", lw=2, ls="--", label=f"平均値 ¥{int(np.mean(prices)):,}")
    ax3.set_title("楽天市場 価格分布"); ax3.set_xlabel("価格（円）"); ax3.set_ylabel("商品数")
    ax3.legend(fontsize=9); ax3.grid(True, alpha=0.3)

    # (D) レビュー数 TOP10
    ax4 = fig.add_subplot(3, 2, (5, 6))
    top10 = rak_df.nlargest(10, "review_count").iloc[::-1]
    names = [n[:30]+"…" if len(n)>30 else n for n in top10["name"]]
    bc = plt.cm.YlOrRd(np.linspace(0.3, 0.9, len(top10)))[::-1]
    hb = ax4.barh(names, top10["review_count"], color=bc, edgecolor="white")
    for bar, rv, rc in zip(hb, top10["review_avg"], top10["review_count"]):
        ax4.text(bar.get_width()+5, bar.get_y()+bar.get_height()/2,
                 f"★{rv:.1f} ({rc:,}件)", va="center", fontsize=8)
    ax4.set_title("楽天市場 レビュー数 TOP10"); ax4.set_xlabel("レビュー件数")
    ax4.grid(True, axis="x", alpha=0.3)
    ax4.set_xlim(0, top10["review_count"].max()*1.3)

    plt.tight_layout(rect=[0,0,1,0.96])
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=140, bbox_inches="tight", facecolor="white")
    plt.close(fig); buf.seek(0)
    return buf

# ── キャッシュ ─────────────────────────────────────────────
_cache = {}
_lock  = threading.Lock()

@app.route("/")
def index():
    return app.send_static_file("index.html")

@app.route("/search", methods=["POST"])
def search():
    keyword = (request.json or {}).get("keyword","").strip()
    if not keyword:
        return jsonify({"error":"キーワードを入力してください"}), 400

    trend_df, trend_ok = fetch_google_trends(keyword)
    sea_df   = seasonality(trend_df)
    fore_df  = forecast(trend_df)
    rak_df, rak_ok = fetch_rakuten(keyword)

    if rak_df.empty:
        rak_df = pd.DataFrame([{"name":"（データなし）","price":0,"review_count":0,"review_avg":0.0,"url":"#"}])
        rak_ok = False

    chart = build_chart(keyword, trend_df, fore_df, sea_df, rak_df, trend_ok, rak_ok)
    key = f"{keyword}_{datetime.now().strftime('%H%M%S')}"
    with _lock:
        _cache[key] = chart.read()

    # サマリー
    prices = rak_df["price"].values
    top1   = rak_df.nlargest(1,"review_count").iloc[0]
    recent = trend_df["trend_index"].tail(12).mean()
    past   = trend_df["trend_index"].head(12).mean()
    chg    = (recent-past)/past*100 if past>0 else 0
    peak   = sea_df.loc[sea_df["avg"].idxmax()]
    fp     = fore_df["forecast"].max()
    fpd    = fore_df["forecast"].idxmax().strftime("%Y年%m月")
    direction = "↑増加傾向" if chg>5 else "↓減少傾向" if chg<-5 else "→横ばい"

    return jsonify({
        "chart_key": key,
        "trend_ok": trend_ok,
        "rakuten_ok": rak_ok,
        "summary": {
            "recent_avg":    f"{recent:.1f}",
            "yoy_change":    f"{chg:+.1f}%  {direction}",
            "peak_month":    f"{peak['label']}（指数 {peak['avg']:.0f}）",
            "forecast_peak": f"{fpd}（指数 {fp:.0f}）",
            "item_count":    len(rak_df),
            "price_range":   f"¥{int(prices.min()):,} ～ ¥{int(prices.max()):,}",
            "price_median":  f"¥{int(np.median(prices)):,}",
            "review_avg":    f"★{rak_df['review_avg'].mean():.2f}",
            "top_item":      top1["name"][:35],
            "top_detail":    f"¥{int(top1['price']):,}  ★{top1['review_avg']}  {int(top1['review_count']):,}件",
        }
    })

@app.route("/api/ping")
def api_ping():
    return jsonify({"ok": True, "bs4": BS4_OK})

# ── ヘルスチェック（プロキシ互換） ────────────────────────────────
@app.route("/api/health")
def api_health():
    return jsonify({"ok": True})

# ── キーワード抽出ユーティリティ ──────────────────────────────────
_STOP = {
    "の","に","は","を","が","で","と","た","て","い","な","れ","も","や","か",
    "セット","送料","無料","対応","可能","用","約","入り","本","個","枚","円",
    "cm","mm","kg","ml","new","sale","off","レディース","メンズ","ユニセックス",
    "サイズ","カラー","タイプ","日本製","国産","限定","おしゃれ","シンプル",
    "かわいい","プレゼント","ギフト","送料無料",
}

def _extract_keywords(names, limit=12):
    import re as _re
    freq = {}
    splitter = _re.compile(r'[\s　\-－/／・|｜【】（）()\[\]「」『』、。,.!！?？★◆■□●○×＋\d�]+')
    jp_re = _re.compile(r'[぀-ゟ゠-ヿ一-鿿]')
    for name in names:
        for w in splitter.split(name or ""):
            if 2 <= len(w) <= 12 and w not in _STOP and jp_re.search(w):
                freq[w] = freq.get(w, 0) + 1
    return [{"word": w, "count": c} for w, c in sorted(freq.items(), key=lambda x: -x[1])[:limit]]

def _rakuten_ranking(genre_id, hits=30):
    params = {"applicationId": RAKUTEN_APP_ID, "hits": hits, "page": 1, "formatVersion": 2}
    if genre_id:
        params["genreId"] = genre_id
    r = requests.get(
        "https://app.rakuten.co.jp/services/api/IchibaItem/Ranking/20170628",
        params=params, timeout=8)
    return r.json().get("Items", [])

# ── メルカリ人気キーワード（楽天ランキングで代替） ─────────────────
@app.route("/api/mercari-keywords")
def api_mercari_keywords():
    try:
        genre_ids = ["100371", "101240", "558885", "101164"]
        all_names = []
        for gid in genre_ids:
            try:
                items = _rakuten_ranking(gid, 15)
                all_names += [it.get("itemName", "") for it in items if it.get("itemName")]
                time.sleep(0.2)
            except Exception:
                pass
        keywords = _extract_keywords(all_names, 12)
        if keywords:
            return jsonify({"ok": True, "keywords": keywords})
        return jsonify({"ok": False, "error": "empty", "keywords": []})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "keywords": []})

# ── Amazonサジェスト ──────────────────────────────────────────────
@app.route("/api/amazon-suggest")
def api_amazon_suggest():
    q = request.args.get("q", "人気")
    try:
        r = requests.get(
            "https://completion.amazon.co.jp/api/2017/suggestions",
            params={"mid": "A1VC38T7YXB528", "alias": "aps", "prefix": q, "limit": 11, "b2b": 0},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=6)
        words = [s.get("value") for s in r.json().get("suggestions", []) if s.get("value")]
        return jsonify({"ok": True, "words": words})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "words": []})

# ── Creema人気キーワード ──────────────────────────────────────────
@app.route("/api/creema-keywords")
def api_creema_keywords():
    try:
        import re as _re
        r = requests.get("https://www.creema.jp/ranking",
                         headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "ja-JP,ja;q=0.9"},
                         timeout=8)
        if not BS4_OK:
            raise ImportError("bs4")
        soup = BeautifulSoup(r.text, "html.parser")
        jp_re = _re.compile(r'[぀-ゟ゠-ヿ一-鿿]')
        names = []
        for a in soup.select("a[href*='/item/']"):
            t = a.get_text(strip=True).replace("　", " ").strip()
            if 4 <= len(t) < 80:
                names.append(t)
        for el in soup.select("[class*='tag'],[class*='category'],[class*='keyword']"):
            t = el.get_text(strip=True)
            if 2 <= len(t) <= 15 and jp_re.search(t):
                names.append(t)
        keywords = _extract_keywords(names)
        if keywords:
            return jsonify({"ok": True, "keywords": keywords})
        raise ValueError("no items")
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "keywords": []})

# ── minne人気キーワード ───────────────────────────────────────────
@app.route("/api/minne-keywords")
def api_minne_keywords():
    try:
        import re as _re
        r = requests.get("https://minne.com/",
                         headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "ja-JP,ja;q=0.9"},
                         timeout=8)
        if not BS4_OK:
            raise ImportError("bs4")
        soup = BeautifulSoup(r.text, "html.parser")
        jp_re = _re.compile(r'[぀-ゟ゠-ヿ一-鿿]')
        names = []
        for a in soup.select("a[href*='/items/']"):
            t = _re.sub(r'[\d,円【】\[\]]+', '', a.get_text(strip=True)).strip()
            if 3 <= len(t) < 60 and jp_re.search(t):
                names.append(t)
        keywords = _extract_keywords(names)
        if keywords:
            return jsonify({"ok": True, "keywords": keywords})
        raise ValueError("no items")
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "keywords": []})

# ── Amazonベストセラーキーワード ──────────────────────────────────
@app.route("/api/amazon-keywords")
def api_amazon_keywords():
    cat_map = {
        "":        "https://www.amazon.co.jp/gp/bestsellers/",
        "kitchen": "https://www.amazon.co.jp/gp/bestsellers/kitchen/",
        "beauty":  "https://www.amazon.co.jp/gp/bestsellers/beauty/",
        "fashion": "https://www.amazon.co.jp/gp/bestsellers/apparel/",
        "outdoor": "https://www.amazon.co.jp/gp/bestsellers/sports/",
        "home":    "https://www.amazon.co.jp/gp/bestsellers/home/",
        "toy":     "https://www.amazon.co.jp/gp/bestsellers/toys/",
    }
    if not BS4_OK:
        return jsonify({"ok": False, "error": "bs4 not installed", "keywords": []})
    url = cat_map.get(request.args.get("category", ""), cat_map[""])
    try:
        r = requests.get(url,
                         headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "ja-JP,ja;q=0.9"},
                         timeout=8)
        soup = BeautifulSoup(r.text, "html.parser")
        names = []
        for sel in [
            "._cDEzb_p13n-sc-css-line-clamp-3_g3dy1",
            ".p13n-sc-truncate-desktop-type2",
            ".p13n-sc-truncated",
        ]:
            for el in soup.select(sel):
                t = el.get_text(strip=True)
                if len(t) > 2:
                    names.append(t)
        if not names:
            for a in soup.find_all("a", attrs={"aria-label": True}):
                t = a.get("aria-label", "")
                if len(t) > 2:
                    names.append(t)
        keywords = _extract_keywords(names)
        return jsonify({"ok": True, "keywords": keywords})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "keywords": []})

@app.route("/api/reviews", methods=["POST"])
def api_reviews():
    """上位商品の楽天レビューページをスクレイピングして感情分析"""
    if not BS4_OK:
        return jsonify({"error": "beautifulsoup4 がインストールされていません。pip install beautifulsoup4 を実行してください。"}), 500

    items = (request.json or {}).get("items", [])
    pos_freq, neg_freq, total_reviews, star_dist = {}, {}, 0, [0,0,0,0,0]
    errors = []

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "ja-JP,ja;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    # レビュー本文のCSSセレクタ（楽天のHTML構造に合わせて複数試す）
    TEXT_SELECTORS = [
        ".revRvwUserFreetext",
        ".review-text",
        "[class*='freetext']",
        "[class*='review-body']",
        "[class*='reviewBody']",
        "p.txt",
    ]

    for item in items[:5]:
        item_code = item.get("itemCode", "")
        if not item_code:
            continue
        url = f"https://review.rakuten.co.jp/item/1/{item_code}/1.1/"
        try:
            r = requests.get(url, headers=headers, timeout=15)
            r.encoding = "utf-8"
            soup = BeautifulSoup(r.text, "html.parser")

            # レビュー本文（複数セレクタを試す）
            review_els = []
            for sel in TEXT_SELECTORS:
                review_els = soup.select(sel)
                if review_els:
                    break

            # セレクタが全滅した場合は長いpタグを拾う
            if not review_els:
                review_els = [p for p in soup.find_all("p") if len(p.get_text(strip=True)) > 20]

            for el in review_els:
                text = el.get_text(strip=True)
                if len(text) < 5:
                    continue
                total_reviews += 1
                for w in POSITIVE_WORDS_PY:
                    if w in text:
                        pos_freq[w] = pos_freq.get(w, 0) + 1
                for w in NEGATIVE_WORDS_PY:
                    if w in text:
                        neg_freq[w] = neg_freq.get(w, 0) + 1

            # 星評価（data属性・class両方を試す）
            for star_el in soup.select("[class*='Star'], [class*='star'], [data-rating]"):
                rating = star_el.get("data-rating")
                if rating:
                    try:
                        s = round(float(rating))
                        if 1 <= s <= 5:
                            star_dist[s-1] += 1
                    except ValueError:
                        pass
                for c in star_el.get("class", []):
                    m = re.search(r"[Ss]tar[-_]?(\d)", c)
                    if m:
                        s = int(m.group(1))
                        if 1 <= s <= 5:
                            star_dist[s-1] += 1

            time.sleep(0.8)
        except Exception as e:
            errors.append(f"{item_code}: {str(e)}")
            continue

    pos_sorted = sorted(pos_freq.items(), key=lambda x: -x[1])[:10]
    neg_sorted = sorted(neg_freq.items(), key=lambda x: -x[1])[:10]

    return jsonify({
        "positive": pos_sorted,
        "negative": neg_sorted,
        "star_dist": star_dist,
        "total_reviews": total_reviews,
        "errors": errors,
    })

@app.route("/chart/<key>")
def chart(key):
    with _lock:
        data = _cache.get(key)
    if not data: return "Not found", 404
    return send_file(io.BytesIO(data), mimetype="image/png")

if __name__ == "__main__":
    threading.Timer(1.5, lambda: webbrowser.open("http://localhost:5000")).start()
    app.run(debug=False, port=5000)
