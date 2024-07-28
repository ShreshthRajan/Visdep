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

    for file_path, file_info in ast_data.items():
        dir_path = os.path.dirname(file_path)
        while dir_path:
            directories.add(dir_path)
            dir_path = os.path.dirname(dir_path)
        files.add(file_path)

        functions = file_info.get("functions", [])
        classes = file_info.get("classes", [])
        imports = file_info.get("imports", [])

        file_label = f"{os.path.basename(file_path)}\nFunctions: {', '.join(functions)}" if functions else os.path.basename(file_path)
        G.add_node(file_path, type="file", label=file_label, shape="ellipse")

        for func in functions:
            func_node = f"{file_path}::{func}"
            G.add_node(func_node, type="function", label=func, shape="ellipse")
            G.add_edge(file_path, func_node, relation="contains")
            methods[func] = file_path

        for cls in classes:
            class_node = f"{file_path}::{cls}"
            G.add_node(class_node, type="class", label=cls, shape="ellipse")
            G.add_edge(file_path, class_node, relation="contains")

        for imp in imports:
            if imp in methods:
                import_node = f"import::{imp}"
                G.add_node(import_node, type="import", label=imp, shape="star", style="dotted")
                G.add_edge(file_path, methods[imp], relation="imports")

    for directory in directories:
        G.add_node(directory, type="directory", label=os.path.basename(directory), shape="box", color="red")

    for directory in directories:
        for file in files:
            if os.path.dirname(file) == directory:
                G.add_edge(directory, file, relation="contains", arrows="none")
        subdirs = [d for d in directories if os.path.dirname(d) == directory]
        for subdir in subdirs:
            G.add_edge(directory, subdir, relation="contains", arrows="none")

    return G

def save_graph_as_json(graph: nx.DiGraph, file_path: str) -> None:
    data = json_graph.node_link_data(graph)
    with open(file_path, 'w') as f:
        json.dump(data, f)

def load_graph_from_json(file_path: str) -> nx.DiGraph:
    with open(file_path, 'r') as f:
        data = json.load(f)
    return json_graph.node_link_graph(data)
