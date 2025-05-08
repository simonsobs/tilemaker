"""
Makes a catalog of high values in a compton y map.
"""

import json
import sys

import numpy as np
from pixell import enmap
from scipy.ndimage import gaussian_filter

from tilemaker.client.add import CatalogIngestItem

data = enmap.read_map(sys.argv[1])
cut = float(sys.argv[2])

blurred = gaussian_filter(data, 5)

mask = blurred > cut
pixels = np.array(np.where(mask)).T

items = []

for id, pixel in enumerate(pixels):
    dec, ra = data.pix2sky(pixel)
    if ra > np.pi:
        ra -= 2 * np.pi

    dec = dec * 180 / np.pi
    ra = ra * 180 / np.pi

    print(ra, dec)

    items.append(
        CatalogIngestItem(
            name=f"Object {id}",
            ra=ra,
            dec=dec,
            flux=data[pixel[0]][pixel[1]],
        )
    )

with open("created_cat.json", "w") as f:
    json.dump([x.dict() for x in items], f)
