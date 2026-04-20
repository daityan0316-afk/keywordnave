const express = require("express");
const axios = require("axios");
const cheerio = require("cheerio");
const cors = require("cors");

const app = express();
const PORT = 3737;

app.use(cors());
app.use(express.json());

const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36";
const RAKUTEN_APP_ID = "1078085414692158559";

const STOP = new Set([
  "の","に","は","を","が","で","と","た","て","い","な","れ","も","や","か",
  "セット","送料","無料","対応","可能","用","約","入り","本","個","枚","円",
  "cm","mm","kg","ml","new","sale","off","レディース","メンズ","ユニセックス",
  "サイズ","カラー","タイプ","日本製","国産","限定","おしゃれ","シンプル",
  "かわいい","プレゼント","ギフト","対応","送料無料",
]);

const JP_RE = /[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]/;

function extractKeywords(names, limit = 12) {
  const splitter = /[\s　\-－/／・|｜【】（）()[\]「」『』、。,.!！?？★◆■□●○×＋\d\uFFFD]+/;
  const freq = {};
  names.forEach(name => {
    (name || "").split(splitter)
      .filter(w => w.length >= 2 && w.length <= 12 && !STOP.has(w) && JP_RE.test(w))
      .forEach(w => { freq[w] = (freq[w] || 0) + 1; });
  });
  return Object.entries(freq)
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit)
    .map(([w, count]) => ({ word: w, count }));
}

async function rakutenRanking(genreId, hits = 30) {
  const params = { applicationId: RAKUTEN_APP_ID, hits, page: 1, formatVersion: 2 };
  if (genreId) params.genreId = genreId;
  const { data } = await axios.get(
    "https://app.rakuten.co.jp/services/api/IchibaItem/Ranking/20170628",
    { params, timeout: 8000 }
  );
  return data.Items || [];
}

// ── Amazon キーワード（ベストセラーページスクレイプ） ─────────────
app.get("/api/amazon-keywords", async (req, res) => {
  const catMap = {
    "":        "https://www.amazon.co.jp/gp/bestsellers/",
    "kitchen": "https://www.amazon.co.jp/gp/bestsellers/kitchen/",
    "beauty":  "https://www.amazon.co.jp/gp/bestsellers/beauty/",
    "fashion": "https://www.amazon.co.jp/gp/bestsellers/apparel/",
    "outdoor": "https://www.amazon.co.jp/gp/bestsellers/sports/",
    "home":    "https://www.amazon.co.jp/gp/bestsellers/home/",
    "toy":     "https://www.amazon.co.jp/gp/bestsellers/toys/",
  };
  const url = catMap[req.query.category || ""] || catMap[""];
  try {
    const { data } = await axios.get(url, {
      headers: { "User-Agent": UA, "Accept-Language": "ja-JP,ja;q=0.9" },
      timeout: 8000,
    });
    const $ = cheerio.load(data);
    const names = [];
    // Amazon ベストセラーの商品名セレクター（複数パターン）
    $("._cDEzb_p13n-sc-css-line-clamp-3_g3dy1, .p13n-sc-truncate-desktop-type2, .p13n-sc-truncated, ._p13n-zg-list-grid-desktop_truncationStyles_p13n-zg-css-truncate-item-V2__1_6EZ").each((_, el) => {
      const t = $(el).text().trim();
      if (t.length > 2) names.push(t);
    });
    if (!names.length) {
      // fallback: aria-label のある商品リンク
      $("a[aria-label]").each((_, el) => { const t = $(el).attr("aria-label"); if (t && t.length > 2) names.push(t); });
    }
    const keywords = extractKeywords(names);
    res.json({ ok: true, keywords });
  } catch (e) {
    res.json({ ok: false, error: e.message, keywords: [] });
  }
});

