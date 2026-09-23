import hashlib
import json
import re
from .models import Fact, Item, Source, uid, now
from .ingest import citation_valid

PROMPT_VERSION = '2026-09-v1'
DIMENSIONS = ['应用场景', '功率', '测试条件', '维护', '服务', '认证', '未披露信息']

def key_for(p, mode, model, inputs):
    data = [sorted(s['sha256'] for s in p['sources']), p['revision'], inputs, PROMPT_VERSION, mode, model, 'responses.parse;max_output_tokens=6000;timeout=60;retry=0']
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

def rule_extract(sources):
    """Deliberately narrow labelled-text parser; arbitrary prose is not claimed understood."""
    result = []
    aliases = {'Supplier':'供应商','Product':'产品','Power':'功率','Application':'应用场景','Condition':'测试条件','Maintenance':'维护','Service':'服务','Certification':'认证','Need':'客户关注点','Industry':'行业信息'}
    allowed = set(DIMENSIONS + ['客户关注点', '行业信息', '供应商', '产品'])
    for s in sources:
        supplier, product = '', ''
        for segment in s.segments:
            for line in segment.text.splitlines():
                cells = [x.strip() for x in line.split('|')]
                m = re.match(r'^([^:：]+)[:：]\s*(.+)$', cells[0])
                if not m:
                    continue
                dim = aliases.get(m[1].strip(), m[1].strip())
                value = m[2].strip()
                if dim not in allowed:
                    continue
                if dim == '供应商': supplier = value
                if dim == '产品': product = value
                condition = cells[1].removeprefix('条件:').removeprefix('条件：').strip() if len(cells) > 1 else ''
                unit = (re.search(r'(kW|W|小时|h)\b', value) or [None, ''])[1]
                f = Fact(source_id=s.source_id, locator=segment.locator, quote=line.strip(), supplier=supplier, product=product, dimension=dim, value=value, unit=unit, condition=condition, kind='来源事实')
                f.citation_valid = citation_valid(f, sources)
                result.append(f)
    return result

def validate_facts(drafts, sources):
    facts = [Fact(**d.model_dump()) for d in drafts]
    for f in facts:
        f.citation_valid = citation_valid(f, sources)
        if not f.citation_valid:
            raise ValueError('模型返回无效来源、定位或原文摘录；本次结果未保存，请重试或减少资料。')
    return facts

def normalize(value):
    m = re.fullmatch(r'\s*(\d+(?:\.\d+)?)\s*(kW|W)\s*', value)
    if m:
        return f'{float(m[1]) / (1000 if m[2] == "W" else 1):g} kW'
    return value

def compare(facts, products, dimensions):
    if not 2 <= len(products) <= 5 or not dimensions:
        raise ValueError('请选择 2—5 个产品和至少一个比较维度。')
    items = []
    for dim in dimensions:
        all_matches = [f for f in facts if f.product in products and f.dimension == dim and f.kind == '来源事实' and f.status != '驳回' and f.citation_valid]
        conditions = {f.condition for f in all_matches}
        for product in products:
            matches = [f for f in all_matches if f.product == product]
            warnings = []
            if dim == '未披露信息':
                missing = [d for d in DIMENSIONS[:-1] if not any(f.product == product and f.dimension == d and f.kind == '来源事实' and f.citation_valid and f.status != '驳回' for f in facts)]
                content = '未披露：' + ('、'.join(missing) or '本次选定维度暂无缺项') + '。未披露不代表不具备。'
            elif not matches:
                content = '未披露（不代表不具备）'
                warnings.append('缺失信息，需向供应商确认')
            else:
                values = {normalize(f.value) for f in matches}
                if len(values) > 1:
                    warnings.append('来源冲突或口径差异：保留全部披露，需确认')
                if dim in {'功率', '维护', '测试条件'} and (len(conditions) > 1 or '' in conditions):
                    warnings.append('不可直接比较：条件不同或未披露，需确认；不排序')
                if dim == '功率' and any(normalize(f.value) == f.value and not re.fullmatch(r'\d+(?:\.\d+)? kW', f.value) for f in matches):
                    warnings.append('单位含义不明确，需确认')
                content = '；'.join(f'{normalize(f.value)}（原值：{f.value}；条件：{f.condition or "未披露"}）' for f in matches)
            items.append(Item(section='竞品对比', title=f'{product} / {dim}', content=content, evidence=[f.fact_id for f in matches], warnings=warnings))
    return items

