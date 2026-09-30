import copy
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock,patch

from textual.app import App
from textual.containers import Vertical
from textual.widgets import Static


ROOT = Path(__file__).resolve().parent.parent


# 只加载被测源码，隔离全局注册、Loop 和真实数据
def load_module(name,path):
    spec = importlib.util.spec_from_file_location(name,path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


extra = load_module('fallback_extra',ROOT/'tui/tui_widget/tui_widgets/AssistantToolCall/widget_extraInfo.py')
registry = load_module('fallback_registry',ROOT/'tui/tui_widget/tui_widgets_core.py')


def load_ui_modules():
    modules = {}
    for name in ('fallback_ui','fallback_ui.tui_channel','fallback_ui.tui_widget',
                 'fallback_ui.tui_widget.tui_widgets','fallback_ui.tui_widget.tui_widgets.AssistantToolCall'):
        module = types.ModuleType(name)
        module.__path__ = []
        modules[name] = module
    modules['fallback_ui.tui_widget'].tuiwidgets = registry.tuiwidgets
    modules['fallback_ui.tui_widget.tui_widgets'].widget_register = registry.widget_register
    modules['fallback_ui.tui_widget.tui_widgets.AssistantToolCall.widget_extraInfo'] = extra
    with patch.dict(sys.modules,modules):
        channel = load_module('fallback_ui.tui_channel.core',ROOT/'tui/tui_channel/tui_channel_core.py')
        tool = load_module('fallback_ui.tui_widget.tui_widgets.AssistantToolCall.widget_core',
                           ROOT/'tui/tui_widget/tui_widgets/AssistantToolCall/widget_core.py')
    return channel,tool


channel_module,tool_module = load_ui_modules()
BAD_TYPES = ('Unknown','default',None,'',False,1,[],{})


def info(widget_id,widget_type='Static',content='first'):
    return {'id':widget_id,'type':widget_type,'content':content}


class ExtraInfoTests(unittest.TestCase):
    def test_top_level_fallback_and_input_preservation(self):
        for fields in ({},*({'type':value} for value in BAD_TYPES)):
            with self.subTest(fields=fields):
                owner = types.SimpleNamespace(extra_info_widgets={},extra_body=Mock())
                handler = extra.ExtraInfoHandler()
                content = {'id':'probe','content':'first',**fields}
                original = copy.deepcopy(content)
                handler.extra_info_handler(owner,content)
                cached = owner.extra_info_widgets['probe']
                self.assertIsInstance(cached['widget'],Static)
                self.assertEqual(cached['type'],'default')
                self.assertIn(f"Info_Type:{content.get('type')}",cached['widget'].content)
                self.assertEqual(content,original)
                updated = {**content,'content':'second'}
                handler.extra_info_handler(owner,updated)
                self.assertIs(owner.extra_info_widgets['probe']['widget'],cached['widget'])
                self.assertIn('Info_Content:second',cached['widget'].content)

    def test_unknown_types_share_default_widget(self):
        owner = types.SimpleNamespace(extra_info_widgets={},extra_body=Mock())
        handler = extra.ExtraInfoHandler()
        handler.extra_info_handler(owner,info('probe','Unknown'))
        widget = owner.extra_info_widgets['probe']['widget']
        handler.extra_info_handler(owner,info('probe','Other','second'))
        self.assertIs(owner.extra_info_widgets['probe']['widget'],widget)
        self.assertIn('Info_Type:Other',widget.content)

    def test_known_static_update(self):
        owner = types.SimpleNamespace(extra_info_widgets={},extra_body=Mock())
        handler = extra.ExtraInfoHandler()
        handler.extra_info_handler(owner,info('probe'))
        widget = owner.extra_info_widgets['probe']['widget']
        handler.extra_info_handler(owner,info('probe',content='second'))
        self.assertEqual(widget.content,'second')
        self.assertEqual(owner.extra_info_widgets['probe']['type'],'Static')


class HostApp(App):
    def __init__(self,widget):
        super().__init__()
        self.host_widget = widget

    def compose(self):
        yield self.host_widget


class MountedFallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_nested_build_and_update(self):
        for container_type in ('Horizontal','Vertical'):
            with self.subTest(container_type=container_type):
                body = Vertical()
                owner = types.SimpleNamespace(extra_info_widgets={},extra_body=body)
                handler = extra.ExtraInfoHandler()
                children = [info(f'child_{index}',value) for index,value in enumerate(BAD_TYPES)]
                children.extend(({'id':'missing','content':'first'},info('known')))
                content = info('parent',container_type,children)
                original = copy.deepcopy(content)
                async with HostApp(body).run_test() as pilot:
                    handler.extra_info_handler(owner,content)
                    await pilot.pause()
                    parent = owner.extra_info_widgets['parent']['widget']
                    self.assertEqual(content,original)
                    for child in children:
                        cached = owner.extra_info_widgets[child['id']]
                        self.assertEqual(cached['type'],'Static' if child['id'] == 'known' else 'default')
                        self.assertIs(parent.get_child_by_id(child['id']),cached['widget'])
                    updated = info('parent',container_type,[{**child,'content':'second'} for child in children])
                    handler.extra_info_handler(owner,updated)
                    await pilot.pause()
                    for child in children:
                        widget = parent.get_child_by_id(child['id'])
                        self.assertIn('second',widget.content)
                        self.assertIs(owner.extra_info_widgets[child['id']]['widget'],widget)

    async def test_top_level_type_transitions(self):
        body = Vertical()
        owner = types.SimpleNamespace(extra_info_widgets={},extra_body=body)
        handler = extra.ExtraInfoHandler()
        async with HostApp(body).run_test() as pilot:
            previous = None
            for widget_type,expected in (('Static','Static'),('Unknown','default'),('Static','Static')):
                handler.extra_info_handler(owner,info('probe',widget_type,widget_type))
                await pilot.pause()
                cached = owner.extra_info_widgets['probe']
                self.assertEqual(cached['type'],expected)
                self.assertIs(body.get_child_by_id('probe'),cached['widget'])
                self.assertIsNot(cached['widget'],previous)
                self.assertEqual(len(body.children),1)
                if previous is not None:
                    self.assertIsNone(previous.parent)
                previous = cached['widget']
                self.assertIn(widget_type,previous.content)

    async def test_recursive_nested_update(self):
        body = Vertical()
        owner = types.SimpleNamespace(extra_info_widgets={},extra_body=body)
        handler = extra.ExtraInfoHandler()
        content = info('outer','Horizontal',[info('inner','Vertical',[info('leaf','Unknown')])])
        async with HostApp(body).run_test() as pilot:
            handler.extra_info_handler(owner,content)
            await pilot.pause()
            leaf = owner.extra_info_widgets['leaf']['widget']
            updated = info('outer','Horizontal',[info('inner','Vertical',[info('leaf','Other','second')])])
            handler.extra_info_handler(owner,updated)
            await pilot.pause()
            self.assertIs(owner.extra_info_widgets['leaf']['widget'],leaf)
            self.assertEqual(owner.extra_info_widgets['leaf']['type'],'default')
            self.assertIn('Info_Type:Other',leaf.content)
            self.assertIn('Info_Content:second',leaf.content)

    async def test_first_tool_mount_with_unknown_extra_info(self):
        widget = tool_module.AssistantToolCall({
            'tool_call_name':'probe','tool_call_state':{'tool_call_state':'success'},
            'tool_call_extra_info':[info('probe','Unknown')],
        })
        app = HostApp(widget)
        async with app.run_test() as pilot:
            await pilot.pause()
            fallback = widget.extra_info_widgets['probe']['widget']
            self.assertTrue(widget.extra_body.display)
            self.assertTrue(fallback.is_mounted)
            self.assertIn('Info_Type:Unknown',fallback.content)
            self.assertEqual(str(fallback.styles.height),'auto')
            self.assertGreater(fallback.size.height,0)
            self.assertIsNone(app._exception)

    async def test_rapid_top_level_type_transitions(self):
        body = Vertical()
        owner = types.SimpleNamespace(extra_info_widgets={},extra_body=body)
        handler = extra.ExtraInfoHandler()
        async with HostApp(body).run_test() as pilot:
            handler.extra_info_handler(owner,info('probe'))
            await pilot.pause()
            handler.extra_info_handler(owner,info('probe','Unknown'))
            handler.extra_info_handler(owner,info('probe','Static','final'))
            await pilot.pause()
            cached = owner.extra_info_widgets['probe']
            self.assertIs(body.get_child_by_id('probe'),cached['widget'])
            self.assertEqual(cached['widget'].content,'final')
            self.assertEqual(len(body.children),1)

    async def test_fallback_stream_lifecycle(self):
        for disabled in (False,True):
            with self.subTest(disabled=disabled):
                widgets = registry.TuiWidgets()
                if disabled:
                    widgets.widget_register('Unknown',None,False)(Mock())
                channel = channel_module.TuiChannel(agent_name='probe')
                app = HostApp(channel.body)
                with patch.object(channel_module,'tuiwidgets',widgets):
                    async with app.run_test() as pilot:
                        channel.append_stream('Unknown',{'content':'first'},'Unknown_stream1')
                        await pilot.pause()
                        widget = channel.stream_widgets['Unknown_stream1']
                        self.assertIsInstance(widget,Static)
                        self.assertIsNone(widget.id)
                        self.assertIn('default_css',widget.classes)
                        self.assertEqual(str(widget.styles.height),'auto')
                        self.assertEqual(widget.size.height,1)
                        original = widget.content
                        channel.append_stream('Unknown',{'content':'second'},'Unknown_stream1')
                        self.assertIs(channel.stream_widgets['Unknown_stream1'],widget)
                        self.assertEqual(widget.content,original)
                        channel.end_stream('stream1')
                        self.assertEqual(channel.stream_widgets,{})
                        self.assertTrue(widget.is_mounted)
                        channel.end_stream('stream1')
                        widget.finalize()
                        self.assertIsNone(app._exception)


if __name__ == '__main__':
    unittest.main()
