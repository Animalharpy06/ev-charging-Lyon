# -*- coding: utf-8 -*-
"""
Created on Fri Feb 20 10:47:44 2026

@author: Admin
"""

import gzip                                # built-in tool called that knows how to open compressed files (.gz)
import xml.etree.ElementTree as ET         # built-in XML reader
from dataclasses import dataclass          # dataclass is a helper that lets you define a data container (a structured object to hold related variables) without writing a lot of repetitive code
import pandas as pd                        # Pandas library (nicknamed pd), which is used to create tables (DataFrames)

@dataclass
class Link:                     # Create the Link class
    link_id: str              # Unique ID of the link
    from_node: str
    to_node: str
    length_m: float             # Length of this link in metres
    freespeed_ms: float         # Free-flow speed of this link in metres per second
    capacity: float             # How many vehicles per hour this link can handle
    modes: set

@dataclass
class Node:
    node_id: str
    x: float                    # The projected coordinates of this node in metres (not latitude/longitude)
    y: float                    # Useful later when you want to assign a link to a geographic zone.

def parse_network(network_path: str) -> tuple[dict[str, Link], dict[str, Node]]:            
    # Takes one input: network_path, which is a text string with the file path.
    # Returns two outputs: a dict of Links and a dict of Nodes. A dict in Python is a lookup table:
    # you give it a key (the ID) and it gives back the object instantly.
    """
    Streaming parser for MATSim output_network.xml(.gz).
    Returns:
        links : dict[link_id  -> Link]
        nodes : dict[node_id  -> Node]
    """
    links: dict[str, Link] = {}
    nodes: dict[str, Node] = {}

    # Handle both plain .xml and .xml.gz
    opener = gzip.open if network_path.endswith(".gz") else open
    # One-line if/else. It says: "If the file path ends in .gz, use gzip.open to read it;
    # otherwise use the normal Python open." 

    with opener(network_path, "rb") as f:
        # Opens the file. "rb" means "read in binary mode", with block ensures the file is automatically closed even if an error occurs
        for _, elem in ET.iterparse(f, events=("start",)):
            # Each iteration gives you:
            # - event: the type of action (here always "start", meaning "I"I just saw an opening tag")
            # - elem: the XML element itself, with its tag name and attributes 
            
            if elem.tag == "node":
                node_id = elem.attrib["id"]
                nodes[node_id] = Node(
                    node_id=node_id,
                    x=float(elem.attrib["x"]),
                    y=float(elem.attrib["y"]),
                )

            elif elem.tag == "link":
                link_id = elem.attrib["id"]
                modes_raw = elem.attrib.get("modes", "")
                links[link_id] = Link(
                    link_id=link_id,
                    from_node=elem.attrib["from"],
                    to_node=elem.attrib["to"],
                    length_m=float(elem.attrib["length"]),
                    freespeed_ms=float(elem.attrib.get("freespeed", 0)),
                    capacity=float(elem.attrib.get("capacity", 0)),
                    modes=set(modes_raw.split(",")),                 # Splits the string "car,bike" into a Python list ["car", "bike"], and set(...) converts it into a set.
                )

            # Free memory after each element to keep RAM low
            elem.clear()

    print(f"Parsed {len(nodes):,} nodes and {len(links):,} links.")   # Prints a confirmation message (:, formats numbers with thousands separators, e.g. 1,234,567)
    return links, nodes


def links_to_dataframe(links: dict[str, Link]) -> pd.DataFrame:
    """
    Converts the links dict to a flat DataFrame for easy lookups.
    """
    records = [
        {
            "link_id":      lnk.link_id,
            "from_node":    lnk.from_node,
            "to_node":      lnk.to_node,
            "length_m":     lnk.length_m,
            "freespeed_ms": lnk.freespeed_ms,
            "capacity":     lnk.capacity,
            "modes":        ",".join(sorted(lnk.modes)),
        }
        for lnk in links.values()
    ]
    return pd.DataFrame(records).set_index("link_id")


# ── Convenience: fast length lookup for event parsing ──────────────────────
def build_length_lookup(links: dict[str, Link]) -> dict[str, float]:
    """
    Returns a plain dict  link_id -> length_m
    This is what the events parser will call millions of times,
    so keeping it as a plain dict is faster than a DataFrame lookup.
    """
    return {lid: lnk.length_m for lid, lnk in links.items()}
