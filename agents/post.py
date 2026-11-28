#!/usr/bin/env python3
"""Kirim antrean yang sudah disetujui CEO ke Threads.

Hanya baris dengan "setujui": true yang diposting. Baris yang sudah terkirim
dilewati, jadi script ini aman dijalankan berkali-kali.
"""
import json, os, sys, time, urllib.parse, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
ANTREAN = os.path.join(DATA, "antrean.json")
TOKEN = os.environ.get("THREADS_TOKEN", "").strip()
BASE = "https://graph.threads.net/v1.0"
WIB = timezone(timedelta(hours=7))
MAX_PER_RUN = 3          # jaga-jaga biar tidak membanjiri timeline
BATAS_HARIAN = 250       # batas resmi Threads per 24 jam


def http(url, data=None, timeout=45):
    req = urllib.request.Request(url, data=data, method="POST" if data is not None else "GET",
                                 headers={"User-Agent": "KantorAI/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def form(params):
    return urllib.parse.urlencode(params).encode()


def me():
    """ID profil Threads; diambil dari token, jadi tidak perlu disimpan terpisah."""
    return http(f"{BASE}/me?fields=id,username&access_token={TOKEN}")


def kirim(user_id, teks):
    """Dua langkah sesuai dokumentasi Threads: bikin container, lalu publish."""
    c = http(f"{BASE}/{user_id}/threads", form({
        "media_type": "TEXT", "text": teks, "access_token": TOKEN}))
    cid = c["id"]
    time.sleep(5)  # beri waktu container diproses
    p = http(f"{BASE}/{user_id}/threads_publish", form({
        "creation_id": cid, "access_token": TOKEN}))
    return p.get("id")


def susun(a):
    """Teks + link afiliasi. Link ditulis sendiri oleh Agung di antrean.json.

    Threads menolak satu post yang memuat lebih dari 5 link, jadi hanya satu
    link yang ikut. Teks dipotong supaya total tetap di bawah 500 karakter.
    """
    teks = (a.get("teks") or "").strip()
    link = (a.get("link") or "").strip()
    if not link:
        return teks[:500]
    ekor = "\n\n" + link
    sisa = 500 - len(ekor)
    return teks[:sisa].rstrip() + ekor


def pengaturan():
    """Setelan pemilik di data/pengaturan.json.

    auto_setujui: true  -> semua baris antrean dianggap disetujui Gembi
    maks_per_hari: angka -> rem jumlah post sekali jalan
    """
    try:
        return json.load(open(os.path.join(DATA, "pengaturan.json"), encoding="utf-8"))
    except Exception:
        return {}


JEDA_JAM = 3             # jarak minimal antar post, walau jadwal GitHub molor berdekatan


BATAS_PER_HARI = 5       # jadwal jalan tiap jam, jadi jumlah post per hari dibatasi


def kunci(teks):
    """Teks dinormalkan untuk cek kembar (tanpa beda huruf besar dan spasi)."""
    return " ".join((teks or "").lower().split())


def pilih(antrean, siap, now):
    """Buang teks yang sudah pernah terkirim atau kembar; urutan mengikuti antrean (yang lama duluan).

    Kosong kalau post terakhir belum lewat JEDA_JAM.
    """
    waktu = []
    for a in antrean:
        try:
            waktu.append(datetime.strptime(a["terkirim"], "%Y-%m-%d %H:%M WIB").replace(tzinfo=WIB))
        except (KeyError, TypeError, ValueError):
            pass
    if sum(w.date() == now.date() for w in waktu) >= BATAS_PER_HARI:
        return []
    if waktu and now - max(waktu) < timedelta(hours=JEDA_JAM):
        return []
    sudah = {kunci(a.get("teks")) for a in antrean if a.get("terkirim")}
    hasil = []
    for a in siap:
        k = kunci(a.get("teks"))
        if k not in sudah:
            sudah.add(k)
            hasil.append(a)
    return hasil


def baca_antrean():
    try:
        return json.load(open(ANTREAN, encoding="utf-8"))
    except Exception:
        return []


def main():
    now = datetime.now(WIB)
    antrean = baca_antrean()
    if not TOKEN:
        print("[post] THREADS_TOKEN belum diisi di repository secrets", file=sys.stderr)
        sys.exit(1)

    setelan = pengaturan()
    auto = setelan.get("auto_setujui") is True
    batas = int(setelan.get("maks_per_hari") or MAX_PER_RUN)
    if auto:
        print("[post] mode setujui otomatis aktif")
    siap = [a for a in antrean
            if (a.get("setujui") is True or (auto and ("-mahim-" not in a.get("id", "") or a.get("versi") == 2)))
            and not a.get("terkirim")
            and ("-mahim-" not in a.get("id", "") or a.get("link"))
            and a.get("platform", "threads") == "threads" and a.get("teks")]
    siap = pilih(antrean, siap, now)
    if not siap:
        print("[post] tidak ada yang layak dikirim (belum disetujui, teks kembar, jeda belum lewat, atau batas harian tercapai)")
        return

    try:
        profil = me()
    except urllib.error.HTTPError as e:
        pesan = e.read().decode()[:300]
        print(f"[post] token ditolak ({e.code}): {pesan}", file=sys.stderr)
        for a in antrean:
            if a in siap:
                a["error"] = f"token ditolak: HTTP {e.code}"
        json.dump(antrean, open(ANTREAN, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        sys.exit(1)

    uid = profil["id"]
    print(f"[post] akun: @{profil.get('username')} ({uid})")

    terkirim = 0
    for a in siap[:batas]:
        teks = susun(a)
        try:
            pid = kirim(uid, teks)
            a["terkirim"] = now.strftime("%Y-%m-%d %H:%M WIB")
            a["post_id"] = pid
            a.pop("error", None)
            terkirim += 1
            print(f"[post] terkirim: {a.get('judul', teks[:40])}")
            time.sleep(10)
        except urllib.error.HTTPError as e:
            pesan = e.read().decode()[:300]
            a["error"] = f"HTTP {e.code}: {pesan}"
            print(f"[post] gagal: {a['error']}", file=sys.stderr)
        except Exception as e:
            a["error"] = f"{type(e).__name__}: {e}"
            print(f"[post] gagal: {a['error']}", file=sys.stderr)

    json.dump(antrean, open(ANTREAN, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    sisa = len([a for a in antrean if a.get("setujui") and not a.get("terkirim")])
    print(f"[post] selesai: {terkirim} terkirim, {sisa} masih antre")


if __name__ == "__main__":
    main()
