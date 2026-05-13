from topology.district import load_district, save_district
from electrical_network.network import (load_substations, load_hta_lines,
                                        clip_substations_to_district, clip_lines_to_district,
                                        build_endpoint_snapping, classify_lines, save,)
from electrical_network.graph import (build_graph_from_snapping, report_graph_topology,)
from visualization.network_map import plot_network


def run_topology_check() -> None:
    district = load_district("data/topology/iris_lyon.geojson")
    district_boundaries = district.dissolve()
    save_district(district, "cache/topology/district.geojson")

    substations = load_substations("data/electrical_network/enedis_nrj_energie.enedis_poste.json")
    substations_district = clip_substations_to_district(substations, district_boundaries)
    save(substations_district, "cache/electrical_network/substations_district.geojson")

    hta_lines = load_hta_lines("data/electrical_network/enedis_nrj_energie.enedis_reseau.json")
    hta_lines_district = clip_lines_to_district(hta_lines, district_boundaries)

    hta_lines_district, endpoint_nodes, _,_ = build_endpoint_snapping(hta_lines_district, substations_district, district_boundaries)

    hta_lines_district = classify_lines(hta_lines_district, endpoint_nodes, district_boundaries)
    save(hta_lines_district, "cache/electrical_network/hta_lines_district.geojson")

    G = build_graph_from_snapping(hta_lines_district, endpoint_nodes, substations_district)
    report_graph_topology(G)

    plot_network(district, district_boundaries, G)


if __name__ == "__main__":
    run_topology_check()
