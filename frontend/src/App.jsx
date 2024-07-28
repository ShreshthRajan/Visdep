// frontend/src/App.jsx
import React from 'react';
import { BrowserRouter as Router, Route, Switch } from 'react-router-dom';
import Navbar from './components/Navbar';
import Home from './components/Home';
import FileUploader from './components/FileUploader';
import Chatbot from './components/Chatbot';
import GraphView from './components/GraphView';

const App = () => (
  <Router>
    <Navbar />
    <Switch>
      <Route path="/" exact component={Home} />
      <Route path="/upload" component={FileUploader} />
      <Route path="/chat" component={Chatbot} />
      <Route path="/graph" component={GraphView} />
    </Switch>
  </Router>
);

export default App;
