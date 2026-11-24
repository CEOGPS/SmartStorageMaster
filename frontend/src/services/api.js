/**
 * API Service
 * Handles all API calls to the backend
 */

const API_BASE_URL = 'http://localhost:8000/api';

export function getThumbnailUrl(fileId) {
  return `${API_BASE_URL}/organizer/thumbnail/${fileId}`;
}

export function formatBytes(bytes) {
  const n = Number(bytes) || 0;
  if (n === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(n) / Math.log(k));
  return `${Math.round((n / Math.pow(k, i)) * 100) / 100} ${sizes[i]}`;
}

async function request(path, options) {
  const response = await fetch(`${API_BASE_URL}${path}`, options);
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail || `Request failed: ${response.status}`);
  }
  return response.json();
}

// Unwraps the backend's common {success, data, error} envelope.
function unwrap(json) {
  if (json && typeof json === 'object' && 'data' in json && 'success' in json) {
    if (json.success === false) throw new Error(json.error || 'Request failed');
    return json.data;
  }
  return json;
}

// Storage/Dashboard APIs
export async function getStorageStats() {
  try {
    const d = unwrap(await request('/storage/stats')) || {};
    return {
      fileCount: d.total_files || 0,
      total: d.total_size || 0,
      totalFormatted: d.total_size_formatted || '0 B',
      available: 0,
      availableFormatted: 'Unknown',
      fileTypes: [],
      lastScan: d.last_scan || null,
    };
  } catch (error) {
    console.error('getStorageStats error:', error);
    throw error;
  }
}

export async function getDuplicateStats() {
  try {
    const d = unwrap(await request('/duplicates/stats')) || {};
    const totalGroups = d.total_groups || 0;
    const totalDuplicates = d.total_duplicates || 0;
    const totalSavings = d.total_savings || 0;
    return {
      groupCount: totalGroups,
      fileCount: totalDuplicates,
      saving: totalSavings,
      savingFormatted: formatBytes(totalSavings),
      total_groups: totalGroups,
      total_duplicates: totalDuplicates,
      savings_possible: totalSavings,
      by_type: d.by_type || {},
    };
  } catch (error) {
    console.error('getDuplicateStats error:', error);
    throw error;
  }
}

// Scan APIs
export async function startScan(path, options = {}) {
  try {
    const json = await request('/scan/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        path,
        recursive: options.recursive !== false,
        include_hidden: options.includeHidden || false,
        compute_hash: options.computeHash !== false,
      }),
    });
    return { scan_id: json.scan_id, message: json.message };
  } catch (error) {
    console.error('startScan error:', error);
    throw error;
  }
}

export async function getScanStatistics(scanId) {
  try {
    return unwrap(await request(`/scan/status/${scanId}`));
  } catch (error) {
    console.error('getScanStatistics error:', error);
    throw error;
  }
}

export async function getScanFiles(scanId, limit = 100, offset = 0) {
  try {
    return unwrap(await request(`/scan/files/${scanId}?limit=${limit}&offset=${offset}`));
  } catch (error) {
    console.error('getScanFiles error:', error);
    throw error;
  }
}

// Duplicate Detection APIs
export async function detectDuplicates(scanId, options = {}) {
  try {
    const json = await request('/duplicates/detect', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        scan_id: scanId,
        detect_exact: options.detectExact !== false,
        detect_images: options.includeSimilar !== false,
        image_similarity: options.similarityThreshold || 0.85,
      }),
    });
    return unwrap(json);
  } catch (error) {
    console.error('detectDuplicates error:', error);
    throw error;
  }
}

const MIME_CATEGORIES = {
  images: (m) => m?.startsWith('image/'),
  videos: (m) => m?.startsWith('video/'),
  documents: (m) =>
    m?.startsWith('text/') ||
    m === 'application/pdf' ||
    m?.includes('msword') ||
    m?.includes('officedocument') ||
    m?.includes('spreadsheet'),
};

