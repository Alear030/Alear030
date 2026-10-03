import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


HOOKS = Path(__file__).resolve().parents[1] / '.claude/hooks'


def run_hook(name, payload, env_project=None):
    # 按 Claude Code 的契约端到端跑：stdin 进 JSON，stdout 出决定，无输出即放行；返回 (决定, 理由, stderr, 退出码)
    env = {k: v for k, v in os.environ.items() if k != 'CLAUDE_PROJECT_DIR'}
    if env_project:
        env['CLAUDE_PROJECT_DIR'] = str(env_project)
    raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode('utf-8')
    proc = subprocess.run([sys.executable, str(HOOKS / name)], input=raw, capture_output=True, timeout=30, env=env)
    out = proc.stdout.decode('utf-8').strip()
    spec = json.loads(out)['hookSpecificOutput'] if out else {}
    return spec.get('permissionDecision'), spec.get('permissionDecisionReason', ''), proc.stderr, proc.returncode


def make_repo(root):
    (root / '.git').mkdir(parents=True)
    return root


def make_worktree(main, wt, relative=False):
    gitdir = main / '.git/worktrees' / wt.name
    gitdir.mkdir(parents=True)
    wt.mkdir(parents=True)
    target = os.path.relpath(gitdir, wt) if relative else gitdir.as_posix()
    (wt / '.git').write_text(f'gitdir: {target}\n', encoding='utf-8')
    return wt


class WorktreeGuardTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.main = make_repo(self.base / 'repo')
        self.wt = make_worktree(self.main, self.main / '.claude/worktrees/dev')

    def decide(self, target, cwd=None, key='file_path'):
        return run_hook('worktree_guard.py', {'tool_name': 'Edit', 'tool_input': {key: str(target)},
                                              'cwd': str(cwd or self.wt)})

    def test_blocks_other_checkouts_of_same_repo(self):
        make_worktree(self.main, self.main / '.claude/worktrees/other')
        make_worktree(self.main, self.base / 'external')
        for target, key in [(self.main / 'config.py', 'file_path'),
                            (self.main / 'tool/x.ipynb', 'notebook_path'),
                            (self.main / '.claude/worktrees/other/a.py', 'file_path'),
                            (self.base / 'external/a.py', 'file_path'),
                            (self.main / '.git/config', 'file_path'),
                            (self.wt / '../../../config.py', 'file_path')]:
            with self.subTest(target=target):
                self.assertEqual(self.decide(target, key=key)[0], 'deny')

    def test_suggested_path_keeps_case(self):
        decision, reason, _, _ = self.decide(self.main / 'docs/NEW_Doc.md')
        self.assertEqual(decision, 'deny')
        self.assertIn((self.wt / 'docs/NEW_Doc.md').as_posix().split('/repo/')[-1], reason)

    def test_allows_own_worktree_and_unrelated_paths(self):
        self.assertIsNone(self.decide(self.wt / 'config.py')[0])
        self.assertIsNone(self.decide('config.py')[0])  # 相对路径按 cwd 解析
        self.assertIsNone(self.decide(self.base / 'scratch.txt')[0])
        unrelated = make_repo(self.base / 'another_repo')
        self.assertIsNone(self.decide(unrelated / 'a.py')[0])

    def test_inactive_in_main_checkout(self):
        self.assertIsNone(self.decide(self.main / 'config.py', cwd=self.main)[0])

    def test_relative_gitdir(self):
        wt = make_worktree(self.main, self.main / '.claude/worktrees/rel', relative=True)
        decision, reason, _, _ = self.decide(self.main / 'config.py', cwd=wt)
        self.assertEqual(decision, 'deny')
        self.assertIn('worktrees/rel/config.py', reason)
        self.assertIsNone(self.decide(wt / 'config.py', cwd=wt)[0])

    def test_fails_open(self):
        decision, _, stderr, code = run_hook('worktree_guard.py', b'not json')
        self.assertIsNone(decision)
        self.assertEqual(code, 0)
        self.assertTrue(stderr)


