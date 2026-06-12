# -*- coding: utf-8 -*-
"""XPathLite 生成器测试：覆盖五层候选 + 真实 hierarchy 唯一性回归。"""

import unittest
import uuid

from ha4t.editor.parser.xpath_lite import XPathLiteGenerator, _xpath_escape


def _node(_type='View', children=None, **attrs):
    """构造一个 _id 自动填、parentId 由 _link 回填的 mock 节点。"""
    n = {'_id': str(uuid.uuid4()), '_parentId': '', '_type': _type, 'children': children or []}
    n.update(attrs)
    return n


def _link(tree, parent_id=''):
    """递归回填 _parentId（构造嵌套树时方便点）。"""
    tree['_parentId'] = parent_id
    for c in tree.get('children', []):
        _link(c, tree['_id'])
    return tree


def _all_matching(tree, predicate):
    """walk 整树返回满足 predicate(node) 的节点，用于唯一性断言。"""
    out = []
    def walk(n):
        if predicate(n):
            out.append(n)
        for c in n.get('children', []):
            walk(c)
    walk(tree)
    return out


class TestXPathLiteEscape(unittest.TestCase):
    def test_no_quote(self):
        self.assertEqual(_xpath_escape('login'), '"login"')

    def test_double_quote(self):
        self.assertEqual(_xpath_escape('say "hi"'), '\'say "hi"\'')

    def test_single_quote(self):
        self.assertEqual(_xpath_escape("it's"), '"it\'s"')

    def test_both_quotes(self):
        # 需 concat() 拼接
        out = _xpath_escape('mix "a" and \'b\'')
        self.assertIn('concat(', out)
        self.assertIn('\'"\'', out)


class TestXPathLiteAndroid(unittest.TestCase):
    """Android 平台的五层候选枚举。"""

    def _gen(self, tree):
        return XPathLiteGenerator('android', tree)

    def test_tier1_unique_resourceId(self):
        """resourceId 全局唯一 → 最短：//*[@resource-id="X"]。"""
        target = _node(resourceId='com.x:id/login', text='登录')
        tree = _link(_node('Root', children=[
            _node('Layout', children=[target]),
        ]))
        xp = self._gen(tree).get_xpathLite(target['_id'])
        self.assertEqual(xp, '//*[@resource-id="com.x:id/login"]')

    def test_tier1_text_when_no_resourceId(self):
        target = _node(text='独一无二的文本')
        tree = _link(_node('Root', children=[_node('Layout', children=[target])]))
        xp = self._gen(tree).get_xpathLite(target['_id'])
        self.assertEqual(xp, '//*[@text="独一无二的文本"]')

    def test_tier1_description_for_flutter(self):
        """Flutter 应用只有 content-desc — 直接走 description。"""
        target = _node(description='标准打印机')
        tree = _link(_node('Root', children=[_node('Layout', children=[target])]))
        xp = self._gen(tree).get_xpathLite(target['_id'])
        self.assertEqual(xp, '//*[@content-desc="标准打印机"]')

    def test_tier2_type_disambiguates(self):
        """两个节点共享 text='确定' 但 type 不同 → //Class[@text]。"""
        t = _node('Button', text='确定')
        tree = _link(_node('Root', children=[
            _node('Layout', children=[
                _node('TextView', text='确定'),  # 同 text 不同 type
                t,
            ]),
        ]))
        xp = self._gen(tree).get_xpathLite(t['_id'])
        self.assertEqual(xp, '//Button[@text="确定"]')

    def test_tier3_two_attrs_unique(self):
        """两个 Button text='确定'，但 resourceId 不同 → 双属性组合。"""
        t = _node('Button', text='确定', resourceId='com.x:id/confirm_dialog')
        tree = _link(_node('Root', children=[
            _node('Button', text='确定', resourceId='com.x:id/confirm_other'),
            t,
        ]))
        xp = self._gen(tree).get_xpathLite(t['_id'])
        # 选最短唯一候选：resourceId 已经全局唯一了，应该走 Tier 1
        self.assertEqual(xp, '//*[@resource-id="com.x:id/confirm_dialog"]')

    def test_tier3_actual_combo(self):
        """没有任何单属性唯一，但 (resourceId+text) 组合唯一 → Tier 3。"""
        t = _node('Button', text='保存', resourceId='com.x:id/btn')
        sibling = _node('Button', text='取消', resourceId='com.x:id/btn')  # 同 resId 不同 text
        another = _node('Button', text='保存', resourceId='com.x:id/other')  # 同 text 不同 resId
        tree = _link(_node('Root', children=[t, sibling, another]))
        xp = self._gen(tree).get_xpathLite(t['_id'])
        self.assertIn('@resource-id="com.x:id/btn"', xp)
        self.assertIn('@text="保存"', xp)
        self.assertIn(' and ', xp)

    def test_tier4_anchor_via_unique_ancestor(self):
        """目标无任何唯一属性 → 锚定唯一祖先，用 // 后代轴。"""
        t = _node('View', text='item')  # 多个同名 item
        sibling = _node('View', text='item')
        list_a = _node('RecyclerView', resourceId='com.x:id/list_a', children=[t])
        list_b = _node('RecyclerView', resourceId='com.x:id/list_b', children=[sibling])
        tree = _link(_node('Root', children=[list_a, list_b]))
        xp = self._gen(tree).get_xpathLite(t['_id'])
        # 应该锚到 list_a，用 // 跟到 target — 中间无论多少 wrapper 都不影响
        self.assertTrue(xp.startswith('//*[@resource-id="com.x:id/list_a"]'))
        self.assertIn('//', xp[len('//*[@resource-id="com.x:id/list_a"]'):])
        self.assertIn('@text="item"', xp)

    def test_tier4_no_attr_target_uses_child_path_not_descendant_idx(self):
        """回归：目标节点完全无属性、anchor 下有多个同类兄弟 View[1] 风险情境。

        旧实现给 `//*[@resource-id="android:id/content"]//View[1]` —— `//View[1]` 在 `//` 后
        是 position 过滤，跨分支匹配每个父级里的第 1 个 View，导致用户"点的"和"高亮的"不一致。
        新实现应改走 anchor → target 的 `/` 子轴绝对路径，每段带 sibling 索引。
        """
        target = _node('android.view.View')                 # 完全无属性
        sibling_a = _node('android.view.View')
        sibling_b = _node('android.view.View')
        content = _node('FrameLayout', resourceId='android:id/content',
                        children=[sibling_a, target, sibling_b])
        tree = _link(_node('Root', children=[content]))
        xp = self._gen(tree).get_xpathLite(target['_id'])

        # 锚到 content
        self.assertTrue(xp.startswith('//*[@resource-id="android:id/content"]'), xp)
        tail = xp[len('//*[@resource-id="android:id/content"]'):]
        # 关键：tail 必须是 `/` 子轴 + 带 sibling 索引；绝不能是 `//Type[idx]`
        self.assertFalse(tail.startswith('//'), f'tail 走了后代轴会歧义: {xp}')
        self.assertTrue(tail.startswith('/android.view.View['), xp)
        # target 在 content.children 中位置是 1（0-based sibling_a） → sameType index = 1（0-based） → xpath [2]
        self.assertIn('/android.view.View[2]', xp, xp)

    def test_tier5_fallback_root_path(self):
        """完全无属性 + 无唯一祖先 → / 子轴全路径兜底，每段强制带 sibling 索引以避免 `//Type[idx]` 歧义。"""
        deep = _node('View')
        tree = _link(_node('Root', children=[
            _node('Layout', children=[
                _node('Layout', children=[deep]),
            ]),
        ]))
        xp = self._gen(tree).get_xpathLite(deep['_id'])
        self.assertTrue(xp.startswith('//'))
        # 末段是 View[1]（同类兄弟唯一也补 [1]，保证 XPath 引擎一致定位）
        self.assertTrue(xp.endswith('/View[1]'), xp)
        # 两层 Layout 嵌套，segment 顺序 Layout[1]/Layout[1] 或 Layout[i]/Layout[j]
        self.assertEqual(xp.count('/Layout['), 2, xp)

    def test_returns_empty_for_unknown_id(self):
        tree = _link(_node('Root', children=[_node('A')]))
        self.assertEqual(self._gen(tree).get_xpathLite('not-existing'), '')

    def test_xpath_escapes_quote_in_text(self):
        """text 里含双引号 → xpath 应正确转义不会语法错误。"""
        t = _node(text='say "hi"')
        tree = _link(_node('Root', children=[t]))
        xp = self._gen(tree).get_xpathLite(t['_id'])
        self.assertEqual(xp, "//*[@text='say \"hi\"']")


