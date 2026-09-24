import importlib.util
import io
import json
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT=Path(__file__).resolve().parent.parent
spec=importlib.util.spec_from_file_location('build_package',ROOT/'Scripts/build_package.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)

class PackageTests(unittest.TestCase):
    def test_reproducible_archive_and_executable_mode(self):
        first,manifest=builder.package_bytes(ROOT)
        self.assertEqual(first,builder.package_bytes(ROOT)[0])
        with zipfile.ZipFile(io.BytesIO(first)) as archive:
            names=archive.namelist()
            self.assertIn('computer-mcp-plugin.toml',names)
            self.assertIn('cli-tree.json',names)
            self.assertIn('bin/plugin_runtime.py',names)
            for entry in archive.infolist():
                self.assertFalse(any(p.startswith('.') or p=='__pycache__' for p in Path(entry.filename).parts))
                self.assertFalse(entry.filename.endswith(('.pyc','.pyo')))
                expected=0o755 if entry.filename==f"bin/{manifest['id']}-mcp-adapter" else 0o644
                self.assertEqual(stat.S_IMODE(entry.external_attr>>16),expected)
            with tempfile.TemporaryDirectory() as temp:
                archive.extractall(temp)
                command=[sys.executable,str(Path(temp)/f"bin/{manifest['id']}-mcp-adapter"),'--version']
                result=subprocess.run(command,capture_output=True,text=True,timeout=3)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual(result.stdout.strip(),manifest['version'])
    def test_bytecode_and_local_metadata_cannot_change_release_bytes(self):
        before,_=builder.package_bytes(ROOT)
        with tempfile.TemporaryDirectory() as temp:
            copy=Path(temp)/'source';copy.mkdir()
            for name in builder.INCLUDE:
                source=ROOT/name
                if source.is_dir():shutil.copytree(source,copy/name)
                else:shutil.copyfile(source,copy/name)
            cache=copy/'bin/__pycache__';cache.mkdir(exist_ok=True)
            (cache/'arbitrary.pyc').write_bytes(b'not-release-content')
            (copy/'bin/.DS_Store').write_bytes(b'not-release-content')
            self.assertEqual(before,builder.package_bytes(copy)[0])
    def test_cli_prompt_mapping_has_an_explicit_option_separator(self):
        tree=json.loads((ROOT/'cli-tree.json').read_text())
        for command in tree['commands']:
            tokens=command.get('argv',[])
            position=next((i for i,x in enumerate(tokens) if x.get('parameter')=='prompt'),None)
            if position is not None:
                self.assertEqual(tokens[position-1],{'kind':'literal','value':'--'})

if __name__=='__main__':unittest.main()
