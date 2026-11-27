#!/usr/bin/env python3
"""Kantor AI - satu shift malam. Jalan di GitHub Actions, tulis hasil ke data/."""
import json, os, re, sys, time, urllib.parse, urllib.request, urllib.error, xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from giliran import giliran

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
KEY = os.environ.get("GEMINI_API_KEY", "").strip()
BASE = "https://generativelanguage.googleapis.com/v1beta"
WIB = timezone(timedelta(hours=7))
UA = "Mozilla/5.0 (compatible; KantorAI/1.0)"
# urutan pilihan model gratis (substring), paling bagus duluan
MODEL_PREF = ["3.8-flash", "3.6-flash", "3.5-flash", "flash-lite", "flash"]
MODEL_BLOCK = ["image", "video", "embedding", "tts", "live", "audio", "vision", "gemma"]


def http(url, data=None, timeout=120):
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
        "generationConfig": {"temperature": 0.9, "maxOutputTokens": 8192,
                             "responseMimeType": "application/json"},
    }).encode()
    last = None
    for model in models:
        for i in range(retries):
            try:
                body = json.loads(http(f"{BASE}/models/{model}:generateContent?key={KEY}", payload))
                txt = body["candidates"][0]["content"]["parts"][0]["text"].strip()
                # bersihkan markdown code block jika ada
                if txt.startswith("```json"):
                    txt = txt[7:]
                if txt.startswith("```"):
                    txt = txt[3:]
                if txt.endswith("```"):
                    txt = txt[:-3]
                return json.loads(txt.strip()), model
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
    "https://news.google.com/rss/search?q=aksesoris+hp&hl=id&gl=ID&ceid=ID:id",
    "https://news.google.com/rss/search?q=gadget+terbaru&hl=id&gl=ID&ceid=ID:id",
]

RULES = ("Aturan wajib: tiap teks di video diberi efek animasi (jangan teks polos). "
         "Di bagian atas frame ada tulisan kecil 'by Agung'. Tanpa watermark/logo lain. "
         "Balas HANYA JSON valid sesuai skema.")


def tren_threads(kata=("aksesoris hp", "powerbank", "earbuds")):
    """Apa yang lagi dibicarakan orang di Threads soal niche ini.

    Pakai keyword search resmi; kalau token tidak punya izinnya atau API menolak,
    kembalikan daftar kosong dan kantor jalan seperti biasa dengan bahan RSS.
    """
    token = os.environ.get("THREADS_TOKEN", "").strip()
    if not token:
        return []
    out = []
    for q in kata:
        url = ("https://graph.threads.net/v1.0/keyword_search"
               f"?q={urllib.parse.quote(q)}&search_type=TOP&fields=text&access_token={token}")
        try:
            body = json.loads(http(url, timeout=25))
            for m in (body.get("data") or [])[:4]:
                t = re.sub(r"\s+", " ", (m.get("text") or "")).strip()
                if 20 < len(t) < 220:
                    out.append(t)
        except Exception as e:
            print(f"[tren] {q} gagal: {e}", file=sys.stderr)
    return out[:10]


def judul_terpakai(n=15):
    """Judul caption yang sudah pernah masuk antrean, supaya tidak diulang."""
    try:
        d = json.load(open(os.path.join(DATA, "antrean.json"), encoding="utf-8"))
        return [a.get("judul", "") for a in d][-n:]
    except Exception:
        return []


def baca_produk():
    """Daftar produk afiliasi milik Agung: nama + link Shopee yang dia tempel sendiri."""
    try:
        d = json.load(open(os.path.join(DATA, "produk.json"), encoding="utf-8"))
        return [p for p in d if p.get("nama") and p.get("link")]
    except Exception:
        return []


