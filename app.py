import json
import os
from datetime import date
import streamlit as st
import pandas as pd
from copilot.store import Store, SessionStore
from copilot.models import Source, Fact
from copilot.ingest import parse_file
from copilot.demo import load_demo
from copilot.engine import DIMENSIONS, rule_extract, validate_facts, compare, rule_copy, validate_copy, batch, key_for, review
from copilot.provider import OpenAIProvider, MAX_INPUT_CHARS
from copilot.exporting import exports

st.set_page_config(page_title='AI市场情报与产品营销助手', page_icon='◈', layout='wide')
public_demo = st.session_state.get('_public_demo', False)
if public_demo:
    if '_demo_store' not in st.session_state:
        st.session_state['_demo_store'] = SessionStore()
    store = st.session_state['_demo_store']
else:
    store = Store()
st.title('AI Market Insight Copilot')
st.caption('AI市场情报与产品营销助手 · 从资料证据到可审核的产品沟通')
st.caption('独立作品集 · 仅使用公开、授权或模拟资料 · 不代表任何企业官方系统')
if public_demo:
    st.info('在线演示 · 仅使用模拟资料，未调用真实模型。数据仅保留在当前访客会话内；刷新、断线或服务重启可能丢失，请及时导出。不要输入敏感信息。')

def action(fn):
    try:
        with st.spinner('正在处理，请稍候…'):
            fn()
        st.success('已完成并保存。')
        st.rerun()
    except ValueError as e:
        st.error(str(e))
    except Exception:
        st.error('处理未完成，已保存工作仍保留。请检查文件或配置后重试。')

projects = store.all()
if 'pending_project' in st.session_state:
    st.session_state['project'] = st.session_state.pop('pending_project')
with st.sidebar:
    st.header('工作空间')
    mode = '演示模式' if public_demo else st.radio('运行模式', ['演示模式', '模型模式'])
    model = os.getenv('OPENAI_MODEL', '') if mode == '模型模式' else ''
    st.caption('模型：' + (model or '未配置 / 不使用'))
    st.caption('API 调用已禁用' if public_demo else 'API Key：' + ('已从环境变量配置' if os.getenv('OPENAI_API_KEY') else '未配置'))
    if public_demo and st.button('重置我的演示'):
        store.close()
        st.session_state.clear()
        st.rerun()
    if st.button('加载演示项目', type='primary'):
        def demo():
            st.session_state['project'] = load_demo(store)['id']
        action(demo)
    if projects:
        ids = [p['id'] for p in projects]
        if st.session_state.get('project') not in ids: st.session_state['project'] = ids[0]
        pid = st.selectbox('选择项目', ids, format_func=lambda i: next(p['name'] for p in projects if p['id'] == i), key='project')
    with st.expander('创建项目', expanded=not projects):
        with st.form('create'):
            name = st.text_input('项目名称', max_chars=80)
            scene = st.text_input('目标应用场景', max_chars=300)
            role = st.text_input('目标客户角色', value='采购', max_chars=100)
            if st.form_submit_button('创建'):
                def create(): st.session_state['pending_project'] = store.create(name, scene, role)['id']
                action(create)
if mode == '演示模式':
    st.info('演示模式，未调用真实模型。使用确定性规则；可识别样例中的“字段：值 | 条件：…”格式，中英文标签均支持。' + ('完整上传与模型功能请下载源码在本地运行。' if public_demo else '自由文本请使用模型模式。'))
else:
    st.warning('模型模式：主动点击分析/生成后，将所选资料文本或提取事实发送至 OpenAI。每次最多40,000字符，每项目最多20次调用，无自动重试；请仅使用有权发送的资料。')
if not projects:
    st.info('从左侧加载演示项目，或创建项目并上传资料。')
    st.stop()
