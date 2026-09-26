import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data_loader import DataLoader
from src.inventory_engine import InventoryEngine
from src.product_master import ProductMaster
from src.low_stock_engine import LowStockEngine

def main():
    print("=== SYMAX AI STOCK ASSISTANT: DATASET AUDIT ===")
    dl = DataLoader()
    pm = ProductMaster(dl)
    inv = InventoryEngine(dl, pm)
    lse = LowStockEngine(dl, pm)

    print(f"Total Raw Stock Records: {len(dl.raw_stock_df)}")
    print(f"Total Minimum Stock Records: {len(dl.raw_min_stock_df)}")
    print(f"Unique Products Identified: {len(pm.get_all_products())}")
    print(f"Data Quality Issues Detected: {len(dl.get_data_quality_issues())}")

    print("\n--- LOCATION TOTALS ---")
    comp = inv.compare_locations()
    for unit, vals in comp["comparison"].items():
        print(f"{unit}: Hyd={vals['Hyderabad']:,.2f}, Blr={vals['Bangalore']:,.2f}, Total={vals['Total']:,.2f}")

    print("\n--- LOW STOCK SHORTAGES ---")
    low = lse.evaluate_all_stock(by_location=True)
    print(f"Total Facility Low Stock Items: {len(low)}")

if __name__ == "__main__":
    main()
