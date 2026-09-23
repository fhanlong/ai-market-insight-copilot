from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4
from pydantic import BaseModel, Field

def uid():
    return uuid4().hex

def now():
    return datetime.now(timezone.utc).isoformat()

class Segment(BaseModel):
    locator: str
    text: str

class Source(BaseModel):
    source_id: str = Field(default_factory=uid)
    filename: str
    sha256: str
    title: str
    url: str = ""
    published: str | None = None
    imported: str = Field(default_factory=now)
    category: str = "产品资料"
    simulated: bool = False
    segments: list[Segment]
    coverage: str = "全文本提取（不含图片、嵌入对象）"

class FactDraft(BaseModel):
    source_id: str
    locator: str
    quote: str
    supplier: str
    product: str
    dimension: str
    value: str
    unit: str
    condition: str
    kind: Literal["来源事实", "分析推断", "营销表述建议", "待确认问题"]

class Fact(FactDraft):
    fact_id: str = Field(default_factory=uid)
    citation_valid: bool = False
    status: str = "待审核"
    support: str = "未核验语义支持"

class Extraction(BaseModel):
    facts: list[FactDraft]

class Item(BaseModel):
    item_id: str = Field(default_factory=uid)
    section: str
    title: str
    content: str
    evidence: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    status: str = "待审核"
    support: str = "未核验语义支持"

class CopyDraft(BaseModel):
    section: Literal["价值链", "价值表述", "沟通要点", "技术确认", "不建议使用", "销售问答"]
    title: str
    content: str
    evidence: list[str]
    warnings: list[str]

class CopyOutput(BaseModel):
    items: list[CopyDraft]
