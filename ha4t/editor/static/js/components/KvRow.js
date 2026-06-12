// 单行 key/value 编辑器。
//
// 为什么单独抽组件：父级用 ref({}) 存全量 vars，把每行 inline 用 v-for 渲染时，
// el-input 受控的 `:model-value` prop 每次输入都被 patch 回去 —— 中文 IME 卡死、key
// 输入框甚至完全打不进字符（因为父侧 `k` 在 rename 成功前永远不变）。
//
// 子组件让每行拥有独立的 key 草稿 state，与父级解耦：
//   - value：直接 v-model 进父级对象的字段（reactive proxy 自带响应）。
//   - key：本地 ref 持有草稿，@change 时再请求父级 rename。

const { ref, watch } = Vue;

const TEMPLATE = `
<div class="kv-row">
  <el-input
    v-model="keyDraft"
    @change="commitKey"
    @keyup.enter="$event.target.blur()"
    size="small" class="kv-key"
  ></el-input>
  <el-input
    :model-value="modelValue"
    @update:modelValue="$emit('update:modelValue', $event)"
    @blur="$emit('value-blur')"
    size="small" class="kv-val"
  ></el-input>
  <el-button text size="small" @click="$emit('remove')">
    <el-icon><Close /></el-icon>
  </el-button>
</div>
`;

export default {
  name: 'KvRow',
  template: TEMPLATE,
  props: {
    keyName:    { type: String, required: true },
    modelValue: { type: String, default: '' },
  },
  emits: ['update:modelValue', 'rename', 'remove', 'value-blur'],

  setup(props, { emit }) {
    const keyDraft = ref(props.keyName);

    // 父级改了 key（rename 成功 / 重新加载用例 / 删除/添加行）后同步草稿。
    watch(() => props.keyName, (v) => { keyDraft.value = v; });

    function commitKey() {
      const newK = (keyDraft.value || '').trim();
      if (!newK || newK === props.keyName) {
        keyDraft.value = props.keyName;  // 空名 / 没变 → 回滚显示
        return;
      }
      emit('rename', props.keyName, newK);
      // rename 成败由父级裁决；不论结果，下一帧 watch(keyName) 会把草稿同步到真实 key
      // （失败时 keyName 没变 → 草稿回到原值；成功时草稿跟上新名）。
    }

    return { keyDraft, commitKey };
  },
};
