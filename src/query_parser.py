import re
import json
from enum import Enum
from typing import Optional, List
from pydantic import BaseModel
import httpx
from src.config import GROQ_API_KEY, GEMINI_API_KEY


class QueryIntent(str, Enum):
    CAS_LOOKUP = "CAS_LOOKUP"
    PRODUCT_NAME_LOOKUP = "PRODUCT_NAME_LOOKUP"
    LOCATION_SUMMARY = "LOCATION_SUMMARY"
    COMPARE_LOCATIONS = "COMPARE_LOCATIONS"
    CONCENTRATIONS_FOR_CAS = "CONCENTRATIONS_FOR_CAS"
    EXCLUSIVE_PRODUCTS = "EXCLUSIVE_PRODUCTS"
    LOW_STOCK = "LOW_STOCK"
    PURCHASE_REQUIREMENTS = "PURCHASE_REQUIREMENTS"
    DATA_QUALITY = "DATA_QUALITY"
    GENERAL_QUERY = "GENERAL_QUERY"


class ExtractedStockQuery(BaseModel):
    intent: QueryIntent
    cas_number: Optional[str] = None
    product_name: Optional[str] = None
    concentration: Optional[str] = None
    location: Optional[str] = None
    confidence: float = 1.0
    reasoning: Optional[str] = None


