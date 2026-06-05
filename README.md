\# EV Charging Topology \& Optimisation Pipeline



PhD research project — University of Padova (UNIPD), Cohort XLI  

\*\*Mattia Samorè\*\* | Energy Engineering



\---



\## Overview



This project develops a pipeline to reconstruct, validate and optimise the MV/LV

electricity distribution network of Lyon (France) for urban electrification studies.

The goal is to assess the hosting capacity of the grid and design smart-charging

strategies for electric vehicles, heat pumps and rooftop PV systems that minimise

grid reinforcement needs and lifecycle emissions.



The pipeline processes open Enedis network data, reconstructs the physical topology

of MV feeders, identifies source substations and builds a model suitable for

linearised power-flow (DLPF) and mixed-integer optimisation (MILP/LP via Gurobi).



\---



\## Repository Structure

src/

├── electrical\_network/

│ └── network.py # Load, clip, merge, classify and validate HTA lines

├── topology/

│ └── district.py # Define and load the study district from IRIS zones

└── run\_topology\_check.py # Orchestrator: build and visualise the MV network



`data/`, `cache/` and `output/` are not tracked in this repository.  

See each subfolder for instructions on the expected input files.



\---



\## Data



All input files go in `data/`. They are not tracked in this repository.



\### Required files



| File | Description | Format |

|---|---|---|

| `data/electrical\_network/enedis\_nrj\_energie.enedis\_poste.json` | Enedis MV/LV substations — Métropole de Lyon | GeoJSON, EPSG:4326 |

| `data/electrical\_network/enedis\_nrj\_energie.enedis\_reseau.json` | Enedis HTA network lines — Métropole de Lyon | GeoJSON, EPSG:4326 |

| `data/topology/iris\_lyon.geojson` | IRIS zone boundaries — Métropole de Lyon | GeoJSON |



\### Download instructions



\*\*Enedis substations\*\*  

👉 https://data.grandlyon.com/portail/fr/jeux-de-donnees/postes-electriques-enedis-sur-le-territoire-de-la-metropole/donnees  

Download as GeoJSON. Place in `data/electrical\_network/`.



\*\*Enedis HTA network lines\*\*  

👉 https://data.grandlyon.com/portail/fr/jeux-de-donnees/reseaux-electriques-enedis-sur-le-territoire-de-la-metropole/donnees  

Download as GeoJSON. Place in `data/electrical\_network/`.



\*\*IRIS zone boundaries\*\*  

👉 https://www.data.gouv.fr/datasets/contours-iris-grande-echelle-de-la-metropole-de-lyon  

Download as GeoJSON. Place in `data/topology/`.



\---



\## Dependencies



\- Python 3.12

\- `geopandas`, `shapely`, `matplotlib`

\- `scipy` (spatial indexing for topology merging)

\- `gurobipy` (optimisation stage, requires licence)



Install dependencies:



```bash

pip install -r requirements.txt

```



\---



\## Status



\- \[x] District definition and IRIS clipping  

\- \[x] MV feeder loading, merging and topology validation  

\- \[x] Orphan endpoint detection and network visualisation  

\- \[X] HV/MV source substation integration  

\- \[ ] Power flow model (DLPF)  

\- \[ ] Smart charging optimisation (MILP)  



\---



\## Acknowledgements



This research is carried out within the PhD programme in Industrial Engineering

at the University of Padova, with focus on urban transport electrification and

energy system integration.

