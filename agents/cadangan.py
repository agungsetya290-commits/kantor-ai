#!/usr/bin/env python3
"""Jaring pengaman: kalau agent AI gagal, antrean tetap diisi dari template.
Dijalankan tiap run, sebelum post.py. Kalau stok belum terkirim sudah cukup, diam saja.
"""
import json, os, random, datetime
from giliran import giliran

TARGET = 5
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "data")

def baca(nama, bawaan):
    try:
        with open(os.path.join(D, nama), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return bawaan

def tulis(nama, data):
    with open(os.path.join(D, nama), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# (pembuka, saran cek) per kategori. Sengaja tanpa klaim fitur, kondisi, atau pengalaman pakai.
TEMPLATE = {
    "charger": (["Lagi cari kepala charger baru?", "Charger lama sudah waktunya diganti?", "Butuh charger cadangan?"],
                "Cocokkan dulu daya dan jenis colokannya dengan HP kamu."),
    "kabel": (["Lagi cari kabel baru?", "Kabel lama sudah waktunya diganti?", "Butuh kabel cadangan?"],
              "Pilih varian dan cek jenis colokannya sebelum checkout."),
    "powerbank": (["Lagi cari power bank?", "Butuh cadangan daya buat di luar rumah?", "Mau punya power bank buat dibawa pergi?"],
                  "Cek kapasitas, colokan, dan kecocokannya dengan HP kamu."),
    "casing": (["Lagi cari case baru buat HP?", "Mau ganti tampilan HP?", "Bosan sama case yang sekarang?"],
               "Pastikan pilih tipe HP yang pas sebelum checkout."),
    "paket": (["Lagi cari paket pelindung atau aksesoris HP?", "Mau beli aksesoris sekaligus?", "Baru ganti HP dan cari aksesorisnya?"],
              "Cek isi paket dan tipe HP yang cocok."),
    "hp": (["Lagi cari-cari HP?", "Ada rencana ganti HP?", "Masih membandingkan pilihan HP?"],
           "Cek varian, spesifikasi, dan reputasi toko sebelum checkout."),
    "hp_bekas": (["Lagi cari HP second?", "Mempertimbangkan beli HP bekas?", "Masih membandingkan pilihan HP second?"],
                 "Ini barang bekas, jadi tanyakan detail unitnya ke penjual sebelum checkout."),
    "tablet": (["Lagi cari tablet?", "Butuh layar lebih lega dari HP?", "Masih membandingkan pilihan tablet?"],
               "Cek merek, spesifikasi, dan reputasi toko sebelum checkout."),
    "audio": (["Lagi cari perangkat audio?", "Mau tambah teman dengerin musik?", "Masih membandingkan pilihan audio?"],
              "Cek spesifikasi, ulasan, dan reputasi toko dulu."),
    "jam": (["Lagi cari smartwatch?", "Mau coba pakai smartwatch?", "Masih membandingkan pilihan smartwatch?"],
            "Cek dulu kecocokannya dengan HP kamu."),
}
UMUM = (["Lagi cari barang ini?", "Siapa tahu lagi butuh.", "Buat yang lagi lihat-lihat."],
        "Cek detail produk dan ulasannya dulu.")
PENGANTAR = ["Salah satu pilihannya:", "Bisa dilirik:", "Yang ini bisa dicek:"]
PENUTUP = ["Detailnya ada di link.", "Selengkapnya cek di link.", "Linknya ada di bawah."]


def buat_teks(p, rnd, sudah):
    """Teks memuat nama produk, jadi tidak tertukar antar produk. Hindari teks yang sudah ada."""
    buka, saran = TEMPLATE.get(p.get("kategori"), UMUM)
    pilihan = ["%s %s %s. %s %s (link afiliasi)" % (b, a, p["nama"], saran, t)
               for b in buka for a in PENGANTAR for t in PENUTUP]
    rnd.shuffle(pilihan)
    return next((x for x in pilihan if x not in sudah), pilihan[0])


def tertunda(antrean):
    """Baris yang masih menunggu dikirim (syaratnya sama dengan post.py)."""
    return [a for a in antrean
            if not a.get("terkirim") and a.get("teks") and a.get("platform", "threads") == "threads"
            and ("-mahim-" not in a.get("id", "") or (a.get("versi") == 2 and a.get("link")))]


def main():
    hari = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=7)
    tanggal = hari.strftime("%Y-%m-%d")

    produk = [p for p in baca("produk.json", []) if p.get("nama") and p.get("link")]
    if not produk:
        print("[cadangan] produk.json kosong, lewat")
        return

    antrean = baca("antrean.json", [])
    kurang = TARGET - len(tertunda(antrean))
    if kurang <= 0:
        print("[cadangan] stok belum terkirim masih cukup, tidak perlu diisi")
        return

    sudah = {a.get("teks") for a in antrean}
    nomor = sum(1 for a in antrean if a.get("id", "").startswith(tanggal + "-cadangan-"))
    baru = []
    for i, p in enumerate(giliran(produk, antrean, kurang), nomor + 1):
        teks = buat_teks(p, random.Random("%s-%d" % (tanggal, i)), sudah)
        baru.append({
            "id": "%s-cadangan-%d" % (tanggal, i),
            "link": p["link"],
            "produk": p["nama"],
            "tanggal": tanggal,
            "judul": p["nama"],
            "platform": "threads",
            "teks": teks,
            "setujui": False,
            "terkirim": False,
        })

    ada = {a.get("id") for a in antrean}
    tambah = [b for b in baru if b["id"] not in ada]
    antrean.extend(tambah)
    tulis("antrean.json", antrean[-60:])
    print("[cadangan] tambah %d baris template" % len(tambah))

if __name__ == "__main__":
    main()
