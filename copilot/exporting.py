import csv
import io
import json
from .models import now

def export_bundle(p, confirmed_only=False):
    batches = []
    for b in p['batches']:
        copy = json.loads(json.dumps(b))
        copy['facts'] = [x for x in copy['facts'] if not confirmed_only or (x['status'] == '已确认' and not b['stale'])]
        copy['items'] = [x for x in copy['items'] if not confirmed_only or (x['status'] == '已确认' and not b['stale'])]
        # Evidence is retained as labelled context, never promoted to confirmed content.
        ids = {ref for x in copy['items'] for ref in x['evidence']}
        copy['evidence_context'] = [f for other in p['batches'] for f in other['facts'] if f['fact_id'] in ids]
        batches.append(copy)
    alerts = sorted({f'{x["title"]}：{w}' for b in p['batches'] for x in b['items'] for w in x['warnings'] if x['section'] == '竞品对比'})
    return dict(project={k:p[k] for k in ('id','name','scene','role')}, generated=now(), label='仅已确认内容（证据上下文保留原审核状态）' if confirmed_only else '未审核草稿', warning='未披露不代表不具备；冲突不得择一认定；不同工况不可直接排序；引用定位有效不等于语义支持。', scope_alerts=alerts, sources=p['sources'], batches=batches, reviews=[] if confirmed_only else p['reviews'], audit_note='仅确认导出不包含修改前草稿；完整审核历史保留在本地项目。')

def exports(p, confirmed_only=False):
    bundle = export_bundle(p, confirmed_only)
    out = io.StringIO(newline='')
    writer = csv.writer(out)
    def safe(value):
        return "'" + value if value.lstrip().startswith(('=', '+', '-', '@')) else value
    writer.writerow(['标识','批次','模式','产品 / 维度','披露内容','提示','证据ID','来源及原文','审核状态','语义支持','需复核'])
    if bundle['scope_alerts']:
        writer.writerow(['范围风险提示','','','', '', safe('；'.join(bundle['scope_alerts'])), '', '', '提示保留，不属于已确认结论', '', ''])
    lines = [f'# {p["name"]} — {bundle["label"]}', f'生成日期：{bundle["generated"]}', f'范围：{p["scene"]}；客户角色：{p["role"]}', bundle['warning'], '## 来源']
    sources = {s['source_id']:s for s in p['sources']}
    lines += ['### 范围风险提示（含被筛除或历史内容的缺失/冲突提示，不属于已确认结论）'] + ['- ' + a for a in bundle['scope_alerts']]
    for b in p['batches']:
        sources.update({s['source_id']:s for s in b['sources']})
    for s in sources.values():
        lines.append(f'- {s["source_id"]} | {s["title"]} | 文件 {s["filename"]} | SHA256 {s["sha256"]} | 发布 {s["published"] or "未知"} | 导入 {s["imported"]} | 模拟 {s["simulated"]} | URL {s["url"] or "未提供"} | {s["coverage"]}')
    for b in bundle['batches']:
        lines += [f'## {b["stage"]} / 批次 {b["batch_id"]}', f'模式：{b["mode"]}；模型：{b["model"] or "未调用真实模型"}；需复核：{b["stale"]}', f'条件：{json.dumps(b["inputs"], ensure_ascii=False)}']
        evidence = {f['fact_id']:f for other in p['batches'] for f in other['facts']}
        for x in b['items']:
            citations = [evidence[r] for r in x['evidence'] if r in evidence]
            detail = '；'.join(f'{f["fact_id"]} / {f["source_id"]} / {f["locator"]} / 原文：{f["quote"]} / {f["status"]}' for f in citations)
            lines += [f'### [{x["section"]}] {x["title"]}', x['content'], f'提示：{"；".join(x["warnings"])}', f'审核：{x["status"]}；{x["support"]}', f'证据：{detail or "无，待核验"}']
            if x['section'] == '竞品对比':
                # Prevent spreadsheet formula injection even in user edits.
                row = [bundle['label'], b['batch_id'], b['mode'], x['title'], x['content'], '；'.join(x['warnings']), ','.join(x['evidence']), detail, x['status'], x['support'], str(b['stale'])]
                writer.writerow([safe(v) for v in row])
        for f in b['facts']:
            lines.append(f'- [{f["kind"]}] {f["fact_id"]} {f["product"]} {f["dimension"]}: {f["value"]} | {f["source_id"]} {f["locator"]} 原文：{f["quote"]} | 定位有效：{f["citation_valid"]} | {f["status"]} | {f["support"]}')
    return {'json':json.dumps(bundle, ensure_ascii=False, indent=2).encode('utf-8'), 'csv':out.getvalue().encode('utf-8-sig'), 'md':'\n\n'.join(lines).encode('utf-8')}
