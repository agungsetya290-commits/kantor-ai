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


def http(url, data=None, timeout=40):
    req = urllib.request.Request(url, data=data, headers={
        "User-Agent": UA, "Content-Type": "application/json", "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def pick_models():
    """Daftar model gratis yang tersedia untuk key ini, urut dari yang paling bagus.
    Tidak hardcode nama, dan menyediakan cadangan kalau satu model lagi penuh (503)."""
    override = os.environ.get("GEMINI_MODEL", "").strip()
    if override:
        return [override]
    try:
        body = json.loads(http(f"{BASE}/models?key={KEY}&pageSize=200"))
    except Exception as e:
        print(f"[model] gagal list model: {e}", file=sys.stderr)
        return ["gemini-flash-latest"]
    names = []
    for m in body.get("models", []):
        n = m.get("name", "").replace("models/", "")
        if "generateContent" not in m.get("supportedGenerationMethods", []):
            continue
        if any(b in n.lower() for b in MODEL_BLOCK):
            continue
        names.append(n)
    ranked = []
    for pref in MODEL_PREF:
        for n in names:
            if pref in n.lower() and n not in ranked:
                ranked.append(n)
    ranked = ranked or names
    print(f"[model] kandidat: {ranked[:3]}")
    return ranked[:3] or ["gemini-flash-latest"]


def ask(models, prompt, retries=2):
    """Satu permintaan ke Gemini, minta JSON. Kalau satu model sibuk (429/503),
    tunggu lalu coba lagi; habis itu pindah ke model cadangan."""
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.9, "maxOutputTokens": 2048,
                             "responseMimeType": "application/json"},
    }).encode()
    last = None
    for model in models:
        for i in range(retries):
            try:
                body = json.loads(http(f"{BASE}/models/{model}:generateContent?key={KEY}", payload))
                txt = body["candidates"][0]["content"]["parts"][0]["text"]
                return json.loads(txt), model
            except urllib.error.HTTPError as e:
                last = f"HTTP {e.code} ({model})"
                print(f"[gemini] {last}: {e.read().decode()[:200]}", file=sys.stderr)
                if e.code in (429, 500, 502, 503) and i < retries - 1:
                    time.sleep(10 * (i + 1))
                    continue
                break
            except Exception as e:
                last = f"{type(e).__name__} ({model}): {e}"
                print(f"[gemini] {last}", file=sys.stderr)
                if i < retries - 1:
                    time.sleep(8)
                    continue
                break
        print(f"[gemini] pindah model, {model} tidak bisa dipakai", file=sys.stderr)
    raise RuntimeError(f"semua model gagal; terakhir: {last}")


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


