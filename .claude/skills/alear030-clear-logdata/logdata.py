"""按 session_id 归集过程文件，供 alear030-clear-logdata 技能清理用。

scan：只读，输出每个 session 的产物、对话量、是否被 memory 引用，JSON 到 stdout
trash：按给定 session_id 重新扫描，把全部产物送进系统回收站（仅 Windows）

发现规则依赖项目约定「单 session 过程数据以 session_id 为文件名」，不枚举目录，
在 git 忽略的目录里找文件名形如 session_id 的文件，新增产物类型无需改这里。
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(subprocess.run(
    ['git', 'rev-parse', '--show-toplevel'], capture_output=True, text=True, check=True
).stdout.strip())
sys.path.insert(0, str(ROOT))

from config import SESSION_MEMORTY_DETAIL_PATH, MEMORY_STORAGE_PATH  # noqa: E402

SESSION_ID = re.compile(r'^\d{8}_\d{6}$')
# 非项目内容 / 模型资产 / 测试夹具，不参与发现
EXCLUDE_TOP = {'workspace', 'z_ccstudy', 'z_old_code', '.cc_file', 'local_model', 'test',
               '.git', '.claude', '.agents', '.local', '.opencode', '.zcode'}
ACTIVE_WINDOW_SECONDS = 600
EXCERPT_CHARS = 80


def _ignored_dirs():
    out = subprocess.run(
        ['git', 'ls-files', '--others', '--ignored', '--exclude-standard', '--directory'],
        cwd=ROOT, capture_output=True, text=True, encoding='utf-8', check=True,
    ).stdout.splitlines()
    for rel in out:
        if not rel.endswith('/') or Path(rel).parts[0] in EXCLUDE_TOP or '__pycache__' in rel:
            continue
        yield ROOT / rel


def _collect_artifacts():
    # git 会同时列出被忽略的父目录与子目录，按文件去重
    found = {f for d in _ignored_dirs() for f in d.rglob('*')
             if f.is_file() and SESSION_ID.match(f.stem)}
    artifacts = {}
    for f in sorted(found):
        artifacts.setdefault(f.stem, []).append(f)
    return artifacts


def _detail_summary(path: Path):
    try:
        data = json.loads(path.read_text(encoding='utf-8') or '{}')
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return {'detail_error': f'{type(e).__name__}: {e}'}
    msgs = data.get('session_messages') or []
    users = [m for m in msgs if m.get('message_role') == 'user']
    return {
        'user_messages': len(users),
        'total_messages': len(msgs),
        'slices': len(data.get('session_slice') or []),
        'user_excerpts': [str(m.get('message_content', ''))[:EXCERPT_CHARS] for m in users[:5]],
    }


def _memory_text():
    if not MEMORY_STORAGE_PATH.exists():
        return ''
    return '\n'.join(f.read_text(encoding='utf-8', errors='replace')
                     for f in MEMORY_STORAGE_PATH.rglob('*') if f.is_file())


def scan():
    detail_dir = Path(SESSION_MEMORTY_DETAIL_PATH)
    detail_files = list(detail_dir.glob('*.json')) if detail_dir.exists() else []
    # 失效自检：session_id 格式或落盘约定变了，发现规则会静默返回空，必须报错而不是当作「没有可清理的」
    if detail_files and not any(SESSION_ID.match(f.stem) for f in detail_files):
        sys.exit(f'session_detail 下的文件名都不匹配 {SESSION_ID.pattern}，session_id 格式可能已变更，停止')

    artifacts = _collect_artifacts()
    memory_text = _memory_text()
    now = time.time()
    sessions = []
    for sid, files in sorted(artifacts.items()):
        detail = detail_dir / f'{sid}.json'
        entry = {
            'session_id': sid,
            'has_detail': detail.exists(),
            'memory_referenced': sid in memory_text,
            'maybe_active': any(now - f.stat().st_mtime < ACTIVE_WINDOW_SECONDS for f in files),
            'files': [{'path': f.relative_to(ROOT).as_posix(), 'bytes': f.stat().st_size} for f in files],
        }
        if entry['has_detail']:
            entry.update(_detail_summary(detail))
        sessions.append(entry)

    kinds = sorted({Path(f['path']).parent.as_posix() for s in sessions for f in s['files']})
    return {'root': ROOT.as_posix(), 'artifact_dirs': kinds, 'sessions': sessions}


def _send_to_recycle_bin(path: Path):
    ps = ("Add-Type -AssemblyName Microsoft.VisualBasic; "
          "[Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile($env:TRASH_TARGET, 'OnlyErrorDialogs', 'SendToRecycleBin')")
    env = {**os.environ, 'TRASH_TARGET': str(path)}
    r = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', ps],
                       capture_output=True, text=True, env=env)
    return r.returncode == 0 and not path.exists(), r.stderr.strip()


def trash(session_ids, allow_referenced):
    if sys.platform != 'win32':
        sys.exit('trash 目前只实现了 Windows 回收站，其他平台请手动处理')
    by_id = {s['session_id']: s for s in scan()['sessions']}
    results = []
    for sid in session_ids:
        s = by_id.get(sid)
        if s is None:
            results.append({'session_id': sid, 'status': 'not_found'})
            continue
        # 重扫后再判一次：确认清单与执行之间可能有新会话启动或 memory 管线写入
        if s['maybe_active']:
            results.append({'session_id': sid, 'status': 'skipped_active'})
            continue
        if s['memory_referenced'] and not allow_referenced:
            results.append({'session_id': sid, 'status': 'skipped_memory_referenced'})
            continue
        done, failed = [], []
        for f in s['files']:
            ok, err = _send_to_recycle_bin(ROOT / f['path'])
            (done if ok else failed).append(f['path'] if ok else {'path': f['path'], 'error': err})
        results.append({'session_id': sid, 'status': 'trashed' if not failed else 'partial',
                        'trashed': done, 'failed': failed})
    return results


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='cmd', required=True)
    sub.add_parser('scan')
    t = sub.add_parser('trash')
    t.add_argument('session_ids', nargs='+')
    t.add_argument('--allow-memory-referenced', action='store_true')
    args = parser.parse_args()

    result = scan() if args.cmd == 'scan' else trash(args.session_ids, args.allow_memory_referenced)
    sys.stdout.reconfigure(encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
