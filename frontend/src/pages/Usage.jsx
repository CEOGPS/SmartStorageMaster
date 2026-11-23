import React, { useState, useEffect } from 'react';
import './Usage.css';
import UsageAnalytics from '../components/UsageAnalytics/UsageAnalytics';
import UsageThresholds from '../components/UsageThresholds/UsageThresholds';

/**
 * Usage Analysis Page
 * View file usage patterns and cleanup recommendations
 */
export default function Usage() {
  const [activeTab, setActiveTab] = useState('overview');

  return (
    <div className="usage-page">
      <div className="usage-header">
        <h1>📈 File Usage Analysis</h1>
        <p className="description">
          Track file usage patterns and get smart cleanup recommendations based on access history.
        </p>
      </div>

      <div className="usage-tabs">
        <button
          className={`tab-button ${activeTab === 'overview' ? 'active' : ''}`}
          onClick={() => setActiveTab('overview')}
        >
          📊 Overview
        </button>
        <button
          className={`tab-button ${activeTab === 'recommendations' ? 'active' : ''}`}
          onClick={() => setActiveTab('recommendations')}
        >
          💡 Recommendations
        </button>
        <button
          className={`tab-button ${activeTab === 'settings' ? 'active' : ''}`}
          onClick={() => setActiveTab('settings')}
        >
          ⚙️ Settings
        </button>
      </div>

      <div className="usage-content">
        {activeTab === 'overview' && <UsageAnalytics />}
        {activeTab === 'recommendations' && <UsageAnalytics showRecommendations={true} />}
        {activeTab === 'settings' && <UsageThresholds />}
      </div>
    </div>
  );
}
