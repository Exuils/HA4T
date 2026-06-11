const { createApp } = Vue;
import App from './App.js';

const app = createApp(App);

// Register all Element Plus components
app.use(window.ElementPlus);

// Register all icons as global components: <el-icon><Plus /></el-icon>
for (const [name, comp] of Object.entries(window.ElementPlusIconsVue)) {
  app.component(name, comp);
}

app.mount('#app');
