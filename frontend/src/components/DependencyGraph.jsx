// frontend/src/components/DependencyGraph.jsx
import React, { useEffect, useState } from 'react';
import { Network } from 'vis-network/standalone';
import axios from 'axios';

const DependencyGraph = () => {
  const [graphData, setGraphData] = useState(null);

  useEffect(() => {
    const fetchGraphData = async () => {
      const response = await axios.get('/path/to/graph/data');
      setGraphData(response.data);
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
