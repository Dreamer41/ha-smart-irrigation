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

Where FAO-56 has no crop, `crop_kc.json` also holds values from these sources (each row says which):

- **Mango and guava:** UF/IFAS Extension EDIS publication AE456, *Crop coefficients of some commercial crops
  in Florida*, https://edis.ifas.ufl.edu/publication/AE456 . The publication takes the mango values from
  De Azevedo et al. (2003) and the guava values from Fares (2008). The highest monthly value is used as the
  full-grown one.
- **Papaya:** Posse et al. (2008), *Engenharia Agricola*, a weighing lysimeter study
  (https://doaj.org/article/193f95d62f5e45ea8a6379edc4f2ece3). The value is taken from the abstract.
- **Basil:** Rahimikhoob, Sohrabi and Delshad (2019), *Iranian Journal of Soil and Water Research* 50(10),
  a greenhouse micro-lysimeter study, https://doi.org/10.22059/ijswr.2019.280405.668191 .
- **Estimates for plants that have nothing of their own:** the water-use classes of landscape plant factors
  (WUCOLS, University of California Davis; California's Model Water Efficient Landscape Ordinance; the UC
  ANR plant factor table,
  https://ucanr.edu/site/center-landscape-urban-horticulture/plant-factor-or-crop-coefficient-whats-difference).
  A plant whose water text starts with low, moderate or high gets the middle of that class's range (0.2,
  0.5, 0.8). These are estimates, not measurements, and the card says so.
- **Weekly amounts worked out from a crop factor:** a plant with a crop factor but no weekly amount of its
  own gets one worked out from the crop factor, with 1 inch (25.4 mm) a week at a crop factor of 1.0, which is
  the figure the Plant Variety Database gives for most vegetables. These are estimates too.

Only numbers were taken, with the sources named; no text, tables or files were copied. This attribution
applies to `plant_water.json` and `crop_kc.json` only. ZoneFlow itself is MIT licensed.
