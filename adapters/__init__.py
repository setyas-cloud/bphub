# Registry adapter bphub — satu entri per layanan bypass.
# Urutan deteksi penting: domain yang lebih spesifik didahulukan.
SERVICES = {
    "cuty": {
        "label": "Cuty.io",
        "hosts": ["cuty.io", "cutty.io", "cuttty.com", "cutty.com"],
    },
    "shrme": {
        "label": "ShrinkMe",
        "hosts": ["shrinkme.click", "shrinkme.io"],
    },
    "srnky": {
        "label": "ShrinkEarn",
        "hosts": ["shrinkearn.com", "srnky.com"],
    },
    "ez4": {
        "label": "Ez4short",
        "hosts": ["ez4short.com"],
    },
    "dplink": {
        "label": "DropLink",
        "hosts": ["droplink.co"],
    },
    "clk": {
        "label": "clk.sh",
        "hosts": ["clk.sh", "clksz.com"],
    },
}
