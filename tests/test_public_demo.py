from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest
from copilot.store import Store, SessionStore

ENTRY = Path(__file__).resolve().parents[1] / 'demo_app.py'

def click(at, label):
    next(b for b in at.button if b.label == label).click().run()
    assert not at.exception
    assert not at.error

def test_public_demo_isolated_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setenv('COPILOT_DATA_DIR', str(tmp_path))
    local = Store(tmp_path)
    private = local.create('LOCAL_PRIVATE_SENTINEL', 'local', 'local')
    monkeypatch.setenv('OPENAI_API_KEY', 'unit-test-placeholder')
    monkeypatch.setenv('OPENAI_MODEL', 'unit-test-model')
    def forbidden(*args, **kwargs):
        raise AssertionError('Public demo must never construct a model client')
    monkeypatch.setattr('copilot.provider.OpenAIProvider.__init__', forbidden)
    first = AppTest.from_file(str(ENTRY), default_timeout=30).run()
    second = AppTest.from_file(str(ENTRY), default_timeout=30).run()
    assert not first.exception and not second.exception
    assert len(first.radio) == 0
    assert not any(s.label == '选择项目' for s in first.selectbox)
    click(first, '加载演示项目')
    assert first.get('file_uploader')[0].proto.disabled
    assert next(b for b in first.button if b.label == '本地导入并提取文字').disabled
    click(first, '开始分析所选资料')
    click(first, '确认口径并生成竞品对比')
    click(first, '生成产品价值说明和销售问答')
    assert len(first.get('download_button')) == 3
    edited = next(t for t in first.text_area if t.label == '修改内容')
    edited.set_value(edited.value + ' 待现场确认。')
    click(first, '保存审核')
    assert first.session_state['_demo_store'].all()[0]['reviews'][-1]['after']['status'] == '待审核'
    next(s for s in first.selectbox if s.label == '审核操作').select('已确认')
    next(c for c in first.checkbox if c.label.startswith('我已重新核对')).check()
    click(first, '保存审核')
    assert first.session_state['_demo_store'].all()[0]['reviews'][-1]['after']['status'] == '已确认'
    second.run()
    assert not second.session_state['_demo_store'].all()
    click(second, '加载演示项目')
    other_id = second.session_state['_demo_store'].all()[0]['id']
    assert first.session_state['_demo_store'].all()[0]['id'] != other_id
    click(first, '重置我的演示')
    assert not first.session_state['_demo_store'].all()
    assert second.session_state['_demo_store'].get(other_id)
    assert local.get(private['id'])['name'] == 'LOCAL_PRIVATE_SENTINEL'

def test_session_limits_and_api_guard():
    store = SessionStore()
    try:
        p = store.create('demo','','')
        with pytest.raises(ValueError, match='不允许'): store.reserve_call(p)
        store.create('second','',''); store.create('third','','')
        with pytest.raises(ValueError, match='最多'): store.create('fourth','','')
        p['batches'] = [{}] * 41
        with pytest.raises(ValueError, match='上限'): store.save(p)
        assert not store.get(p['id'])['batches']
    finally:
        store.close()
