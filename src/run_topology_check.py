import matplotlib.pyplot as plt
from pathlib import Path

from topology.district import load_district, save_district
from electrical_network.network import (
    load_substations, load_hta_lines,
    clip_substations_to_district, clip_lines_to_district,
    merge_line_segments, classify_lines, check_orphan_endpoints, save)

from electrical_network.graph import (
    build_graph, report_graph_topology)

from visualization.network_map import plot_network


def run_topology_check() -> None:
    
    district          = load_district("data/topology/iris_lyon.geojson")
    district_boundary = district.dissolve()
    save_district(district, "cache/topology/district.geojson")

    substations          = load_substations("data/electrical_network/enedis_nrj_energie.enedis_poste.json")
    substations_district = clip_substations_to_district(substations, district_boundary)
    save(substations_district, "cache/electrical_network/substations_district.geojson")

    hta_lines          = load_hta_lines("data/electrical_network/enedis_nrj_energie.enedis_reseau.json")
    hta_lines_district = clip_lines_to_district(hta_lines, district_boundary)
    hta_lines_district = merge_line_segments(hta_lines_district, substations_district, district_boundary)
    hta_lines_district = classify_lines(hta_lines_district, district_boundary, substations_district)
    orphans            = check_orphan_endpoints(hta_lines_district, substations_district, district_boundary)

    
    G = build_graph(hta_lines_district, substations_district)

    report_graph_topology(G, district_boundary)
    save(hta_lines_district, "cache/electrical_network/hta_lines_district.geojson")

    plot_network(district, district_boundary, G, substations_district, orphans)



if __name__ == "__main__":
    run_topology_check()