p = store.get(pid)
st.subheader(p['name'])
st.caption(f'场景：{p["scene"]} · 角色：{p["role"]} · 来源 {len(p["sources"])} · 模型调用 {p["api_calls"]}/20')
tabs = st.tabs(['1 项目与资料', '2 信息提取', '3 竞品对比', '4 产品价值与问答', '5 审核与导出'])

with tabs[0]:
    with st.expander('编辑项目范围'):
        with st.form('scope'):
            new_scene = st.text_input('应用场景', p['scene'], max_chars=300)
            new_role = st.text_input('客户角色', p['role'], max_chars=100)
            if st.form_submit_button('保存项目范围'):
                def scope():
                    if (new_scene, new_role) != (p['scene'], p['role']):
                        p.update(scene=new_scene, role=new_role)
                        store.invalidate(p)
                        store.save(p)
                action(scope)
    if public_demo:
        st.caption('在线版仅分析内置模拟资料，文件上传已关闭；每位访客独立操作，不读取本地项目数据库。')
    with st.form('upload', clear_on_submit=True):
        uploaded = st.file_uploader('上传资料（每文件≤10MB；TXT/CSV 使用UTF-8）', type=['pdf','docx','txt','csv'], disabled=public_demo)
        title = st.text_input('来源标题（可选）')
        url = st.text_input('原始URL（可选，仅保存，不抓取）')
        published = st.text_input('发布日期（可选 YYYY-MM-DD；未知留空）')
        category = st.selectbox('资料类别', ['产品资料','客户需求','行业简报','其他'])
        simulated = st.checkbox('此文件为模拟资料')
        if st.form_submit_button('本地导入并提取文字', disabled=public_demo):
            def upload():
                if public_demo: raise ValueError('在线演示不接收文件上传。')
                if not uploaded: raise ValueError('请先选择文件。')
                if url and not url.startswith(('https://','http://')): raise ValueError('URL 需以 http:// 或 https:// 开头。')
                if published: date.fromisoformat(published)
                data = uploaded.getvalue()
                source = parse_file(uploaded.name, data, title=title, url=url, published=published or None, category=category, simulated=simulated)
                store.add(p, source, data)
            action(upload)
    for s in p['sources']:
        with st.expander(('【模拟数据】' if s['simulated'] else '') + s['title']):
            st.json({k:v for k,v in s.items() if k != 'segments'})
            st.caption('状态：本地文字已提取；下方为完整提取预览。')
            st.dataframe(pd.DataFrame(s['segments']), hide_index=True, width='stretch')
            if st.button('移除此资料并使旧分析待复核', key='remove'+s['source_id']):
                action(lambda: store.remove(p, s['source_id']))
    with st.expander('删除项目'):
        sure = st.checkbox('确认删除该项目、关联文件与审核记录')
        if st.button('永久删除当前项目', disabled=not sure): action(lambda: store.delete(p['id']))

def latest(stage):
    return next((b for b in reversed(p['batches']) if b['stage'] == stage and not b['stale']), None)

def display_items(items):
    for item in items:
        with st.expander(f'[{item["status"]}] {item["title"]}', expanded=item['section'] == '价值表述'):
            st.write(item['content'])
            for w in item['warnings']: st.warning(w)
            st.caption('信息类型：' + ('来源事实的规则整理' if item['section'] == '竞品对比' else '营销表述建议／分析推断'))
            st.caption('语义支持：' + item['support'])
            for ref in item['evidence']:
                f = next((f for b in p['batches'] for f in b['facts'] if f['fact_id'] == ref), None)
                if f:
                    st.caption(f'{ref} · {f["source_id"]} · {f["locator"]} · 引用定位：{"有效" if f["citation_valid"] else "无效"}')
                    st.text(f['quote'])

