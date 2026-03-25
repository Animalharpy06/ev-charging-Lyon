#ENEDIS DATA
import geopandas as gpd

substations = gpd.read_file("data/enedis_nrj_energie.enedis_poste.json")
print(substations.shape)
print(substations.columns.tolist())
print(substations.crs)