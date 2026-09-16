import importlib.util
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock,patch


ROOT = Path(__file__).resolve().parents[2]


# 直接加载配置与门面源码，隔离应用注册、线程与真实配置
def load_module(name,path):
    spec = importlib.util.spec_from_file_location(name,path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


config = types.ModuleType('config')
config.ROOT_DIRECTORY = ROOT
config.MCP_CONFIG_PATH = ROOT/'unused-mcp.json'
with patch.dict(sys.modules,{'config':config}):
    cwd_config = load_module('cwd_config',ROOT/'mcp_client/mcp_config.py')


class CwdTests(unittest.TestCase):
    def build(self,**fields):
        return cwd_config.build_params('sample',{'command':'server',**fields})

    def test_invalid_types(self):
        for value in (0,0.0,False,[],{},123,True,['dir'],{'path':'dir'}):
            with self.subTest(value=value):
                with self.assertRaisesRegex(cwd_config.McpConfigError,'sample.*cwd'):
                    self.build(cwd=value)

    def test_defaults(self):
        for fields in ({},{'cwd':None},{'cwd':''}):
            with self.subTest(fields=fields):
                self.assertEqual(self.build(**fields).cwd,str(ROOT))

    def test_paths_and_expansion(self):
        with patch.dict(os.environ,{'CWD_TEST_PATH':'workspace'}):
            for value in ('workspace','./workspace','${CWD_TEST_PATH}'):
                with self.subTest(value=value):
                    self.assertEqual(self.build(cwd=value).cwd,str(ROOT/'workspace'))
        absolute = str(ROOT/'external')
        with patch.dict(os.environ,{'CWD_TEST_PATH':absolute}):
            self.assertEqual(self.build(cwd='${CWD_TEST_PATH}').cwd,absolute)
        self.assertEqual(self.build(cwd=absolute).cwd,absolute)

    def test_missing_or_empty_variable(self):
        for env in ({},{'CWD_TEST_PATH':''}):
            with self.subTest(env=env),patch.dict(os.environ,env,clear=True):
                with self.assertRaises(cwd_config.McpConfigError):
                    self.build(cwd='${CWD_TEST_PATH}')

    def test_other_stdio_fields(self):
        with patch.dict(os.environ,{'CWD_TEST_PATH':'value'}):
            params = self.build(command='${CWD_TEST_PATH}',args=['${CWD_TEST_PATH}'],env={'KEY':'${CWD_TEST_PATH}'})
        self.assertEqual((params.command,params.args,params.env),('value',['value'],{'KEY':'value'}))

    def test_http_ignores_cwd(self):
        from datetime import timedelta
        for transport in ('http','streamable-http','streamable_http',None):
            with self.subTest(transport=transport):
                params = cwd_config.build_params('http',{'type':transport,'url':'https://example.com/mcp','cwd':False,'timeout':12,'sse_read_timeout':45})
                self.assertEqual(params.url,'https://example.com/mcp')
                self.assertEqual(params.timeout,timedelta(seconds=12))
                self.assertEqual(params.sse_read_timeout,timedelta(seconds=45))

    def test_prewarm_skips_invalid_and_connects_next(self):
        package = types.ModuleType('cwd_probe')
        package.__path__ = []
        supervisor = types.ModuleType('cwd_probe.mcp_supervisor')
        supervisor.McpSupervisorError = RuntimeError
        connection = Mock()
        connection.connect.return_value = []
        supervisor.get_supervisor = Mock(return_value=connection)
        bridge = types.ModuleType('cwd_probe.mcp_bridge')
        bridge.register_server_tools = Mock(return_value=[])
        bridge.unregister_server_tools = Mock()
        bridge.refresh_agent_tools = Mock()
        modules = {'cwd_probe':package,'cwd_probe.mcp_config':cwd_config,'cwd_probe.mcp_supervisor':supervisor,'cwd_probe.mcp_bridge':bridge}
        with patch.dict(sys.modules,modules):
            core = load_module('cwd_probe.mcp_core',ROOT/'mcp_client/mcp_core.py')
        entries = {'bad':{'command':'server','cwd':False},'good':{'command':'server'}}
        with patch.object(core,'read_config',return_value=entries):
            manager = core.McpManager()
            manager._prewarm_run()
        self.assertIn('cwd',manager._errors['bad'])
        self.assertNotIn('good',manager._errors)
        connection.connect.assert_called_once()
        self.assertEqual(connection.connect.call_args.args[0],'good')


if __name__ == '__main__':
    unittest.main()
