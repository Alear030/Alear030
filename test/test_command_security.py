import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]

# 只加载安全层，隔离工具注册和真实数据
spec = importlib.util.spec_from_file_location('command_security_under_test', ROOT / 'tool/tools/command/security.py')
security = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {spec.name: security}):
    spec.loader.exec_module(security)


class CommandSecurityTests(unittest.TestCase):
    def assert_blocked(self, command):
        safe, reason, category, warning = security.validate_command(command)
        self.assertFalse(safe, command)
        self.assertTrue(reason, command)
        self.assertEqual(category, 'destructive', command)
        self.assertIsNone(warning, command)

    def assert_allowed(self, command):
        safe, reason, category, warning = security.validate_command(command)
        self.assertTrue(safe, (command, reason))
        self.assertEqual(reason, '')
        self.assertNotEqual(category, 'destructive')
        self.assertIsNone(warning)

    def test_issue_examples(self):
        commands = (
            'Remove-Item -Recurse -Force x', 'Remove-Item x -Recurse',
            'remove-item -r x', 'ri -Rec x', 'rd x -Recurse',
            'rmdir x -Recurse -Force', 'del x -Recurse', 'erase x -r',
            r'Remove-Item -Recurse -Force memory\memory_storage',
        )
        for command in commands:
            with self.subTest(command=command):
                self.assert_blocked(command)

    def test_aliases_prefixes_and_case(self):
        aliases = ('Remove-Item', 'ri', 'rm', 'del', 'erase', 'rd', 'rmdir')
        flags = ('-r', '-re', '-rec', '-recu', '-recur', '-recurs', '-recurse')
        for alias in aliases:
            for flag in flags:
                for command in (f'{alias} {flag} x', f'{alias.upper()} x {flag.upper()} -Force'):
                    with self.subTest(command=command):
                        self.assert_blocked(command)

    def test_switch_values(self):
        for flag in ('-Recurse:$true', '-Rec:$false', '-R:1'):
            with self.subTest(flag=flag):
                self.assert_blocked(f'Remove-Item x {flag}')

    def test_segments_and_whitespace(self):
        for prefix in ('  \t', 'echo ok & ', 'echo ok && ', 'echo ok || ', 'echo ok; ', 'echo ok | '):
            with self.subTest(prefix=prefix):
                self.assert_blocked(prefix + 'Remove-Item "build folder" -Recurse')
        self.assert_blocked('Remove-Item x -Recurse > result.txt')

    def test_interpreter_payloads(self):
        for interpreter in ('powershell', 'pwsh', 'PowerShell.exe', 'PWSH.EXE'):
            for flag in ('-Command', '-c'):
                with self.subTest(interpreter=interpreter, flag=flag):
                    self.assert_blocked(f'{interpreter} {flag} "Remove-Item x -Recurse"')
                    self.assert_blocked(f'{interpreter} {flag} "echo ok; ri x -Rec"')
                    self.assert_blocked(f'{interpreter} {flag} Remove-Item x -Recurse')
                    self.assert_blocked(f'{interpreter} {flag} "Remove-Item x" -Recurse')
                    self.assert_blocked(f'{interpreter} {flag}="Remove-Item x" -Recurse')
                    self.assert_allowed(f'{interpreter} {flag} "Remove-Item foo.txt"')
                    self.assert_allowed(f'{interpreter} {flag} Remove-Item foo.txt')

    def test_non_recursive_and_literal_arguments(self):
        commands = (
            'Remove-Item foo.txt', 'Remove-Item "folder name/foo.txt"',
            'ri foo.txt', 'rm foo.txt', 'del foo.txt', 'erase foo.txt',
            'rd empty_dir', 'rmdir empty_dir',
            'Remove-Item ./-Recurse.txt', 'Remove-Item "-Recurse"',
            "Remove-Item '-Recurse'", 'Remove-Item "folder -Recurse/file.txt"',
            'Remove-Item -LiteralPath "-Recurse"',
            'Remove-Item -RecurseSomething foo.txt',
            'echo "Remove-Item -Recurse x"', 'echo Remove-Item -Recurse x',
            'echo "Remove-Item; -Recurse"',
            'Remove-Item foo.txt; echo -Recurse',
        )
        for command in commands:
            with self.subTest(command=command):
                self.assert_allowed(command)

    def test_existing_deletion_guards(self):
        for command in ('rm -rf x', 'rm -f foo.txt', 'git rm -rf x', 'del /s x', 'rd /s x'):
            with self.subTest(command=command):
                self.assert_blocked(command)
        self.assert_allowed('git rm --cached foo.txt')


if __name__ == '__main__':
    unittest.main()