// ── Amazon サジェスト ─────────────────────────────────────────
app.get("/api/amazon-suggest", async (req, res) => {
  const q = req.query.q || "人気";
  try {
    const { data } = await axios.get("https://completion.amazon.co.jp/api/2017/suggestions", {
      params: { mid: "A1VC38T7YXB528", alias: "aps", prefix: q, limit: 11, b2b: 0 },
      headers: { "User-Agent": UA },
      timeout: 6000,
    });
    const words = (data.suggestions || []).map(s => s.value).filter(Boolean);
    res.json({ ok: true, words });
  } catch (e) {
    res.json({ ok: false, error: e.message, words: [] });
  }
});

// ── メルカリ 人気キーワード ───────────────────────────────────
// メルカリはSPA → 楽天ランキングのメルカリ的ジャンルから代替抽出
app.get("/api/mercari-keywords", async (req, res) => {
  try {
    const genreIds = ["100371", "101240", "558885", "101164"]; // ファッション・ホビー・コスメ・おもちゃ
    const allNames = [];
    await Promise.all(genreIds.map(async gid => {
      const items = await rakutenRanking(gid, 15);
      items.forEach(it => { if (it.itemName) allNames.push(it.itemName); });
    }));
    const keywords = extractKeywords(allNames, 12);
    if (keywords.length) return res.json({ ok: true, keywords });
    throw new Error("empty");
  } catch (e) {
    res.json({ ok: false, error: e.message, keywords: [] });
  }
});

// ── Creema 人気キーワード ─────────────────────────────────────
app.get("/api/creema-keywords", async (req, res) => {
  try {
    const { data } = await axios.get("https://www.creema.jp/ranking", {
      headers: { "User-Agent": UA, "Accept-Language": "ja-JP,ja;q=0.9" },
      timeout: 8000,
    });
    const $ = cheerio.load(data);
    const names = [];
    // ランキングページの商品名（リンクテキスト）
    $("a[href*='/item/']").each((_, el) => {
      const t = $(el).text().trim().replace(/\s+/g, " ");
      if (t.length >= 4 && t.length < 80) names.push(t);
    });
    // タグ・カテゴリラベル
    $("[class*='tag'], [class*='category'], [class*='keyword']").each((_, el) => {
      const t = $(el).text().trim();
      if (t.length >= 2 && t.length <= 15 && JP_RE.test(t)) names.push(t);
    });
    const keywords = extractKeywords(names);
    if (keywords.length) return res.json({ ok: true, keywords });
    throw new Error("no items");
  } catch (e) {
    res.json({ ok: false, error: e.message, keywords: [] });
  }
});

// ── minne 人気キーワード ──────────────────────────────────────
app.get("/api/minne-keywords", async (req, res) => {
  try {
    const { data } = await axios.get("https://minne.com/", {
      headers: { "User-Agent": UA, "Accept-Language": "ja-JP,ja;q=0.9" },
      timeout: 8000,
    });
    const $ = cheerio.load(data);
    const names = [];
    $("a[href*='/items/']").each((_, el) => {
      // 価格・数字を除去
      const t = $(el).text().trim().replace(/[\d,円【】\[\]]+/g, "").trim();
      if (t.length >= 3 && t.length < 60 && JP_RE.test(t)) names.push(t);
    });
    const keywords = extractKeywords(names);
    if (keywords.length) return res.json({ ok: true, keywords });
    throw new Error("no items");
  } catch (e) {
    res.json({ ok: false, error: e.message, keywords: [] });
  }
});

// ── ヘルスチェック ────────────────────────────────────────────
app.get("/api/health", (_, res) => res.json({ ok: true }));

app.listen(PORT, () => {
  console.log(`\n🚀 キーワードなび プロキシサーバー起動`);
  console.log(`   http://localhost:${PORT}`);
  console.log(`\n利用可能なAPI:`);
  console.log(`   GET  /api/amazon-suggest?q=キーワード`);
  console.log(`   GET  /api/amazon-keywords?category=  (kitchen/beauty/fashion/outdoor/home/toy)`);
  console.log(`   GET  /api/mercari-keywords`);
  console.log(`   GET  /api/creema-keywords`);
  console.log(`   GET  /api/minne-keywords`);
  console.log(`\nindex.html を開いて使ってください。\n`);
});