with tabs[1]:
    source_ids = st.multiselect('选择要分析的资料', [s['source_id'] for s in p['sources']], default=[s['source_id'] for s in p['sources']], format_func=lambda i: next(s['title'] for s in p['sources'] if s['source_id'] == i))
    selected = [Source(**s) for s in p['sources'] if s['source_id'] in source_ids]
    payload_chars = len(json.dumps([s.model_dump() for s in selected], ensure_ascii=False))
    st.caption(f'处理范围：{len(selected)} 份资料，{sum(len(s.segments) for s in selected)} 个定位段；序列化输入 {payload_chars:,} 字符。全部所选可提取文字；不截断。')
    if st.button('开始分析所选资料', type='primary', disabled=not selected):
        def extract():
            inputs = {'source_ids':sorted(source_ids)}
            ck = key_for(p, mode, model, inputs)
            if any(b['cache_key'] == ck and b['stage'] == '提取' and not b['stale'] for b in p['batches']): return
            if mode == '模型模式':
                provider = OpenAIProvider()
                if payload_chars > MAX_INPUT_CHARS: raise ValueError('超出40,000字符，请减少所选资料。')
                store.reserve_call(p)
                facts = validate_facts(provider.extract(selected).facts, selected)
            else: facts = rule_extract(selected)
            if not facts: raise ValueError('没有识别到字段。规则模式请参考样例格式；自由文本可配置模型模式。')
            for b in p['batches']: b['stale'] = True
            batch(p, '提取', mode, model, inputs, facts=facts)
            store.save(p)
        action(extract)
    extraction = latest('提取')
    if extraction:
        st.caption(f'当前提取批次：{extraction["mode"]} / {extraction["model"] or "规则处理"}')
        st.caption('来源事实仅表示资料有此表述，不代表系统独立证实。定位校验与语义审核分开显示。')
        st.dataframe(pd.DataFrame(extraction['facts']), hide_index=True, width='stretch')
    else: st.info('请先选择资料并开始分析。旧批次可在审核页查看。')

facts = [Fact(**f) for f in extraction['facts']] if extraction else []
products = sorted({f.product for f in facts if f.product})
with tabs[2]:
    chosen = st.multiselect('比较产品（2—5个）', products, default=products[:3])
    dims = st.multiselect('比较维度', DIMENSIONS, default=DIMENSIONS)
    basis = st.text_input('比较口径说明', '仅比较已披露信息；同条件才可讨论差异，不生成排名', max_chars=1000)
    compare_inputs = {'products':chosen,'dimensions':dims,'basis':basis,'extraction':extraction['batch_id'] if extraction else ''}
    current_compare = latest('对比')
    if current_compare and current_compare['inputs'] != compare_inputs:
        current_compare['stale'] = True
        for b in p['batches']:
            if b['stage'] == '文案': b['stale'] = True
        store.save(p)
        st.warning('比较条件已变化，旧对比及文案需要重新生成。')
    st.caption('先确认产品、维度及口径，再生成。功率等条件不同的值不会排序。')
    if st.button('确认口径并生成竞品对比', disabled=not facts):
        def comparison():
            items = compare(facts, chosen, dims)
            for b in p['batches']:
                if b['stage'] in {'对比','文案'}: b['stale'] = True
            batch(p, '对比', '规则整理', '', compare_inputs, items=items)
            store.save(p)
        action(comparison)
    comparison_batch = latest('对比')
    if comparison_batch:
        st.dataframe(pd.DataFrame([{'产品 / 维度':x['title'],'披露':x['content'],'提示':'；'.join(x['warnings'])} for x in comparison_batch['items']]), hide_index=True, width='stretch')
        display_items(comparison_batch['items'])
    else: st.info('完成信息提取后选择产品。')

