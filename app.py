import os, json
from datetime import date
from flask import Flask, jsonify, request
import requests

app = Flask(__name__)

API_KEY = os.environ.get("NOTION_API_KEY", "")
DB_ID   = os.environ.get("NOTION_DB_ID", "")

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type":  "application/json",
    "Notion-Version": "2022-06-28",
}

CATEGORIES = ["食品", "飲料", "日用品", "衛生用品", "掃除用品", "医薬品", "ペット用品", "その他"]
STORES     = ["スーパー", "コンビニ", "ドラッグストア", "Amazon", "楽天",
              "ネット通販", "ホームセンター", "業務スーパー", "コストコ", "その他"]

# ── Notion helpers ────────────────────────────────────────────────────────────

def notion_query(payload):
    results, cursor = [], None
    while True:
        if cursor:
            payload["start_cursor"] = cursor
        r = requests.post(
            f"https://api.notion.com/v1/databases/{DB_ID}/query",
            headers=HEADERS, json=payload, timeout=10
        )
        d = r.json()
        results.extend(d.get("results", []))
        if not d.get("has_more"):
            break
        cursor = d["next_cursor"]
    return results

def parse(page):
    p = page["properties"]
    def txt(k):
        arr = (p.get(k) or {}).get("title") or (p.get(k) or {}).get("rich_text") or []
        return "".join(t["plain_text"] for t in arr)
    def num(k):  return (p.get(k) or {}).get("number") or 0
    def sel(k):
        s = (p.get(k) or {}).get("select")
        return s["name"] if s else ""
    def dt(k):
        d = (p.get(k) or {}).get("date")
        return d["start"] if d else ""
    vol  = num("容量")
    price= num("購入金額")
    return {
        "id":       page["id"],
        "name":     txt("商品名"),
        "category": sel("カテゴリ"),
        "date":     dt("購入日"),
        "price":    price,
        "volume":   vol,
        "unit_price": round(price / vol, 2) if vol else 0,
        "store":    sel("購入場所"),
        "memo":     txt("メモ"),
    }

# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return HTML

@app.route("/api/products")
def get_products():
    pages = notion_query({
        "page_size": 100,
        "sorts": [{"property": "購入日", "direction": "descending"}]
    })
    records = [parse(p) for p in pages if parse(p)["name"]]

    # 商品ごとに最新1件 + 全履歴から最安単価を計算
    latest    = {}
    best_unit = {}  # 商品名 → {unit_price, store}

    for r in records:
        name = r["name"]
        if name not in latest:
            latest[name] = r
        if r["unit_price"] > 0:
            if name not in best_unit or r["unit_price"] < best_unit[name]["unit_price"]:
                best_unit[name] = {"unit_price": r["unit_price"], "store": r["store"]}

    # 最安値情報をマージ
    for name, p in latest.items():
        b = best_unit.get(name)
        p["best_unit_price"] = b["unit_price"] if b else 0
        p["best_store"]      = b["store"]      if b else ""

    products   = sorted(latest.values(), key=lambda x: x["name"])
    categories = sorted({r["category"] for r in records if r["category"]})
    names      = sorted(latest.keys())

    return jsonify({"products": products, "categories": categories, "names": names})

@app.route("/api/history/<path:name>")
def get_history(name):
    pages = notion_query({
        "page_size": 100,
        "filter": {"property": "商品名", "title": {"equals": name}},
        "sorts":  [{"property": "購入日", "direction": "descending"}]
    })
    return jsonify([parse(p) for p in pages])

@app.route("/api/save", methods=["POST"])
def save():
    d = request.json
    props = {
        "商品名":   {"title": [{"text": {"content": d["name"]}}]},
        "購入金額": {"number": float(d.get("price", 0))},
        "購入日":   {"date":   {"start": d.get("date", str(date.today()))}},
    }
    if d.get("category"): props["カテゴリ"]   = {"select": {"name": d["category"]}}
    if d.get("volume"):   props["容量"]       = {"number": float(d["volume"])}
    if d.get("store"):    props["購入場所"]   = {"select": {"name": d["store"]}}
    if d.get("memo"):     props["メモ"]       = {"rich_text": [{"text": {"content": d["memo"]}}]}

    r = requests.post("https://api.notion.com/v1/pages",
                      headers=HEADERS,
                      json={"parent": {"database_id": DB_ID}, "properties": props},
                      timeout=10)
    if r.status_code == 200:
        return jsonify({"ok": True, "record": parse(r.json())})
    return jsonify({"ok": False, "error": r.text}), 400

