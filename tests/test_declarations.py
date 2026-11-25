import tempfile
import tomllib
import unittest
from support import Client, ROOT

READ = {'cursor.acp.session.prompt.result', 'cursor.acp.session.list', 'cursor.acp.events.read', 'cursor.acp.requests.list'}

class DeclarationTests(unittest.TestCase):
    def test_manifest_matches_actual_catalog(self):
        (ROOT / '.agent/host6').mkdir(parents=True, exist_ok=True)
        manifest = tomllib.loads((ROOT / 'computer-mcp-plugin.toml').read_text())
        self.assertEqual(manifest['permissions'], [{'id': 'project', 'access': 'write', 'purpose': 'Open Cursor sessions and run requested project tasks and edits in owner-selected worktrees, including cancellation and native response delivery.'}])
        self.assertNotIn('sandbox', manifest)
        self.assertNotIn('host_service_contract', manifest['mcp'][0])
        mcp = manifest['mcp'][0]
        self.assertEqual(mcp['requirements'], {'project': 'write'})
        self.assertEqual(mcp['tool_requirements'], {name: {'project': 'read'} for name in READ})
        with tempfile.TemporaryDirectory(dir=ROOT / '.agent/host6') as temp:
            client = Client(temp)
            try:
                tools = client.request('tools/list')['result']['tools']
                self.assertEqual(len(tools), 12)
                self.assertEqual({tool['name'] for tool in tools if tool['_meta']['io.github.computer-mcp/risk'] == 'read-only'}, READ)
                for tool in tools:
                    self.assertNotIn('requirements', tool.get('_meta', {}))
            finally: client.close()
        self.assertEqual([c['id'] for c in manifest['cli']], ['agent'])
        self.assertEqual([c['id'] for c in manifest['skills']], ['cursor-agent'])

if __name__ == '__main__': unittest.main()