class QueryParser:
    KNOWN_PRODUCTS = [
        "n-butyllithium",
        "2-methoxyphenylmagnesium bromide",
        "boron trifluoride methanol solution",
        "benzyl chloroformate",
        "benzyl bromide",
        "benzoyl chloride",
        "dibenzoyl peroxide",
        "dichloromethane",
        "isopropyl alcohol",
        "methyl isobutyl ketone",
        "acetonitrile",
        "methanol",
        "toluene",
        "ethanol",
        "n-heptane",
        "n-hexane",
    ]

    def __init__(self):
        self.groq_key = GROQ_API_KEY
        self.gemini_key = GEMINI_API_KEY

    def parse(self, user_question: str) -> ExtractedStockQuery:
        # 1. Deterministic parse
        det = self._deterministic_parse(user_question)
        if det and det.confidence >= 0.8:
            return det

        # 2. LLM parse via Groq if available
        if self.groq_key:
            try:
                llm_res = self._parse_with_groq(user_question)
                if llm_res:
                    return llm_res
            except Exception:
                pass

        # 3. LLM parse via Gemini if available
        if self.gemini_key:
            try:
                gemini_res = self._parse_with_gemini(user_question)
                if gemini_res:
                    return gemini_res
            except Exception:
                pass

        if det:
            return det

        return ExtractedStockQuery(
            intent=QueryIntent.GENERAL_QUERY,
            confidence=0.5,
            reasoning="Default fallback to general query guidance."
        )

    def _extract_location(self, text: str) -> Optional[str]:
        t = text.lower()
        if "hyderabad" in t or "hyd." in t or " hyd " in f" {t} " or t.startswith("hyd"):
            return "Hyderabad"
        if "bangalore" in t or "bengaluru" in t or "blr." in t or " blr " in f" {t} " or t.startswith("blr"):
            return "Bangalore"
        return None

    def _extract_concentration(self, q: str) -> Optional[str]:
        match = re.search(r'(\d+(?:\.\d+)?\s*(?:M|%|N)(?:\s+in\s+[a-zA-Z]+)?)', q, re.IGNORECASE)
        if match:
            conc = match.group(1).strip()
            conc = re.sub(r'(\d+(?:\.\d+)?)([mM])(\s)', r'\1 M\3', conc)
            conc = re.sub(r'(\d+(?:\.\d+)?)([mM])$', r'\1 M', conc)
            return conc
        return None

    def _deterministic_parse(self, q: str) -> Optional[ExtractedStockQuery]:
        text = q.lower().strip()
        loc = self._extract_location(q)

        cas_match = re.search(r'\b(\d{2,7}-\d{2}-\d)\b', q)
        cas_num = cas_match.group(1) if cas_match else None

        conc = self._extract_concentration(q)

        # 1. PURCHASE REQUIREMENTS / ORDERS
        if (
            "purchase requirement" in text
            or "purchase order" in text
            or "purchase alert" in text
            or "replenishment" in text
            or "procure" in text
            or "stock alert" in text
            or ("alert" in text and ("stock" in text or "purchase" in text or "low" in text))
            or "what should i buy" in text
            or "what to buy" in text
            or "what should i order" in text
            or "what to order" in text
        ):
            return ExtractedStockQuery(
                intent=QueryIntent.PURCHASE_REQUIREMENTS,
                location=loc,
                confidence=0.95,
                reasoning="Identified purchase/replenishment requirement intent."
            )

        # 2. LOW STOCK / BELOW MINIMUM
        if (
            "below minimum" in text
            or "low stock" in text
            or "under stock" in text
            or "shortage" in text
            or "deficit" in text
            or "reorder" in text
            or ("minimum" in text and ("below" in text or "under" in text or "reach" in text or "stock" in text))
        ):
            return ExtractedStockQuery(
                intent=QueryIntent.LOW_STOCK,
                location=loc,
                confidence=0.95,
                reasoning="Identified below minimum / low stock intent."
            )

        # 3. EXCLUSIVE PRODUCTS (in X but not Y, or exclusive to X)
        excl_keywords = ("but not", "not in", "only in", "exclusive")
        if any(k in text for k in excl_keywords):
            blr_excl = ("exclusive to bangalore", "only in bangalore", "not in hyderabad", "but not hyderabad")
            if "bangalore" in text and any(k in text for k in blr_excl):
                return ExtractedStockQuery(
                    intent=QueryIntent.EXCLUSIVE_PRODUCTS,
                    location="Bangalore",
                    confidence=0.95,
                    reasoning="Identified products exclusive to Bangalore."
                )
            if "hyderabad" in text:
                return ExtractedStockQuery(
                    intent=QueryIntent.EXCLUSIVE_PRODUCTS,
                    location="Hyderabad",
                    confidence=0.95,
                    reasoning="Identified products exclusive to Hyderabad."
                )
            target_loc = "Bangalore" if "bangalore" in text else "Hyderabad"
            return ExtractedStockQuery(
                intent=QueryIntent.EXCLUSIVE_PRODUCTS,
                location=target_loc,
                confidence=0.95,
                reasoning=f"Identified products exclusive to {target_loc}."
            )

        # 4. COMPARE LOCATIONS
        if ("compare" in text or "difference" in text or " vs " in text or "versus" in text) and (
            "hyderabad" in text or "bangalore" in text or "location" in text or "facility" in text or "facilities" in text
        ):
            return ExtractedStockQuery(
                intent=QueryIntent.COMPARE_LOCATIONS,
                confidence=0.95,
                reasoning="Identified facility comparison intent."
            )

        # 5. DATA QUALITY / ANOMALIES
        if (
            "data quality" in text
            or "anomaly" in text
            or "anomalies" in text
            or "discrepanc" in text
            or "audit" in text
            or "clean" in text and "data" in text
            or "unknown location" in text
            or "negative quantit" in text
            or "duplicate" in text
        ):
            return ExtractedStockQuery(
                intent=QueryIntent.DATA_QUALITY,
                confidence=0.95,
                reasoning="Identified data quality / audit intent."
            )

        # 6. CONCENTRATIONS FOR CAS
        if cas_num and (
            "concentration" in text
            or "formulation" in text
            or "variant" in text
            or "strength" in text
            or "which conc" in text
            or "what conc" in text
        ):
            return ExtractedStockQuery(
                intent=QueryIntent.CONCENTRATIONS_FOR_CAS,
                cas_number=cas_num,
                location=loc,
                confidence=0.95,
                reasoning="Identified request for available formulations/concentrations for CAS."
            )

        # 7. CAS LOOKUP
        if cas_num:
            return ExtractedStockQuery(
                intent=QueryIntent.CAS_LOOKUP,
                cas_number=cas_num,
                concentration=conc,
                location=loc,
                confidence=0.95,
                reasoning=f"Identified direct CAS lookup for {cas_num}."
            )

        # 8. PRODUCT NAME LOOKUP
        matched_product = None
        for kp in self.KNOWN_PRODUCTS:
            if kp in text:
                matched_product = kp
                break

        if matched_product:
            orig_match = re.search(re.escape(matched_product), q, re.IGNORECASE)
            p_name = orig_match.group(0) if orig_match else matched_product
            if matched_product == "n-butyllithium":
                p_name = "n-Butyllithium"
            elif matched_product == "2-methoxyphenylmagnesium bromide":
                p_name = "2-Methoxyphenylmagnesium bromide"
            elif matched_product == "benzyl chloroformate":
                p_name = "Benzyl Chloroformate"
            elif matched_product == "boron trifluoride methanol solution":
                p_name = "Boron Trifluoride Methanol Solution"
            elif matched_product == "dibenzoyl peroxide":
                p_name = "Dibenzoyl peroxide"
            elif matched_product == "methyl isobutyl ketone":
                p_name = "Methyl Isobutyl Ketone"
            elif matched_product == "isopropyl alcohol":
                p_name = "Isopropyl Alcohol"
            else:
                p_name = p_name.capitalize()

            return ExtractedStockQuery(
                intent=QueryIntent.PRODUCT_NAME_LOOKUP,
                product_name=p_name,
                concentration=conc,
                location=loc,
                confidence=0.95,
                reasoning=f"Identified product name inquiry for {p_name}."
            )

        # 9. LOCATION SUMMARY
        if loc and (
            "how much" in text
            or "total stock" in text
            or "total" in text
            or "stock in" in text
            or "available in" in text
            or "inventory in" in text
            or text.endswith(loc.lower())
            or text.endswith("hyderabad?")
            or text.endswith("bangalore?")
        ):
            return ExtractedStockQuery(
                intent=QueryIntent.LOCATION_SUMMARY,
                location=loc,
                confidence=0.9,
                reasoning=f"Identified location total stock summary for {loc}."
            )

        return None

    def _parse_with_groq(self, question: str) -> Optional[ExtractedStockQuery]:
        prompt = f"""You are an expert chemical inventory intent parser for Symax Laboratories.
Extract the user intent and search parameters into a JSON response.

Valid intents:
- CAS_LOOKUP: Asking about stock for a specific CAS number.
- PRODUCT_NAME_LOOKUP: Asking about stock for a specific chemical name (e.g. n-Butyllithium, Toluene, Methanol).
- LOCATION_SUMMARY: Asking for total stock or overall inventory in Hyderabad or Bangalore.
- COMPARE_LOCATIONS: Comparing inventory between Hyderabad and Bangalore.
- CONCENTRATIONS_FOR_CAS: Asking which concentrations/formulations exist for a CAS number.
- EXCLUSIVE_PRODUCTS: Asking which products are available in one location but not another.
- LOW_STOCK: Asking about products below minimum threshold, shortages, or low inventory.
- PURCHASE_REQUIREMENTS: Asking for purchase orders, replenishment, or what needs to be bought.
- DATA_QUALITY: Asking about anomalies, data cleaning, negative stock, unknown locations, or audit issues.
- GENERAL_QUERY: General inquiries.

User Question: "{question}"

Respond with ONLY valid JSON with keys:
{{
  "intent": "CAS_LOOKUP" | "PRODUCT_NAME_LOOKUP" | "LOCATION_SUMMARY" | "COMPARE_LOCATIONS" | "CONCENTRATIONS_FOR_CAS" | "EXCLUSIVE_PRODUCTS" | "LOW_STOCK" | "PURCHASE_REQUIREMENTS" | "DATA_QUALITY" | "GENERAL_QUERY",
  "cas_number": "string" or null,
  "product_name": "string" or null,
  "concentration": "string" or null,
  "location": "Hyderabad" | "Bangalore" | null,
  "confidence": 0.95,
  "reasoning": "brief explanation"
}}
"""
        headers = {
            "Authorization": f"Bearer {self.groq_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "openai/gpt-oss-120b",
            "messages": [
                {"role": "system", "content": "You are a precise JSON-only intent extractor."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.0,
            "response_format": {"type": "json_object"}
        }

        with httpx.Client(timeout=8.0) as client:
            resp = client.post("https://api.groq.com/openai/v1/chat/completions", json=payload, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                raw_json = data["choices"][0]["message"]["content"]
                parsed = json.loads(raw_json)
                return ExtractedStockQuery(**parsed)
        return None

    def _parse_with_gemini(self, question: str) -> Optional[ExtractedStockQuery]:
        prompt = f"""You are an expert chemical inventory intent parser for Symax Laboratories.
Extract the user intent and search parameters into a JSON response.

Valid intents:
- CAS_LOOKUP, PRODUCT_NAME_LOOKUP, LOCATION_SUMMARY, COMPARE_LOCATIONS, CONCENTRATIONS_FOR_CAS, EXCLUSIVE_PRODUCTS, LOW_STOCK, PURCHASE_REQUIREMENTS, DATA_QUALITY, GENERAL_QUERY

User Question: "{question}"

Output JSON only with keys: intent, cas_number, product_name, concentration, location, confidence, reasoning.
"""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={self.gemini_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"response_mime_type": "application/json"}
        }
        with httpx.Client(timeout=8.0) as client:
            resp = client.post(url, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"]
                parsed = json.loads(text)
                return ExtractedStockQuery(**parsed)
        return None
