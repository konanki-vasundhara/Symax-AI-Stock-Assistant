import difflib
import pandas as pd
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from src.data_loader import DataLoader

@dataclass
class ProductMasterRecord:
    product_id: str
    cas_number: str
    product_name: str
    concentration: str
    unit: str
    aliases: List[str] = field(default_factory=list)
    min_stock_level: Optional[float] = None
    min_stock_location: str = "All"
    notes: List[str] = field(default_factory=list)

@dataclass
class MatchResult:
    match_tier: str  # EXACT_FULL, EXACT_CAS_CONC, CAS_MULTIPLE_VARIANTS, NAME_MATCH, FUZZY_CANDIDATES, NO_MATCH
    products: List[ProductMasterRecord]
    confidence: float
    message: str

class ProductMaster:
    def __init__(self, data_loader: DataLoader):
        self.data_loader = data_loader
        self.products: Dict[str, ProductMasterRecord] = {}
        self.cas_to_products: Dict[str, List[ProductMasterRecord]] = {}
        self.name_to_products: Dict[str, List[ProductMasterRecord]] = {}
        self._build_master()

    def get_all_products(self) -> List[ProductMasterRecord]:
        return list(self.products.values())

    def _build_master(self):
        stock_df = self.data_loader.get_stock_data()
        min_df = self.data_loader.get_minimum_stock_data()

        # Build unique products from Stock Data
        for _, row in stock_df.iterrows():
            cas = row['norm_cas']
            name = row['norm_product_name']
            conc = row['norm_concentration']
            unit = str(row['Unit']).strip()

            # Product Identity is the 3-tuple: (CAS, Name, Concentration)
            prod_id = f"{cas}__{name.lower()}___{conc.lower()}".replace(" ", "_")

            if prod_id not in self.products:
                self.products[prod_id] = ProductMasterRecord(
                    product_id=prod_id,
                    cas_number=cas,
                    product_name=name,
                    concentration=conc,
                    unit=unit
                )

        # Merge with Minimum Stock Data
        for _, row in min_df.iterrows():
            cas = row['norm_cas']
            name = row['norm_product_name']
            conc = row['norm_concentration']
            unit = str(row['Unit']).strip()
            min_val = float(row['Minimum_Stock']) if not pd.isna(row['Minimum_Stock']) else 0.0
            loc = row['norm_location']

            # Match to existing product
            matched = False
            for p in self.products.values():
                if p.cas_number == cas and p.concentration.lower() == conc.lower():
                    p.min_stock_level = min_val
                    p.min_stock_location = loc
                    if name.lower() != p.product_name.lower() and name not in p.aliases:
                        p.aliases.append(name)
                    matched = True
                    break

            if not matched:
                # Add standalone min stock product record
                prod_id = f"{cas}__{name.lower()}___{conc.lower()}".replace(" ", "_")
                self.products[prod_id] = ProductMasterRecord(
                    product_id=prod_id,
                    cas_number=cas,
                    product_name=name,
                    concentration=conc,
                    unit=unit,
                    min_stock_level=min_val,
                    min_stock_location=loc
                )

        # Index by CAS and Name
        for p in self.products.values():
            if p.cas_number:
                self.cas_to_products.setdefault(p.cas_number, []).append(p)
            self.name_to_products.setdefault(p.product_name.lower(), []).append(p)

    def get_all_products(self) -> List[ProductMasterRecord]:
        return list(self.products.values())

    def match_product(self, cas: Optional[str] = None, name: Optional[str] = None, concentration: Optional[str] = None) -> MatchResult:
        """
        Implements 5-tier product matching priority:
        1. Exact CAS number, product name, and concentration.
        2. Exact CAS number and concentration, with alias.
        3. Exact CAS number with multiple possible product variants.
        4. Product-name search when CAS number is not provided.
        5. Controlled fuzzy matching to suggest candidates.
        """
        clean_cas = cas.strip() if cas else ""
        clean_name = name.strip().lower() if name else ""
        clean_conc = concentration.strip().lower() if concentration else ""

        # 1. Exact CAS, Name, and Concentration
        if clean_cas and clean_name and clean_conc:
            matches = [
                p for p in self.products.values()
                if p.cas_number == clean_cas
                and (p.product_name.lower() == clean_name or clean_name in [a.lower() for a in p.aliases])
                and p.concentration.lower() == clean_conc
            ]
            if matches:
                return MatchResult(
                    match_tier="EXACT_FULL",
                    products=matches,
                    confidence=1.0,
                    message=f"Exact match found for CAS {clean_cas}, {matches[0].product_name}, {matches[0].concentration}."
                )

        # 2. Exact CAS and Concentration
        if clean_cas and clean_conc:
            matches = [
                p for p in self.products.values()
                if p.cas_number == clean_cas and p.concentration.lower() == clean_conc
            ]
            if matches:
                return MatchResult(
                    match_tier="EXACT_CAS_CONC",
                    products=matches,
                    confidence=0.95,
                    message=f"Exact match on CAS {clean_cas} and concentration {clean_conc}."
                )

        # 3. Exact CAS with multiple possible variants
        if clean_cas and clean_cas in self.cas_to_products:
            variants = self.cas_to_products[clean_cas]
            return MatchResult(
                match_tier="CAS_MULTIPLE_VARIANTS",
                products=variants,
                confidence=0.90,
                message=f"Found {len(variants)} formulation(s)/variant(s) for CAS {clean_cas}."
            )

        # 4. Product-Name Search
        if clean_name:
            exact_name_matches = [
                p for p in self.products.values()
                if p.product_name.lower() == clean_name or clean_name in [a.lower() for a in p.aliases]
            ]
            if clean_conc:
                exact_name_matches = [p for p in exact_name_matches if p.concentration.lower() == clean_conc]

            if exact_name_matches:
                return MatchResult(
                    match_tier="NAME_MATCH",
                    products=exact_name_matches,
                    confidence=0.85,
                    message=f"Found {len(exact_name_matches)} product(s) matching name '{name}'."
                )

        # 5. Controlled Fuzzy Matching
        if clean_name or clean_cas:
            query = clean_name if clean_name else clean_cas
            all_names = list(set([p.product_name for p in self.products.values()] + [p.cas_number for p in self.products.values()]))
            close_matches = difflib.get_close_matches(query, all_names, n=3, cutoff=0.6)

            if close_matches:
                candidate_prods = []
                for cm in close_matches:
                    candidate_prods.extend([p for p in self.products.values() if p.product_name == cm or p.cas_number == cm])
                return MatchResult(
                    match_tier="FUZZY_CANDIDATES",
                    products=candidate_prods,
                    confidence=0.5,
                    message=f"No exact match. Found {len(candidate_prods)} possible candidate(s) for '{query}'."
                )

        return MatchResult(
            match_tier="NO_MATCH",
            products=[],
            confidence=0.0,
            message=f"No matching chemical product found in inventory."
        )
