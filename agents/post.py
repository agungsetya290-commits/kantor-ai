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

    siap = [a for a in antrean
            if a.get("setujui") is True and not a.get("terkirim")
            and a.get("platform", "threads") == "threads" and a.get("teks")]
    if not siap:
        print("[post] tidak ada yang disetujui; tidak ada yang dikirim")
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
    for a in siap[:MAX_PER_RUN]:
        teks = a["teks"].strip()[:500]  # batas satu post Threads
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