def shift(models):
    """Satu shift. Tiap agent dibungkus sendiri: kalau satu gagal, sisanya tetap kerja."""
    agents, log, dipakai = {}, [], []
    mulai = time.time()
    BATAS = 420  # detik; shift berhenti rapi kalau Google lambat terus

    def kerja(key, nama, divisi, peran, prompt, catatan=None):
        entry = {"nama": nama, "divisi": divisi, "peran": peran}
        if catatan:
            entry["catatan"] = catatan
        try:
            if time.time() - mulai > BATAS:
                raise RuntimeError("batas waktu shift tercapai, agent ini dilewati")
            hasil, model = ask(models, prompt)
            entry["hasil"] = hasil
            dipakai.append(model)
            log.append(f"{nama} {peran.lower()} selesai")
        except Exception as e:
            entry["hasil"] = {"gagal": str(e)}
            entry["error"] = str(e)
            log.append(f"{nama} gagal: {e}")
        agents[key] = entry
        return entry.get("hasil") if "error" not in entry else {}

    # --- Divisi Shorts & Editor ---
    tren = feed(FEED_SHORTS)
    nova = kerja("gendol", "Gendol", "Shorts & Editor", "Trend hunter", f"""Kamu Gendol, karyawan trend hunter di kantor milik CEO Gembi. Judul berita/post minggu ini:
{json.dumps(tren, ensure_ascii=False)}

Dari bahan itu, usulkan 3 ide YouTube Shorts 9:16 untuk penonton LUAR NEGERI (narasi bahasa Inggris).
Niche yang dipegang kanal: kisah/sejarah singkat, horor atmosferik, ambience. Hindari ide yang butuh wajah di kamera.
Tandai sumber tiap ide: "berita" kalau dari judul di atas, "lab" kalau ide sendiri (bukan tren nyata).
Skema: {{"ide":[{{"judul_kerja":"","sudut":"","kenapa_nonton":"","sumber":"berita|lab"}}]}}""",
        catatan=f"{len(tren)} judul terbaca dari RSS")

    pilih = (nova.get("ide") or [{}])[0] if isinstance(nova, dict) else {}
    ale = kerja("paero", "Paero", "Shorts & Editor", "Naskah", f"""Kamu Paero, karyawan penulis naskah Shorts. Ide terpilih:
{json.dumps(pilih, ensure_ascii=False)}

Tulis naskah Shorts 35-45 detik, narasi bahasa INGGRIS, hook di 2 detik pertama, ada pertanyaan penutup.
Skema: {{"hook":"","naskah":[{{"detik":"0-3","narasi":"","teks_layar":""}}],"cta":"","durasi_detik":0}}
{RULES}""")

    kerja("bonyek", "Bonyek", "Shorts & Editor", "Editor video", f"""Kamu Bonyek, karyawan editor video. Naskah:
{json.dumps(ale, ensure_ascii=False)}

Buat instruksi edit siap pakai (CapCut/Remotion): per shot ada visual, animasi teks (nama efek + durasi), transisi, SFX/musik.
Skema: {{"shot":[{{"detik":"","visual":"","teks":"","animasi_teks":"","transisi":"","sfx":""}}],"musik":"","safe_area":"","by_agung":"posisi tulisan kecil 'by Agung' di atas"}}
{RULES}""")

    # --- Divisi Affiliate & Sosmed ---
    gadget = feed(FEED_GADGET)
    sari = kerja("botak", "Botak", "Affiliate & Sosmed", "Riset produk", f"""Kamu Botak, karyawan riset produk affiliate gadget. Judul berita gadget hari ini:
{json.dumps(gadget, ensure_ascii=False)}

Usulkan 3 ide konten "tips gadget" untuk TikTok/Shopee affiliate (keranjang kuning), format video pendek, tanpa wajah.
Jangan sebut harga pasti atau klaim penghasilan. Tandai sumber: "berita" atau "lab".
Skema: {{"ide":[{{"topik":"","masalah_penonton":"","produk_tipe":"","hook":"","sumber":"berita|lab"}}]}}""",
        catatan=f"{len(gadget)} judul terbaca dari RSS")

    dimas = kerja("mahim", "Mahim", "Affiliate & Sosmed", "Caption", f"""Kamu Mahim, karyawan copywriter sosmed. Ide produk:
{json.dumps((sari.get("ide") or [])[:2] if isinstance(sari, dict) else [], ensure_ascii=False)}

Tulis caption untuk 3 platform: TikTok (pendek, ada CTA keranjang kuning), Threads (santai), Facebook (agak panjang).
Bahasa Indonesia, tanpa klaim berlebihan, tanpa harga pasti.
Skema: {{"paket":[{{"topik":"","tiktok":"","threads":"","facebook":"","hashtag":[]}}]}}""")

    kerja("rahma", "Rahma", "Sekretariat", "Sekretaris CEO", f"""Kamu Rahma, sekretaris CEO Gembi. Laporan karyawan malam ini:
Status kerja: {json.dumps(log, ensure_ascii=False)}
Shorts: {json.dumps({"hook": ale.get("hook") if isinstance(ale, dict) else None}, ensure_ascii=False)}
Caption: {json.dumps([p.get("topik") for p in (dimas.get("paket") or [])] if isinstance(dimas, dict) else [], ensure_ascii=False)}

Tulis laporan singkat untuk CEO Gembi: apa yang sudah jadi, apa yang gagal, dan apa yang perlu Gembi cek dulu.
Lalu susun antrean posting 3 hari ke depan (jam padat Indonesia untuk affiliate, jam padat US/EU untuk Shorts Inggris).
Gembi yang memutuskan dan posting manual; kamu tidak posting.
Skema: {{"laporan_ceo":"","perlu_dicek":[],"antrean":[{{"hari":"","jam_wib":"","platform":"","isi":"","status":"nunggu persetujuan CEO"}}]}}""")

    return agents, log, dipakai


