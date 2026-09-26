import re
import pandas as pd
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from src.config import EXCEL_PATH, LOCATION_MAPPING, STANDARD_LOCATIONS

@dataclass
class DataQualityIssue:
    issue_type: str
    record_id: Any
    sheet: str
    original_value: Any
    proposed_value: Any
    reason: str
    safe_to_include: bool
    requires_manual_review: bool

def normalize_cas(cas: Any) -> str:
    """Normalize CAS number format: digits-digits-digit."""
    if pd.isna(cas) or cas is None:
        return ""
    val = str(cas).strip()
    match = re.search(r'(\d{2,7}-\d{2}-\d)', val)
    if match:
        return match.group(1)
    digits = re.sub(r'[^\d]', '', val)
    if len(digits) >= 5:
        return f"{digits[:-3]}-{digits[-3:-1]}-{digits[-1]}"
    return val

def normalize_string(s: Any) -> str:
    """Trim and standardize whitespace for names and general text."""
    if pd.isna(s) or s is None:
        return ""
    return re.sub(r'\s+', ' ', str(s).strip())

def normalize_concentration(conc: Any) -> str:
    """Normalize concentration string while preserving exact chemistry."""
    if pd.isna(conc) or conc is None:
        return ""
    val = str(conc).strip()
    val = re.sub(r'(\d+(?:\.\d+)?)\s*([mM])(\s|$)', r'\1 M\3', val)
    val = re.sub(r'(\d+(?:\.\d+)?)\s+%', r'\1%', val)
    val = re.sub(r'\s+', ' ', val).strip()
    return val

def normalize_location(loc: Any) -> Tuple[str, bool, Optional[str]]:
    """
    Returns (normalized_loc, is_recognized, original_loc).
    If unknown/blank, marks as not recognized so it can be handled safely.
    """
    if pd.isna(loc) or loc is None:
        return "Unknown", False, None
    raw_loc = str(loc).strip()
    clean_key = raw_loc.lower().rstrip('.')
    if clean_key in LOCATION_MAPPING:
        return LOCATION_MAPPING[clean_key], True, raw_loc
    return raw_loc, False, raw_loc

