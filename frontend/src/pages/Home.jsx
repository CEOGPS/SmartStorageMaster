import React from 'react';
import Dashboard from '../components/Dashboard/Dashboard';
import './Home.css';

/**
 * Home Page
 * Main landing page with storage dashboard
 */
export default function Home() {
  return (
    <div className="home-page">
      <Dashboard />
    </div>
  );
}
