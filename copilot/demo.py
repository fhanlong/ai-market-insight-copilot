from pathlib import Path
from .ingest import parse_file

def load_demo(store):
    p = store.create('模拟 · 循环水设备选型沟通', '工厂循环水输送', '采购与技术')
    for path in sorted((Path(__file__).resolve().parents[1] / 'samples').glob('*.txt')):
        data = path.read_bytes()
        category = '客户需求' if '客户' in path.name else ('行业简报' if '行业' in path.name else '产品资料')
        store.add(p, parse_file(path.name, data, simulated=True, category=category), data)
    return p