with tabs[3]:
    main = st.selectbox('主推产品', products) if products else ''
    target_scene = st.text_input('本次目标应用场景', p['scene'], max_chars=300)
    target_role = st.selectbox('本次客户角色', ['采购','技术','设备使用方'])
    needs = st.text_area('客户需求（可编辑；人工新增内容标为用户提供，待核验）', '\n'.join(f.value for f in facts if f.dimension == '客户关注点'), max_chars=5000 if public_demo else None)
    copy_inputs = {'product':main,'scene':target_scene,'role':target_role,'needs':needs,'comparison':comparison_batch['batch_id'] if comparison_batch else ''}
    current_copy = latest('文案')
    if current_copy and current_copy['inputs'] != copy_inputs:
        current_copy['stale'] = True
        store.save(p)
        st.warning('文案输入已变化，旧文案需要复核并重新生成。')
    st.caption('模型模式会发送当前提取事实（含原文摘录）与上述输入；不发送文件二进制。')
    if st.button('生成产品价值说明和销售问答', disabled=not comparison_batch):
        def copy():
            ck = key_for(p, mode, model, copy_inputs)
            if any(b['stage'] == '文案' and b['cache_key'] == ck and not b['stale'] for b in p['batches']): return
            if mode == '模型模式':
                provider = OpenAIProvider()
                if len(json.dumps({'facts':[f.model_dump() for f in facts], 'inputs':copy_inputs}, ensure_ascii=False)) > MAX_INPUT_CHARS: raise ValueError('事实输入超过40,000字符，请缩小项目资料范围。')
                store.reserve_call(p)
                items = validate_copy(provider.copy(facts, copy_inputs).items, facts)
            else: items = rule_copy(facts, main, target_scene, target_role, needs)
            for b in p['batches']:
                if b['stage'] == '文案': b['stale'] = True
            batch(p, '文案', mode, model, copy_inputs, items=items)
            store.save(p)
        action(copy)
    if latest('文案'):
        st.caption(f'当前文案批次：{latest("文案")["mode"]} / {latest("文案")["model"] or "规则处理"}')
        display_items(latest('文案')['items'])

with tabs[4]:
    st.info('修改后自动转为待审核。请保存修改后再次核对引用与语义支持，才能确认；不会覆盖原始摘录。')
    if p['batches']:
        b_id = st.selectbox('生成批次', [b['batch_id'] for b in reversed(p['batches'])], format_func=lambda bid: next(f'{b["stage"]} · {b["created"]} · {"需要复核" if b["stale"] else "当前"}' for b in p['batches'] if b['batch_id'] == bid))
        b = next(b for b in p['batches'] if b['batch_id'] == b_id)
        objs = b['facts'] + b['items']
        if objs:
            id_of = lambda x: x.get('fact_id', x.get('item_id'))
            obj_id = st.selectbox('逐项审核', [id_of(x) for x in objs], format_func=lambda i: next(x.get('title', x.get('dimension','')) + ' · ' + x['status'] for x in objs if id_of(x) == i))
            obj = next(x for x in objs if id_of(x) == obj_id)
            st.json(obj)
            if 'item_id' in obj: display_items([obj])
            with st.form('review'+obj_id):
                content = st.text_area('修改内容', obj.get('content', obj.get('value','')), height=130, max_chars=15000 if public_demo else None)
                status = st.selectbox('审核操作', ['待确认','已确认','驳回'])
                note = st.text_input('审核备注', max_chars=1000)
                checked = st.checkbox('我已重新核对原文、引用及内容的语义支持；不把定位有效当作已证实')
                if st.form_submit_button('保存审核'):
                    def save_review():
                        review(p, b, obj_id, content, status, note, checked)
                        store.save(p)
                    action(save_review)
        with st.expander('审核历史'):
            st.json(p['reviews'])
    else: st.info('生成结果后即可逐项审核。')
    confirmed = st.checkbox('仅导出已确认内容')
    st.caption('全部导出带“未审核草稿”标识；已确认筛选排除失效批次，保留证据上下文及原审核状态。')
    files = exports(p, confirmed)
    columns = st.columns(3)
    for col, ext, label, mime in zip(columns, ['csv','json','md'], ['竞品对比 CSV','完整结构化 JSON','Markdown 分析报告'], ['text/csv','application/json','text/markdown']):
        col.download_button(label, files[ext], file_name=f'market-insight.{ext}', mime=mime)
