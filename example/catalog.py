"""
Add a catalog to the database.
"""

import argparse as ap

import numpy as np

import tilemaker.database as db
import tilemaker.orm

parser = ap.ArgumentParser(
    description="Add a catalog to the database. This catalog must be a CSV file with columns 'flux', 'ra', and 'dec'. We skip the first row, assuming it is a header."
)

parser.add_argument("catalog", type=str, help="The path to the catalog CSV file.")
parser.add_argument("--name", type=str, help="The name of the catalog.")
parser.add_argument("--description", type=str, help="A description of the catalog.")

args = parser.parse_args()

data = np.loadtxt(args.catalog, delimiter=",", skiprows=1)

db.create_database_and_tables()
with db.get_session() as session:
    catalog = tilemaker.orm.SourceList(name=args.name, description=args.description)
    session.add(catalog)

    items = [
        tilemaker.orm.SourceItem(
            source_list=catalog, flux=row[0], ra=row[1], dec=row[2]
        )
        for row in data
    ]
    session.add_all(items)

    session.commit()

print("Catalog successfully added.")
