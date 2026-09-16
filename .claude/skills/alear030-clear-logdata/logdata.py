"""按 session_id 归集过程文件，供 alear030-clear-logdata 技能清理用。

scan：只读，输出每个 session 的产物、对话量、是否被 memory 引用，JSON 到 stdout
quarantine：按给定 session_id 重新扫描，把全部产物移进仓库外的隔离目录，每批一份 manifest
restore：遍历一个隔离批次目录，按相对路径移回原处（manifest 只做记录）

发现规则依赖项目约定「单 session 过程数据以 session_id 为文件名」，不枚举目录：
在 git 忽略的目录里找文件名形如 session_id 的文件，再只保留「按会话存数据」的目录——
该目录里多数文件能对上现有 session_detail。不沿用这条约定的产物会被漏掉。

不走系统回收站：shell 在放不进回收站时会改为永久删除，而压掉确认框又会让这一步静默发生。
"""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(subprocess.run(
    ['git', 'rev-parse', '--show-toplevel'], capture_output=True, text=True, check=True
).stdout.strip())
sys.path.insert(0, str(ROOT))

from config import SESSION_MEMORTY_DETAIL_PATH, MEMORY_STORAGE_PATH  # noqa: E402

SESSION_ID = re.compile(r'^\d{8}_\d{6}$')
BATCH_ID = re.compile(r'^\d{8}_\d{6}_*$')
# 非项目内容 / 模型资产 / 测试夹具，不参与发现
EXCLUDE_TOP = {'workspace', 'z_ccstudy', 'z_old_code', '.cc_file', 'local_model', 'test',
               '.git', '.claude', '.agents', '.local', '.opencode', '.zcode'}
ACTIVE_WINDOW_SECONDS = 600
EXCERPT_CHARS = 80
# 至少这么多文件对上 session_detail 且过半，才算按会话存数据的目录；只有一个文件时宁可漏清
KEYED_DIR_MIN_MATCHES = 2
# 按 checkout 分开：主仓库与各 worktree 的同名 session 是不同的文件
QUARANTINE_ROOT = (Path.home() / '.alear030' / 'logdata_quarantine'
                   / f"{ROOT.name}_{hashlib.md5(str(ROOT).lower().encode()).hexdigest()[:8]}")
# 会话进程：直接跑 main.py，或经 alear030 命令启动
RUNNING_PATTERN = re.compile(r'(^|[\\/\s"\'])(main\.py|alear030(\.exe)?)(["\'\s]|$)', re.IGNORECASE)


def _ignored_dirs():
    out = subprocess.run(
        ['git', 'ls-files', '--others', '--ignored', '--exclude-standard', '--directory'],
        cwd=ROOT, capture_output=True, text=True, encoding='utf-8', check=True,
    ).stdout.splitlines()
    for rel in out:
        if not rel.endswith('/') or Path(rel).parts[0] in EXCLUDE_TOP or '__pycache__' in rel:
            continue
        yield ROOT / rel


def _collect_artifacts(detail_dir: Path, known_ids: set):
    # git 会同时列出被忽略的父目录与子目录，按文件去重
    found = {f for d in _ignored_dirs() for f in d.rglob('*')
             if f.is_file() and SESSION_ID.match(f.stem)}
    by_dir = {}
    for f in found:
        by_dir.setdefault(f.parent, []).append(f)

    artifacts, unkeyed = {}, []
    for d, files in sorted(by_dir.items()):
        matches = sum(f.stem in known_ids for f in files)
        total_files = sum(f.is_file() for f in d.iterdir())  # 普通文件也计入目录匹配比例
        keyed = d == detail_dir or (matches >= KEYED_DIR_MIN_MATCHES and matches * 2 > total_files)
        for f in sorted(files):
            if keyed:
                artifacts.setdefault(f.stem, []).append(f)
            else:
                unkeyed.append(f)
    return artifacts, unkeyed


def _detail_summary(path: Path):
    try:
        raw = path.read_text(encoding='utf-8')
        if not raw.strip():
            return {'detail_error': '空文件'}
        data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return {'detail_error': f'{type(e).__name__}: {e}'}
    msgs = data.get('session_messages') if isinstance(data, dict) else None
    if not isinstance(msgs, list) or not all(isinstance(m, dict) for m in msgs):
        return {'detail_error': 'session_messages 结构不符'}
    users = [m for m in msgs if m.get('message_role') == 'user']
    return {
        'user_messages': len(users),
        'total_messages': len(msgs),
        'user_excerpts': [str(m.get('message_content', ''))[:EXCERPT_CHARS] for m in users[:5]],
    }


def _memory_text():
    if not MEMORY_STORAGE_PATH.exists():
        return ''
    return '\n'.join(f.read_text(encoding='utf-8', errors='replace')
                     for f in MEMORY_STORAGE_PATH.rglob('*') if f.is_file())


