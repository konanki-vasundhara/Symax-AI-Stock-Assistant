import pandas as pd
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from src.data_loader import DataLoader
from src.product_master import ProductMaster, ProductMasterRecord

@dataclass
class StockBreakdown:
    product_id: str
    product_name: str
    cas_number: str
    concentration: str
    unit: str
    location: str
    total_quantity: float
    record_count: int
    records: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

@dataclass
class StockSummaryResponse:
    cas_number: Optional[str]
    product_name: Optional[str]
    concentration: Optional[str]
    requested_location: Optional[str]
    total_quantity: float
    unit: str
    breakdowns: List[StockBreakdown]
    warnings: List[str]
    explanation: str

class InventoryEngine:
    def __init__(self, data_loader: DataLoader, product_master: ProductMaster):
        self.data_loader = data_loader
        self.product_master = product_master

    def get_stock_by_cas(self, cas_number: str, location: Optional[str] = None, concentration: Optional[str] = None) -> StockSummaryResponse:
        stock_df = self.data_loader.get_stock_data()
        clean_cas = cas_number.strip()
        
        # Filter matching records
        mask = (stock_df['norm_cas'] == clean_cas) & (stock_df['is_valid_stock'] == True)
        
        if location and location.lower() != "all":
            mask = mask & (stock_df['norm_location'].str.lower() == location.strip().lower())
            
        if concentration and concentration.lower() != "all":
            mask = mask & (stock_df['norm_concentration'].str.lower() == concentration.strip().lower())

        matched_df = stock_df[mask]
        
        # Check for non-valid stock (negative / missing) for audit warnings
        audit_mask = (stock_df['norm_cas'] == clean_cas) & (stock_df['is_valid_stock'] == False)
        audit_df = stock_df[audit_mask]
        warnings = []
        if not audit_df.empty:
            for _, r in audit_df.iterrows():
                warnings.append(f"Excluded record Stock_ID {r['Stock_ID']}: {r['Quantity']} {r['Unit']} ({r['inclusion_reason']}) at {r['norm_location']}")

        # Build breakdowns grouped by (Product, Concentration, Unit, Location)
        breakdowns: List[StockBreakdown] = []
        total_qty = 0.0
        primary_unit = ""

        if not matched_df.empty:
            grouped = matched_df.groupby(['norm_cas', 'norm_product_name', 'norm_concentration', 'Unit', 'norm_location'])
            for (cas, name, conc, unit, loc), grp in grouped:
                grp_total = float(grp['Quantity'].sum())
                primary_unit = str(unit).strip()
                recs = grp[['Stock_ID', 'Batch_No', 'Quantity', 'norm_location']].to_dict('records')
                
                breakdowns.append(StockBreakdown(
                    product_id=f"{cas}__{name.lower()}___{conc.lower()}",
                    product_name=name,
                    cas_number=cas,
                    concentration=conc,
                    unit=primary_unit,
                    location=loc,
                    total_quantity=grp_total,
                    record_count=len(grp),
                    records=recs
                ))
            total_qty = float(matched_df['Quantity'].sum())
        else:
            # Check if product exists in catalog even if 0 stock
            variants = self.product_master.cas_to_products.get(clean_cas, [])
            if variants:
                primary_unit = variants[0].unit

        loc_str = f" in {location}" if location and location.lower() != "all" else " across all locations"
        conc_str = f" ({concentration})" if concentration and concentration.lower() != "all" else ""
        explanation = f"Calculated verified on-hand stock for CAS {clean_cas}{conc_str}{loc_str} from {len(matched_df)} eligible physical records."

        return StockSummaryResponse(
            cas_number=clean_cas,
            product_name=breakdowns[0].product_name if breakdowns else None,
            concentration=concentration,
            requested_location=location,
            total_quantity=total_qty,
            unit=primary_unit or "Litre",
            breakdowns=breakdowns,
            warnings=warnings,
            explanation=explanation
        )

    def get_stock_by_product_name(self, product_name: str, location: Optional[str] = None, concentration: Optional[str] = None) -> StockSummaryResponse:
        stock_df = self.data_loader.get_stock_data()
        clean_name = product_name.strip().lower()

        mask = (stock_df['norm_product_name'].str.lower() == clean_name) & (stock_df['is_valid_stock'] == True)
        if location and location.lower() != "all":
            mask = mask & (stock_df['norm_location'].str.lower() == location.strip().lower())
        if concentration and concentration.lower() != "all":
            mask = mask & (stock_df['norm_concentration'].str.lower() == concentration.strip().lower())

        matched_df = stock_df[mask]
        
        # Excluded records warnings
        audit_mask = (stock_df['norm_product_name'].str.lower() == clean_name) & (stock_df['is_valid_stock'] == False)
        audit_df = stock_df[audit_mask]
        warnings = []
        if not audit_df.empty:
            for _, r in audit_df.iterrows():
                warnings.append(f"Excluded record Stock_ID {r['Stock_ID']}: {r['Quantity']} {r['Unit']} ({r['inclusion_reason']}) at {r['norm_location']}")

        breakdowns: List[StockBreakdown] = []
        total_qty = 0.0
        primary_unit = ""

        if not matched_df.empty:
            grouped = matched_df.groupby(['norm_cas', 'norm_product_name', 'norm_concentration', 'Unit', 'norm_location'])
            for (cas, name, conc, unit, loc), grp in grouped:
                grp_total = float(grp['Quantity'].sum())
                primary_unit = str(unit).strip()
                recs = grp[['Stock_ID', 'Batch_No', 'Quantity', 'norm_location']].to_dict('records')
                
                breakdowns.append(StockBreakdown(
                    product_id=f"{cas}__{name.lower()}___{conc.lower()}",
                    product_name=name,
                    cas_number=cas,
                    concentration=conc,
                    unit=primary_unit,
                    location=loc,
                    total_quantity=grp_total,
                    record_count=len(grp),
                    records=recs
                ))
            total_qty = float(matched_df['Quantity'].sum())

        loc_str = f" in {location}" if location and location.lower() != "all" else " across all locations"
        explanation = f"Calculated verified on-hand stock for '{product_name}'{loc_str} from {len(matched_df)} eligible physical records."

        return StockSummaryResponse(
            cas_number=breakdowns[0].cas_number if breakdowns else None,
            product_name=product_name,
            concentration=concentration,
            requested_location=location,
            total_quantity=total_qty,
            unit=primary_unit or "Unit",
            breakdowns=breakdowns,
            warnings=warnings,
            explanation=explanation
        )

    def get_stock_by_location(self, location: str) -> Dict[str, Any]:
        """Aggregate total confirmed stock in a specific location by Unit."""
        stock_df = self.data_loader.get_stock_data()
        clean_loc = location.strip().lower()

        mask = (stock_df['norm_location'].str.lower() == clean_loc) & (stock_df['is_valid_stock'] == True)
        matched_df = stock_df[mask]

        unit_totals = {}
        for unit, grp in matched_df.groupby('Unit'):
            unit_totals[str(unit).strip()] = float(grp['Quantity'].sum())

        # Excluded records
        audit_mask = (stock_df['norm_location'].str.lower() == clean_loc) & (stock_df['is_valid_stock'] == False)
        audit_df = stock_df[audit_mask]
        warnings = [f"Excluded Stock_ID {r['Stock_ID']}: {r['Quantity']} {r['Unit']} ({r['inclusion_reason']})" for _, r in audit_df.iterrows()]

        return {
            "location": location.capitalize(),
            "record_count": len(matched_df),
            "unit_totals": unit_totals,
            "warnings": warnings,
            "excluded_count": len(audit_df)
        }

    def get_concentrations_for_cas(self, cas_number: str) -> List[Dict[str, Any]]:
        clean_cas = cas_number.strip()
        stock_df = self.data_loader.get_stock_data()
        
        cas_df = stock_df[(stock_df['norm_cas'] == clean_cas) & (stock_df['is_valid_stock'] == True)]
        results = []
        
        for (conc, name, unit), grp in cas_df.groupby(['norm_concentration', 'norm_product_name', 'Unit']):
            hyd_qty = float(grp[grp['norm_location'] == 'Hyderabad']['Quantity'].sum())
            blr_qty = float(grp[grp['norm_location'] == 'Bangalore']['Quantity'].sum())
            total_qty = float(grp['Quantity'].sum())
            
            results.append({
                "concentration": conc,
                "product_name": name,
                "unit": unit,
                "total_quantity": total_qty,
                "hyderabad_quantity": hyd_qty,
                "bangalore_quantity": blr_qty,
                "record_count": len(grp)
            })
        return results

    def compare_locations(self) -> Dict[str, Any]:
        hyd_summary = self.get_stock_by_location("Hyderabad")
        blr_summary = self.get_stock_by_location("Bangalore")

        return {
            "Hyderabad": hyd_summary,
            "Bangalore": blr_summary,
            "comparison": {
                "Litre": {
                    "Hyderabad": hyd_summary["unit_totals"].get("Litre", 0.0),
                    "Bangalore": blr_summary["unit_totals"].get("Litre", 0.0),
                    "Total": hyd_summary["unit_totals"].get("Litre", 0.0) + blr_summary["unit_totals"].get("Litre", 0.0)
                },
                "Kg": {
                    "Hyderabad": hyd_summary["unit_totals"].get("Kg", 0.0),
                    "Bangalore": blr_summary["unit_totals"].get("Kg", 0.0),
                    "Total": hyd_summary["unit_totals"].get("Kg", 0.0) + blr_summary["unit_totals"].get("Kg", 0.0)
                }
            }
        }

    def get_products_available_in_hyd_not_blr(self) -> List[Dict[str, Any]]:
        stock_df = self.data_loader.get_stock_data()
        valid_df = stock_df[stock_df['is_valid_stock'] == True]

        hyd_prods = valid_df[valid_df['norm_location'] == 'Hyderabad'].groupby(['norm_cas', 'norm_product_name', 'norm_concentration', 'Unit'])['Quantity'].sum().reset_index()
        blr_prods = valid_df[valid_df['norm_location'] == 'Bangalore'].groupby(['norm_cas', 'norm_product_name', 'norm_concentration', 'Unit'])['Quantity'].sum().reset_index()

        hyd_prods = hyd_prods[hyd_prods['Quantity'] > 0]
        blr_prods = blr_prods[blr_prods['Quantity'] > 0]

        blr_keys = set(zip(blr_prods['norm_cas'], blr_prods['norm_concentration']))
        
        exclusive_hyd = []
        for _, row in hyd_prods.iterrows():
            key = (row['norm_cas'], row['norm_concentration'])
            if key not in blr_keys:
                exclusive_hyd.append({
                    "cas_number": row['norm_cas'],
                    "product_name": row['norm_product_name'],
                    "concentration": row['norm_concentration'],
                    "unit": row['Unit'],
                    "hyderabad_quantity": float(row['Quantity'])
                })
        return exclusive_hyd

    def get_products_available_in_blr_not_hyd(self) -> List[Dict[str, Any]]:
        stock_df = self.data_loader.get_stock_data()
        valid_df = stock_df[stock_df['is_valid_stock'] == True]

        hyd_prods = valid_df[valid_df['norm_location'] == 'Hyderabad'].groupby(['norm_cas', 'norm_product_name', 'norm_concentration', 'Unit'])['Quantity'].sum().reset_index()
        blr_prods = valid_df[valid_df['norm_location'] == 'Bangalore'].groupby(['norm_cas', 'norm_product_name', 'norm_concentration', 'Unit'])['Quantity'].sum().reset_index()

        hyd_prods = hyd_prods[hyd_prods['Quantity'] > 0]
        blr_prods = blr_prods[blr_prods['Quantity'] > 0]

        hyd_keys = set(zip(hyd_prods['norm_cas'], hyd_prods['norm_concentration']))
        
        exclusive_blr = []
        for _, row in blr_prods.iterrows():
            key = (row['norm_cas'], row['norm_concentration'])
            if key not in hyd_keys:
                exclusive_blr.append({
                    "cas_number": row['norm_cas'],
                    "product_name": row['norm_product_name'],
                    "concentration": row['norm_concentration'],
                    "unit": row['Unit'],
                    "bangalore_quantity": float(row['Quantity'])
                })
        return exclusive_blr
