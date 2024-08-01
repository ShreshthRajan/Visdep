# dependency_extraction/backend/api/graph_generator.py
import os
import networkx as nx
from typing import Dict, Any
from networkx.readwrite import json_graph
import json

def create_dependency_graph(ast_data: Dict[str, Any]) -> nx.DiGraph:
    G = nx.DiGraph()

    directories = set()
    files = set()
    methods = {}
    package_imports = set()

    for file_path, file_info in ast_data.items():
        dir_path = os.path.dirname(file_path)
        while dir_path:
            directories.add(dir_path)
            dir_path = os.path.dirname(dir_path)
        files.add(file_path)

        functions = file_info.get("functions", [])
        classes = file_info.get("classes", [])
        imports = file_info.get("imports", [])

        file_label = f"{os.path.basename(file_path)}\nFunctions: {', '.join(functions)}\nClasses: {', '.join(classes)}"
        G.add_node(file_path, type="file", label=file_label, shape="ellipse")

        for func in functions:
            methods[func] = file_path

        for imp in imports:
            if '.' in imp:  # Assuming package imports contain a dot
                package_imports.add(imp)
                G.add_node(imp, type="package", label=imp, shape="star")
                G.add_edge(imp, file_path, relation="imports")
            elif imp in methods:
                source_file = methods[imp]
                if source_file != file_path:
                    mid_point = f"{source_file}::{file_path}::{imp}"
                    G.add_node(mid_point, type="import", label=imp, shape="diamond")
                    G.add_edge(source_file, mid_point, relation="exports")
                    G.add_edge(mid_point, file_path, relation="imports")
            else:
                # Handle unknown imports (could be built-in modules)
                G.add_node(imp, type="unknown", label=imp, shape="triangle")
                G.add_edge(imp, file_path, relation="imports")

    for directory in directories:
        G.add_node(directory, type="directory", label=os.path.basename(directory), shape="box")

    for directory in directories:
        for file in files:
            if os.path.dirname(file) == directory:
                G.add_edge(directory, file, relation="contains")
        subdirs = [d for d in directories if os.path.dirname(d) == directory]
        for subdir in subdirs:
            G.add_edge(directory, subdir, relation="contains")

    return G

def save_graph_as_json(graph: nx.DiGraph, file_path: str) -> None:
    data = json_graph.node_link_data(graph)
    with open(file_path, 'w') as f:
        json.dump(data, f)

def load_graph_from_json(file_path: str) -> nx.DiGraph:
    with open(file_path, 'r') as f:
        data = json.load(f)
    return json_graph.node_link_graph(data)
