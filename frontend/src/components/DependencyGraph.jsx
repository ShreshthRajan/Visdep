import React, { useEffect, useState } from 'react';
import { Network, DataSet } from 'vis-network/standalone';
import axios from 'axios';

const DependencyGraph = () => {
  const [graphData, setGraphData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchGraphData = async () => {
      try {
        const response = await axios.get('http://localhost:8000/api/dependency_graph');
        setGraphData(response.data);
      } catch (error) {
        setError('Error fetching graph data');
        console.error('Error fetching graph data:', error);
      }
    };
    fetchGraphData();
  }, []);

  useEffect(() => {
    if (graphData) {
      const nodes = new DataSet(graphData.nodes.map(node => ({
        id: node.id,
        label: node.label,
        shape: node.type === "directory" ? "box" : (node.type === "file" ? "ellipse" : "star"),
        color: node.type === "directory" ? { border: "red", background: "white" } : (node.type === "file" ? { border: "blue", background: "lightblue" } : { border: "green", background: "lightgreen" }),
        font: { size: 16 },
      })));

      const edges = new DataSet(graphData.edges.map(edge => ({
        from: edge.source,
        to: edge.target,
        arrows: edge.relation === "imports" ? "to" : "",
        dashes: edge.relation === "imports",
      })));

      const container = document.getElementById('graph');
      const data = { nodes, edges };
      const options = {
        layout: {
          hierarchical: false,
          improvedLayout: true,
        },
        nodes: {
          shape: 'ellipse',
          size: 20,
        },
        edges: {
          smooth: {
            type: 'continuous',
          },
        },
        physics: {
          enabled: true,
          barnesHut: {
            gravitationalConstant: -3000,
            centralGravity: 0.3,
            springLength: 200,
            springConstant: 0.04,
            damping: 0.09,
            avoidOverlap: 1,
          },
          stabilization: {
            iterations: 1500,
            updateInterval: 25,
          },
        },
        interaction: {
          dragNodes: true,
          dragView: true,
          zoomView: true,
        },
      };
      const network = new Network(container, data, options);
      network.on('stabilizationIterationsDone', function () {
        network.setOptions({ physics: false });
        network.fit();
      });
    }
  }, [graphData]);

  return (
    <div>
      {error && <p>{error}</p>}
      <div id="graph" style={{ height: '100vh', width: '100%' }} />
    </div>
  );
};

export default DependencyGraph;
