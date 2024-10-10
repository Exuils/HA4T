#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName :jsCode.py
# @Time :2024/8/26 下午9:18
# @Author :CAISHILONG
"""
js代码, 用于获取元素,或其他操作
"""


class Jscript:
    def __init__(self):
        # 用于存储临时变量的名称
        self.TEMP_VAR_NAME = "tempVar"

    def get_element(self, locator: tuple, var_name=None):
        """获取js代码，用于获取元素,
        :param locator: 元素定位器，格式为(type, value)
        :type locator: tuple
        :param var_name: 临时变量的名称，默认为None,如果需要保存元素，可以传入变量名
        """
        loc_type = locator[0]
        loc_value = locator[1]
        if var_name is None:
            var_name = self.TEMP_VAR_NAME
        else:
            var_name = var_name
        return f"""function findElement(locator) {{
                    var element = null;
                    var type = locator.type;
                    var value = locator.value;
                
                    // 辅助函数，增加了对doc的参数，减少全局查找
                    function locateInDocument(doc, type, value) {{
                        try {{
                            switch (type) {{
                                case 'id':
                                    return doc.getElementById(value);
                                case 'class':
                                    return doc.getElementsByClassName(value)[0];
                                case 'css':
                                    return doc.querySelector(value);
                                case 'xpath':
                                    return evaluateXPath(doc, value);
                                case 'text':
                                    return findElementByInnerText(doc, value);
                                default:
                                    throw new Error('Unsupported locator type: ' + type);
                            }}
                        }} catch (e) {{
                            console.error('查找元素时出错:', e);
                        }}
                        return null;
                    }}
                
                    // 优化XPath查找，避免每次查找都重新编译XPath
                    function evaluateXPath(doc, xpath) {{
                        var iterator = doc.evaluate(xpath, doc, null, XPathResult.ANY_TYPE, null);
                        return iterator.iterateNext();
                    }}
                
                    // 首先在当前文档中查找元素
                    element = locateInDocument(document, type, value);
                
                    // 如果当前文档中未找到元素，再遍历所有iframe查找
                    if (!element) {{
                        var iframes = document.getElementsByTagName("iframe");
                        for (var i = 0; i < iframes.length; i++) {{
                            var iframeDocument = iframes[i].contentWindow.document;
                            element = locateInDocument(iframeDocument, type, value);
                            if (element) break;
                        }}
                    }}
                
                    return element;
                }}
                
                // 辅助函数：根据文本内容在指定文档中查找元素
                function findElementByInnerText(doc, text) {{
                    function recursiveSearch(node) {{
                        for (var i = 0; i < node.childNodes.length; i++) {{
                            var child = node.childNodes[i];
                            if (child.nodeType === Node.TEXT_NODE && child.nodeValue.trim() === text) {{
                                return child.parentNode;
                            }}
                            if (child.childNodes) {{
                                var foundElement = recursiveSearch(child);
                                if (foundElement) return foundElement;
                            }}
                        }}
                        return null;
                    }}
                    var element = recursiveSearch(doc);
                    return element; // 返回找到的元素，如果没有找到返回null
                }}
                // 调用findElement函数并返回结果
                var locator = {{
                    type: '{loc_type}', // 定位类型
                    value: '{loc_value}' // 定位值
                }};
                var {var_name} = findElement(locator);"""

    def element_exists(self, locator: tuple, var_name: str = None):
        """js脚本，用于判断元素是否存在
        locator: 元素定位器
        var_name: 元素变量名，默认为None，此时使用临时变量名，如果指定了变量名，则使用指定的变量名"""
        if var_name is None:
            var_name = self.TEMP_VAR_NAME
        else:
            var_name = var_name
        return self.get_element(locator=locator, var_name=var_name) + f"{var_name} !== null"

    @staticmethod
    def add_click(element_var_name: str):
        """js脚本，用于模拟点击事件
        element_var_name: 元素变量名
        返回：js脚本"""
        return f"{element_var_name}" + (".dispatchEvent(new MouseEvent('click', {'view': window,'bubbles': true,"
                                        "'cancelable':"
                                        "true}))")

