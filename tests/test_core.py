import io
import json
import pytest
import pymupdf
from docx import Document
from copilot.demo import load_demo
from copilot.store import Store
from copilot.models import Source, Fact
from copilot.ingest import parse_file, citation_valid
from copilot.engine import rule_extract, compare, rule_copy, batch, review, normalize, key_for, DIMENSIONS
from copilot.exporting import exports

@pytest.fixture
def setup(tmp_path):
    store = Store(tmp_path)
    p = load_demo(store)
    facts = rule_extract([Source(**s) for s in p['sources']])
    return store, p, facts

def test_extraction_and_exact_citations(setup):
    _, p, facts = setup
    assert len(facts) >= 20
    assert all(f.citation_valid for f in facts)
    assert any(f.product == 'NM-75' and f.value == '7500 W' for f in facts)
    assert not any('环境密钥' in f.quote for f in facts)
    f = facts[0].model_copy(update={'quote':'不存在的引用'})
    assert not citation_valid(f, [Source(**s) for s in p['sources']])
    f.quote, f.source_id = facts[0].quote, 'invented'
    assert not citation_valid(f, [Source(**s) for s in p['sources']])

def test_comparison_flags(setup):
    _, _, facts = setup
    items = compare(facts, ['CC-75','NM-75','YT-8'], DIMENSIONS)
    assert normalize('7500 W') == '7.5 kW'
    assert any('来源冲突' in ' '.join(i.warnings) for i in items)
    assert any('不可直接比较' in ' '.join(i.warnings) for i in items)
    assert next(i for i in items if i.title == 'YT-8 / 维护').content.startswith('未披露')
    with pytest.raises(ValueError): compare(facts, ['CC-75'], DIMENSIONS)

def test_review_persistence_and_export(setup):
    store, p, facts = setup
    b = batch(p, '提取','演示模式','',{}, facts=facts)
    c = batch(p, '对比','规则整理','',{}, items=compare(facts,['CC-75','NM-75'],DIMENSIONS))
    original = facts[0].quote
    edited = review(p,b,facts[0].fact_id,'用户新增','已确认','修订',True)
    assert edited['status'] == '待审核' and edited['quote'] == original
    assert edited['kind'] == '待确认问题'
    assert c['stale']
    review(p,b,facts[0].fact_id,'用户新增','已确认','再次核对',True)
    store.save(p)
    saved = Store(store.root).get(p['id'])
    assert len(saved['reviews']) == 2
    result = exports(saved)
    assert result['csv'].startswith(b'\xef\xbb\xbf')
    data = json.loads(result['json'])
    assert data['sources'][0]['sha256'] and data['reviews'][0]['before']['quote']
    assert '未审核草稿' in result['md'].decode()
    confirmed = json.loads(exports(saved,True)['json'])
    assert not confirmed['batches'][1]['items']

def test_remove_duplicate_delete_isolation(setup):
    store,p,facts = setup
    batch(p,'提取','演示模式','',{},facts=facts)
    s = Source(**p['sources'][0])
    with pytest.raises(ValueError): store.add(p,s,b'x')
    other = store.create('other','','')
    store.remove(p,s.source_id)
    assert p['batches'][0]['stale']
    store.delete(p['id'])
    assert store.get(other['id'])['name'] == 'other'
    with store.connect() as db:
        assert db.execute('SELECT count(*) FROM files WHERE project_id=?',(p['id'],)).fetchone()[0] == 0

def test_file_validation_and_locators():
    for name in ['../evil.txt','x.exe','x\\evil.txt']:
        with pytest.raises(ValueError): parse_file(name,b'text')
    with pytest.raises(ValueError): parse_file('x.pdf',b'not pdf')
    doc = pymupdf.open()
    doc.new_page()
    with pytest.raises(ValueError, match='OCR'): parse_file('scan.pdf',doc.tobytes())
    doc.new_page().insert_text((50,50),'Power: 7500 W')
    s = parse_file('mixed.pdf',doc.tobytes())
    assert s.segments[0].locator == '页 2' and '页 1' in s.coverage
    d = Document(); d.add_paragraph('Power: 5 kW')
    out = io.BytesIO(); d.save(out)
    assert parse_file('x.docx',out.getvalue()).segments[0].locator == '段落 1'
    assert '2' in parse_file('x.csv',b'Power,Condition\n7500 W,20C').segments[0].locator

def test_value_and_keys(setup):
    _,p,facts = setup
    items = rule_copy(facts,'CC-75','循环水','采购','维护')
    assert len([i for i in items if i.section == '销售问答']) == 6
    assert any('不能给出节省比例' in i.content for i in items)
    assert key_for(p,'演示模式','',{'x':1}) != key_for(p,'演示模式','',{'x':2})
    assert key_for(p,'模型模式','a',{}) != key_for(p,'模型模式','b',{})

def test_call_budget(setup):
    store,p,_ = setup
    p['api_calls'] = 20; store.save(p)
    with pytest.raises(ValueError,match='20'): store.reserve_call(p)

def test_invalid_review_and_formula_csv(setup):
    _,p,facts = setup
    b = batch(p,'对比','规则整理','',{},items=compare(facts,['CC-75','NM-75'],['功率']))
    item = b['items'][0]
    with pytest.raises(ValueError): review(p,b,item['item_id'],item['content'],'已确认','',False)
    item['content'] = '=HYPERLINK("bad")'
    assert "'=HYPERLINK" in exports(p)['csv'].decode('utf-8-sig')