def shift(models):
    """Satu shift. Tiap agent dibungkus sendiri: kalau satu gagal, sisanya tetap kerja."""
    agents, log, dipakai = {}, [], []
    mulai = time.time()
    BATAS = 900  # detik; shift berhenti rapi kalau Google lambat terus

    def kerja(key, nama, divisi, peran, prompt, catatan=None, syarat=True):
        entry = {"nama": nama, "divisi": divisi, "peran": peran}
        if catatan:
            entry["catatan"] = catatan
        try:
            if not syarat:
                raise RuntimeError("bahan dari agent sebelumnya kosong, agent ini dilewati")
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
    semua_produk = baca_produk()
    try:
        antrean_lama = json.load(open(os.path.join(DATA, "antrean.json"), encoding="utf-8"))
    except Exception:
        antrean_lama = []
    produk = giliran(semua_produk, antrean_lama, 5)
    nama_produk = [p["nama"] for p in produk]
    riwayat = judul_terpakai()
    tren = tren_threads()
    aturan_produk = (f"\nPilih produk HANYA dari daftar ini, salin namanya persis: "
                     f"{json.dumps(nama_produk, ensure_ascii=False)}. Isi field produk dengan nama itu."
                     if nama_produk else
                     "\nDaftar produk afiliasi masih kosong, isi field produk dengan string kosong.")
    sari = kerja("botak", "Botak", "Affiliate & Sosmed", "Riset produk", f"""Kamu Botak, karyawan riset produk affiliate gadget. Judul berita gadget hari ini:
{json.dumps(gadget, ensure_ascii=False)}

NICHE KANTOR INI: HP, tablet, aksesorisnya, dan barang lain yang ada di daftar produk giliran ini.
Tiap ide harus sesuai jenis produknya. Jangan membahas produk di luar daftar, dan jangan memaksakan topik charger ke produk lain.
Untuk produk "second" (HP bekas): jangan menyebut atau menyiratkan kondisi fisik, kesehatan baterai, kelengkapan, garansi, atau keaslian.

Usulkan 5 ide konten untuk TikTok/Shopee affiliate (keranjang kuning), format video pendek, tanpa wajah.
Satu ide untuk tiap produk di daftar. Produk tetap sama tiap hari, jadi WAJIB ganti sudut pandang:
masalah yang diangkat, gaya hook, dan contoh situasi harus beda dari judul yang sudah dipakai di bawah ini.
Judul yang sudah dipakai: {json.dumps(riwayat, ensure_ascii=False)}
Yang lagi dibicarakan orang di Threads soal topik ini: {json.dumps(tren, ensure_ascii=False)}
Kalau daftar itu berisi, sambungkan minimal satu ide ke obrolan yang sedang ramai, tetap di akun sendiri.
Jangan sebut harga pasti atau klaim penghasilan. Tandai sumber: "berita" atau "lab".{aturan_produk}
Skema: {{"ide":[{{"topik":"","masalah_penonton":"","produk":"","hook":"","sumber":"berita|lab"}}]}}""",
        catatan=f"{len(gadget)} judul berita, giliran {len(produk)} dari {len(semua_produk)} produk afiliasi")

    dimas = kerja("mahim", "Mahim", "Affiliate & Sosmed", "Caption", f"""Kamu Mahim, karyawan copywriter sosmed. Ide produk:
{json.dumps((sari.get("ide") or [])[:5] if isinstance(sari, dict) else [], ensure_ascii=False)}

Tulis caption untuk 3 platform: TikTok (pendek, ada CTA keranjang kuning), Threads (santai), Facebook (agak panjang).
Buat satu paket untuk tiap ide. Kalimat pembuka tiap paket harus beda satu sama lain, jangan pakai pola yang sama.
Bahasa Indonesia, tanpa klaim berlebihan, tanpa harga pasti.
JANGAN mengaku sudah membeli atau memakai produk, jangan mengarang pengalaman atau testimoni.
Jangan menyebut fitur yang tidak tertulis di nama produk. Jangan mengklaim original, resmi, atau bergaransi.
Produk bertuliskan "second" wajib disebut second/bekas, tanpa klaim kondisi, baterai, kelengkapan, garansi, atau keaslian. Caption Threads wajib diakhiri "(link afiliasi)".
Salin field produk dari ide yang kamu pakai apa adanya.
Skema: {{"paket":[{{"topik":"","produk":"","tiktok":"","threads":"","facebook":"","hashtag":[]}}]}}""",
        syarat=bool(isinstance(sari, dict) and sari.get("ide")))

    kerja("rahma", "Rahma", "Sekretariat", "Sekretaris CEO", f"""Kamu Rahma, sekretaris CEO Gembi. Laporan karyawan malam ini:
Status kerja: {json.dumps(log, ensure_ascii=False)}
Shorts: {json.dumps({"hook": ale.get("hook") if isinstance(ale, dict) else None}, ensure_ascii=False)}
Caption: {json.dumps([p.get("topik") for p in (dimas.get("paket") or [])] if isinstance(dimas, dict) else [], ensure_ascii=False)}

Tulis laporan singkat untuk CEO Gembi: apa yang sudah jadi, apa yang gagal, dan apa yang perlu Gembi cek dulu.
Lalu susun antrean posting 3 hari ke depan (jam padat Indonesia untuk affiliate, jam padat US/EU untuk Shorts Inggris).
Gembi yang memutuskan dan posting manual; kamu tidak posting.
Skema: {{"laporan_ceo":"","perlu_dicek":[],"antrean":[{{"hari":"","jam_wib":"","platform":"","isi":"","status":"nunggu persetujuan CEO"}}]}}""")

    return agents, log, dipakai


KLAIM_BEKAS = re.compile(r"\b(garansi|bergaransi|original|ori|resmi|mulus|normal|battery health|bh|like new|segel)\b", re.I)


def layak(teks, produk):
    """HP bekas: wajib bilang bekas/second dan tanpa klaim kondisi, garansi, atau keaslian."""
    if produk.get("kategori") != "hp_bekas":
        return True
    return bool(re.search(r"\b(bekas|second)\b", teks, re.I)) and not KLAIM_BEKAS.search(teks)


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

    produk = {p["nama"].strip().lower(): p for p in baca_produk()}
    link_run = set()
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
        barang = produk.get((p.get("produk") or "").strip().lower())
        if not barang:
            print(f"[antrean] dibuang, produk tidak ada di daftar: {p.get('produk')}", file=sys.stderr)
            continue
        link = barang["link"]
        if link in link_run:
            print(f"[antrean] dibuang, produk dobel dalam satu shift: {p.get('produk')}", file=sys.stderr)
            continue
        if not layak(teks, barang):
            print(f"[antrean] dibuang, caption HP bekas tidak aman: {p.get('produk')}", file=sys.stderr)
            continue
        link_run.add(link)
        if "(link afiliasi)" not in teks.lower():
            teks += " (link afiliasi)"
        antrean.append({
            "id": kid,
            "link": link,
            "tanggal": data["tanggal"],
            "judul": p.get("topik") or f"caption {i}",
            "versi": 2,
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
    # Selalu exit 0 agar GitHub Actions tetap hijau dan cadangan.py bisa jalan
    sys.exit(0)


if __name__ == "__main__":
    main()
