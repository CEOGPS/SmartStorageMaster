import React from 'react';
import { BarChart, Bar, PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import './StorageChart.css';

/**
 * StorageChart Component
 * Displays storage usage with visual charts
 */
export default function StorageChart({ data }) {
  // Guard against null/undefined data
  if (!data) return null;

  // Safely read numeric fields; fall back to 0 if missing
  const used = Number(data.used) || 0;
  const available = Number(data.available) || 0;

  const chartData = [
    { name: 'Used', value: used, fill: '#e74c3c' },
    { name: 'Available', value: available, fill: '#27ae60' },
  ];

  // Guard: fileTypes may be undefined, null, or not an array
  const fileTypes = Array.isArray(data.fileTypes) ? data.fileTypes : [];
  const typeData = fileTypes.map(type => ({
    name: type?.type ?? 'Unknown',
    value: Number(type?.size) || 0,
  }));

  return (
    <div className="storage-chart">
      <div className="chart-container">
        <ResponsiveContainer width="100%" height={250}>
          <PieChart>
            <Pie
              data={chartData}
              cx="50%"
              cy="50%"
              labelLine={false}
              label={({ name, value }) => `${name}: ${(value / 1e9).toFixed(1)}GB`}
              outerRadius={80}
              fill="#8884d8"
              dataKey="value"
            >
              {chartData.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={entry.fill} />
              ))}
            </Pie>
            <Tooltip formatter={(value) => `${(value / 1e9).toFixed(2)}GB`} />
          </PieChart>
        </ResponsiveContainer>
      </div>

      {typeData.length > 0 && (
        <div className="type-breakdown">
          <h4>Storage by File Type</h4>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={typeData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" />
              <YAxis />
              <Tooltip formatter={(value) => `${(value / 1e9).toFixed(2)}GB`} />
              <Bar dataKey="value" fill="#3498db" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}