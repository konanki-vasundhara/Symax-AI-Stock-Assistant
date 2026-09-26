import pandas as pd
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from src.data_loader import DataLoader
from src.product_master import ProductMaster


@dataclass
class LowStockItem:
    cas_number: str
    product_name: str
    concentration: str
    location: str
    current_stock: float
    minimum_stock: float
    deficit: float
    unit: str
    status: str  # 'CRITICAL', 'LOW', 'OK'


class LowStockResult(list):
    def __init__(self, items: List[LowStockItem], company_wide: List[Dict[str, Any]], by_location: Dict[str, List[Dict[str, Any]]]):
        super().__init__(items)
        self.company_wide = company_wide
        self.by_location = by_location

    def __getitem__(self, key):
        if key == 'company_wide':
            return self.company_wide
        if key == 'by_location':
            return self.by_location
        return super().__getitem__(key)

    def get(self, key, default=None):
        if key == 'company_wide':
            return self.company_wide
        if key == 'by_location':
            return self.by_location
        return default


@dataclass
class PurchaseRequirement:
    requirement_id: str
    scope: str
    cas_number: str
    product_name: str
    concentration: str
    location: str
    current_stock: float
    minimum_stock: float
    required_quantity: float
    unit: str
    priority: str
    reason: str = ''
    approval_status: str = 'Pending Approval'

    def to_dict(self) -> Dict[str, Any]:
        return {
            'requirement_id': self.requirement_id,
            'scope': self.scope,
            'cas_number': self.cas_number,
            'product_name': self.product_name,
            'concentration': self.concentration,
            'available_stock': self.current_stock,
            'minimum_stock': self.minimum_stock,
            'shortage_quantity': self.required_quantity,
            'unit': self.unit,
            'reason': self.reason or f'Stock deficit of {self.required_quantity:,.2f} {self.unit} in {self.location}.',
            'approval_status': self.approval_status
        }


class LowStockEngine:
    def __init__(self, data_loader: DataLoader, product_master: ProductMaster, inventory_engine: Optional[Any] = None):
        self.data_loader = data_loader
        self.product_master = product_master
        self.inventory_engine = inventory_engine

    def evaluate_all_stock(self, by_location: bool = True) -> LowStockResult:
        min_df = self.data_loader.get_minimum_stock_data()
        stock_df = self.data_loader.get_stock_data()
        valid_stock = stock_df[stock_df['is_valid_stock'] == True]

        items_list: List[LowStockItem] = []
        cw_dicts: List[Dict[str, Any]] = []
        by_loc_dicts: Dict[str, List[Dict[str, Any]]] = {'Hyderabad': [], 'Bangalore': []}

        for _, min_row in min_df.iterrows():
            cas = min_row['norm_cas']
            name = min_row['norm_product_name']
            conc = min_row['norm_concentration']
            unit = str(min_row['Unit']).strip()
            min_thresh = float(min_row['Minimum_Stock'])
            min_loc = min_row['norm_location']

            locations_to_check = ['Hyderabad', 'Bangalore']
            if min_loc in ['Hyderabad', 'Bangalore']:
                locations_to_check = [min_loc]

            for loc in locations_to_check:
                matching_stock = valid_stock[
                    (valid_stock['norm_cas'] == cas) &
                    (valid_stock['norm_concentration'].str.lower() == conc.lower()) &
                    (valid_stock['norm_location'] == loc)
                ]

                current_qty = float(matching_stock['Quantity'].sum()) if not matching_stock.empty else 0.0
                deficit = max(0.0, min_thresh - current_qty)
                status = 'OK'
                if current_qty == 0:
                    status = 'CRITICAL'
                elif current_qty < min_thresh:
                    status = 'LOW'

                row_dict = {
                    'cas_number': cas,
                    'product_name': name,
                    'concentration': conc,
                    'available_stock': current_qty,
                    'minimum_stock': min_thresh,
                    'shortage': deficit,
                    'unit': unit,
                    'status': status
                }
                by_loc_dicts[loc].append(row_dict)

                if current_qty < min_thresh:
                    items_list.append(LowStockItem(
                        cas_number=cas,
                        product_name=name,
                        concentration=conc,
                        location=loc,
                        current_stock=current_qty,
                        minimum_stock=min_thresh,
                        deficit=deficit,
                        unit=unit,
                        status=status
                    ))

            matching_stock_all = valid_stock[
                (valid_stock['norm_cas'] == cas) &
                (valid_stock['norm_concentration'].str.lower() == conc.lower())
            ]
            cw_qty = float(matching_stock_all['Quantity'].sum()) if not matching_stock_all.empty else 0.0
            cw_deficit = max(0.0, min_thresh - cw_qty)
            cw_status = 'OK'
            if cw_qty == 0:
                cw_status = 'CRITICAL'
            elif cw_qty < min_thresh:
                cw_status = 'LOW'

            cw_dicts.append({
                'cas_number': cas,
                'product_name': name,
                'concentration': conc,
                'available_stock': cw_qty,
                'minimum_stock': min_thresh,
                'shortage': cw_deficit,
                'unit': unit,
                'status': cw_status
            })

        return LowStockResult(items=items_list, company_wide=cw_dicts, by_location=by_loc_dicts)

    def generate_purchase_requirements(self, evaluation_scope: str = 'location') -> List[PurchaseRequirement]:
        low_items = self.evaluate_all_stock(by_location=True)
        requirements: List[PurchaseRequirement] = []

        counter = 1001
        for item in low_items:
            priority = 'HIGH' if item.status == 'CRITICAL' else 'MEDIUM'
            requirements.append(PurchaseRequirement(
                requirement_id=f'PR-{counter}',
                scope=f'Facility ({item.location})',
                cas_number=item.cas_number,
                product_name=item.product_name,
                concentration=item.concentration,
                location=item.location,
                current_stock=item.current_stock,
                minimum_stock=item.minimum_stock,
                required_quantity=item.deficit,
                unit=item.unit,
                priority=priority,
                reason=f'Stock deficit of {item.deficit:,.2f} {item.unit} vs minimum {item.minimum_stock:,.2f} {item.unit} at {item.location}.',
                approval_status='Pending Approval'
            ))
            counter += 1

        return sorted(requirements, key=lambda x: (x.priority == 'HIGH', x.required_quantity), reverse=True)