def _running_sessions():
    # 拿不到进程列表时返回 None，由调用方按「可能在跑」处理
    if sys.platform == 'win32':
        ps = ("Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -or $_.Name -like 'alear030*' } "
              "| Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress")
        cmd = ['powershell', '-NoProfile', '-NonInteractive', '-Command', ps]
    else:
        cmd = ['ps', '-eo', 'pid=,args=']
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    if sys.platform == 'win32':
        rows = json.loads(r.stdout) if r.stdout.strip() else []
        rows = [rows] if isinstance(rows, dict) else rows
        procs = [(row.get('ProcessId'), row.get('CommandLine') or '') for row in rows]
    else:
        procs = []
        for line in r.stdout.splitlines():
            parts = line.strip().split(None, 1)
            if parts:
                procs.append((int(parts[0]), parts[1] if len(parts) > 1 else ''))
    me = Path(__file__).name
    return [{'pid': pid, 'cmdline': c} for pid, c in procs
            if RUNNING_PATTERN.search(c) and me not in c]


def scan():
    detail_dir = Path(SESSION_MEMORTY_DETAIL_PATH)
    detail_files = [f for f in detail_dir.iterdir() if f.is_file()] if detail_dir.exists() else []
    # 失效自检：格式一变，新会话会从发现结果里静默消失而旧会话照常匹配，所以有一个对不上就停
    unrecognized = sorted(f.name for f in detail_files
                          if f.suffix != '.json' or not SESSION_ID.match(f.stem))
    if unrecognized:
        sys.exit(f'session_detail 下有文件不符合 <session_id>.json，格式可能已变更，停止：{unrecognized}')

    known_ids = {f.stem for f in detail_files}
    artifacts, unkeyed = _collect_artifacts(detail_dir, known_ids)
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
    return {
        'root': ROOT.as_posix(),
        'quarantine_dir': QUARANTINE_ROOT.as_posix(),
        'running_sessions': _running_sessions(),
        'artifact_dirs': kinds,
        'unkeyed_files': [f.relative_to(ROOT).as_posix() for f in unkeyed],
        'sessions': sessions,
    }


def _move(src: Path, dest: Path):
    if dest.exists():
        return f'目标已存在：{dest}'
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))
    except OSError as e:
        return f'{type(e).__name__}: {e}'
    return None if dest.exists() and not src.exists() else '移动后校验失败'


def quarantine(session_ids, allow_referenced):
    result = scan()
    # 闲置中的会话不写文件、mtime 判不出来；移走 detail 后它下一轮写入会崩，trace/log 会在原处重新长出来
    if result['running_sessions'] is None:
        sys.exit('无法获取进程列表，不能确认没有会话在运行，停止')
    if result['running_sessions']:
        sys.exit(f"有 Alear030 会话进程在运行，先关掉再清理：{result['running_sessions']}")

    by_id = {s['session_id']: s for s in result['sessions']}
    batch = datetime.now().strftime('%Y%m%d_%H%M%S')
    batch_dir = QUARANTINE_ROOT / batch
    while batch_dir.exists():
        batch += '_'
        batch_dir = QUARANTINE_ROOT / batch
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
        moved, failed = [], []
        for f in s['files']:
            err = _move(ROOT / f['path'], batch_dir / f['path'])
            if err:
                failed.append({'path': f['path'], 'error': err})
            else:
                moved.append(f['path'])
        results.append({'session_id': sid, 'status': 'partial' if failed else 'quarantined',
                        'moved': moved, 'failed': failed})
    if batch_dir.exists():
        manifest = {'root': ROOT.as_posix(), 'batch': batch, 'results': results}
        (batch_dir / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    return {'batch': batch, 'batch_dir': batch_dir.as_posix(), 'results': results}


def restore(batch):
    batch_dir = QUARANTINE_ROOT / batch
    if not BATCH_ID.match(batch) or batch_dir.resolve().parent != QUARANTINE_ROOT.resolve():
        sys.exit(f'批次名不合法：{batch}')
    if not batch_dir.is_dir():
        sys.exit(f'隔离批次不存在：{batch_dir}')
    restored, failed = [], []
    for f in sorted(batch_dir.rglob('*')):
        if not f.is_file() or f == batch_dir / 'manifest.json':
            continue
        rel = f.relative_to(batch_dir)
        err = _move(f, ROOT / rel)
        if err:
            failed.append({'path': rel.as_posix(), 'error': err})
        else:
            restored.append(rel.as_posix())
    if not failed:
        shutil.rmtree(batch_dir)
    return {'batch': batch, 'restored': restored, 'failed': failed}


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='cmd', required=True)
    sub.add_parser('scan')
    q = sub.add_parser('quarantine')
    q.add_argument('session_ids', nargs='+')
    q.add_argument('--allow-memory-referenced', action='store_true')
    r = sub.add_parser('restore')
    r.add_argument('batch')
    args = parser.parse_args()

    if args.cmd == 'scan':
        result = scan()
    elif args.cmd == 'quarantine':
        result = quarantine(args.session_ids, args.allow_memory_referenced)
    else:
        result = restore(args.batch)
    sys.stdout.reconfigure(encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
