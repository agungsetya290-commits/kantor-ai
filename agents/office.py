#!/usr/bin/env python3
"""Kantor AI - satu shift malam. Jalan di GitHub Actions, tulis hasil ke data/."""
import json, os, re, sys, time, urllib.request, urllib.error, xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
KEY = os.environ.get("GEMINI_API_KEY", "").strip()
BASE = "https://generativelanguage.googleapis.com/v1beta"
WIB = timezone(timedelta(hours=7))
UA = "Mozilla/5.0 (compatible; KantorAI/1.0)"
# urutan pilihan model gratis (substring), paling bagus duluan
MODEL_PREF = ["3.8-flash", "3.6-flash", "3.5-flash", "flash-lite", "flash"]
MODEL_BLOCK = ["image", "video", "embedding", "tts", "live", "audio", "vision", "gemma"]


def http(url, data=None, timeout=90):
    req = urllib.request.Request(url, data=data, headers={
        "User-Agent": UA, "Content-Type": "application/json", "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def pick_model():
    """Tanya API model apa yang tersedia untuk key ini. Tidak hardcode nama."""
    override = os.environ.get("GEMINI_MODEL", "").strip()
    if override:
        return override
    try:
        body = json.loads(http(f"{BASE}/models?key={KEY}&pageSize=200"))
    except Exception as e:
        print(f"[model] gagal list model: {e}", file=sys.stderr)
        return "gemini-flash-latest"
    names = []
    for m in body.get("models", []):
        n = m.get("name", "").replace("models/", "")
        if "generateContent" not in m.get("supportedGenerationMethods", []):
            continue
        if any(b in n.lower() for b in MODEL_BLOCK):
            continue
        names.append(n)
    for pref in MODEL_PREF:
        hit = [n for n in names if pref in n.lower() and "preview" not in n.lower()]
        hit += [n for n in names if pref in n.lower() and "preview" in n.lower()]
        if hit:
            print(f"[model] pakai {hit[0]}")
            return hit[0]
    print(f"[model] fallback; kandidat={names[:5]}", file=sys.stderr)
    return names[0] if names else "gemini-flash-latest"


def ask(model, prompt, retries=3):
    """Satu panggilan Gemini, minta JSON. Free tier ~5 RPM -> ada jeda + retry 429."""
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.9, "maxOutputTokens": 2048,
                             "responseMimeType": "application/json"},
    }).encode()
    url = f"{BASE}/models/{model}:generateContent?key={KEY}"
    for i in range(retries):
        try:
            body = json.loads(http(url, payload))
            txt = body["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(txt)
        except urllib.error.HTTPError as e:
            msg = e.read().decode()[:300]
            print(f"[gemini] HTTP {e.code}: {msg}", file=sys.stderr)
            if e.code in (429, 500, 503) and i < retries - 1:
                time.sleep(20 * (i + 1))
                continue
            raise
        except Exception as e:
            print(f"[gemini] {type(e).__name__}: {e}", file=sys.stderr)
            if i < retries - 1:
                time.sleep(10)
                continue
            raise


def feed(urls, limit=12):
    """Judul berita/post dari RSS. Data nyata, bukan tebakan model."""
    out = []
    for u in urls:
        try:
            raw = http(u, timeout=30)
            root = ET.fromstring(raw)
            for item in root.iter():
                if item.tag.split("}")[-1] not in ("item", "entry"):
                    continue  # lewati judul feed-nya sendiri, ambil judul isi saja
                for t in item:
                    if t.tag.split("}")[-1] == "title" and t.text:
                        s = re.sub(r"\s+", " ", t.text).strip()
                        if len(s) > 15:
                            out.append(s)
        except Exception as e:
            print(f"[feed] {u} gagal: {e}", file=sys.stderr)
    seen, uniq = set(), []
    for s in out:
        if s.lower() not in seen:
            seen.add(s.lower())
            uniq.append(s)
    return uniq[:limit]


FEED_SHORTS = [
    "https://news.google.com/rss/search?q=youtube+shorts+trend&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=viral+short+video&hl=en-US&gl=US&ceid=US:en",
]
FEED_GADGET = [
    "https://news.google.com/rss/search?q=gadget+murah+review&hl=id&gl=ID&ceid=ID:id",
    "https://news.google.com/rss/search?q=hp+baru+rilis&hl=id&gl=ID&ceid=ID:id",
]

RULES = ("Aturan wajib: tiap teks di video diberi efek animasi (jangan teks polos). "
         "Di bagian atas frame ada tulisan kecil 'by Agung'. Tanpa watermark/logo lain. "
         "Balas HANYA JSON valid sesuai skema.")


def shift(model):
    log = []
    agents = {}

    # --- Divisi Shorts & Editor ---
    tren = feed(FEED_SHORTS)
    nova = ask(model, f"""Kamu Nova, trend hunter kantor konten. Judul berita/post minggu ini:
{json.dumps(tren, ensure_ascii=False)}

Dari bahan itu, usulkan 3 ide YouTube Shorts 9:16 untuk penonton LUAR NEGERI (narasi bahasa Inggris).
Niche yang dipegang kanal: kisah/sejarah singkat, horor atmosferik, ambience. Hindari ide yang butuh wajah di kamera.
Tandai sumber tiap ide: "berita" kalau dari judul di atas, "lab" kalau ide sendiri (bukan tren nyata).
Skema: {{"ide":[{{"judul_kerja":"","sudut":"","kenapa_nonton":"","sumber":"berita|lab"}}]}}""")
    agents["nova"] = {"nama": "Nova", "divisi": "Shorts & Editor", "peran": "Trend hunter",
                      "hasil": nova, "catatan": f"{len(tren)} judul terbaca dari RSS"}
    log.append("Nova riset tren Shorts")

    pilih = (nova.get("ide") or [{}])[0]
    ale = ask(model, f"""Kamu Ale, penulis naskah Shorts. Ide terpilih:
{json.dumps(pilih, ensure_ascii=False)}

Tulis naskah Shorts 35-45 detik, narasi bahasa INGGRIS, hook di 2 detik pertama, ada pertanyaan penutup.
Skema: {{"hook":"","naskah":[{{"detik":"0-3","narasi":"","teks_layar":""}}],"cta":"","durasi_detik":0}}
{RULES}""")
    agents["ale"] = {"nama": "Ale", "divisi": "Shorts & Editor", "peran": "Naskah", "hasil": ale}
    log.append("Ale tulis naskah Shorts")

    rara = ask(model, f"""Kamu Rara, editor video. Naskah:
{json.dumps(ale, ensure_ascii=False)}

Buat instruksi edit siap pakai (CapCut/Remotion): per shot ada visual, animasi teks (nama efek + durasi), transisi, SFX/musik.
Skema: {{"shot":[{{"detik":"","visual":"","teks":"","animasi_teks":"","transisi":"","sfx":""}}],"musik":"","safe_area":"","by_agung":"posisi tulisan kecil 'by Agung' di atas"}}
{RULES}""")
    agents["rara"] = {"nama": "Rara", "divisi": "Shorts & Editor", "peran": "Editor", "hasil": rara}
    log.append("Rara susun instruksi edit")

    # --- Divisi Affiliate & Sosmed ---
    gadget = feed(FEED_GADGET)
    sari = ask(model, f"""Kamu Sari, riset produk affiliate gadget. Judul berita gadget hari ini:
{json.dumps(gadget, ensure_ascii=False)}

Usulkan 3 ide konten "tips gadget" untuk TikTok/Shopee affiliate (keranjang kuning), format video pendek, tanpa wajah.
Jangan sebut harga pasti atau klaim penghasilan. Tandai sumber: "berita" atau "lab".
Skema: {{"ide":[{{"topik":"","masalah_penonton":"","produk_tipe":"","hook":"","sumber":"berita|lab"}}]}}""")
    agents["sari"] = {"nama": "Sari", "divisi": "Affiliate & Sosmed", "peran": "Riset produk",
                      "hasil": sari, "catatan": f"{len(gadget)} judul terbaca dari RSS"}
    log.append("Sari riset produk gadget")

    dimas = ask(model, f"""Kamu Dimas, copywriter sosmed. Ide produk:
{json.dumps(sari.get("ide", [])[:2], ensure_ascii=False)}

Tulis caption untuk 3 platform: TikTok (pendek, ada CTA keranjang kuning), Threads (santai), Facebook (agak panjang).
Bahasa Indonesia, tanpa klaim berlebihan, tanpa harga pasti.
Skema: {{"paket":[{{"topik":"","tiktok":"","threads":"","facebook":"","hashtag":[]}}]}}""")
    agents["dimas"] = {"nama": "Dimas", "divisi": "Affiliate & Sosmed", "peran": "Caption",
                       "hasil": dimas}
    log.append("Dimas tulis caption 3 platform")

    bima = ask(model, f"""Kamu Bima, admin antrean posting. Bahan siap:
Shorts: {json.dumps({"hook": ale.get("hook"), "durasi": ale.get("durasi_detik")}, ensure_ascii=False)}
Caption: {json.dumps([p.get("topik") for p in dimas.get("paket", [])], ensure_ascii=False)}

Susun antrean posting 3 hari ke depan. Jam padat penonton Indonesia untuk affiliate, jam padat US/EU untuk Shorts bahasa Inggris.
Agung posting manual dari antrean ini.
Skema: {{"antrean":[{{"hari":"","jam_wib":"","platform":"","isi":"","status":"nunggu dicek"}}]}}""")
    agents["bima"] = {"nama": "Bima", "divisi": "Affiliate & Sosmed", "peran": "Antrean posting",
                      "hasil": bima}
    log.append("Bima susun antrean posting")

    return agents, log


def main():
    now = datetime.now(WIB)
    shift_data = {"tanggal": now.strftime("%Y-%m-%d"), "jam": now.strftime("%H:%M WIB"),
                  "status": "selesai", "model": None, "agents": {}, "log": [], "error": None}
    if not KEY:
        shift_data.update(status="gagal", error="GEMINI_API_KEY belum diisi di repository secrets")
    else:
        model = pick_model()
        shift_data["model"] = model
        try:
            agents, log = shift(model)
            shift_data["agents"], shift_data["log"] = agents, log
        except Exception as e:
            shift_data.update(status="gagal", error=f"{type(e).__name__}: {e}")

    os.makedirs(DATA, exist_ok=True)
    with open(os.path.join(DATA, "shift.json"), "w", encoding="utf-8") as f:
        json.dump(shift_data, f, ensure_ascii=False, indent=1)

    hist_path = os.path.join(DATA, "history.json")
    try:
        hist = json.load(open(hist_path, encoding="utf-8"))
    except Exception:
        hist = []
    hist = [h for h in hist if h.get("tanggal") != shift_data["tanggal"]]
    hist.insert(0, shift_data)
    with open(hist_path, "w", encoding="utf-8") as f:
        json.dump(hist[:7], f, ensure_ascii=False, indent=1)

    print(f"[shift] {shift_data['status']} - {len(shift_data['agents'])} agent")
    sys.exit(0 if shift_data["status"] == "selesai" else 1)


if __name__ == "__main__":
    main()
