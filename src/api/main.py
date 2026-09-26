from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List, Dict, Any

from src.data_loader import DataLoader
from src.product_master import ProductMaster
from src.inventory_engine import InventoryEngine
from src.low_stock_engine import LowStockEngine
from src.ai_assistant import AIAssistant
from src.api.schemas import ChatRequest, ChatResponse, StockLookupRequest, DataQualityItemResponse

app = FastAPI(
    title="Symax AI Stock Assistant API",
    description="Deterministic Chemical Inventory Calculation and LLM Assistant Backend",
    version="1.0.0"
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global Singletons
data_loader = DataLoader()
product_master = ProductMaster(data_loader)
inventory_engine = InventoryEngine(data_loader, product_master)
low_stock_engine = LowStockEngine(data_loader, product_master, inventory_engine)
ai_assistant = AIAssistant(data_loader, product_master, inventory_engine, low_stock_engine)


@app.get("/", include_in_schema=False)
def root_redirect():
    """Redirect root path to interactive Swagger documentation."""
    return RedirectResponse(url="/docs")


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "Symax AI Stock Assistant",
        "total_stock_records": len(data_loader.get_stock_data()),
        "total_min_stock_records": len(data_loader.get_minimum_stock_data())
    }

@app.post("/api/chat", response_model=ChatResponse)
def chat_endpoint(req: ChatRequest):
    try:
        resp = ai_assistant.process_query(req.query)
        return ChatResponse(
            answer=resp.answer,
            intent=resp.intent,
            sources=resp.sources,
            warnings=resp.warnings,
            query_details=resp.query_details
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/products")
def get_products():
    return [p.__dict__ for p in product_master.get_all_products()]

@app.get("/api/stock/cas/{cas_number}")
def get_stock_by_cas(cas_number: str, location: Optional[str] = None, concentration: Optional[str] = None):
    res = inventory_engine.get_stock_by_cas(cas_number, location, concentration)
    return res

@app.get("/api/stock/location/{location}")
def get_stock_by_location(location: str):
    return inventory_engine.get_stock_by_location(location)

@app.get("/api/stock/concentrations/{cas_number}")
def get_concentrations_for_cas(cas_number: str):
    return inventory_engine.get_concentrations_for_cas(cas_number)

@app.get("/api/stock/compare-locations")
def compare_locations():
    return inventory_engine.compare_locations()

@app.get("/api/stock/exclusive/hyderabad")
def get_exclusive_hyderabad():
    return inventory_engine.get_products_available_in_hyd_not_blr()

@app.get("/api/stock/exclusive/bangalore")
def get_exclusive_bangalore():
    return inventory_engine.get_products_available_in_blr_not_hyd()

@app.get("/api/stock/low-stock")
def get_low_stock():
    items = low_stock_engine.evaluate_all_stock(by_location=True)
    return [item.__dict__ for item in items]

@app.get("/api/purchase-requirements")
def get_purchase_requirements():
    reqs = low_stock_engine.generate_purchase_requirements()
    return [r.__dict__ for r in reqs]

@app.get("/api/data-quality-report", response_model=List[DataQualityItemResponse])
def get_data_quality_report():
    issues = data_loader.get_data_quality_issues()
    return [DataQualityItemResponse(**iss.__dict__) for iss in issues]