class WorktreeMainOnlyIgnoredTest(unittest.TestCase):
    # 真仓库 + git worktree add：例外判据要靠 git check-ignore
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.main = Path(tmp.name) / 'repo'
        self.main.mkdir()
        git = lambda *a: subprocess.run(['git', '-C', str(self.main), *a], check=True, capture_output=True)
        git('init', '-q')
        (self.main / '.gitignore').write_text('.local/\n.env\nlog/log_data/\n', encoding='utf-8')
        (self.main / 'config.py').write_text('', encoding='utf-8')
        git('add', '.')
        git('-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-q', '-m', 'init')
        self.wt = self.main / '.claude/worktrees/dev'
        git('worktree', 'add', '-q', str(self.wt))
        self.addCleanup(lambda: subprocess.run(['git', '-C', str(self.main), 'worktree', 'remove', '--force', str(self.wt)],
                                               capture_output=True))

    def decide(self, target):
        return run_hook('worktree_guard.py', {'tool_name': 'Write', 'tool_input': {'file_path': str(target)},
                                              'cwd': str(self.wt)})[0]

    def test_allows_main_only_ignored(self):
        self.assertIsNone(self.decide(self.main / '.local/note.html'))

    def test_still_blocks(self):
        (self.main / '.env').write_text('', encoding='utf-8')
        (self.wt / '.env').write_text('', encoding='utf-8')
        self.assertEqual(self.decide(self.main / '.env'), 'deny')  # 两边都有：多半是写错了 checkout
        self.assertEqual(self.decide(self.main / 'log/log_data/a.log'), 'deny')  # 运行数据目录不在例外内
        self.assertEqual(self.decide(self.main / 'config.py'), 'deny')  # 被跟踪的文件


class ReadonlyGuardTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = Path(tmp.name) / 'repo'
        self.repo.mkdir()
        subprocess.run(['git', 'init', '-q', str(self.repo)], check=True)
        self.outside = (Path(tmp.name) / 'scratch').as_posix()

    def decide(self, cmd, tool='Bash'):
        return run_hook('readonly_guard.py', {'tool_name': tool, 'tool_input': {'command': cmd},
                                              'cwd': str(self.repo)})[0]

    def test_blocks(self):
        for cmd in ['git commit -m x', 'git add -A', 'git stash', 'git checkout master', 'git push',
                    'git branch feature', 'git branch -D old', 'git tag v1', 'git config user.name x',
                    'git -C . reset --hard', 'git worktree add ../x',
                    'gh pr comment 179 -b hi', 'gh pr merge 179', 'gh api repos/a/b/issues -f title=x',
                    'gh api -X DELETE repos/a/b/issues/comments/1',
                    'echo x > notes.md', 'rm config.py', 'mv a.py b.py', 'cp /tmp/x.py tool/x.py',
                    'bash -c "git commit -m x"', 'git status && git commit -m x']:
            with self.subTest(cmd=cmd):
                self.assertEqual(self.decide(cmd), 'deny')
        self.assertEqual(self.decide('Set-Content -Path notes.md -Value x', tool='PowerShell'), 'deny')

    def test_allows(self):
        for cmd in ['git status', 'git log --oneline -3', 'git diff origin/master...HEAD',
                    'git show HEAD:config.py', 'git fetch origin', 'git merge-base origin/master HEAD',
                    'git branch', 'git branch -a', 'git branch --contains HEAD', 'git stash list',
                    'git worktree list', 'git config --get user.name', 'git ls-files -- session',
                    'gh pr view 179', 'gh pr diff 179', 'gh api repos/a/b/pulls/179',
                    f'mkdir -p {self.outside} && echo x > {self.outside}/probe.json',
                    f'python tool.py < {self.outside}/probe.json',
                    'git diff | tee', 'python -m unittest test.test_x']:
            with self.subTest(cmd=cmd):
                self.assertIsNone(self.decide(cmd))
        self.assertIsNone(self.decide('git diff | Out-File $env:TEMP\\d.txt', tool='PowerShell'))

    def test_fails_open(self):
        decision, _, stderr, code = run_hook('readonly_guard.py', b'not json')
        self.assertIsNone(decision)
        self.assertEqual(code, 0)
        self.assertTrue(stderr)


