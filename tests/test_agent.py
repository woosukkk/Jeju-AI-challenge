from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from trade_itsuda.agent import AgentError, extract_quote, quote_text, run_agent
from trade_itsuda.config import Settings
from trade_itsuda.ingest import demo_companies
from trade_itsuda.models import SearchRequest


def config(allow=True):
    return Settings(Path('unused'), 'openai', 'test-model', 'not-a-key', '', allow)


class Message(NS):
    def model_dump(self, **kwargs):
        return {'role': 'assistant', 'content': None, 'tool_calls': []}


class FakeClient:
    def __init__(self, messages):
        self.messages = iter(messages)
        self.requests = []
        self.chat = NS(completions=NS(create=self.create))

    def create(self, **kwargs):
        self.requests.append(kwargs)
        return NS(choices=[NS(message=next(self.messages))])


def tool(name='search_companies', arguments='{"query":"라벨"}'):
    return Message(tool_calls=[NS(id='call1', function=NS(name=name, arguments=arguments))], content=None)


def final(content):
    return Message(tool_calls=[], content=content)


def test_grounded_agent_and_filter_lock():
    client = FakeClient([tool(), final('{"company_ids":["demo-print"],"questions":[]}')])
    result = run_agent(config(), demo_companies(), SearchRequest(query='라벨'), client=client)
    assert result.hits[0].company.id == 'demo-print'
    assert len(result.trace) == 1
    assert len(client.requests) == 2
    with pytest.raises(AgentError, match='근거'):
        run_agent(config(), demo_companies(), SearchRequest(query='서귀포 라벨'),
                  client=FakeClient([tool(arguments='{"query":"라벨","region":"서귀포"}'),
                                     final('{"company_ids":["demo-print"]}')]))
    with pytest.raises(AgentError, match='근거'):
        run_agent(config(), demo_companies(), SearchRequest(query='라벨', region='서귀포'),
                  client=FakeClient([tool(), final('{"company_ids":["demo-print"]}')]))


def test_external_block_and_disallowed_tools_and_budget():
    client = FakeClient([])
    with pytest.raises(AgentError):
        run_agent(config(False), [], SearchRequest(query='라벨'), client=client)
    with pytest.raises(AgentError):
        extract_quote(config(False), '견적 원문', client)
    assert client.requests == []
    with pytest.raises(AgentError, match='허용되지'):
        run_agent(config(), [], SearchRequest(query='라벨'), client=FakeClient([tool('shell')]))
    with pytest.raises(AgentError, match='한도'):
        run_agent(config(), [], SearchRequest(query='라벨'), client=FakeClient([tool()] * 6))
    with pytest.raises(AgentError, match='형식'):
        run_agent(config(), [], SearchRequest(query='라벨'), client=FakeClient([tool('count_by_region', '{"bad":1}')]))


def test_agent_explores_categories_and_other_regions_when_empty():
    client = FakeClient([
        tool('list_categories', '{"keyword":"상자"}'),
        tool('search_companies', '{"query":"종이 상자","region":"제주시"}'),
        tool('count_by_region', '{"query":"상자"}'),
        final('{"company_ids":[],"questions":[],"summary":"서귀포에는 0곳, 제주시 한림읍에 1곳 있습니다."}'),
    ])
    result = run_agent(config(), demo_companies(), SearchRequest(query='상자', region='서귀포'), client=client)
    assert [step['tool'] for step in result.trace] == ['list_categories', 'search_companies', 'count_by_region']
    # 사용자가 정한 지역은 Agent가 바꾸지 못한다.
    assert result.trace[0]['args']['region'] == '서귀포' and result.trace[0]['result']['matched_total'] == 0
    assert result.trace[1]['args']['region'] == '서귀포' and result.trace[1]['result_ids'] == []
    assert {'region': '제주시 한림읍', 'count': 1} in result.trace[2]['result']['regions']
    assert result.hits == [] and '한림읍에 1곳' in result.summary
    assert [t['function']['name'] for t in client.requests[0]['tools']] == ['list_categories', 'search_companies', 'count_by_region']


def test_summary_with_numbers_not_in_tool_results_is_hidden():
    client = FakeClient([tool(), final('{"company_ids":["demo-print"],"summary":"후보 37곳 중 최저가입니다."}')])
    result = run_agent(config(), demo_companies(), SearchRequest(query='라벨'), client=client)
    assert result.hits[0].company.id == 'demo-print'
    assert result.summary == '' and result.trace[-1]['tool'] == 'summary_check'


def test_unconfirmed_extraction_and_read_boundaries():
    result = extract_quote(config(), '가격 미기재', FakeClient([final('{"item":"라벨"}')]))
    assert result.unit_price is None
    with pytest.raises(AgentError):
        extract_quote(config(), '원문', FakeClient([final('{"unit_price":-1}')]))
    assert quote_text('견적'.encode(), 'a.txt') == '견적'
    with pytest.raises(AgentError):
        quote_text(b'bad', 'a.exe')
