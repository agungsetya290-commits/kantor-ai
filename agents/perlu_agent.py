#!/usr/bin/env python3
"""Cetak "ya" kalau agent belum menghasilkan caption sejak jam 15:00 WIB terakhir.

Kalau jadwal 15:00 telat sampai lewat tengah malam, run berikutnya tetap menyusul.
"""
import json, os
from datetime import datetime, timezone, timedelta

WIB = timezone(timedelta(hours=7))
SHIFT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "shift.json")


def perlu(shift, now):
    batas = now.replace(hour=15, minute=0, second=0, microsecond=0)
    if now < batas:
        batas -= timedelta(days=1)
    try:
        waktu = datetime.strptime(shift["tanggal"] + " " + shift["jam"], "%Y-%m-%d %H:%M WIB").replace(tzinfo=WIB)
        mahim = shift["agents"]["mahim"]
    except (KeyError, TypeError, ValueError):
        return True
    return waktu < batas or "error" in mahim


if __name__ == "__main__":
    try:
        data = json.load(open(SHIFT, encoding="utf-8"))
    except Exception:
        data = {}
    print("ya" if perlu(data, datetime.now(WIB)) else "tidak")
