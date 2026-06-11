# HA4T Editor — Frontend Development

## Architecture

The frontend is a **Vue 3 Options-API + Element Plus** single-page app, served as static files by FastAPI.  
No build step required: all dependencies are vendored under `static/cdn/`.

## Stack

| Asset | Location | Exposed as |
|---|---|---|
| Vue 3.4 | `static/cdn/vue@3/vue.global.prod.js` | `window.Vue` |
| Element Plus 2.8 | `static/cdn/element-plus/index.full.min.js` | `window.ElementPlus` |
| Element Plus icons | `static/cdn/element-plus-icons/index.iife.min.js` | `window.ElementPlusIconsVue` |
| SortableJS 1.15 | `static/cdn/sortablejs/Sortable.min.js` | `window.Sortable` |

## Directory Layout

```
static/
  index.html              # minimal shell — just loads the CDN scripts and <div id="app">
  css/style.css           # CSS Grid IDE layout + design tokens
  js/
    index.js              # createApp entry — mounts App.js
    App.js                # top-level component: header + 4-zone grid + keyboard shortcuts
    components/
      DevicePane.js       # left: canvas screenshot, hierarchy tree mouse events
      StepPane.js         # center: step list (drag-sort) + CLI input
      InspectorPane.js    # right: hierarchy tree tab + element detail + step properties
      ConsolePane.js      # bottom: collapsible run log
    composables/
      useMsg.js           # thin wrapper around ElMessage
      useDevice.js        # device connection, screenshot, capture mode state
      useTask.js          # task CRUD, step parsing/serialization, step prop helpers
      useRunner.js        # WebSocket runner, run-from-step, all-steps, Allure
      useUndo.js          # undo/redo stack
    api.js                # fetch wrappers for every backend endpoint
    config.js             # API_HOST constant
    utils.js              # localStorage helpers, clipboard
```

## Development Workflow

1. Start the dev server:
   ```
   python -m ha4t.editor [-p 8765]
   ```
2. Open `http://localhost:8765` in Chrome.
3. Edit any `.js` or `.css` file, refresh the browser — no rebuild needed.
4. **Vue Devtools**: install the [Vue Devtools](https://devtools.vuejs.org/) Chrome extension and inspect component state live.

## State Sharing

All composables are instantiated in `App.js` setup and shared via `provide/inject`:

```js
provide('device', useDevice())   // useDevice composable instance
provide('task',   useTask())
provide('runner', useRunner(task, device))
provide('undo',   useUndo())
provide('msg',    useMsg())
```

Child components call `inject('task')` etc. — no Vuex/Pinia needed.

## Adding a New API Endpoint

1. Add route to `ha4t/editor/routers/api.py` — specific routes must come **before** the `/{filename:path}` wildcards.
2. Add a `fetch` wrapper in `static/js/api.js`.
3. Import and call from the appropriate composable or component.

## Dark Theme

Controlled entirely by `<html class="dark">` (set in `index.html`) plus:
- `static/cdn/element-plus/dark.css` (Element Plus CSS variables for dark mode)
- `:root` custom properties in `style.css` (`--bg-0`, `--fg`, `--bd`, `--accent`, …)

To add custom dark overrides for a specific component, add to `style.css`:
```css
html.dark .el-some-component { background: var(--bg-1) !important; }
```