export async function getDuplicates(filterType = 'all') {
  try {
    const d = unwrap(await request('/duplicates/groups')) || {};
    const groups = (d.groups || []).map((g) => ({
      id: g.id,
      type: g.type,
      totalSize: g.total_size,
      totalSizeFormatted: formatBytes(g.total_size),
      fileCount: g.file_count,
      savings: g.savings,
      files: (g.files || []).map((f) => ({
        id: f.id,
        path: f.path,
        name: f.name,
        size: f.size,
        sizeFormatted: formatBytes(f.size),
        mimeType: f.mime_type,
        isPrimary: f.is_primary,
        similarity: f.similarity,
        modifiedDate: f.modified_at ? new Date(f.modified_at).toLocaleString() : '',
      })),
    }));

    if (filterType === 'all') return groups;
    const matches = MIME_CATEGORIES[filterType];
    if (!matches) return groups;
    return groups.filter((g) => g.files.some((f) => matches(f.mimeType)));
  } catch (error) {
    // Before the first scan completes there is simply nothing to show; that is
    // an empty state, not a failure.
    if (/no completed scans/i.test(error?.message || '')) return [];
    console.error('getDuplicates error:', error);
    throw error;
  }
}

export async function getDuplicateSavings() {
  try {
    return unwrap(await request('/duplicates/savings'));
  } catch (error) {
    console.error('getDuplicateSavings error:', error);
    throw error;
  }
}

// Usage Analysis APIs
export async function getUsageSummary() {
  try {
    const json = await request('/usage/summary');
    const summary = {};
    for (const [category, stats] of Object.entries(json.summary || {})) {
      summary[category] = { ...stats, size_mb: stats.total_size_mb };
    }
    return { ...json, summary };
  } catch (error) {
    console.error('getUsageSummary error:', error);
    throw error;
  }
}

export async function getUsageRecommendations(limit = 100, minPriority = 0.7) {
  try {
    return await request(`/usage/recommendations?limit=${limit}&min_priority=${minPriority}`);
  } catch (error) {
    console.error('getUsageRecommendations error:', error);
    throw error;
  }
}

export async function getUsageThresholds() {
  try {
    return await request('/usage/thresholds');
  } catch (error) {
    console.error('getUsageThresholds error:', error);
    throw error;
  }
}

