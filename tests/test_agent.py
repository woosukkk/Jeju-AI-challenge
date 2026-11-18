from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from trade_itsuda.agent import (AgentError, explain_comparison, extract_quote, inquiry_questions, quote_text, run_agent,
                                trace_lines)
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
    # 도구 한도(5회)에 닿으면 도구 없이 마무리하게 하고, 그래도 도구를 부르면 중단한다.
    with pytest.raises(AgentError, match='한도'):
        run_agent(config(), [], SearchRequest(query='라벨'), client=FakeClient([tool()] * 6))
    client = FakeClient([tool()] * 5 + [final('{"company_ids":[],"summary":"라벨 후보를 찾지 못했습니다."}')])
    result = run_agent(config(), [], SearchRequest(query='라벨'), client=client)
    assert len(result.trace) == 5 and client.requests[-1]['tool_choice'] == 'none'
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
    # 분류명 확인은 제주 전체에서 하고, 후보 검색의 지역은 Agent가 바꾸지 못한다.
    assert result.trace[0]['args']['region'] == '' and result.trace[0]['result']['matched_total'] == 2
    assert result.trace[1]['args']['region'] == '서귀포' and result.trace[1]['result_ids'] == []
    assert {'region': '제주시 한림읍', 'count': 1} in result.trace[2]['result']['regions']
    assert result.hits == [] and '한림읍에 1곳' in result.summary
    lines = trace_lines(result.trace)
    assert lines[0].startswith("업종 분류 확인: '상자' → 관련 업소 2곳 (")
    assert lines[1] == "업체 검색: '종이 상자' · 지역 서귀포 → 후보 0곳"
    assert lines[2].startswith("지역별 집계: '상자' → 전체 2곳") and '제주시 한림읍 1곳' in lines[2]
    assert [t['function']['name'] for t in client.requests[0]['tools']] == ['list_categories', 'search_companies', 'count_by_region']


def test_json_wrapped_in_code_fence_is_accepted():
    client = FakeClient([tool(), final('```json\n{"company_ids":["demo-print"],"questions":[]}\n```')])
    assert run_agent(config(), demo_companies(), SearchRequest(query='라벨'), client=client).hits[0].company.id == 'demo-print'
    advice = explain_comparison(config(), TABLE, '기존상회', FakeClient([final('```json\n{"summary":"후보 비교"}\n```')]))
    assert advice.summary == '후보 비교'


class StatusError(Exception):
    def __init__(self, status_code):
        super().__init__(f'status {status_code}')
        self.status_code = status_code


class FlakyClient(FakeClient):
    """앞의 응답 대신 지정한 HTTP 오류를 먼저 낸다."""
    def __init__(self, errors, messages):
        super().__init__(messages)
        self.errors = list(errors)

    def create(self, **kwargs):
        if self.errors:
            self.requests.append(kwargs)
            raise StatusError(self.errors.pop(0))
        return super().create(**kwargs)


def test_server_overload_is_retried_once_but_quota_errors_are_not(monkeypatch):
    monkeypatch.setattr('trade_itsuda.agent.time.sleep', lambda seconds: None)
    client = FlakyClient([503], [final('{"questions":["취급하시나요?"]}')])
    assert inquiry_questions(config(), {'item': '상자'}, None, client) == ['취급하시나요?']
    assert len(client.requests) == 2
    with pytest.raises(AgentError, match='503 서버 과부하'):
        inquiry_questions(config(), {'item': '상자'}, None, FlakyClient([503, 503], []))
    client = FlakyClient([429], [final('{"questions":[]}')])
    with pytest.raises(AgentError, match='429 호출 한도'):
        inquiry_questions(config(), {'item': '상자'}, None, client)
    assert len(client.requests) == 1


def test_summary_with_numbers_not_in_tool_results_is_hidden():
    client = FakeClient([tool(), final('{"company_ids":["demo-print"],"summary":"후보 37곳 중 최저가입니다."}')])
    result = run_agent(config(), demo_companies(), SearchRequest(query='라벨'), client=client)
    assert result.hits[0].company.id == 'demo-print'
    assert result.summary == '' and result.trace[-1]['tool'] == 'summary_check'


