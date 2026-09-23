import os
from types import SimpleNamespace
import httpx
import pytest
from openai import AuthenticationError, RateLimitError, APITimeoutError, APIConnectionError
from copilot.provider import OpenAIProvider
from copilot.models import Extraction, FactDraft, CopyDraft
from copilot.engine import validate_facts, validate_copy

@pytest.mark.parametrize('kind,word', [('auth','密钥'),('rate','限流'),('timeout','60'),('network','网络'),('empty','结构化')])
def test_errors_do_not_fallback(monkeypatch,kind,word):
    monkeypatch.setenv('OPENAI_API_KEY','unit-test-placeholder')
    monkeypatch.setenv('OPENAI_MODEL','test-model')
    req = httpx.Request('POST','https://api.openai.com/v1/responses')
    response = httpx.Response(401,request=req)
    errors = {'auth':AuthenticationError('redacted',response=response,body=None), 'rate':RateLimitError('redacted',response=response,body=None), 'timeout':APITimeoutError(request=req), 'network':APIConnectionError(request=req)}
    class Client:
        def __init__(self,**kwargs): self.responses = self
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def parse(self,**kwargs):
            assert kwargs['store'] is False and kwargs['model'] == 'test-model'
            if kind == 'empty': return SimpleNamespace(output_parsed=None)
            raise errors[kind]
    monkeypatch.setattr('copilot.provider.OpenAI',Client)
    with pytest.raises(ValueError,match=word): OpenAIProvider().extract([])

def test_missing_config_and_size(monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    with pytest.raises(ValueError): OpenAIProvider()
    monkeypatch.setenv('OPENAI_API_KEY','placeholder')
    monkeypatch.setenv('OPENAI_MODEL','test-model')
    with pytest.raises(ValueError,match='40,000'): OpenAIProvider().call('x'*40001,Extraction,'')

def test_bad_structured_evidence():
    f = FactDraft(source_id='invented',locator='页 1',quote='fake',supplier='',product='',dimension='功率',value='8kW',unit='',condition='',kind='来源事实')
    with pytest.raises(ValueError,match='无效'): validate_facts([f],[])
    d = CopyDraft(section='价值表述',title='fake',content='fake',evidence=['invented'],warnings=[])
    with pytest.raises(ValueError,match='无效'): validate_copy([d],[])