def tulis_antrean(data):
    """Tambahkan caption Threads dari Mahim ke antrean, status menunggu CEO.

    Baris lama tidak diubah: yang sudah disetujui atau terkirim tetap apa adanya.
    """
    path = os.path.join(DATA, "antrean.json")
    try:
        antrean = json.load(open(path, encoding="utf-8"))
    except Exception:
        antrean = []
    sudah = {a.get("id") for a in antrean}

    mahim = (data.get("agents", {}).get("mahim") or {}).get("hasil") or {}
    paket = mahim.get("paket") if isinstance(mahim, dict) else None
    baru = 0
    for i, p in enumerate(paket or [], 1):
        teks = (p.get("threads") or "").strip()
        if not teks:
            continue
        tag = " ".join(p.get("hashtag") or [])
        kid = f"{data['tanggal']}-mahim-{i}"
        if kid in sudah:
            continue
        antrean.append({
            "id": kid,
            "tanggal": data["tanggal"],
            "judul": p.get("topik") or f"caption {i}",
            "platform": "threads",
            "teks": (teks + ("\n\n" + tag if tag else "")).strip(),
            "setujui": False,
            "terkirim": False,
        })
        baru += 1

    antrean = antrean[-60:]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(antrean, f, ensure_ascii=False, indent=1)
    print(f"[antrean] {baru} baris baru, total {len(antrean)}")


def main():
    now = datetime.now(WIB)
    data = {"tanggal": now.strftime("%Y-%m-%d"), "jam": now.strftime("%H:%M WIB"),
            "status": "selesai", "model": None, "agents": {}, "log": [], "error": None}
    if not KEY:
        data.update(status="gagal", error="GEMINI_API_KEY belum diisi di repository secrets")
    else:
        models = pick_models()
        try:
            agents, log, dipakai = shift(models)
            data["agents"], data["log"] = agents, log
            data["model"] = dipakai[0] if dipakai else models[0]
            gagal = [a for a in agents.values() if "error" in a]
            if len(gagal) == len(agents):
                data.update(status="gagal", error=gagal[0]["error"] if gagal else "semua agent gagal")
            elif gagal:
                data.update(status="sebagian", error=f"{len(gagal)} agent gagal: {gagal[0]['error']}")
        except Exception as e:
            data.update(status="gagal", error=f"{type(e).__name__}: {e}")

    os.makedirs(DATA, exist_ok=True)
    with open(os.path.join(DATA, "shift.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    tulis_antrean(data)

    hist_path = os.path.join(DATA, "history.json")
    try:
        hist = json.load(open(hist_path, encoding="utf-8"))
    except Exception:
        hist = []
    hist = [h for h in hist if h.get("tanggal") != data["tanggal"]]
    hist.insert(0, data)
    with open(hist_path, "w", encoding="utf-8") as f:
        json.dump(hist[:7], f, ensure_ascii=False, indent=1)

    print(f"[shift] {data['status']} - {len(data['agents'])} agent")
    sys.exit(0 if data["status"] in ("selesai", "sebagian") else 1)


if __name__ == "__main__":
    main()
