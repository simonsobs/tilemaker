"""
Makes a catalog of high values in a compton y map.
"""

import json
import sys

from astropy import table

from tilemaker.metadata.sources import Source

data = table.Table.read(sys.argv[1])

items = []

for ra, dec, name, snr in zip(
    data["RADeg"], data["decDeg"], data["name"], data["fixed_SNR"]
):
    if ra > 180:
        ra -= 360

    print(ra, dec)

    items.append(Source(name=name, ra=ra, dec=dec, extra={"SNR": snr}))

with open("created_cat.json", "w") as f:
    json.dump([x.dict() for x in items], f)
