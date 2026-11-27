"""Giliran produk: yang belum pernah atau paling lama tidak masuk antrean didahulukan."""


def giliran(produk, antrean, n=5):
    terakhir = {a.get("link"): i for i, a in enumerate(antrean) if a.get("link")}
    return sorted(produk, key=lambda p: terakhir.get(p["link"], -1))[:n]
