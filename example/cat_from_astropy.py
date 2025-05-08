"""
Makes a catalog of high values in a compton y map.
"""

import json
import sys

from astropy import table

from tilemaker.client.add import CatalogIngestItem

data = table.Table.read(sys.argv[1])

import pdb; pdb.set_trace()

items = []

for ra, dec, name, flux in zip(
    data["RADeg"], data["decDeg"], data["name"], data["fixed_SNR"]
):
    if ra > 180:
        ra -= 360

    print(ra, dec)

    items.append(
        CatalogIngestItem(
            name=name,
            ra=ra,
            dec=dec,
            flux=flux,
        )
    )

with open("created_cat.json", "w") as f:
    json.dump([x.dict() for x in items], f)