class DataLoader:
    def __init__(self, excel_path=EXCEL_PATH):
        self.excel_path = excel_path
        self.issues: List[DataQualityIssue] = []
        self.stock_df = pd.DataFrame()
        self.min_stock_df = pd.DataFrame()
        self._load_and_clean()

    def _load_and_clean(self):
        xls = pd.ExcelFile(self.excel_path)
        self.raw_stock_df = pd.read_excel(xls, 'Stock_Data')
        self.raw_min_stock_df = pd.read_excel(xls, 'Minimum_Stock')

        self._process_stock_data()
        self._process_minimum_stock()

    def _process_stock_data(self):
        df = self.raw_stock_df.copy()

        df['norm_cas'] = df['CAS_Number'].apply(normalize_cas)
        df['norm_product_name'] = df['Product_Name'].apply(normalize_string)
        df['norm_concentration'] = df['Concentration'].apply(normalize_concentration)

        norm_locs = []
        for idx, row in df.iterrows():
            loc_val = row.get('Location')
            norm_loc, is_rec, orig_loc = normalize_location(loc_val)
            norm_locs.append(norm_loc)

            if not is_rec:
                self.issues.append(DataQualityIssue(
                    issue_type="Non-Standard Location",
                    record_id=row.get('Stock_ID', idx),
                    sheet="Stock_Data",
                    original_value=orig_loc,
                    proposed_value=norm_loc,
                    reason=f"Location '{orig_loc}' could not be unambiguously mapped to Hyderabad or Bangalore.",
                    safe_to_include=False,
                    requires_manual_review=True
                ))
            elif orig_loc.strip() != norm_loc:
                self.issues.append(DataQualityIssue(
                    issue_type="Location Spelling Variation",
                    record_id=row.get('Stock_ID', idx),
                    sheet="Stock_Data",
                    original_value=orig_loc,
                    proposed_value=norm_loc,
                    reason=f"Normalized location variant '{orig_loc}' to standard '{norm_loc}'.",
                    safe_to_include=True,
                    requires_manual_review=False
                ))

        df['norm_location'] = norm_locs
        df['is_valid_stock'] = True
        df['inclusion_reason'] = "Valid record"

        dup_ids = df[df.duplicated(subset=['Stock_ID'], keep=False)]
        if not dup_ids.empty:
            for idx, row in dup_ids.iterrows():
                self.issues.append(DataQualityIssue(
                    issue_type="Duplicate Stock_ID",
                    record_id=row.get('Stock_ID', idx),
                    sheet="Stock_Data",
                    original_value=row.get('Stock_ID'),
                    proposed_value=None,
                    reason="Stock_ID appears multiple times with distinct physical/batch attributes.",
                    safe_to_include=True,
                    requires_manual_review=True
                ))

        for idx, row in df.iterrows():
            stock_id = row.get('Stock_ID', idx)
            qty = row.get('Quantity')
            unit = str(row.get('Unit', '')).strip()

            if pd.isna(qty):
                df.at[idx, 'is_valid_stock'] = False
                df.at[idx, 'inclusion_reason'] = "Missing quantity"
                self.issues.append(DataQualityIssue(
                    issue_type="Missing Quantity",
                    record_id=stock_id,
                    sheet="Stock_Data",
                    original_value=None,
                    proposed_value=None,
                    reason="Record has NaN quantity; excluded from confirmed on-hand stock.",
                    safe_to_include=False,
                    requires_manual_review=True
                ))
                continue

            if pd.isna(row.get('CAS_Number')) or not row.get('norm_cas'):
                self.issues.append(DataQualityIssue(
                    issue_type="Missing CAS Number",
                    record_id=stock_id,
                    sheet="Stock_Data",
                    original_value=row.get('CAS_Number'),
                    proposed_value=None,
                    reason="Missing valid CAS Number. Mapped through chemical product name.",
                    safe_to_include=True,
                    requires_manual_review=True
                ))

            if not normalize_location(row.get('Location'))[1]:
                df.at[idx, 'is_valid_stock'] = False
                df.at[idx, 'inclusion_reason'] = "Unknown / non-standard location"
                continue

            try:
                qty_num = float(qty)
            except (ValueError, TypeError):
                df.at[idx, 'is_valid_stock'] = False
                df.at[idx, 'inclusion_reason'] = "Non-numeric quantity"
                self.issues.append(DataQualityIssue(
                    issue_type="Invalid Quantity Format",
                    record_id=stock_id,
                    sheet="Stock_Data",
                    original_value=qty,
                    proposed_value=None,
                    reason="Quantity is not a valid number; excluded from confirmed physical stock.",
                    safe_to_include=False,
                    requires_manual_review=True
                ))
                continue

            if qty_num < 0:
                df.at[idx, 'is_valid_stock'] = False
                df.at[idx, 'inclusion_reason'] = "Negative quantity / Adjustment"
                self.issues.append(DataQualityIssue(
                    issue_type="Negative Quantity",
                    record_id=stock_id,
                    sheet="Stock_Data",
                    original_value=qty_num,
                    proposed_value=None,
                    reason=f"Negative stock quantity ({qty_num} {unit}); flagged as audit adjustment / return. Excluded from confirmed on-hand stock.",
                    safe_to_include=False,
                    requires_manual_review=True
                ))

            elif qty_num == 0:
                self.issues.append(DataQualityIssue(
                    issue_type="Zero Quantity Stock",
                    record_id=stock_id,
                    sheet="Stock_Data",
                    original_value=0,
                    proposed_value=0,
                    reason="Stock level is recorded as 0; product is out of stock at this location.",
                    safe_to_include=True,
                    requires_manual_review=False
                ))

        # Add UI-compatible column aliases
        df['norm_CAS_Number'] = df['norm_cas']
        df['norm_Product_Name'] = df['norm_product_name']
        df['norm_Concentration'] = df['norm_concentration']
        df['norm_Location'] = df['norm_location']
        df['is_eligible_for_stock'] = df['is_valid_stock']
        df['data_quality_warnings'] = df.apply(
            lambda r: "" if r['is_valid_stock'] else str(r['inclusion_reason']), axis=1
        )

        self.stock_df = df

    def _process_minimum_stock(self):
        df = self.raw_min_stock_df.copy()
        df['norm_cas'] = df['CAS_Number'].apply(normalize_cas)
        df['norm_product_name'] = df['Product_Name'].apply(normalize_string)
        df['norm_concentration'] = df['Concentration'].apply(normalize_concentration)

        if 'Location' in df.columns:
            df['norm_location'] = df['Location'].apply(lambda x: normalize_location(x)[0])
        else:
            df['norm_location'] = "All"

        self.min_stock_df = df

    def get_stock_data(self) -> pd.DataFrame:
        return self.stock_df

    def get_minimum_stock_data(self) -> pd.DataFrame:
        return self.min_stock_df

    def get_data_quality_issues(self) -> List[DataQualityIssue]:
        return self.issues

    def get_data_quality_report(self) -> List[DataQualityIssue]:
        return self.issues

    def get_data_quality_df(self) -> pd.DataFrame:
        rows = []
        for iss in self.issues:
            itype = iss.issue_type
            if itype == "Location Variation Normalized":
                itype = "Location Spelling Variation"
            elif "Location" in itype and ("Unknown" in itype or "Missing" in itype):
                itype = "Non-Standard Location"

            rows.append({
                "issue_type": itype,
                "record_id": iss.record_id,
                "sheet": iss.sheet,
                "original_value": str(iss.original_value),
                "proposed_value": str(iss.proposed_value),
                "reason": iss.reason,
                "safe_to_include": iss.safe_to_include,
                "requires_manual_review": iss.requires_manual_review,
            })
        return pd.DataFrame(rows)
