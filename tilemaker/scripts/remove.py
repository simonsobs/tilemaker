"""
Script to remove a map from the database.
"""

import argparse as ap

parser = ap.ArgumentParser(description="Remove a map from the database.")

parser.add_argument(
    "map_name",
    type=str,
    help="The name of the map to remove from the database.",
)


def main():
    import tilemaker.database as db
    import tilemaker.orm

    args = parser.parse_args()

    with db.get_session() as session:
        if (map_metadata := session.get(tilemaker.orm.Map, args.map_name)) is None:
            print(f"Map '{args.map_name}' not found in the database.")
            return

        session.delete(map_metadata)
        session.commit()

    print(f"Map '{args.map_name}' removed from the database.")
