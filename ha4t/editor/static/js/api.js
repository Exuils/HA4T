import { API_HOST } from './config.js';

async function checkResponse(response) {
  if (response.status === 500) {
    throw new Error('Server error: 500');
  }
  return response.json();
}

export async function getVersion() {
  const response = await fetch(`${API_HOST}version`);
  return checkResponse(response);
}

export async function getConfig() {
  const response = await fetch(`${API_HOST}config`);
  return checkResponse(response);
}

export async function setConfig(key, value) {
  const response = await fetch(`${API_HOST}config`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ key, value })
  });
  return checkResponse(response);
}

export async function listDevices(platform) {
  const response = await fetch(`${API_HOST}${platform}/serials`);
  return checkResponse(response);
}

export async function connectDevice(platform, serial, wdaUrl, maxDepth) {
  let url = `${API_HOST}${platform}/${serial}/connect`;

  if (platform === 'ios') {
    const queryParams = [];
    if (wdaUrl) {
      queryParams.push(`wdaUrl=${encodeURIComponent(wdaUrl)}`);
    }
    if (maxDepth) {
      queryParams.push(`maxDepth=${encodeURIComponent(maxDepth)}`);
    }

    if (queryParams.length > 0) {
      url += `?${queryParams.join('&')}`;
    }
  }

  const response = await fetch(url, {
    method: 'POST'
  });

  return checkResponse(response);
}

export async function fetchScreenshot(platform, serial) {
  const response = await fetch(`${API_HOST}${platform}/${serial}/screenshot`);
  return checkResponse(response);
}

export async function fetchHierarchy(platform, serial) {
  const response = await fetch(`${API_HOST}${platform}/${serial}/hierarchy`);
  return checkResponse(response);
}

export async function fetchXpathLite(platform, treeData, nodeId) {
  const response = await fetch(`${API_HOST}${platform}/hierarchy/xpathLite`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      tree_data: treeData,
      node_id: nodeId
    })
  });

  return checkResponse(response);
}

export async function listTasks() {
  const response = await fetch(`${API_HOST}tasks`);
  return checkResponse(response);
}

export async function getTask(filename) {
  const response = await fetch(`${API_HOST}tasks/${encodeURIComponent(filename)}`);
  return checkResponse(response);
}

export async function saveTask(filename, content) {
  const response = await fetch(`${API_HOST}tasks/${encodeURIComponent(filename)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content })
  });
  return checkResponse(response);
}

export async function runTask(platform, serial, filename, content) {
  const response = await fetch(`${API_HOST}tasks/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ platform, serial, filename, content })
  });
  return checkResponse(response);
}

export async function listPackages(platform, serial) {
  const response = await fetch(`${API_HOST}${platform}/${serial}/packages`);
  return checkResponse(response);
}

export async function getProjectId(filename) {
  const response = await fetch(`${API_HOST}tasks/${encodeURIComponent(filename)}/project-id`);
  return checkResponse(response);
}

export async function getImage(imgname) {
  const response = await fetch(`${API_HOST}images/${encodeURIComponent(imgname)}`);
  return checkResponse(response);
}

export async function saveImage(imgname, data) {
  const response = await fetch(`${API_HOST}images/${encodeURIComponent(imgname)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ data })
  });
  return checkResponse(response);
}

export async function cleanupImages(filename) {
  const response = await fetch(`${API_HOST}tasks/${encodeURIComponent(filename)}/cleanup-images`, {
    method: 'POST'
  });
  return checkResponse(response);
}

export async function runAllure(filename) {
  const response = await fetch(`${API_HOST}tasks/${encodeURIComponent(filename)}/run-allure`, {
    method: 'POST'
  });
  return checkResponse(response);
}
export async function taskMeta(filename) {
  const response = await fetch(`${API_HOST}tasks/${encodeURIComponent(filename)}/meta`);
  return checkResponse(response);
}

export async function reorderTask(filename, newOrder) {
  const response = await fetch(`${API_HOST}tasks/${encodeURIComponent(filename)}/reorder`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ new_order: newOrder })
  });
  return checkResponse(response);
}

export async function pomListPages() {
  const response = await fetch(`${API_HOST}pom/pages`);
  return checkResponse(response);
}

export async function pomGetPage(filename) {
  const response = await fetch(`${API_HOST}pom/pages/${encodeURIComponent(filename)}`);
  return checkResponse(response);
}

export async function pomSavePage(payload) {
  const response = await fetch(`${API_HOST}pom/pages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  return checkResponse(response);
}

export async function pomDeletePage(filename) {
  const response = await fetch(`${API_HOST}pom/pages/${encodeURIComponent(filename)}`, {
    method: 'DELETE'
  });
  return checkResponse(response);
}

export async function pomGetMeta() {
  const response = await fetch(`${API_HOST}pom/meta`);
  return checkResponse(response);
}

export async function pomSaveMeta(payload) {
  const response = await fetch(`${API_HOST}pom/meta`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  return checkResponse(response);
}

export async function pomInstallSkill() {
  const response = await fetch(`${API_HOST}pom/install-skill`, {
    method: 'POST'
  });
  return checkResponse(response);
}

export async function pomVerifySelector(payload) {
  const response = await fetch(`${API_HOST}pom/verify-selector`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  return checkResponse(response);
}

// ── Workspace / FS browse ────────────────────────────────────────

export async function getWorkspace() {
  const response = await fetch(`${API_HOST}workspace`);
  return checkResponse(response);
}

export async function openWorkspace(path) {
  const response = await fetch(`${API_HOST}workspace/open`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path })
  });
  return checkResponse(response);
}

export async function initWorkspace(parent, name) {
  const response = await fetch(`${API_HOST}workspace/init`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ parent, name })
  });
  return checkResponse(response);
}

export async function fsList(path) {
  const url = `${API_HOST}fs/list?path=${encodeURIComponent(path || '')}`;
  const response = await fetch(url);
  return checkResponse(response);
}
