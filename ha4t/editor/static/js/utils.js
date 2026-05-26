export function saveToLocalStorage(key, value) {
    localStorage.setItem(key, JSON.stringify(value));
}

export function getFromLocalStorage(key, defaultValue) {
    const v = localStorage.getItem(key);
    if (v === null) return defaultValue;
    try { return JSON.parse(v); } catch (e) { return defaultValue; }
}
  
  export function copyToClipboard(value) {
    if (typeof value === 'object') {
      value = JSON.stringify(value, null, 2);
    }
  
    if (value === null || value === undefined || value === '') {
      value = '';
    }
  
    const textarea = document.createElement('textarea');
    textarea.value = value;
    document.body.appendChild(textarea);
    textarea.select();
    try {
      document.execCommand('copy');
      return true;
    } catch (err) {
      return false;
    } finally {
      document.body.removeChild(textarea);
    }
  }