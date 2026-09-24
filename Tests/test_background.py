import tempfile
import time
import unittest
from support import Client

class BackgroundTests(unittest.TestCase):
    def test_background_prompt_and_interactive_response(self):
        with tempfile.TemporaryDirectory() as temp:
            c=Client(temp)
            try:
                opened=c.call('cursor.acp.session.open',{'permission_policy':'manual'})
                self.assertFalse(opened['result']['isError'],opened)
                session=Client.value(opened)['session']
                started=c.call('cursor.acp.session.prompt.start',{'session':session,'prompt':'permission'})
                self.assertFalse(started['result']['isError'],started)
                prompt=Client.value(started)['prompt_id']
                for _ in range(100):
                    pending=Client.value(c.call('cursor.acp.requests.list',{'session':session}))['requests']
                    if pending:break
                    time.sleep(.02)
                else:self.fail('Pending permission not observable')
                c.call('cursor.acp.requests.respond',{'session':session,'request_id':pending[0]['request_id'],'response':{'outcome':{'outcome':'selected','optionId':'opaque-no'}}})
                for _ in range(100):
                    result=c.call('cursor.acp.session.prompt.result',{'session':session,'prompt_id':prompt})
                    if Client.value(result).get('completed'):break
                    time.sleep(.02)
                else:self.fail('Background prompt did not complete')
                self.assertFalse(result['result']['isError'],result)
                self.assertFalse(Client.value(result)['busy'])
            finally:c.close()

if __name__=='__main__':unittest.main()