# ── HTML ──────────────────────────────────────────────────────────────────────

HTML = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="theme-color" content="#4f46e5">
<title>ストック管理</title>
<style>
:root{
  --p:#4f46e5;--pl:#eef2ff;--bg:#f1f5f9;--card:#fff;
  --up:#ef4444;--upl:#fef2f2;--dn:#16a34a;--dnl:#f0fdf4;
  --tx:#0f172a;--sub:#64748b;--bd:#e2e8f0;
  --sh:0 2px 12px rgba(0,0,0,.08);
  --r:14px;
}
*{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}
body{font-family:-apple-system,'Hiragino Sans','Yu Gothic UI',sans-serif;
     background:var(--bg);color:var(--tx);min-height:100vh;
     padding-bottom:env(safe-area-inset-bottom)}

/* ─── Header ─── */
header{
  background:var(--p);color:#fff;
  padding:16px 20px calc(16px + env(safe-area-inset-top));
  padding-top:calc(16px + env(safe-area-inset-top));
  position:sticky;top:0;z-index:10;
}
header h1{font-size:1.1rem;font-weight:700}
header p{font-size:.75rem;opacity:.75;margin-top:2px}

/* ─── Category tabs ─── */
.tabs{
  display:flex;gap:8px;overflow-x:auto;
  padding:14px 16px;scrollbar-width:none;
  background:var(--card);border-bottom:1px solid var(--bd);
  position:sticky;top:57px;z-index:9;
}
.tabs::-webkit-scrollbar{display:none}
.tab{
  flex-shrink:0;padding:6px 14px;border-radius:99px;
  font-size:.82rem;font-weight:600;cursor:pointer;
  background:var(--bg);color:var(--sub);border:none;transition:.15s;
}
.tab.active{background:var(--p);color:#fff}

/* ─── Product list ─── */
.list{padding:12px 12px 80px}
.product-card{
  background:var(--card);border-radius:var(--r);
  box-shadow:var(--sh);margin-bottom:10px;
  display:flex;align-items:center;gap:12px;
  padding:14px 16px;cursor:pointer;
  transition:transform .12s,box-shadow .12s;
  border:none;width:100%;text-align:left;
}
.product-card:active{transform:scale(.98);box-shadow:none}
.pc-icon{
  width:42px;height:42px;border-radius:10px;
  background:var(--pl);color:var(--p);
  display:flex;align-items:center;justify-content:center;
  font-size:1.2rem;flex-shrink:0;
}
.pc-body{flex:1;min-width:0}
.pc-name{font-size:.95rem;font-weight:700;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pc-meta{font-size:.78rem;color:var(--sub);margin-top:3px}
.pc-price{text-align:right;flex-shrink:0}
.pc-price-val{font-size:1.05rem;font-weight:800;color:var(--tx)}
.pc-price-sub{font-size:.72rem;color:var(--sub);margin-top:2px}
.pc-best{font-size:.72rem;font-weight:700;margin-top:3px}
.pc-best.is-best{color:var(--dn)}
.pc-best.not-best{color:var(--up)}

.empty{text-align:center;color:var(--sub);padding:60px 20px;font-size:.9rem}
.loading{text-align:center;color:var(--sub);padding:40px;font-size:.9rem}

/* ─── FAB ─── */
.fab{
  position:fixed;right:20px;
  bottom:calc(20px + env(safe-area-inset-bottom));
  z-index:20;width:56px;height:56px;border-radius:50%;
  background:var(--p);color:#fff;font-size:1.5rem;
  border:none;cursor:pointer;box-shadow:0 4px 20px rgba(79,70,229,.4);
  display:flex;align-items:center;justify-content:center;
  transition:transform .12s;
}
.fab:active{transform:scale(.92)}

/* ─── Bottom sheet ─── */
.overlay{
  position:fixed;inset:0;background:rgba(0,0,0,.45);
  z-index:30;opacity:0;pointer-events:none;transition:opacity .25s;
}
.overlay.show{opacity:1;pointer-events:all}
.sheet{
  position:fixed;bottom:0;left:0;right:0;z-index:31;
  background:var(--card);border-radius:20px 20px 0 0;
  padding:0 20px calc(24px + env(safe-area-inset-bottom));
  transform:translateY(100%);transition:transform .3s cubic-bezier(.4,0,.2,1);
  max-height:92vh;overflow-y:auto;
}
.sheet.show{transform:translateY(0)}
.sheet-handle{
  width:36px;height:4px;border-radius:2px;background:var(--bd);
  margin:12px auto 4px;
}
.sheet-head{
  display:flex;align-items:center;justify-content:space-between;
  padding:10px 0 14px;
}
.sheet-title{font-size:1rem;font-weight:700}
.btn-close{
  background:var(--bg);border:none;border-radius:50%;
  width:32px;height:32px;font-size:1rem;cursor:pointer;
  display:flex;align-items:center;justify-content:center;
}

/* ─── Prev data block ─── */
.prev-block{
  background:var(--pl);border-radius:12px;
  padding:14px 16px;margin-bottom:16px;
}
.prev-label{font-size:.72rem;font-weight:700;color:var(--p);
  text-transform:uppercase;letter-spacing:.06em;margin-bottom:8px}
.prev-price{font-size:2.6rem;font-weight:900;color:var(--tx);line-height:1}
.prev-unit{font-size:.82rem;color:var(--sub);margin-top:4px}
.prev-meta{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}
.badge{
  background:#fff;color:var(--sub);border-radius:99px;
  padding:3px 10px;font-size:.75rem;font-weight:500;
}
.no-prev{color:var(--sub);font-size:.88rem;padding:4px 0}

/* ─── Form ─── */
.form-section{margin-bottom:20px}
.form-label{font-size:.78rem;font-weight:600;color:var(--sub);
  margin-bottom:6px;display:block}
.row2{display:grid;grid-template-columns:1fr 1fr;gap:10px}
input[type=number],input[type=text],input[type=date],select{
  width:100%;padding:12px 13px;
  border:1.5px solid var(--bd);border-radius:10px;
  font-size:1rem;color:var(--tx);background:var(--card);
  outline:none;transition:border .15s;
  -webkit-appearance:none;appearance:none;
}
input:focus,select:focus{border-color:var(--p)}

/* ─── Compare result ─── */
.result-box{
  border-radius:12px;padding:16px;margin:14px 0;
  display:none;
}
.result-box.show{display:block}
.result-box.cheaper{background:var(--dnl)}
.result-box.pricier{background:var(--upl)}
.result-box.same{background:var(--bg)}
.result-verdict{
  display:flex;align-items:center;gap:8px;
  font-size:1.1rem;font-weight:800;margin-bottom:10px;
}
.result-verdict.cheaper{color:var(--dn)}
.result-verdict.pricier{color:var(--up)}
.result-verdict.same{color:var(--sub)}
.bars{display:flex;flex-direction:column;gap:8px}
.bar-row{display:flex;align-items:center;gap:8px}
.bar-label-txt{font-size:.75rem;color:var(--sub);width:22px;flex-shrink:0}
.bar-track{flex:1;height:10px;background:var(--bd);border-radius:99px;overflow:hidden}
.bar-fill{height:100%;border-radius:99px;transition:width .5s cubic-bezier(.4,0,.2,1)}
.bar-fill.prev-bar{background:#94a3b8}
.bar-fill.now-bar{background:var(--dn)}
.bar-fill.now-bar.up{background:var(--up)}
.bar-val{font-size:.75rem;font-weight:700;width:68px;flex-shrink:0;text-align:right;
  white-space:nowrap;color:var(--tx)}

/* ─── Buttons ─── */
.btn-save{
  display:block;width:100%;padding:16px;
  background:var(--p);color:#fff;border:none;border-radius:12px;
  font-size:1rem;font-weight:700;cursor:pointer;
  transition:opacity .15s,transform .1s;
}
.btn-save:active{transform:scale(.98);opacity:.9}
.btn-save:disabled{opacity:.45;cursor:default}
.save-msg{text-align:center;font-size:.85rem;margin-top:10px;min-height:1.2em}

/* ─── Datalist ─── */
datalist{display:none}
</style>
</head>
<body>

<header>
  <h1>🏠 ストック管理</h1>
  <p>商品をタップして価格を記録・比較</p>
</header>

<div class="tabs" id="tabs">
  <button class="tab active" onclick="filterCat('')">すべて</button>
</div>

<div class="list" id="list">
  <div class="loading">読み込み中…</div>
</div>

<button class="fab" onclick="openNew()" title="新規商品">＋</button>

<!-- Overlay -->
<div class="overlay" id="overlay" onclick="closeSheet()"></div>

<!-- Bottom sheet -->
<div class="sheet" id="sheet">
  <div class="sheet-handle"></div>
  <div class="sheet-head">
    <span class="sheet-title" id="sheet-title">価格を記録</span>
    <button class="btn-close" onclick="closeSheet()">✕</button>
  </div>

  <!-- 前回データ -->
  <div class="prev-block" id="prev-block">
    <div class="prev-label">前回購入</div>
    <div id="prev-content"></div>
  </div>

  <!-- 入力フォーム -->
  <div class="form-section">
    <label class="form-label" for="f-name">商品名</label>
    <input type="text" id="f-name" list="name-list" placeholder="商品名を入力" autocomplete="off">
    <datalist id="name-list"></datalist>
  </div>

  <div class="form-section row2">
    <div>
      <label class="form-label" for="f-cat">カテゴリ</label>
      <select id="f-cat">
        <option value="">— 選択 —</option>
      </select>
    </div>
    <div>
      <label class="form-label" for="f-date">購入日</label>
      <input type="date" id="f-date">
    </div>
  </div>

  <div class="form-section row2">
    <div>
      <label class="form-label" for="f-price">💴 金額（円）</label>
      <input type="number" id="f-price" placeholder="例: 498" min="0" inputmode="numeric">
    </div>
    <div>
      <label class="form-label" for="f-volume">📦 容量</label>
      <input type="number" id="f-volume" placeholder="例: 500" min="0" inputmode="numeric">
    </div>
  </div>

  <div class="form-section">
    <label class="form-label" for="f-store">🏪 購入場所</label>
    <select id="f-store">
      <option value="">— 選択 —</option>
    </select>
  </div>

  <!-- 比較結果 -->
  <div class="result-box" id="result-box">
    <div class="result-verdict" id="result-verdict"></div>
    <div class="bars" id="bars"></div>
  </div>

  <button class="btn-save" id="btn-save" onclick="savePurchase()">💾 保存する</button>
  <div class="save-msg" id="save-msg"></div>
</div>

<script>
// ── State ──────────────────────────────────────────────────────────────────
let products = [], allNames = [], currentCat = '', selectedProduct = null;

const CATS = ["食品","飲料","日用品","衛生用品","掃除用品","医薬品","ペット用品","その他"];
const STORES = ["スーパー","コンビニ","ドラッグストア","Amazon","楽天","ネット通販","ホームセンター","業務スーパー","コストコ","その他"];

const CAT_ICONS = {
  "食品":"🍱","飲料":"🥤","日用品":"🧴","衛生用品":"🪥",
  "掃除用品":"🧹","医薬品":"💊","ペット用品":"🐾","その他":"📦","":" 📦"
};

// ── Init ───────────────────────────────────────────────────────────────────
document.getElementById('f-date').value = new Date().toISOString().slice(0,10);

CATS.forEach(c => {
  const o = document.createElement('option'); o.value = c; o.textContent = c;
  document.getElementById('f-cat').appendChild(o);
});
STORES.forEach(s => {
  const o = document.createElement('option'); o.value = s; o.textContent = s;
  document.getElementById('f-store').appendChild(o);
});

async function loadProducts() {
  try {
    const r = await fetch('/api/products');
    const d = await r.json();
    products = d.products;
    allNames = d.names;

    // datalist
    const dl = document.getElementById('name-list');
    dl.innerHTML = '';
    allNames.forEach(n => {
      const o = document.createElement('option'); o.value = n; dl.appendChild(o);
    });

    // category tabs
    const tabs = document.getElementById('tabs');
    tabs.innerHTML = '<button class="tab active" onclick="filterCat(\\'\\')">すべて</button>';
    d.categories.forEach(c => {
      const b = document.createElement('button');
      b.className = 'tab';
      b.textContent = (CAT_ICONS[c] || '📦') + ' ' + c;
      b.onclick = () => filterCat(c);
      tabs.appendChild(b);
    });

    renderList();
  } catch(e) {
    document.getElementById('list').innerHTML =
      '<div class="empty">⚠️ 読み込みに失敗しました<br><small>サーバーを確認してください</small></div>';
  }
}

function renderList() {
  const filtered = currentCat
    ? products.filter(p => p.category === currentCat)
    : products;
  const list = document.getElementById('list');

  if (!filtered.length) {
    list.innerHTML = '<div class="empty">商品がありません<br><small>＋ボタンで追加してください</small></div>';
    return;
  }

  list.innerHTML = filtered.map(p => {
    const icon = CAT_ICONS[p.category] || '📦';
    const priceStr = p.price ? '¥' + p.price.toLocaleString('ja-JP') : '未記録';
    const unitStr  = (p.unit_price && p.volume)
      ? `¥${p.unit_price.toFixed(1)}/単位` : '';
    const meta = [p.store, p.date ? p.date.slice(0,7) : ''].filter(Boolean).join(' · ');

    // 最安値バッジ（単価データがある場合のみ）
    let bestHtml = '';
    if (p.best_unit_price > 0 && p.unit_price > 0) {
      const isBest = Math.abs(p.unit_price - p.best_unit_price) < 0.001;
      if (isBest) {
        bestHtml = `<div class="pc-best is-best">★ 最安値</div>`;
      } else {
        bestHtml = `<div class="pc-best not-best">最安 ¥${p.best_unit_price.toFixed(1)}/単位</div>`;
      }
    }

    return `
      <button class="product-card" onclick="openProduct('${p.name.replace(/'/g,"\\'")}')">
        <div class="pc-icon">${icon}</div>
        <div class="pc-body">
          <div class="pc-name">${p.name}</div>
          <div class="pc-meta">${meta}</div>
        </div>
        <div class="pc-price">
          <div class="pc-price-val">${priceStr}</div>
          <div class="pc-price-sub">${unitStr}</div>
          ${bestHtml}
        </div>
      </button>`;
  }).join('');
}

function filterCat(cat) {
  currentCat = cat;
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  event.currentTarget.classList.add('active');
  renderList();
}

// ── Sheet ──────────────────────────────────────────────────────────────────
function openSheet() {
  document.getElementById('overlay').classList.add('show');
  document.getElementById('sheet').classList.add('show');
  document.body.style.overflow = 'hidden';
  resetResult();
}
function closeSheet() {
  document.getElementById('overlay').classList.remove('show');
  document.getElementById('sheet').classList.remove('show');
  document.body.style.overflow = '';
  selectedProduct = null;
}

function openNew() {
  selectedProduct = null;
  document.getElementById('sheet-title').textContent = '新規商品を追加';
  document.getElementById('f-name').value = '';
  document.getElementById('f-name').readOnly = false;
  document.getElementById('f-price').value = '';
  document.getElementById('f-volume').value = '';
  document.getElementById('f-cat').value = '';
  document.getElementById('f-store').value = '';
  document.getElementById('f-date').value = new Date().toISOString().slice(0,10);
  document.getElementById('prev-block').style.display = 'none';
  openSheet();
}

async function openProduct(name) {
  document.getElementById('sheet-title').textContent = name;
  document.getElementById('f-name').value = name;
  document.getElementById('f-name').readOnly = true;
  document.getElementById('f-price').value = '';
  document.getElementById('f-volume').value = '';
  document.getElementById('f-date').value = new Date().toISOString().slice(0,10);

  // 前回データを取得（最新1件）
  const prev = products.find(p => p.name === name);
  selectedProduct = prev || null;

  const pb = document.getElementById('prev-block');
  const pc = document.getElementById('prev-content');

  if (prev && prev.price) {
    pb.style.display = 'block';
    const unitLine = (prev.unit_price && prev.volume)
      ? `<div class="prev-unit">¥${prev.unit_price.toFixed(2)} / 単位 (${prev.volume})</div>` : '';
    const badges = [prev.store, prev.date, prev.volume ? `容量 ${prev.volume}` : '']
      .filter(Boolean)
      .map(t => `<span class="badge">${t}</span>`).join('');
    pc.innerHTML = `
      <div class="prev-price">¥${prev.price.toLocaleString('ja-JP')}</div>
      ${unitLine}
      <div class="prev-meta">${badges}</div>`;

    // 購入場所・カテゴリをプリセット
    if (prev.store)    document.getElementById('f-store').value = prev.store;
    if (prev.category) document.getElementById('f-cat').value   = prev.category;
    if (prev.volume)   document.getElementById('f-volume').value = prev.volume;
  } else {
    pb.style.display = 'block';
    pc.innerHTML = '<div class="no-prev">前回のデータがありません（初回登録）</div>';
  }

  openSheet();
}

// ── Live compare ───────────────────────────────────────────────────────────
['f-price','f-volume'].forEach(id => {
  document.getElementById(id).addEventListener('input', showCompare);
});

function resetResult() {
  const rb = document.getElementById('result-box');
  rb.className = 'result-box';
}

function showCompare() {
  const rb  = document.getElementById('result-box');
  const rv  = document.getElementById('result-verdict');
  const bars= document.getElementById('bars');

  const price  = parseFloat(document.getElementById('f-price').value) || 0;
  const volume = parseFloat(document.getElementById('f-volume').value) || 0;

  if (!price || !selectedProduct || !selectedProduct.price) {
    rb.className = 'result-box'; return;
  }

  const prev = selectedProduct;
  let prevVal, nowVal, label;

  if (volume && prev.volume) {
    prevVal = prev.price / prev.volume;
    nowVal  = price     / volume;
    label   = '単位あたり';
  } else {
    prevVal = prev.price;
    nowVal  = price;
    label   = '金額';
  }

  const ratio   = nowVal / prevVal;
  const pct     = Math.abs((ratio - 1) * 100).toFixed(1);
  const cheaper = ratio < 0.9995;
  const pricier = ratio > 1.0005;
  const cls     = cheaper ? 'cheaper' : pricier ? 'pricier' : 'same';

  const emojis  = {cheaper:'📉',pricier:'📈',same:'➡️'};
  const texts   = {
    cheaper: `${pct}% お得！`,
    pricier: `${pct}% 高い`,
    same:    '変動なし'
  };

  rb.className = `result-box show ${cls}`;
  rv.className = `result-verdict ${cls}`;
  rv.innerHTML = `${emojis[cls]} <span>${texts[cls]}</span>`;

  const maxV   = Math.max(prevVal, nowVal);
  const prevW  = Math.round(prevVal / maxV * 100);
  const nowW   = Math.round(nowVal  / maxV * 100);
  const nowCls = pricier ? 'now-bar up' : 'now-bar';

  const fmt = v => label === '単位あたり'
    ? `¥${v.toFixed(2)}`
    : `¥${Math.round(v).toLocaleString('ja-JP')}`;

  bars.innerHTML = `
    <div class="bar-row">
      <span class="bar-label-txt">前</span>
      <div class="bar-track"><div class="bar-fill prev-bar" style="width:${prevW}%"></div></div>
      <span class="bar-val">${fmt(prevVal)}</span>
    </div>
    <div class="bar-row">
      <span class="bar-label-txt">今</span>
      <div class="bar-track"><div class="bar-fill ${nowCls}" style="width:0%"
        data-w="${nowW}"></div></div>
      <span class="bar-val">${fmt(nowVal)}</span>
    </div>`;

  // バーアニメーション
  setTimeout(() => {
    const fill = bars.querySelector('[data-w]');
    if (fill) fill.style.width = fill.dataset.w + '%';
  }, 30);
}

// ── Save ───────────────────────────────────────────────────────────────────
async function savePurchase() {
  const btn = document.getElementById('btn-save');
  const msg = document.getElementById('save-msg');
  const name  = document.getElementById('f-name').value.trim();
  const price = parseFloat(document.getElementById('f-price').value) || 0;

  if (!name)  { msg.textContent = '⚠️ 商品名を入力してください'; msg.style.color='var(--up)'; return; }
  if (!price) { msg.textContent = '⚠️ 金額を入力してください';   msg.style.color='var(--up)'; return; }

  btn.disabled = true;
  msg.textContent = '保存中…';
  msg.style.color = 'var(--sub)';

  const body = {
    name,
    price,
    volume:   parseFloat(document.getElementById('f-volume').value) || 0,
    category: document.getElementById('f-cat').value,
    store:    document.getElementById('f-store').value,
    date:     document.getElementById('f-date').value,
  };

  try {
    const r = await fetch('/api/save', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify(body)
    });
    const d = await r.json();
    if (d.ok) {
      msg.textContent = '✅ 保存しました！';
      msg.style.color = 'var(--dn)';

      // ローカルのproductsを更新
      const idx = products.findIndex(p => p.name === name);
      if (idx >= 0) products[idx] = d.record;
      else { products.push(d.record); products.sort((a,b)=>a.name.localeCompare(b.name,'ja')); }
      if (!allNames.includes(name)) allNames.push(name);
      renderList();

      setTimeout(() => { closeSheet(); }, 1200);
    } else {
      throw new Error(d.error);
    }
  } catch(e) {
    msg.textContent = '❌ 保存失敗: ' + e.message;
    msg.style.color = 'var(--up)';
    btn.disabled = false;
  }
}

// ── Boot ───────────────────────────────────────────────────────────────────
loadProducts();
</script>
</body>
</html>"""

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
