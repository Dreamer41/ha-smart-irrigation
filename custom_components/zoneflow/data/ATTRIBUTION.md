# Attribution

`plant_water.json` is derived from the **Plant Variety Database**.

- **Creator:** Wind River Greens
- **Source:** https://github.com/bripatch/plant-variety-database
- **License:** Creative Commons Attribution 4.0 International (CC BY 4.0), https://creativecommons.org/licenses/by/4.0/

**Changes made:** only each variety's name, kind, Latin name and water-requirement text were kept.
Where the text gives a weekly amount in inches ("1-1.5 inches per week"), it was also converted to
millimetres. Nothing else from the database is included. The file is rebuilt with
`scripts/build_plant_water_data.py`.

This attribution applies to `plant_water.json` only. ZoneFlow itself is MIT licensed.