class BacktickGuardTest(unittest.TestCase):
    def decide(self, cmd):
        return run_hook('backtick_guard.py', {'tool_name': 'Bash', 'tool_input': {'command': cmd}, 'cwd': os.getcwd()})[0]

    def test_blocks(self):
        for cmd in ['python -c "print(`x`)"',
                    'py -3 -c "s = \'`a`\'"',
                    '"C:/Python/python.exe" -c"`x`"',
                    'git commit -m "fix `foo`"',
                    'cat <<EOF > a.md\nuse `foo`\nEOF',
                    'cat <<-EOF\n\t`x`\n\tEOF',
                    'cat <<EOF\nline\n  EOF\n`x`\nEOF',  # 缩进的 EOF 不是 <<EOF 的结束符
                    'echo $\'it\\\'s\' "`x`"',  # $'...' 里的 \' 不结束串
                    'echo hi;# it\'s\necho "`x`"',  # ;# 开始的是注释
                    'x="$(echo "`y`")"']:  # $(...) 里的双引号串照样要查
            with self.subTest(cmd=cmd):
                self.assertEqual(self.decide(cmd), 'deny')

    def test_allows(self):
        for cmd in ["python -c 'print(`x`)'",
                    "cat <<'EOF' > a.md\nuse `foo`\nEOF",
                    'cat <<"EOF"\n`x`\nEOF',
                    'cat <<\\EOF\n`x`\nEOF',
                    'python -c "print(1)"',
                    'python -c "print(1)" && echo \'a `b`\'',
                    'echo "escaped \\`x\\`"',
                    'cat <<EOF\nplain\nEOF\necho `date`',
                    'echo hi # "`x`"',
                    'git commit -m "$(cat <<\'EOF\'\nuse `foo`\nEOF\n)"',
                    'y="$(echo \'`x`\')"',
                    'gh pr create --body "$(cat <<\'EOF\'\n(a) `b` (c)\nEOF\n)" --title t']:
            with self.subTest(cmd=cmd):
                self.assertIsNone(self.decide(cmd))

    def test_powershell(self):
        def ps(cmd):
            return run_hook('backtick_guard.py', {'tool_name': 'PowerShell', 'tool_input': {'command': cmd},
                                                  'cwd': os.getcwd()})[0]
        for cmd in ['git commit -m "use `name` here"',
                    'python -c "print(1)" "x `vy` z"',
                    '$m = @"\nuse `tag`\n"@']:
            with self.subTest(cmd=cmd):
                self.assertEqual(ps(cmd), 'deny')
        for cmd in ["git commit -m 'use `name` here'",
                    "$m = @'\nuse `tag`\n'@",
                    "Write-Output 'it''s `x`'",
                    'Get-ChildItem `\n  -Recurse',  # 引号外的行尾续行
                    'echo hi # "`x`"',
                    'echo "plain"']:
            with self.subTest(cmd=cmd):
                self.assertIsNone(ps(cmd))

    def test_fails_open(self):
        decision, _, stderr, code = run_hook('backtick_guard.py', b'not json')
        self.assertIsNone(decision)
        self.assertEqual(code, 0)
        self.assertTrue(stderr)


class DataGuardTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        # 真仓库：git 类判据要靠 ls-files 查受保护目录里有没有被跟踪的文件
        self.repo = Path(tmp.name) / 'repo'
        self.repo.mkdir()
        subprocess.run(['git', 'init', '-q', str(self.repo)], check=True)
        self.outside = Path(tmp.name) / 'scratch'
        self.outside.mkdir()

    def decide(self, cmd, tool='Bash', cwd=None, project=None):
        return run_hook('data_guard.py', {'tool_name': tool, 'tool_input': {'command': cmd},
                                          'cwd': str(cwd or self.repo)}, env_project=project)[0]

    def test_asks(self):
        cases = [
            'rm -rf session/session_detail',
            'git status && rm memory/memory_storage/memory_storages/a.json',
            'cd eval/trace/trace_log && rm -rf *',
            'cd session && rm -rf session_detail',
            'rm -rf session',
            'rm -rf memory/memory_config',
            'rm -rf session/session_*',
            'rm -rf ./session/./session_detail',
            'find log/log_data -name "*.log" -delete',
            'find log/log_data -exec rm {} \\;',
            'cp memory_type.example.json memory/memory_config/memory_configs/memory_type.json',
            'cp a.json memory/memory_config/memory_configs/x.json 2>/dev/null',
            'cp -t memory/memory_config/memory_configs a.json',
            'echo {} > memory/memory_config/memory_configs/user_info.json',
            'git clean -fdx',
            'git -C . clean -fdX',
            'git stash push --all',
            'sleep 1 & rm -rf log/log_data',
            'sudo rm -rf log/log_data',
            'env X=1 rm -rf log/log_data',
            '\\rm -rf log/log_data',
            '/bin/rm -rf log/log_data',
            '(rm -rf log/log_data)',
            'bash -c "rm -rf log/log_data"',
            'rsync -a --delete empty/ log/log_data/',
            'sed -i s/a/b/ memory/memory_config/memory_configs/user_info.json',
            'sed --in-place s/a/b/ memory/memory_config/memory_configs/user_info.json',
            'rm -rf .',
            'find log/log_data -print0 | xargs -0 rm -f',
            'ls log/log_data | xargs -n1 rm',
            'ls log/log_data/*.log | sort | head | xargs rm',
            'bash -lc "rm -rf log/log_data"',
            'sh -ec "rm -rf log/log_data"',
            'nice rm -rf log/log_data',
            'timeout 10 rm -rf log/log_data',
            'sudo -u root rm -rf log/log_data',
            'env -i X=1 rm -rf log/log_data',
            'rsync -a empty/ memory/memory_config/memory_configs/',
        ]
        ps_cases = [
            'Remove-Item -Recurse session\\session_plan',
            *(['Remove-Item -Recurse Session\\Session_Detail'] if os.name == 'nt' else []),  # 大小写不敏感只在 Windows 成立
            'Get-ChildItem memory\\memory_log\\memory_logs | Remove-Item',
            'Get-ChildItem log\\log_data | ForEach-Object { Remove-Item $_ }',
            'gci log\\log_data | ? { $_.Length -gt 0 } | ri',
            'Copy-Item a.json memory\\memory_config\\memory_configs\\x.json -Force',
            'Set-Location session; Remove-Item -Recurse session_detail',
            'Push-Location session; Remove-Item -Recurse session_detail',
            'Remove-Item -Path:log\\log_data -Recurse',
            'cmd /c rd /s /q session\\session_detail',
            'cmd /c "rd /s /q log\\log_data"',
            'robocopy empty log\\log_data /MIR',
            'Rename-Item log\\log_data old',
        ]
        for cmd in cases:
            with self.subTest(cmd=cmd):
                self.assertEqual(self.decide(cmd), 'ask')
        for cmd in ps_cases:
            with self.subTest(cmd=cmd):
                self.assertEqual(self.decide(cmd, tool='PowerShell'), 'ask')

    def test_allows(self):
        cases = [
            'ls session/session_detail',
            'git ls-files -- session/session_detail',
            'cat log/log_data/a.log > test/out.txt',
            'cp session/session_detail/a.json test/fixture.json',
            'ls session/session_detail 2>/dev/null && rm test/tmp.txt',
            'cd session/session_detail && cd ../.. && rm test/tmp.txt',
            'cd session/session_detail/.. && rm tmp.txt',
            'cd session/session_detail && ls > /dev/null',
            'cd session/session_detail && jq ".x > 1" a.json',
            'git log -- session/session_detail | rm -f test/x',
            'rm test/a.txt # session/session_detail',
            'git restore --staged session/session_detail/a.json',
            'git clean -fd',
            'git stash push -m wip',
            'git reset HEAD~1',
            'python .claude/skills/alear030-clear-logdata/logdata.py quarantine 20260916_000000',
            'rm -rf test/memory_recall/tmp',
            'rm -rf test/*',
            'find test -name "*.pyc" -delete',
            'rsync -a log/log_data/ backup/',
            # 受保护目录的上一级里是被跟踪的源码，不是运行数据
            'git checkout -- memory/memory_storage/memory_storage_core.py',
            'sed -i s/a/b/ memory/memory_log/memory_log_core.py',
            'echo x > memory/memory_log/__init__.py',
            'rm -rf memory/memory_storage/__pycache__',
            # 受保护目录里没有被跟踪的文件时，只动被跟踪文件的 git 命令碰不到它
            'git checkout -- session/session_detail',
            'git reset --hard',
            'git restore .',
            # heredoc 正文是数据
            "python - <<'X'\nsession = 1\ndel session\nX",
            "cat > notes.md <<'X'\nrm -rf log/log_data is what we must never do\nX",
            "git commit -F - <<'X'\nmv memory notes into docs\nX",
            'cat session/session_detail/a.json | tee',
        ]
        ps_cases = [
            'Get-ChildItem session\\session_detail -Filter *.json | Select-Object Name | Out-File test\\list.txt',
            'Get-Content session\\session_detail\\a.json | Set-Content test\\copy.json',
            'Copy-Item session\\session_detail\\a.json test\\a.json',
            'New-Item -ItemType Directory -Force log\\log_data',
        ]
        for cmd in cases:
            with self.subTest(cmd=cmd):
                self.assertIsNone(self.decide(cmd))
        for cmd in ps_cases:
            with self.subTest(cmd=cmd):
                self.assertIsNone(self.decide(cmd, tool='PowerShell'))
        # 不在任何仓库里、也没有会话起点时不判断
        self.assertIsNone(self.decide('rm -rf log/log_data', cwd=self.outside))

    def test_git_ignores_tracked_seeds(self):
        # 真实仓库的 memory_configs 下跟踪着 .example.json 种子；还原它们不算动运行数据
        seed = self.repo / 'memory/memory_config/memory_configs/user_info.example.json'
        seed.parent.mkdir(parents=True)
        seed.write_text('{}', encoding='utf-8')
        subprocess.run(['git', '-C', str(self.repo), 'add', '-f', str(seed)], check=True)
        self.assertIsNone(self.decide('git reset --hard'))
        self.assertIsNone(self.decide('git checkout -- .'))

    def test_git_counts_tracked_data(self):
        # 历史上被跟踪进来的数据文件：checkout / reset --hard 会改写它们
        tracked = self.repo / 'session/session_detail/old.json'
        tracked.parent.mkdir(parents=True)
        tracked.write_text('{}', encoding='utf-8')
        subprocess.run(['git', '-C', str(self.repo), 'add', '-f', str(tracked)], check=True)
        self.assertEqual(self.decide('git checkout -- session/session_detail'), 'ask')
        self.assertEqual(self.decide('git reset --hard'), 'ask')
        self.assertIsNone(self.decide('git checkout -- log/log_data'))

    def test_project_dir_extends_protection(self):
        # cwd 在仓库外（比如 scratchpad）时，靠会话起点定位仓库：绝对路径与相对路径都能认出
        target = (self.repo / 'log/log_data').as_posix()
        self.assertEqual(self.decide(f'rm -rf {target}', cwd=self.outside, project=self.repo), 'ask')
        self.assertEqual(self.decide('rm -rf ../repo/log', cwd=self.outside, project=self.repo), 'ask')

    def test_worktree_also_protects_main_checkout(self):
        wt = make_worktree(self.repo, self.repo / '.claude/worktrees/dev')
        target = (self.repo / 'session/session_detail').as_posix()
        self.assertEqual(self.decide(f'rm -rf {target}', cwd=wt), 'ask')

    def test_fails_open(self):
        decision, _, stderr, code = run_hook('data_guard.py', b'not json')
        self.assertIsNone(decision)
        self.assertEqual(code, 0)
        self.assertTrue(stderr)


if __name__ == '__main__':
    unittest.main()
