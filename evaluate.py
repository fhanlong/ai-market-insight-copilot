"""Reproducible synthetic pipeline checks, never presented as real-world accuracy."""
import argparse
import json
import tempfile
from pathlib import Path
from copilot.demo import load_demo
from copilot.store import Store
from copilot.models import Source
from copilot.engine import rule_extract, compare, rule_copy, batch, review, validate_facts, validate_copy, DIMENSIONS
from copilot.ingest import citation_valid
from copilot.exporting import exports
from copilot.provider import OpenAIProvider

def run(real=False):
    labels = json.loads(Path('evaluation/labels.json').read_text(encoding='utf-8'))
    with tempfile.TemporaryDirectory() as root:
        store = Store(root); p = load_demo(store)
        sources = [Source(**s) for s in p['sources']]
        if real:
            provider = OpenAIProvider(); store.reserve_call(p)
            facts = validate_facts(provider.extract(sources).facts, sources)
        else: facts = rule_extract(sources)
        matches = sum(any(all(getattr(f,k) == v for k,v in row.items()) for f in facts) for row in labels['fields'])
        comparisons = compare(facts,['CC-75','NM-75','YT-8'],DIMENSIONS)
        by_title = {i.title:i for i in comparisons}
        if real:
            store.reserve_call(p)
            items = validate_copy(provider.copy(facts,dict(product='CC-75',scene=p['scene'],role=p['role'],needs='维护与服务')).items,facts)
        else: items = rule_copy(facts,'CC-75',p['scene'],p['role'],'维护与服务')
        b = batch(p,'提取','模型模式' if real else '演示模式',provider.model if real else '',{},facts=facts)
        batch(p,'对比','规则整理','',{},items=comparisons)
        batch(p,'文案','模型模式' if real else '演示模式',provider.model if real else '',{},items=items)
        edited = review(p,b,facts[0].fact_id,'人工修订','已确认','模拟评估',True)
        store.save(p)
        files = exports(store.get(p['id']))
        bad = facts[0].model_copy(update={'quote':'伪造摘录'})
        return {
            'mode':'真实API（模拟评估集）' if real else '演示规则（模拟数据；不代表模型效果）',
            'field_accuracy':matches / len(labels['fields']), 'field_denominator':len(labels['fields']),
            'citation_location_valid_rate':sum(citation_valid(f,sources) for f in facts)/len(facts),
            'missing_recognition':{t:by_title[t].content.startswith('未披露') for t in labels['missing']},
            'unit_conversion': '7.5 kW' in by_title['NM-75 / 功率'].content,
            'incomparable_recognition':any('不可直接比较' in w for w in by_title[labels['incomparable']].warnings),
            'conflict_recognition':any('来源冲突' in w for w in by_title[labels['conflict']].warnings),
            'unsupported_claim_check':{'review_required':True,'cost_answer_cautious':any('不能给出节省比例' in i.content or '资料不足' in i.content or '需验证' in i.content for i in items if i.section == '销售问答'), 'semantic_support':'需人工评估；措辞检查不证明无幻觉'},
            'invalid_citation_rejected':not citation_valid(bad,sources),
            'malicious_instruction_not_extracted':not any('环境密钥' in f.quote for f in facts),
            'edited_status_pending':edited['status'] == '待审核',
            'export_provenance_retained':bool(json.loads(files['json'])['sources']) and '审核' in files['md'].decode(),
            'end_to_end_complete':all(files.values()),
            'caveat':'引用定位正确不等于语义支持关系必然正确；字段指标仅统计五个人工标注字段的精确匹配。'
        }

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--real',action='store_true',help='主动向OpenAI发送模拟评估资料；最多两次调用')
    parser.add_argument('--output',default='evaluation/demo-results.json')
    args = parser.parse_args()
    result = run(args.real)
    path = Path('evaluation/real-results.json') if args.real and args.output == 'evaluation/demo-results.json' else Path(args.output)
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