def rule_copy(facts, product, scene, role, needs):
    selected = [f for f in facts if f.product == product and f.kind == '来源事实' and f.citation_valid and f.status != '驳回' and f.dimension not in {'供应商','产品'}]
    if not selected:
        raise ValueError('主推产品缺少可引用事实。')
    refs = [f.fact_id for f in selected]
    warning = ['潜在价值，需验证；引用定位有效不代表语义支持已确认']
    items = [Item(section='价值链', title=f'{product} · {role}', content=f'客户需求：{needs or "待补充"}（用户提供，待核验） → 产品特点：{selected[0].value} → 潜在客户利益：可作为{scene}选型验证候选 → 支持证据：见引用 → 适用条件／待验证项：需技术人员核对工况、负载和现场试验。', evidence=refs, warnings=warning), Item(section='价值表述', title='简短产品价值表述', content=f'针对{scene}的{role}需求，可将{product}纳入技术评估。当前资料提供初步选型依据，适配效果及维护成本仍需现场验证。', evidence=refs, warnings=warning)]
    for f in selected[:5]:
        items.append(Item(section='沟通要点', title=f.dimension, content=f'资料披露：{f.value}。适用条件：{f.condition or "未披露，需确认"}。', evidence=[f.fact_id], warnings=warning))
    items.append(Item(section='技术确认', title='待补充资料', content='请补充同工况测试、维护周期定义、易损件价格、服务范围、认证证书和当前有效性。', evidence=refs, warnings=['需要技术／业务确认']))
    items.append(Item(section='不建议使用', title='未经验证表述', content='不建议对外宣称：最佳产品、保证降低成本30%、必定优于竞品、未披露认证即未获认证。', evidence=[], warnings=['缺乏支持证据，禁止作为已证实承诺']))
    questions = [('为什么考虑该产品？', '可基于已披露参数开展初步选型；客户收益属于潜在价值，需验证。'), ('适用场景与限制是什么？', f'拟用于{scene}，实际负载、环境和限制需技术确认。'), ('与竞品有什么已知差异？', '请参照对比表中的原值、工况和冲突标识；不同条件数据不可排序。'), ('需要怎样测试？', '需要在相同工况下验证功率、性能和维护要求，并记录验收口径。'), ('能节省多少使用成本？', '资料不足，不能给出节省比例；需要能耗、运行时长、备件与人工费用。'), ('价格、交付、质保如何？', '需要技术／业务确认；当前资料不足以作出承诺。')]
    for q, a in questions:
        items.append(Item(section='销售问答', title=q, content=a, evidence=refs, warnings=['需要技术／业务确认']))
    return items

def validate_copy(drafts, facts):
    valid_ids = {f.fact_id for f in facts if f.citation_valid and f.status != '驳回'}
    items = []
    for d in drafts:
        if not set(d.evidence) <= valid_ids:
            raise ValueError('文案包含无效事实标识，本次结果未保存。')
        item = Item(**d.model_dump())
        if not item.evidence:
            item.warnings.append('无来源支持，用户／模型提供，待核验')
        if re.search(r'\d+(?:\.\d+)?\s*[%％]|最佳|保证|承诺', item.content):
            item.warnings.append('检测到比例或承诺措辞：需人工核实，不得直接对外使用')
        items.append(item)
    qas = [i for i in items if i.section == '销售问答']
    points = [i for i in items if i.section == '沟通要点']
    if not 5 <= len(qas) <= 8 or not 3 <= len(points) <= 5:
        raise ValueError('结构化内容不完整：要求 5—8 条问答及 3—5 条沟通要点。')
    if not {'价值链','价值表述','技术确认','不建议使用'} <= {i.section for i in items}:
        raise ValueError('结构化内容缺少价值说明或待确认部分，请重试。')
    if any(not i.evidence for i in qas + points):
        raise ValueError('问答或沟通要点缺少证据关联，请重试。')
    return items

def batch(p, stage, mode, model, inputs, facts=None, items=None):
    b = dict(batch_id=uid(), stage=stage, mode=mode, model=model, prompt_version=PROMPT_VERSION, created=now(), cache_key=key_for(p, mode, model, inputs), inputs=inputs, stale=False, facts=[f.model_dump() for f in facts or []], items=[i.model_dump() for i in items or []], sources=p['sources'].copy())
    p['batches'].append(b)
    return b

def review(p, b, identifier, content, status, note, refs_confirmed=False):
    obj = next((x for x in b['facts'] + b['items'] if x.get('fact_id', x.get('item_id')) == identifier), None)
    if obj is None: raise ValueError('审核项不存在。')
    before = json.loads(json.dumps(obj))
    field = 'value' if 'fact_id' in obj else 'content'
    changed = content != obj[field]
    if status == '已确认':
        if b['stale']: raise ValueError('旧批次需重新生成，不能确认为当前有效。')
        if not refs_confirmed: raise ValueError('确认前必须核对引用及语义支持。')
        if 'fact_id' in obj and not obj['citation_valid']: raise ValueError('无效引用不可确认。')
        if 'item_id' in obj and not obj['evidence']: raise ValueError('无证据内容不能作为已确认事实导出。')
    obj[field] = content
    obj['status'] = '待审核' if changed else status
    obj['support'] = '人工修改，引用需重新确认；无来源新增内容属于用户提供，待核验' if changed else ('人工确认语义支持' if status == '已确认' else '未核验语义支持')
    if 'fact_id' in obj and changed:
        obj['kind'] = '待确认问题'
    elif 'fact_id' in obj and status == '已确认':
        obj['kind'] = '来源事实'
    p['reviews'].append(dict(review_id=uid(), batch_id=b['batch_id'], item_id=identifier, before=before, after=json.loads(json.dumps(obj)), requested_status=status, note=note, time=now(), source_ids=[s['source_id'] for s in b['sources']]))
    # Changed/rejected facts invalidate dependent analysis; preserve raw quote.
    if 'fact_id' in obj and (changed or status == '驳回'):
        for other in p['batches']:
            if other['stage'] != '提取': other['stale'] = True
    return obj