export async function updateUsageThresholds(thresholds) {
  try {
    const params = new URLSearchParams();
    if (thresholds.recently_used_days) params.append('recently_used_days', thresholds.recently_used_days);
    if (thresholds.rarely_used_days) params.append('rarely_used_days', thresholds.rarely_used_days);
    if (thresholds.not_used_days) params.append('not_used_days', thresholds.not_used_days);
    if (thresholds.min_priority_size_mb) params.append('min_priority_size_mb', thresholds.min_priority_size_mb);

    const json = await request(`/usage/thresholds?${params}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
    });
    return json.thresholds;
  } catch (error) {
    console.error('updateUsageThresholds error:', error);
    throw error;
  }
}

// Cleanup APIs
export async function backupFiles(fileIds) {
  try {
    return unwrap(
      await request('/cleanup/backup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file_ids: fileIds }),
      })
    );
  } catch (error) {
    console.error('backupFiles error:', error);
    throw error;
  }
}

export async function deleteFiles(fileIds) {
  try {
    return unwrap(
      await request('/cleanup/delete', {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file_ids: fileIds }),
      })
    );
  } catch (error) {
    console.error('deleteFiles error:', error);
    throw error;
  }
}

// Backs up files, then deletes them — files are always recoverable from backup.
export async function selectForCleanup(fileIds) {
  await backupFiles(fileIds);
  return deleteFiles(fileIds);
}

export async function getBackups() {
  try {
    const [backupsJson, statsJson] = await Promise.all([
      request('/cleanup/backups'),
      request('/cleanup/stats'),
    ]);
    const backupsData = unwrap(backupsJson);
    const stats = unwrap(statsJson);

    const files = (backupsData?.backups || []).map((b) => ({
      id: b.id,
      originalPath: b.original_path,
      backupPath: b.backup_path,
      size: b.file_size,
      sizeFormatted: formatBytes(b.file_size),
      backedUpAt: b.deleted_at ? new Date(b.deleted_at).toLocaleString() : '',
      restored: b.is_restored,
    }));

    return {
      files,
      stats: {
        backupCount: stats?.total_backups || 0,
        totalSizeFormatted: formatBytes(stats?.total_backup_size),
        spaceFreeFormatted: formatBytes(stats?.disk_free),
      },
    };
  } catch (error) {
    console.error('getBackups error:', error);
    throw error;
  }
}

export async function restoreFile(backupId) {
  try {
    return unwrap(
      await request('/cleanup/restore', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ backup_id: backupId }),
      })
    );
  } catch (error) {
    console.error('restoreFile error:', error);
    throw error;
  }
}

export async function clearBackups(days = 30) {
  try {
    return unwrap(
      await request('/cleanup/clear', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ days }),
      })
    );
  } catch (error) {
    console.error('clearBackups error:', error);
    throw error;
  }
}

// Agent chat API
export async function sendAgentMessage(message, history = []) {
  try {
    const json = await request('/agent/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, history }),
    });
    return unwrap(json);
  } catch (error) {
    console.error('sendAgentMessage error:', error);
    throw error;
  }
}

// Organizer APIs
export async function listOrganizerFiles(folder, fileType, limit = 50, offset = 0) {
  try {
    const params = new URLSearchParams();
    if (folder) params.append('folder', folder);
    if (fileType && fileType !== 'all') params.append('file_type', fileType);
    params.append('limit', limit);
    params.append('offset', offset);
    return unwrap(await request(`/organizer/files?${params}`));
  } catch (error) {
    console.error('listOrganizerFiles error:', error);
    throw error;
  }
}

export async function listOrganizerFolders() {
  try {
    return unwrap(await request('/organizer/folders'));
  } catch (error) {
    console.error('listOrganizerFolders error:', error);
    throw error;
  }
}

export async function createFolder(path) {
  try {
    return unwrap(
      await request('/organizer/create-folder', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path }),
      })
    );
  } catch (error) {
    console.error('createFolder error:', error);
    throw error;
  }
}

export async function moveFiles(fileIds, destination, createIfMissing = true) {
  try {
    return unwrap(
      await request('/organizer/move', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          file_ids: fileIds,
          destination,
          create_if_missing: createIfMissing,
        }),
      })
    );
  } catch (error) {
    console.error('moveFiles error:', error);
    throw error;
  }
}

export async function deleteEmptyFolders(root) {
  try {
    return unwrap(
      await request('/organizer/delete-empty-folders', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ root }),
      })
    );
  } catch (error) {
    console.error('deleteEmptyFolders error:', error);
    throw error;
  }
}

export async function deleteOrganizerFiles(fileIds) {
  try {
    return unwrap(
      await request('/organizer/delete-files', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file_ids: fileIds }),
      })
    );
  } catch (error) {
    console.error('deleteOrganizerFiles error:', error);
    throw error;
  }
}

// WebSocket connection for scan progress
export function connectScanWebSocket(scanId, onProgress, onComplete, onError) {
  const ws = new WebSocket(`ws://localhost:8000/ws/scan?scan_id=${scanId}`);

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.status === 'progress') {
      onProgress(data);
    } else if (data.status === 'completed' || data.status === 'complete') {
      onComplete(data);
    } else if (data.status === 'failed') {
      onError(new Error(data.error_message || 'Scan failed'));
    }
  };

  ws.onerror = (error) => {
    console.error('WebSocket error:', error);
    onError(error);
  };

  return ws;
}

export function disconnectWebSocket(ws) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.close();
  }
}

// Auto-sort + undo journal
async function postJson(path, body) {
  return unwrap(
    await request(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
  );
}

export const previewSort = (opts) => postJson('/organizer/sort/preview', opts);
export const applySort = (opts) => postJson('/organizer/sort/apply', opts);

export async function listJournal(limit = 20) {
  return unwrap(await request(`/journal?limit=${limit}`));
}

export async function undoOperation(operationId) {
  return unwrap(await request(`/journal/${operationId}/undo`, { method: 'POST' }));
}

// Bulk rename
export const previewRename = (opts) => postJson('/organizer/rename/preview', opts);
export const applyRename = (opts) => postJson('/organizer/rename/apply', opts);

// Protected folders
export async function getProtectedFolders() {
  return unwrap(await request('/protection'));
}
export const addProtectedFolder = (path, note) => postJson('/protection', { path, note: note || null });
export async function removeProtectedFolder(id) {
  return unwrap(await request(`/protection/${id}`, { method: 'DELETE' }));
}
