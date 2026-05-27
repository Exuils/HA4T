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

export async function listTaskImages(filename) {
  const response = await fetch(`${API_HOST}tasks/${encodeURIComponent(filename)}/images`);
  return checkResponse(response);
}

export async function getTaskImage(filename, imgname) {
  const response = await fetch(`${API_HOST}tasks/${encodeURIComponent(filename)}/images/${encodeURIComponent(imgname)}`);
  return checkResponse(response);
}

export async function saveTaskImage(filename, imgname, data) {
  const response = await fetch(`${API_HOST}tasks/${encodeURIComponent(filename)}/images/${encodeURIComponent(imgname)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ data })
  });
  return checkResponse(response);
}
