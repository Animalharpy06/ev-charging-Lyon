import matplotlib.pyplot as plt
from pathlib import Path

from topology.district import load_district, save_district
from electrical_network.network import (
    load_substations, load_hta_lines,
    clip_substations_to_district, clip_lines_to_district,
    merge_line_segments, check_orphan_endpoints,
    classify_lines, save,)


def run_topology_check():
    district          = load_district("data/topology/iris_lyon.geojson")
    district_boundary = district.dissolve()
    save_district(district, "cache/topology/district.geojson")

    substations          = load_substations("data/electrical_network/enedis_nrj_energie.enedis_poste.json")
    substations_district = clip_substations_to_district(substations, district_boundary)
    save(substations_district, "cache/electrical_network/substations_district.geojson")

    hta_lines            = load_hta_lines("data/electrical_network/enedis_nrj_energie.enedis_reseau.json")
    hta_lines_district   = clip_lines_to_district(hta_lines, district_boundary)
    hta_lines_district   = merge_line_segments(hta_lines_district, substations_district, district_boundary)
    orphans = check_orphan_endpoints(hta_lines_district, substations_district, district_boundary)
    hta_lines_district   = classify_lines(hta_lines_district, district_boundary, substations_district)
    print(hta_lines_district["category"].value_counts())
    save(hta_lines_district, "cache/electrical_network/hta_lines_district.geojson")

    _plot_network(district, district_boundary, hta_lines_district, substations_district, orphans)


def _plot_network(district, district_boundary, hta_lines, substations, orphan_points):
    fig, ax = plt.subplots(figsize=(12, 12))

    district.plot(ax=ax, color="lightyellow", edgecolor="gray", linewidth=0.5)
    district_boundary.plot(ax=ax, color="none", edgecolor="black", linewidth=1.5)

    internal = hta_lines[hta_lines["category"] == "internal"]
    boundary = hta_lines[hta_lines["category"] == "boundary"]
    orphan   = hta_lines[hta_lines["category"] == "orphan"]

    internal.plot(ax=ax, color="steelblue", linewidth=0.5,label=f"Internal HTA lines ({len(internal)})")
    boundary.plot(ax=ax, color="green", linewidth=0.5,label=f"Boundary HTA lines ({len(boundary)})")
    if not orphan.empty:
        orphan.plot(ax=ax, color="orange", linewidth=0.1, label=f"Orphan lines ({len(orphan)})")
    
    substations.plot(ax=ax, color="red", markersize=5,label=f"Substations ({len(substations)})")
    
    orphan_points.plot(ax=ax, color="orange", markersize=1, zorder=5, label=f"Orphan endpoints ({len(orphan_points)})")

    ax.set_title("Quartier 5 — HTA Network", fontsize=14)
    ax.legend()

    Path("output/topology_check").mkdir(parents=True, exist_ok=True)
    plt.savefig("output/topology_check/network_map.png", dpi=1000, bbox_inches="tight")
    print("Map saved to output/topology_check/network_map.png")


if __name__ == "__main__":
    run_topology_check()