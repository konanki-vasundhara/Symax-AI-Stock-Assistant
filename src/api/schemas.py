from typing import Optional, List, Dict, Any
from pydantic import BaseModel

class ChatRequest(BaseModel):
    query: str

class ChatResponse(BaseModel):
    answer: str
    intent: str
    sources: List[str]
    warnings: List[str]
    query_details: Dict[str, Any]

class StockLookupRequest(BaseModel):
    cas_number: Optional[str] = None
    product_name: Optional[str] = None
    concentration: Optional[str] = None
    location: Optional[str] = None

class DataQualityItemResponse(BaseModel):
    issue_type: str
    record_id: Any
    sheet: str
    original_value: Any
    proposed_value: Any
    reason: str
    safe_to_include: bool
    requires_manual_review: bool
