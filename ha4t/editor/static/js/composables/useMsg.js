// Thin wrapper around ElementPlus.ElMessage so all components share one API.
export function useMsg() {
  return {
    info(text)    { ElementPlus.ElMessage({ message: text, type: 'info',    showClose: true }); },
    success(text) { ElementPlus.ElMessage({ message: text, type: 'success', showClose: true }); },
    warn(text)    { ElementPlus.ElMessage({ message: text, type: 'warning', showClose: true }); },
    error(text)   { ElementPlus.ElMessage({ message: text, type: 'error',   showClose: true }); },
  };
}
