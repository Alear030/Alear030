import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / '.claude/skills/alear030-clear-logdata/logdata.py'
spec = importlib.util.spec_from_file_location('logdata_under_test', SCRIPT)
logdata = importlib.util.module_from_spec(spec)
config = types.ModuleType('config')
config.SESSION_MEMORTY_DETAIL_PATH = Path('unused_detail')
config.MEMORY_STORAGE_PATH = Path('unused_memory')
with patch.dict(sys.modules, {'config': config}):
    spec.loader.exec_module(logdata)


class CollectArtifactsTest(unittest.TestCase):
    def test_directory_majority(self):
        # 普通文件参与分母，但不能进入待清理文件列表
        cases = [(2, 100, False), (2, 2, False), (2, 1, True), (1, 0, False)]
        for matched, ordinary, expected in cases:
            with self.subTest(matched=matched, ordinary=ordinary), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                ids = {f'20260916_{i:06d}' for i in range(matched)}
                candidates = {root / f'{sid}.json' for sid in ids}
                for path in candidates:
                    path.touch()
                for i in range(ordinary):
                    (root / f'notes_{i}.txt').touch()
                with patch.object(logdata, '_ignored_dirs', return_value=[root]):
                    artifacts, unkeyed = logdata._collect_artifacts(root / 'detail', ids)
                self.assertEqual({p for paths in artifacts.values() for p in paths},
                                 candidates if expected else set())
                self.assertEqual(set(unkeyed), set() if expected else candidates)

    def test_detail_directory_keeps_explicit_exception(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            detail = root / '20260916_000001.json'
            detail.touch()
            (root / 'notes.txt').touch()
            with patch.object(logdata, '_ignored_dirs', return_value=[root]):
                artifacts, unkeyed = logdata._collect_artifacts(root, {detail.stem})
            self.assertEqual(artifacts, {detail.stem: [detail]})
            self.assertEqual(unkeyed, [])

    def test_nested_files_and_duplicate_discovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nested = root / 'nested'
            nested.mkdir()
            (nested / 'notes.txt').touch()
            paths = [root / f'20260916_{i:06d}.json' for i in range(3)]
            for path in paths:
                path.touch()
            # 未知会话仍计入分母，已识别目录仍归集其产物
            with patch.object(logdata, '_ignored_dirs', return_value=[root, nested, root]):
                artifacts, unkeyed = logdata._collect_artifacts(root / 'detail',
                                                               {p.stem for p in paths[:2]})
            self.assertEqual(artifacts, {p.stem: [p] for p in paths})
            self.assertEqual(unkeyed, [])


if __name__ == '__main__':
    unittest.main()
