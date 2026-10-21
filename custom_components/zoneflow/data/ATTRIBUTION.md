# Attribution

`plant_water.json` is derived from the **Plant Variety Database**.

- **Creator:** Wind River Greens
- **Source:** https://github.com/bripatch/plant-variety-database
- **License:** Creative Commons Attribution 4.0 International (CC BY 4.0), https://creativecommons.org/licenses/by/4.0/

**Changes made:** only each variety's name, kind, Latin name and water-requirement text were kept.
Where the text gives a weekly amount in inches ("1-1.5 inches per week"), it was also converted to
millimetres. Nothing else from the database is included. The file is rebuilt with
`scripts/build_plant_water_data.py`.

`crop_kc.json` holds crop coefficients (Kc) from **FAO Irrigation and drainage paper 56**, Table 12.

- **Authors:** Allen, R. G., Pereira, L. S., Raes, D. and Smith, M. (1998), *Crop evapotranspiration -
  Guidelines for computing crop water requirements*, FAO Irrigation and drainage paper 56, Rome
- **Source:** https://www.fao.org/3/x0490E/x0490e00.htm

**Changes made:** the Kc values of Table 12 were typed in by hand, one row per crop. Where the table gives
several variants (with or without ground cover, a range at the end of the season) one is used, and the
middle of a range. Which plants of the first database each crop stands for was added. The file is rebuilt
with `scripts/build_crop_kc.py`.

This attribution applies to `plant_water.json` and `crop_kc.json` only. ZoneFlow itself is MIT licensed.
