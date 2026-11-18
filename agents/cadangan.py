#!/usr/bin/env python3
"""Jaring pengaman: kalau agent AI gagal, antrean tetap diisi dari template.
Dijalankan tiap run, sebelum post.py. Kalau antrean hari ini sudah cukup, diam saja.
"""
import json, os, random, datetime

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

PASANGAN = [
    ("Charger bawaan hp makin lama makin lemot ngecasnya?",
     "Biasanya bukan baterainya yang rusak, tapi kepala chargernya sudah turun kemampuan."),
    ("Sering ngecas semalaman tapi paginya masih belum penuh?",
     "Arus yang masuk kekecilan. Kepala charger yang dayanya pas bikin bedanya kerasa."),
    ("Colokan di rumah terbatas tapi yang dicas ada tiga barang?",
     "Satu kepala charger beberapa port lebih masuk akal daripada rebutan stopkontak."),
    ("Charger murah sering bikin hp hangat pas dipakai sambil ngecas.",
     "Yang bikin aman itu proteksi suhu dan arusnya, bukan angka watt di kemasan."),
    ("Kabel sama kepala charger numpuk di tas tiap mau pergi?",
     "GaN bikin kepala charger jauh lebih kecil tanpa ngurangi dayanya. Tas jadi enteng."),
    ("Hp tinggal 20 persen padahal sepuluh menit lagi harus jalan.",
     "Ngecas cepat paling kerasa gunanya di momen kayak gini, sepuluh menit pun nambah banyak."),
    ("Bawa charger gembul ke mana-mana itu ribet.",
     "Ukuran GaN muat di kantong celana, jadi nggak ada alasan ketinggalan charger."),
    ("Baterai hp cepat soak itu sering gara-gara chargernya, bukan hpnya.",
     "Arus yang stabil bikin baterai lebih awet daripada arus yang naik turun sembarangan."),
    ("Satu kepala charger buat hp, earbuds, sama tablet sekaligus.",
     "Hemat colokan, hemat tempat, dan nggak perlu gonta-ganti adaptor."),
    ("Angka watt besar belum tentu kepakai semua.",
     "Yang penting chargernya bisa nyesuaikan arus ke kemampuan baterai hp kita."),
    ("Ngecas di mobil sering kalah cepat sama borosnya baterai.",
     "Kepala charger yang dayanya cukup bikin baterai naik, bukan cuma bertahan."),
    ("Charger tipis sering dikira lemah.",
     "GaN justru kebalikannya, bentuknya kecil tapi panasnya lebih terkendali."),
]

PENUTUP = [
    "Detail lengkapnya di link.",
    "Spesifikasinya bisa dicek di link.",
    "Yang mau lihat-lihat dulu, linknya di bawah.",
    "Cek sendiri di link kalau penasaran.",
    "Infonya ada di link.",
]

def main():
    hari = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=7)
    tanggal = hari.strftime("%Y-%m-%d")

    produk = [p for p in baca("produk.json", []) if p.get("nama") and p.get("link")]
    if not produk:
        print("[cadangan] produk.json kosong, lewat")
        return

    antrean = baca("antrean.json", [])
    hari_ini = [a for a in antrean if a.get("tanggal") == tanggal]
    kurang = TARGET - len(hari_ini)
    if kurang <= 0:
        print("[cadangan] antrean hari ini sudah %d, tidak perlu diisi" % len(hari_ini))
        return

    # acak tetap: sama sepanjang hari, beda tiap hari
    rnd = random.Random(tanggal)
    urut = produk[:]
    rnd.shuffle(urut)

    dipakai = {a.get("produk") for a in hari_ini}
    sisa = [p for p in urut if p["nama"] not in dipakai] or urut

    baru = []
    for i in range(kurang):
        p = sisa[i % len(sisa)]
        r = random.Random(tanggal + p["nama"] + str(i))
        buka, isi = r.choice(PASANGAN)
        teks = "%s %s %s" % (buka, isi, r.choice(PENUTUP))
        baru.append({
            "id": "%s-cadangan-%d" % (tanggal, i + 1),
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
    print("[cadangan] tambah %d baris template (antrean hari ini jadi %d)" % (len(tambah), len(hari_ini) + len(tambah)))

if __name__ == "__main__":
    main()
