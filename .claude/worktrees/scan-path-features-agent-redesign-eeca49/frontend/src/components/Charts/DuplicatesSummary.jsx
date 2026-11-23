import React from 'react';
import { PieChart, Pie, Cell, Legend, Tooltip, ResponsiveContainer } from 'recharts';

/**
 * DuplicatesSummary Component
 * Accepts either:
 *   - an array of { name, count } groups, OR
 *   - an object { total_duplicates, total_size, ... } from /duplicates/stats
 * Never crashes on null / undefined / non-array.
 */
export default function DuplicatesSummary({ data }) {
  // Normalize input to an array of pie slices
  let slices = [];

  if (Array.isArray(data)) {
    slices = data
      .filter(item => item && typeof item === 'object')
      .map((item, index) => ({
        name: String(item.name ?? item.type ?? `Group ${index + 1}`),
        count: Number(item.count ?? item.size ?? item.value ?? 0),
      }));
  } else if (data && typeof data === 'object') {
    // Backend returned a stats object — build slices from its fields
    const candidates = [
      { name: 'Duplicate Files', count: Number(data.total_duplicates) || 0 },
      { name: 'Total Size (bytes)', count: Number(data.total_size) || 0 },
      { name: 'Savings (bytes)', count: Number(data.savings_possible) || 0 },
    ].filter(s => s.count > 0);

    slices = candidates.length > 0 ? candidates : [];
  }

  if (slices.length === 0) {
    return <p>No duplicate data</p>;
  }

  return (
    <ResponsiveContainer width="100%" height={250}>
      <PieChart>
        <Pie
          data={slices}
          cx="50%"
          cy="50%"
          labelLine={false}
          label={({ name, value }) => `${name}: ${value}`}
          outerRadius={80}
          fill="#8884d8"
          dataKey="count"
        >
          {slices.map((entry, index) => (
            <Cell
              key={`cell-${index}`}
              fill={['#e74c3c', '#f39c12', '#3498db'][index % 3]}
            />
          ))}
        </Pie>
        <Tooltip />
        <Legend />
      </PieChart>
    </ResponsiveContainer>
  );
}
