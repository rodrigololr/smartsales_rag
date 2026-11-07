"""Executable regression checks for the reference examples, not application tests."""
import ast
import json
import re
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def blocks(path):
    return re.findall(r'^[ \t]*```python[^\n]*\n(.*?)^[ \t]*```[ \t]*$',
                      (ROOT / path).read_text(encoding='utf-8'), re.S | re.M)

def immediate(coroutine):
    try:
        coroutine.send(None)
    except StopIteration as result:
        return result.value
    raise AssertionError('Unexpected I/O in fixture')

class Contracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.examples = blocks('specs/components/02_middleend_gateway_sse_redis_spec.md')
        cls.cache = {}
        exec(compile(cls.examples[0], 'cache_example', 'exec'), cls.cache)
        cls.stream = {}
        exec(compile(cls.examples[1], 'stream_example', 'exec'), cls.stream)
        cls.api = json.loads((ROOT / 'openapi.yaml').read_text(encoding='utf-8'))

    def key(self, query, history=None, filters=None, policy='v1'):
        return self.cache['build_cache_key']('1', query, filters or {'sku':'AF-400'}, history or [], policy)

    def test_cache_direction(self):
        self.assertNotEqual(self.key('cesto 4L na airfryer 5L'), self.key('cesto 5L na airfryer 4L'))

    def test_cache_history(self):
        self.assertNotEqual(self.key('Cabe?', ['30cm']), self.key('Cabe?', ['60cm']))

    def test_cache_equivalence(self):
        self.assertEqual(self.key('é  220V?'), self.key('e\u0301 220V?'))

    def test_cache_filters_policy(self):
        self.assertNotEqual(self.key('Qual?', filters={'budget':500}), self.key('Qual?', filters={'budget':600}))
        self.assertNotEqual(self.key('Qual?'), self.key('Qual?', policy='v2'))

    def run_stream(self, events, failure=None, disconnect=False, cancel=False):
        cleaned=[]
        class Request:
            async def is_disconnected(self): return disconnect
        async def backend():
            try:
                for event in events: yield event
                if failure: raise failure
            finally: cleaned.append('backend')
        async def release(): cleaned.append('lock')
        async def products(): return []
        async def collect():
            result=[]
            gen=self.stream['sse_chat_generator'](Request(), 's', 'm', backend(), False, release, products)
            if cancel:
                await anext(gen)
                await gen.aclose()
                return result
            async for frame in gen:
                lines=frame.splitlines()
                result.append((lines[0][7:], json.loads(lines[1][6:])))
            return result
        result=immediate(collect())
        self.assertIn('lock',cleaned)
        self.assertIn('backend',cleaned)
        return result

    def test_stream_success(self):
        result=self.run_stream([{'event':'token','data':{'delta':'ok'}},{'event':'end','data':{'tokens_used':1}}])
        self.assertEqual([x[0] for x in result],['metadata','token','done'])
        self.assertEqual(result[-1][1]['finish_reason'],'stop')

    def test_stream_eof_is_error(self):
        result=self.run_stream([{'event':'token','data':{'delta':'partial'}}])
        self.assertIn('error',[x[0] for x in result])
        self.assertEqual(result[-1][1]['finish_reason'],'error')

    def test_stream_runtime_and_timeout(self):
        for failure in [RuntimeError('fault'),TimeoutError('timeout')]:
            with self.subTest(failure=type(failure).__name__):
                result=self.run_stream([{'event':'token','data':{'delta':'partial'}}],failure)
                self.assertEqual([x[0] for x in result].count('metadata'),1)
                self.assertEqual(result[-1][1]['finish_reason'],'error')

    def test_stream_disconnect_cleanup(self):
        self.assertEqual(self.run_stream([{'event':'token','data':{'delta':'ok'}}],disconnect=True),[])

    def test_stream_cancel_cleanup(self):
        self.run_stream([{'event':'token','data':{'delta':'ok'}}],cancel=True)

    def test_stream_fallback(self):
        result=self.run_stream([{'event':'error','data':{'code':'LOW_SIMILARITY_FALLBACK'}}, {'event':'end','data':{'tokens_used':0}}])
        self.assertEqual(result[-1][1]['finish_reason'],'fallback')

    def test_openapi_valid(self):
        from openapi_spec_validator import validate
        validate(self.api)

    def test_money_actual_serialization(self):
        from decimal import Decimal
        namespace={}
        code=blocks('specs/components/01_backend_rag_and_guardrails_spec.md')[0]
        exec(compile(code,'backend_models','exec'),namespace)
        model=namespace['ProductRecommendation'](sku='AF',name='Test',price=Decimal('499.90'),stock_quantity=1,
            voltage='220V',image_url='/test.png',marketplace='AMAZON',checkout_url='https://example.com',
            recommendation_type='PRIMARY',badge_label='Test',justification='Test')
        self.assertIsInstance(json.loads(model.model_dump_json())['price'],(int,float))
        self.assertEqual(json.loads(model.model_dump_json())['price'],499.90)

    def test_new_contracts(self):
        self.assertIn('/api/v1/products',self.api['paths'])
        self.assertIn('client_request_id',self.api['components']['schemas']['ChatStreamRequest']['required'])
        self.assertEqual(len(self.api['components']['schemas']['StreamEvent']['oneOf']),7)

    def test_python_examples_compile(self):
        # Only project documentation is normative; installed dependency READMEs
        # can contain illustrative, intentionally non-executable snippets.
        paths = [*ROOT.glob('*.md'), *(ROOT / 'specs').rglob('*.md')]
        for path in paths:
            for code in blocks(str(path.relative_to(ROOT))):
                ast.parse(textwrap.dedent(code))

if __name__=='__main__': unittest.main()
