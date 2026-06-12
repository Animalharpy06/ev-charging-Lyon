# EV Charging Topology & Optimisation Pipeline

PhD research project — University of Padova (UNIPD), Cohort XLI  
**Mattia Samorè** | Energy Engineering

---

## Research Objective

Analyse how smart coordination of electric vehicles (EVs), residential heat pumps
(HPs) and rooftop PV in urban areas can reduce grid dependency and identify the
grid-emission threshold at which large-scale electrification becomes globally
beneficial in full life-cycle terms.

The work combines agent-based transport modelling, urban building energy demand,
distribution-network constraints. Both operational CO₂ emissions (linked to the electricity mix) and
embodied emissions (EVs, batteries, PV, heat pumps) are compared against a fossil-based reference scenario (ICE vehicles + gas boilers).


---

## Model Components

| # | Component | Method |
|---|-----------|--------|
| 1 | Transport demand | MATSim / EQASim — synthetic population, Lyon case study |
| 2a | EV charging & V2G | Per-vehicle SOC tracking (Paper 1); zone-level fleet aggregation (Paper 2) |
| 2b | Fleet aggregation | Feasible charging envelopes per zone/class (Brodnicke et al.) |
| 3 | Building energy demand | Typology-based (BDNB + BD TOPO); hourly heating & electricity profiles |
| 4 | Rooftop PV | GIS-based potential from BD TOPO footprints; ERA5 hourly irradiance |
| 5 | Electrical network | DLPF linearised power flow (Yang et al., 2017) |
| 6 | Network topology | Real Enedis/Grand Lyon HTA/BT data; one node per MV/LV substation |

---

## Repository Structure

```
src/
├── electrical_network/
│   ├── network.py          # Load, clip, merge, classify and validate HTA lines
│   └── graph.py            # Build and tag NetworkX graph from snapped endpoints
├── topology/
│   └── district.py         # Define and load the study district from IRIS zones
├── buildings/
    ├── load.py             # Load, clip the buildings to the area
│   └── demand.py           # Hourly heating & electricity demand (BDNB typology)
├── visualization/
│   └── networkmap.py       # Map rendering for MV network topology
└── run_pipeline.py         # Orchestrator: build and visualise the MV network
```

`data/`, `cache/` and `output/` are not tracked in this repository.  
See each subfolder for instructions on the expected input files.

---

## Data

All input files go in `data/`. They are not tracked in this repository.

### Required files

| File | Description | Format |
|---|---|---|
| `data/electrical_network/enedis_nrj_energie.enedis_poste.json` | Enedis MV/LV substations — Métropole de Lyon | GeoJSON, EPSG:4326 |
| `data/electrical_network/enedis_nrj_energie.enedis_reseau.json` | Enedis HTA network lines — Métropole de Lyon | GeoJSON, EPSG:4326 |
| `data/topology/iris_lyon.geojson` | IRIS zone boundaries — Métropole de Lyon | GeoJSON |
| `data/buildings/batiment_groupe_compile.parquet` | BDNB building stock — Métropole de Lyon | Parquet |
| `data/weather/

### Download instructions

**Enedis substations**  
👉 https://data.grandlyon.com/portail/fr/jeux-de-donnees/postes-electriques-enedis-sur-le-territoire-de-la-metropole/donnees  
Download as GeoJSON. Place in `data/electrical_network/`.

**Enedis HTA network lines**  
👉 https://data.grandlyon.com/portail/fr/jeux-de-donnees/reseaux-electriques-enedis-sur-le-territoire-de-la-metropole/donnees  
Download as GeoJSON. Place in `data/electrical_network/`.

**IRIS zone boundaries**  
👉 https://www.data.gouv.fr/datasets/contours-iris-grande-echelle-de-la-metropole-de-lyon  
Download as GeoJSON. Place in `data/topology/`.

**BDNB building stock**  
👉 https://bdnb.io  
Download `batiment_groupe_compile` for Métropole de Lyon. Place in `data/buildings/`.

---

## Dependencies

- Python 3.12
- `geopandas`, `shapely`, `matplotlib`
- `scipy` (spatial indexing for topology merging)
- `pandas`, `numpy`
- `gurobipy` (optimisation stage, requires licence)

Install dependencies:

```bash
pip install -r requirements.txt
```

---

## Status

- [x] District definition and IRIS clipping
- [x] MV feeder loading, merging and topology validation
- [x] Orphan endpoint detection and network visualisation
- [x] HV/MV source substation integration
- [x] Building demand profiles (BDNB typology — `buildings/demand.py`)
- [ ] Rooftop PV potential 
- [ ] Power flow model (DLPF)
- [ ] Smart charging optimisation (MILP)

---

## Acknowledgements

This research is carried out within the PhD programme in Industrial Engineering
at the University of Padova, with focus on urban transport electrification and
energy system integration.
