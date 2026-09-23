from pathlib import Path
from streamlit.testing.v1 import AppTest

def button(at, label):
    return next(b for b in at.button if b.label == label)

def test_full_demo_ui(tmp_path, monkeypatch):
    monkeypatch.setenv('COPILOT_DATA_DIR',str(tmp_path))
    at = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'), default_timeout=30).run()
    assert not at.exception
    button(at,'加载演示项目').click().run()
    assert not at.exception
    button(at,'开始分析所选资料').click().run()
    assert not at.exception
    button(at,'确认口径并生成竞品对比').click().run()
    assert not at.exception
    button(at,'生成产品价值说明和销售问答').click().run()
    assert not at.exception
    assert any('修改后' in x.value for x in at.info)
    from copilot.store import Store
    p = Store(tmp_path).all()[0]
    assert {b['stage'] for b in p['batches']} == {'提取','对比','文案'}
    content = next(t for t in at.text_area if t.label == '修改内容')
    content.set_value(content.value + ' 请现场确认。')
    button(at,'保存审核').click().run()
    assert not at.exception
    p = Store(tmp_path).all()[0]
    assert p['reviews'][-1]['after']['status'] == '待审核'
    next(s for s in at.selectbox if s.label == '审核操作').select('已确认')
    next(c for c in at.checkbox if c.label.startswith('我已重新核对')).check()
    button(at,'保存审核').click().run()
    assert not at.exception
    assert Store(tmp_path).all()[0]['reviews'][-1]['after']['status'] == '已确认'
    assert len(at.get('download_button')) == 3
