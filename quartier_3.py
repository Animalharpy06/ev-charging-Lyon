import geopandas as gpd
import pandas as pd
import matplotlib.pyplot as plt

iris = gpd.read_file("data/iris_lyon.geojson")

print(repr(iris[iris['commune'] == 'Lyon 3e Arrondissement']['codeiris'].iloc[0]))

keep_3e = [693830102, 693830103, 693830104, 693830105,
           693830201, 693830202, 693830203, 693830204, 693830205]

keep_7e = [693870101, 693870103, 693870201, 693870202, 693870203,
           693870301, 693870302, 693870401]

remove_codes = [693860104, 693860701]

sixe = iris[
    (iris['commune'] == 'Lyon 6e Arrondissement') &
    (iris['type'] == 'H') &
    (~iris['codeiris'].isin(remove_codes))]

trois_e = iris[iris['codeiris'].isin(keep_3e)]

sept_e = iris[iris['codeiris'].isin(keep_7e)]


selected = gpd.GeoDataFrame(pd.concat([sixe, trois_e, sept_e], ignore_index=True), crs=iris.crs)

print(selected['commune'].value_counts())



print(selected[['codeiris', 'libelle', 'commune']].to_string())

fig, ax = plt.subplots(figsize=(12, 10))
selected.plot(column='commune', legend=True, ax=ax)

for idx, row in selected.iterrows():
    centroid = row.geometry.centroid
    ax.annotate(row['codeiris'], xy=(centroid.x, centroid.y),
                fontsize=6, ha='center', color='black')

plt.savefig("data/IRIS/selected_district_3.png", dpi=150)
