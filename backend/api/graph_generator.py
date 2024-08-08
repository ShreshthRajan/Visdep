import os
import networkx as nx
from typing import Dict, Any
from networkx.readwrite import json_graph
import json
from collections import defaultdict

def create_dependency_graph(ast_data: Dict[str, Any]) -> nx.DiGraph:
    G = nx.DiGraph()

    directories = set()
    files = set()
    methods = {}
    imported_methods = {}

    # First pass: collect all files and methods
    for file_path, file_info in ast_data.items():
        files.add(file_path)
        for func in file_info.get("functions", []):
            methods[func] = file_path
        for cls in file_info.get("classes", []):
            methods[cls] = file_path

    # Second pass: create nodes and edges
    for file_path, file_info in ast_data.items():
        dir_path = os.path.dirname(file_path)
        while dir_path:
            directories.add(dir_path)
            dir_path = os.path.dirname(dir_path)

        functions = file_info.get("functions", [])
        classes = file_info.get("classes", [])
        imports = file_info.get("imports", [])

        file_label = f"{os.path.basename(file_path)}\nFunctions: {', '.join(functions)}\nClasses: {', '.join(classes)}"
        G.add_node(file_path, type="file", label=file_label, shape="ellipse", level=file_path.count('/') + 1)

        file_extension = os.path.splitext(file_path)[1].lower()

        for imp in imports:
            if file_extension in ['.py', '.js', '.ts']:
                handle_python_style_import(G, imp, file_path, files, methods, imported_methods)
            elif file_extension in ['.java', '.kt']:
                handle_java_style_import(G, imp, file_path)
            elif file_extension in ['.go']:
                handle_go_style_import(G, imp, file_path)
            elif file_extension in ['.c', '.cpp', '.h', '.hpp']:
                handle_c_style_import(G, imp, file_path)
            else:
                # Generic handling for unknown file types
                G.add_node(imp, type="package", label=imp, shape="star", level=imp.count('.') + 1)
                G.add_edge(imp, file_path, relation="imports")

    # Add directory nodes and edges
    for directory in directories:
        G.add_node(directory, type="directory", label=os.path.basename(directory), shape="box", level=directory.count('/'))
        for file in files:
            if os.path.dirname(file) == directory:
                G.add_edge(directory, file, relation="contains")
        subdirs = [d for d in directories if os.path.dirname(d) == directory]
        for subdir in subdirs:
            G.add_edge(directory, subdir, relation="contains")

    # Perform edge clustering
    G = cluster_edges(G)

    return G

def handle_python_style_import(G, imp, file_path, files, methods, imported_methods):
    if '.' in imp:
        module_path, method = imp.rsplit('.', 1)
        source_file = next((file for file in files if file.endswith(module_path.replace('.', '/') + '.py')), None)
        if source_file:
            # This is an import from within the project
            if method not in imported_methods:
                mid_point = f"{source_file}::{method}"
                G.add_node(mid_point, type="import", label=method, shape="box", level=source_file.count('/') + 2)
                G.add_edge(source_file, mid_point, relation="exports")
                imported_methods[method] = mid_point
            G.add_edge(imported_methods[method], file_path, relation="imports")
        else:
            # This is a package import
            G.add_node(module_path, type="package", label=module_path, shape="star", level=module_path.count('.') + 1)
            G.add_edge(module_path, file_path, relation="imports", label=method)
    elif imp in methods:
        # This is a direct import of a method or class from another file
        source_file = methods[imp]
        if source_file != file_path:
            if imp not in imported_methods:
                mid_point = f"{source_file}::{imp}"
                G.add_node(mid_point, type="import", label=imp, shape="box", level=source_file.count('/') + 2)
                G.add_edge(source_file, mid_point, relation="exports")
                imported_methods[imp] = mid_point
            G.add_edge(imported_methods[imp], file_path, relation="imports")
    else:
        # This is likely a built-in or unknown import
        G.add_node(imp, type="package", label=imp, shape="star", level=1)
        G.add_edge(imp, file_path, relation="imports")

def handle_java_style_import(G, imp, file_path):
    package_path = imp.rsplit('.', 1)[0]
    G.add_node(package_path, type="package", label=package_path, shape="star", level=package_path.count('.') + 1)
    G.add_edge(package_path, file_path, relation="imports")

def handle_go_style_import(G, imp, file_path):
    G.add_node(imp, type="package", label=imp, shape="star", level=imp.count('/') + 1)
    G.add_edge(imp, file_path, relation="imports")

def handle_c_style_import(G, imp, file_path):
    G.add_node(imp, type="header", label=imp, shape="diamond", level=imp.count('/') + 1)
    G.add_edge(imp, file_path, relation="includes")

def cluster_edges(G):
    edge_groups = defaultdict(list)
    for edge in G.edges(data=True):
        source, target = edge[0], edge[1]
        edge_groups[(source, target)].append(edge[2])
    
    for (source, target), edges in edge_groups.items():
        if len(edges) > 1:
            G.add_edge(source, target, relation="multiple", count=len(edges))
            for edge in edges:
                G.remove_edge(source, target, key=None)
    
    return G

def save_graph_as_json(graph: nx.DiGraph, file_path: str) -> None:
    data = json_graph.node_link_data(graph)
    with open(file_path, 'w') as f:
        json.dump(data, f)

def load_graph_from_json(file_path: str) -> nx.DiGraph:
    with open(file_path, 'r') as f:
        data = json.load(f)
    return json_graph.node_link_graph(data)

def get_subgraph_at_level(G: nx.DiGraph, level: int) -> nx.DiGraph:
    nodes = [node for node, data in G.nodes(data=True) if data['level'] <= level]
    return G.subgraph(nodes)