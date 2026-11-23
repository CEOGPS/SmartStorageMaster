import { useEffect, useState } from 'react';
import { BrowserRouter as Router, Routes, Route, NavLink } from 'react-router-dom';
import Home from './pages/Home';
import Scan from './pages/Scan';
import Duplicates from './pages/Duplicates';
import Cleanup from './pages/Cleanup';
import Organizer from './pages/Organizer';
import Usage from './pages/Usage';
import Settings from './pages/Settings';
import DotGridBackground from './components/DotGridBackground/DotGridBackground';
import AgentChat from './components/AgentChat/AgentChat';
import './App.css';
import { initTheme } from './utils/theme';

/**
 * Main App Component
 * Handles routing and navigation
 */
function App() {
  const [sidebarOpen, setSidebarOpen] = useState(true);

  useEffect(() => {
    initTheme();
  }, []);

  return (
    <Router>
      <DotGridBackground />
      <AgentChat />
      <div className="app-container">
        <nav className={`sidebar ${sidebarOpen ? 'open' : 'closed'}`}>
          <div className="logo">
            <span className="logo-icon">💾</span>
            <span className="logo-text">Storage Manager</span>
          </div>

          <ul className="nav-menu">
            <li>
              <NavLink to="/" end className={({isActive}) => `nav-link${isActive ? " active" : ""}`}>
                <span className="icon">📊</span>
                <span className="label">Dashboard</span>
              </NavLink>
            </li>
            <li>
              <NavLink to="/scan" className={({isActive}) => `nav-link${isActive ? " active" : ""}`}>
                <span className="icon">📁</span>
                <span className="label">Scan</span>
              </NavLink>
            </li>
            <li>
              <NavLink to="/duplicates" className={({isActive}) => `nav-link${isActive ? " active" : ""}`}>
                <span className="icon">🔄</span>
                <span className="label">Duplicates</span>
              </NavLink>
            </li>
            <li>
              <NavLink to="/cleanup" className={({isActive}) => `nav-link${isActive ? " active" : ""}`}>
                <span className="icon">🗑️</span>
                <span className="label">Cleanup</span>
              </NavLink>
            </li>
            <li>
              <NavLink to="/organizer" className={({isActive}) => `nav-link${isActive ? " active" : ""}`}>
                <span className="icon">🗂️</span>
                <span className="label">Organizer</span>
              </NavLink>
            </li>
            <li>
              <NavLink to="/usage" className={({isActive}) => `nav-link${isActive ? " active" : ""}`}>
                <span className="icon">📈</span>
                <span className="label">Usage</span>
              </NavLink>
            </li>
          </ul>

          <ul className="nav-footer">
            <li>
              <NavLink to="/settings" className={({isActive}) => `nav-link${isActive ? " active" : ""}`}>
                <span className="icon">⚙️</span>
                <span className="label">Settings</span>
              </NavLink>
            </li>
          </ul>
        </nav>

        <div className="main-content">
          <header className="top-bar">
            <button 
              className="toggle-sidebar" 
              onClick={() => setSidebarOpen(!sidebarOpen)}
              title="Toggle Sidebar"
            >
              {sidebarOpen ? '◀' : '▶'}
            </button>
            <h1>Storage Manager Pro</h1>
            <div className="header-right">
              <span className="version">v1.0.0</span>
            </div>
          </header>

          <div className="content-area">
            <Routes>
              <Route path="/" element={<Home />} />
              <Route path="/scan" element={<Scan />} />
              <Route path="/duplicates" element={<Duplicates />} />
              <Route path="/cleanup" element={<Cleanup />} />
              <Route path="/organizer" element={<Organizer />} />
               <Route path="/usage" element={<Usage />} />
              <Route path="/settings" element={<Settings />} />
            </Routes>
          </div>
        </div>
      </div>
    </Router>
  );
}

export default App;
