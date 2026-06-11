const { ref } = Vue;

export function useUndo() {
  const undoStack = ref([]);
  const redoStack = ref([]);
  const undoDepthMax = 50;

  function pushUndo(steps) {
    undoStack.value.push(JSON.parse(JSON.stringify(steps)));
    if (undoStack.value.length > undoDepthMax) undoStack.value.shift();
    redoStack.value = [];
  }

  function undo(steps) {
    if (undoStack.value.length === 0) return steps;
    redoStack.value.push(JSON.parse(JSON.stringify(steps)));
    return undoStack.value.pop();
  }

  function redo(steps) {
    if (redoStack.value.length === 0) return steps;
    undoStack.value.push(JSON.parse(JSON.stringify(steps)));
    return redoStack.value.pop();
  }

  return { undoStack, redoStack, pushUndo, undo, redo };
}
