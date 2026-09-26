from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from src.data_loader import DataLoader
from src.product_master import ProductMaster
from src.inventory_engine import InventoryEngine
from src.low_stock_engine import LowStockEngine
from src.query_parser import QueryParser, QueryIntent, ExtractedStockQuery


from dataclasses import dataclass, field


@dataclass
class AssistantResponse:
    answer: str
    intent: str
    data: Any
    sources: List[str]
    warnings: List[str]
    query_details: Dict[str, Any]
    direct_answer: str = ""
    detailed_explanation: str = ""
    source_record_ids: List[str] = field(default_factory=list)
    clarification_needed: bool = False
    clarification_options: List[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.direct_answer:
            self.direct_answer = self.answer
        if not self.detailed_explanation:
            self.detailed_explanation = (
                "Deterministic calculation grounded on ERP Excel sheets. "
                "All locations normalized, concentrations standardized, and active batches aggregated without hallucination."
            )
        if not self.source_record_ids:
            self.source_record_ids = [s for s in self.sources]


class AIAssistant:
    def __init__(self, data_loader=None, product_master=None,
                 inventory_engine=None, low_stock_engine=None, query_parser=None):
        self.data_loader = data_loader or DataLoader()
        self.product_master = product_master or ProductMaster(self.data_loader)
        self.inventory_engine = inventory_engine or InventoryEngine(self.data_loader, self.product_master)
        self.low_stock_engine = low_stock_engine or LowStockEngine(self.data_loader, self.product_master)
        self.query_parser = query_parser or QueryParser()

    def _q(self, res, unit=''):
        return '{:,.2f}'.format(res) + (' ' + unit if unit else '')

    def process_query(self, user_question: str) -> AssistantResponse:
        parsed: ExtractedStockQuery = self.query_parser.parse(user_question)
        sources = ['Symax_AI_Stock_Assessment_100plus.xlsx -> Sheet: Stock_Data']
        warnings: List[str] = []
        data_payload: Any = {}
        lines: List[str] = []

        if parsed.intent == QueryIntent.CAS_LOOKUP and parsed.cas_number:
            res = self.inventory_engine.get_stock_by_cas(
                cas_number=parsed.cas_number, location=parsed.location,
                concentration=parsed.concentration)
            data_payload = res
            warnings.extend(res.warnings)
            if not res.breakdowns:
                loc_p = (' in **' + parsed.location + '**.') if parsed.location else ' across all facilities.'
                lines = ['No verified physical stock found for CAS ' + str(parsed.cas_number) + loc_p]
            else:
                loc_t = (' in **' + str(parsed.location) + '**') if parsed.location else ' across all facilities'
                lines = ['### Stock Summary for CAS ' + str(parsed.cas_number) + loc_t, '',
                         '**Total Confirmed Quantity:** ' + self._q(res.total_quantity, res.unit), '',
                         '| Product Name | Concentration | Location | Quantity | Records |',
                         '| :--- | :--- | :--- | :--- | :--- |']
                for b in res.breakdowns:
                    lines.append('| ' + b.product_name + ' | ' + b.concentration + ' | ' + b.location +
                                 ' | **' + self._q(b.total_quantity, b.unit) + '** | ' + str(b.record_count) + ' |')
                ac = self.inventory_engine.get_concentrations_for_cas(parsed.cas_number)
                if len(ac) > 1 and not parsed.concentration:
                    lines += ['', '> **Note:** CAS ' + str(parsed.cas_number) + ' has **' +
                              str(len(ac)) + ' distinct formulations** each tracked separately.']

        elif parsed.intent == QueryIntent.CONCENTRATIONS_FOR_CAS:
            if not parsed.cas_number:
                lines = [
                    '### ⚠️ CAS Number Required',
                    '',
                    'You asked for available concentrations, but no CAS number was specified in your query.',
                    '',
                    '**Please specify a CAS number to view formulations:**',
                    '- `Which concentrations are available for CAS 109-72-8?` (*n-Butyllithium*)',
                    '- `What formulations are available for CAS 75-05-8?` (*Acetonitrile*)',
                    '- `Show concentrations for CAS 104-88-1` (*Benzyl Chloroformate*)'
                ]
            else:
                concs = self.inventory_engine.get_concentrations_for_cas(parsed.cas_number)
                data_payload = concs
                if not concs:
                    lines = ['No concentrations found for CAS ' + str(parsed.cas_number) + '.']
                else:
                    lines = ['### Formulations for CAS ' + str(parsed.cas_number), '',
                             '| Concentration | Product Name | Hyderabad | Bangalore | Total |',
                             '| :--- | :--- | :--- | :--- | :--- |']
                    for c in concs:
                        lines.append('| **' + c['concentration'] + '** | ' + c['product_name'] +
                                     ' | ' + self._q(c['hyderabad_quantity'], c['unit']) +
                                     ' | ' + self._q(c['bangalore_quantity'], c['unit']) +
                                     ' | **' + self._q(c['total_quantity'], c['unit']) + '** |')

        elif parsed.intent == QueryIntent.PRODUCT_NAME_LOOKUP and parsed.product_name:
            res = self.inventory_engine.get_stock_by_product_name(
                product_name=parsed.product_name, location=parsed.location,
                concentration=parsed.concentration)
            data_payload = res
            warnings.extend(res.warnings)
            if not res.breakdowns:
                lines = ['No confirmed stock for product: ' + str(parsed.product_name)]
            else:
                lines = ['### Stock for ' + str(parsed.product_name), '',
                         '**Total:** ' + self._q(res.total_quantity, res.unit), '',
                         '| Product Name | CAS | Concentration | Location | Quantity |',
                         '| :--- | :--- | :--- | :--- | :--- |']
                for b in res.breakdowns:
                    lines.append('| ' + b.product_name + ' | ' + str(b.cas_number) + ' | ' +
                                 b.concentration + ' | ' + b.location +
                                 ' | **' + self._q(b.total_quantity, b.unit) + '** |')

        elif parsed.intent == QueryIntent.LOCATION_SUMMARY and parsed.location:
            loc_data = self.inventory_engine.get_stock_by_location(parsed.location)
            data_payload = loc_data
            warnings.extend(loc_data['warnings'])
            totals = ', '.join('**' + self._q(qty, unit) + '**' for unit, qty in loc_data['unit_totals'].items())
            lines = ['### Total Stock in **' + loc_data['location'] + '**', '',
                     '- **Total Stock:** ' + totals,
                     '- **Valid Records:** ' + str(loc_data['record_count'])]
            if loc_data['excluded_count'] > 0:
                lines.append('- **Excluded (returns/negatives):** ' + str(loc_data['excluded_count']))

        elif parsed.intent == QueryIntent.COMPARE_LOCATIONS:
            comp = self.inventory_engine.compare_locations()
            data_payload = comp
            warnings.extend(comp['Hyderabad']['warnings'] + comp['Bangalore']['warnings'])
            lines = ['### Facility Stock Comparison: Hyderabad vs. Bangalore', '',
                     '| Unit | Hyderabad Facility | Bangalore Facility | Total |',
                     '| :--- | :--- | :--- | :--- |']
            for unit, vals in comp['comparison'].items():
                lines.append('| **' + unit + '** | **' + self._q(vals['Hyderabad'], unit) +
                             '** | **' + self._q(vals['Bangalore'], unit) +
                             '** | **' + self._q(vals['Total'], unit) + '** |')
            lines += ['', '- **Hyderabad:** ' + str(comp['Hyderabad']['record_count']) +
                      ' active, ' + str(comp['Hyderabad']['excluded_count']) + ' excluded',
                      '- **Bangalore:** ' + str(comp['Bangalore']['record_count']) +
                      ' active, ' + str(comp['Bangalore']['excluded_count']) + ' excluded']

        elif parsed.intent == QueryIntent.EXCLUSIVE_PRODUCTS:
            if parsed.location == 'Bangalore':
                items = self.inventory_engine.get_products_available_in_blr_not_hyd()
                title = '### Products in Bangalore but NOT in Hyderabad'
                qkey = 'bangalore_quantity'
                qcol = 'Bangalore Stock'
            else:
                items = self.inventory_engine.get_products_available_in_hyd_not_blr()
                title = '### Products in Hyderabad but NOT in Bangalore'
                qkey = 'hyderabad_quantity'
                qcol = 'Hyderabad Stock'
            data_payload = items
            lines = [title, '']
            if not items:
                lines.append('All products are available in both locations.')
            else:
                lines.append(f"There are **{len(items)} products** exclusive to {parsed.location or 'Hyderabad'}:")
                lines.append('')
                lines += ['| CAS Number | Product Name | Concentration | ' + qcol + ' |',
                          '| :--- | :--- | :--- | :--- |']
                for item in items:
                    lines.append('| ' + item['cas_number'] + ' | ' + item['product_name'] +
                                 ' | ' + item['concentration'] +
                                 ' | **' + self._q(item[qkey], item['unit']) + '** |')

        elif parsed.intent == QueryIntent.LOW_STOCK:
            sources.append('Symax_AI_Stock_Assessment_100plus.xlsx -> Sheet: Minimum_Stock')
            low_items = self.low_stock_engine.evaluate_all_stock(by_location=True)
            data_payload = low_items
            lines = ['### Low Stock — Below Minimum Thresholds', '',
                     'Found **' + str(len(low_items)) + ' instances** below minimum:', '',
                     '| Facility | CAS | Product Name | Concentration | Current | Min | Deficit |',
                     '| :--- | :--- | :--- | :--- | :--- | :--- | :--- |']
            for item in low_items:
                icon = 'x CRITICAL' if item.status == 'CRITICAL' else '! LOW'
                lines.append('| **' + item.location + '** | ' + item.cas_number + ' | ' +
                             item.product_name + ' | ' + item.concentration +
                             ' | [' + icon + '] ' + self._q(item.current_stock, item.unit) +
                             ' | ' + self._q(item.minimum_stock, item.unit) +
                             ' | **-' + self._q(item.deficit, item.unit) + '** |')

        elif parsed.intent == QueryIntent.PURCHASE_REQUIREMENTS:
            sources.append('Symax_AI_Stock_Assessment_100plus.xlsx -> Sheet: Minimum_Stock')
            reqs = self.low_stock_engine.generate_purchase_requirements()
            data_payload = reqs
            lines = ['### Purchase Requirements — Replenishment Plan', '',
                     'Generated **' + str(len(reqs)) + ' replenishment requisitions**:', '',
                     '| Priority | Facility | CAS | Product | Concentration | Order Qty |',
                     '| :--- | :--- | :--- | :--- | :--- | :--- |']
            for r in reqs:
                badge = 'HIGH' if r.priority == 'HIGH' else 'MEDIUM'
                lines.append('| **' + badge + '** | **' + r.location + '** | ' + r.cas_number +
                             ' | ' + r.product_name + ' | ' + r.concentration +
                             ' | **' + self._q(r.required_quantity, r.unit) + '** |')

        elif parsed.intent == QueryIntent.DATA_QUALITY:
            issues = self.data_loader.get_data_quality_issues()
            data_payload = issues
            lines = ['### Data Quality & Audit Report', '',
                     'Identified **' + str(len(issues)) + ' data quality items**:', '',
                     '| Issue Type | Record ID | Original Value | Proposed | Safe? |',
                     '| :--- | :--- | :--- | :--- | :--- |']
            for iss in issues[:20]:
                safe = 'Yes' if iss.safe_to_include else 'No - Excluded'
                lines.append('| ' + iss.issue_type + ' | ' + str(iss.record_id) +
                             ' | ' + str(iss.original_value) + ' | ' +
                             str(iss.proposed_value) + ' | ' + safe + ' |')
            if len(issues) > 20:
                lines += ['', '*...and ' + str(len(issues)-20) + ' more items.*']

        else:
            lines = ['I am **Symax AI Stock Assistant**. You can ask:', '',
                     '- Stock for a CAS number: *What is the stock for CAS 109-72-8?*',
                     '- Formulations: *Which concentrations are available for CAS 109-72-8?*',
                     '- Product stock: *What is the stock of n-Butyllithium 1.6 M in Hexane?*',
                     '- Location totals: *How much is available in Hyderabad?*',
                     '- Comparison: *Compare Hyderabad vs Bangalore stock*',
                     '- Exclusive products: *Which products are in Hyderabad but not Bangalore?*',
                     '- Low stock: *Which products are below minimum stock?*',
                     '- Purchase plan: *Generate purchase requirements*',
                     '- Data quality: *Show data quality issues*']

        return AssistantResponse(
            answer='\n'.join(lines),
            intent=parsed.intent.value,
            data=data_payload,
            sources=sources,
            warnings=warnings,
            query_details=parsed.model_dump(),
            clarification_needed=parsed.clarification_needed,
            clarification_options=parsed.clarification_options
        )