TABLE = [{'업체': '기존상회', '총액': '110000.00', '기준 대비 차액': '0.00', '비교 제한': ''},
         {'업체': '가상포장', '총액': '99000.00', '기준 대비 차액': '-11000.00', '비교 제한': ''},
         {'업체': '가상인쇄', '총액': '미확정', '기준 대비 차액': '비교 불가', '비교 제한': '배송비 미확인'}]


def test_comparison_advice_uses_only_table_numbers():
    good = final('{"summary":"가상포장은 기존상회보다 11,000원 낮습니다. 견적 3개 중 1곳은 총액 미확정입니다.",'
                 '"checks":["가상인쇄의 배송비를 확인하세요."],"keep":"","parallel":"","switch":"가상포장의 납기가 맞으면"}')
    advice = explain_comparison(config(), TABLE, '기존상회', FakeClient([good]))
    assert advice.checks == ['가상인쇄의 배송비를 확인하세요.']
    with pytest.raises(AgentError, match='없는 숫자'):
        explain_comparison(config(), TABLE, '기존상회', FakeClient([final('{"summary":"연간 132,000원을 아낄 수 있습니다."}')]))
    with pytest.raises(AgentError, match='형식'):
        explain_comparison(config(), TABLE, '기존상회', FakeClient([final('not json')]))
    client = FakeClient([])
    with pytest.raises(AgentError):
        explain_comparison(config(False), TABLE, '기존상회', client)
    assert client.requests == []


def test_inquiry_questions_are_added_to_the_fixed_draft():
    from trade_itsuda.exporting import inquiry
    client = FakeClient([final('{"questions":["포장 및 충전업으로 등록되어 있는데 종이 상자 제작도 하시나요?"]}')])
    company = demo_companies()[1]
    questions = inquiry_questions(config(), {'item': '종이 상자', 'quantity': '500'}, company, client)
    sent = client.requests[0]['messages'][1]['content']
    assert company.products in sent and '종이 상자' in sent
    draft = inquiry(company.name, '종이 상자', '30cm', '500', '개', '', questions)
    assert '1. 포장 및 충전업으로 등록되어 있는데' in draft and '아직 발송되지 않았습니다' in draft
    with pytest.raises(AgentError):
        inquiry_questions(config(), {'item': '상자'}, None, FakeClient([final('{"questions":["' + '가' * 201 + '"]}')]))


def test_unconfirmed_extraction_and_read_boundaries():
    result = extract_quote(config(), '가격 미기재', FakeClient([final('{"item":"라벨"}')]))
    assert result.unit_price is None
    with pytest.raises(AgentError):
        extract_quote(config(), '원문', FakeClient([final('{"unit_price":-1}')]))
    assert quote_text('견적'.encode(), 'a.txt') == '견적'
    with pytest.raises(AgentError):
        quote_text(b'bad', 'a.exe')


def test_search_results_use_short_letters_and_miscopied_ids_are_blocked():
    # OpenAI 실호출에서 24자 업체 ID를 한 글자 틀리게 옮겨 적은 사례: 짧은 후보 번호(A, B…)로 고르게 한다.
    import json
    client = FakeClient([tool(), tool(), final('{"company_ids":["A"],"questions":[]}')])
    result = run_agent(config(), demo_companies(), SearchRequest(query='라벨'), client=client)
    assert result.hits[0].company.id == 'demo-print'
    shown = json.loads(client.requests[1]['messages'][-1]['content'])
    assert [row['id'] for row in shown] == ['A']  # 같은 업체는 다시 검색해도 같은 번호를 받는다.
    with pytest.raises(AgentError, match='근거'):
        run_agent(config(), demo_companies(), SearchRequest(query='라벨'),
                  client=FakeClient([tool(), final('{"company_ids":["demo-prinT"]}')]))
    with pytest.raises(AgentError, match='근거'):  # 번호와 실제 ID로 같은 업체를 두 번 고를 수 없다.
        run_agent(config(), demo_companies(), SearchRequest(query='라벨'),
                  client=FakeClient([tool(), final('{"company_ids":["A","demo-print"]}')]))