class TestXPathLiteShortAndStable(unittest.TestCase):
    """关键性质：所有生成结果都比旧实现"更短或同样短"，且 // 锚定路径稳定。"""

    def test_short_when_unique(self):
        """resourceId 唯一时，生成长度等于 //*[@resource-id="X"]，不会拼父链。"""
        t = _node(resourceId='com.x:id/btn', text='按')
        tree = _link(_node('Root', children=[
            _node('Wrapper1', children=[
                _node('Wrapper2', children=[
                    _node('Wrapper3', children=[t]),
                ]),
            ]),
        ]))
        xp = XPathLiteGenerator('android', tree).get_xpathLite(t['_id'])
        # 不应包含任何 wrapper class 名
        self.assertNotIn('Wrapper1', xp)
        self.assertNotIn('Wrapper2', xp)
        self.assertNotIn('Wrapper3', xp)

    def test_descendant_axis_used_for_anchor(self):
        """祖先锚定时用 // 后代轴而不是 / 子轴 — 反脆弱。"""
        t = _node('View', text='x')
        another = _node('View', text='x')
        # 故意加 3 层 wrapper 在 target 上
        target_branch = _node('A', resourceId='com.x:id/anchor', children=[
            _node('W1', children=[_node('W2', children=[_node('W3', children=[t])])]),
        ])
        tree = _link(_node('Root', children=[target_branch, _node('Other', children=[another])]))
        xp = XPathLiteGenerator('android', tree).get_xpathLite(t['_id'])
        # 锚 + 后代轴
        self.assertTrue(xp.startswith('//*[@resource-id="com.x:id/anchor"]'))
        # 不能出现 wrapper 类名 — 用 // 拼到目标
        self.assertNotIn('W1', xp)
        self.assertNotIn('W2', xp)
        self.assertNotIn('W3', xp)


class TestXPathLiteIos(unittest.TestCase):
    def test_ios_priority(self):
        """iOS 优先 id / name / label，而非 resourceId / text。"""
        t = _node(_type='XCUIElementTypeButton', id='loginBtn', name='Sign In')
        tree = _link(_node('XCUIElementTypeApplication', children=[t]))
        xp = XPathLiteGenerator('ios', tree).get_xpathLite(t['_id'])
        self.assertEqual(xp, '//*[@id="loginBtn"]')


if __name__ == '__main__':
    unittest.main()
