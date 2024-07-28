import React, { useEffect, useState } from 'react';
import { DataSet, Network } from 'vis-network/standalone';
import axios from 'axios';

const DependencyGraph = () => {
  const [graphData, setGraphData] = useState(null);

  useEffect(() => {
    const fetchGraphData = async () => {
      try {
        const response = await axios.get('http://localhost:8000/api/dependency_graph');
        setGraphData(response.data);
      } catch (error) {
        console.error('Error fetching graph data:', error);
      }
    };
    fetchGraphData();
  }, []);

  useEffect(() => {
    if (graphData) {
      const nodes = new DataSet(graphData.nodes);
      const edges = new DataSet(graphData.edges);

      const container = document.getElementById('graph');
      const data = { nodes, edges };
      const options = {};
      new Network(container, data, options);
    }
  }, [graphData]);

  return <div id="graph" style={{ height: '600px' }} />;
};

export default DependencyGraph;
