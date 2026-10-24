"""Lab Report Text and Table Extraction Service.

Multi-strategy extraction engine:
1. Digital Table Extraction (pdfplumber table detection - Layout A / Rajesh).
2. Line-Based Pattern Extraction (regex parser for line layouts - Layout B / Meena).
3. Modality Guardrail (ECG / Ultrasound / Imaging non-lab document rejection).
4. Vision Fallback Interface (Gemini Flash / OpenAI for scanned image PDFs - Layout C / Arun).

Safety Invariant:
-----------------
Extracted rows are strictly staged as candidates with status='needs_review'.
They are completely isolated from the patient timeline until human confirmation.
"""

from datetime import date, datetime
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import pdfplumber
from sqlalchemy.orm import Session

from app.models.extraction import ExtractionRow
from app.models.report import Report
from app.core.config import get_settings


# Keywords indicating non-quantitative or non-laboratory modalities
NON_LAB_KEYWORDS = [
    "electrocardiogram", "ecg", "ekg", "ultrasound", "usg", "sonography",
    "echocardiogram", "echo", "chest x-ray", "radiology", "ct scan",
    "mri scan", "mammogram", "endoscopy"
]

# Common lab biomarkers to confirm validity of extraction
KNOWN_MARKER_KEYWORDS = [
    "creatinine", "glucose", "sugar", "hba1c", "hemoglobin", "haemoglobin",
    "hb", "mcv", "rdw", "urea", "platelet", "wbc", "rbc", "bilirubin",
    "sgot", "sgpt", "alt", "ast", "cholesterol", "triglyceride", "tsh"
]


def _clean_str(val: Any) -> str:
    """Clean and strip extracted string text."""
    return str(val).strip() if val is not None else ""


def _parse_float(val_str: str) -> Optional[float]:
    """Parse numeric float from a result string."""
    cleaned = re.sub(r"[^\d\.]", "", val_str)
    try:
        return float(cleaned) if cleaned else None
    except ValueError:
        return None


def _parse_report_date(text: str) -> Optional[date]:
    """Extract specimen or collection date from text if present."""
    # Matches DD-Mon-YYYY (e.g. 15-Jan-2023)
    match = re.search(r"\b(\d{1,2})-(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)-(\d{4})\b", text, re.IGNORECASE)
    if match:
        try:
            return datetime.strptime(f"{match.group(1)}-{match.group(2).capitalize()}-{match.group(3)}", "%d-%b-%Y").date()
        except Exception:
            pass

    # Matches DD/MM/YYYY or MM/DD/YYYY
    match = re.search(r"\b(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})\b", text)
    if match:
        for fmt in ("%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(match.group(0), fmt).date()
            except Exception:
                pass
    return None


def _check_modality_guardrail(full_text: str) -> bool:
    """Check if document is an unsupported modality (e.g. ECG, Ultrasound).

    Returns True if the document should be rejected as an unsupported modality.
    """
    text_lower = full_text.lower()
    has_non_lab = any(kw in text_lower for kw in NON_LAB_KEYWORDS)
    has_known_lab = any(kw in text_lower for kw in KNOWN_MARKER_KEYWORDS)

    # If it explicitly mentions non-lab modality and lacks lab markers -> trigger guardrail
    if has_non_lab and not has_known_lab:
        return True
    return False


class ExtractionService:
    """Orchestrates document extraction across table and line strategies."""

    def extract_from_pdf(self, pdf_path: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Extract candidate rows and document metadata from a PDF file.

        Returns:
            Tuple[List[Dict[str, Any]], Dict[str, Any]]: (candidates, metadata)
        """
        candidates: List[Dict[str, Any]] = []
        metadata: Dict[str, Any] = {"lab_name": None, "collection_date": None, "is_unsupported_modality": False}

        with pdfplumber.open(str(pdf_path)) as pdf:
            all_text_list: List[str] = []
            all_tables: List[List[List[str]]] = []

            for page in pdf.pages:
                txt = page.extract_text() or ""
                all_text_list.append(txt)
                tables = page.extract_tables() or []
                all_tables.extend(tables)

            full_text = "\n".join(all_text_list)

            # Metadata discovery from header lines
            first_page_text = all_text_list[0] if all_text_list else ""
            lines = [line.strip() for line in first_page_text.splitlines() if line.strip()]
            if lines and not metadata["lab_name"]:
                metadata["lab_name"] = lines[0]

            metadata["collection_date"] = _parse_report_date(full_text)

            # Modality Guardrail inspection
            if _check_modality_guardrail(full_text):
                metadata["is_unsupported_modality"] = True
                return [], metadata

            # Strategy 1: Table Extraction (Layout A)
            for table in all_tables:
                if not table or len(table) < 2:
                    continue

                # Locate header row
                header_idx = -1
                for idx, row in enumerate(table):
                    row_str = " ".join([_clean_str(c).lower() for c in row if c])
                    if any(k in row_str for k in ["test", "investigation", "parameter", "analyte"]) and any(k in row_str for k in ["result", "observed", "value"]):
                        header_idx = idx
                        break

                if header_idx != -1:
                    headers = [_clean_str(c).lower() for c in table[header_idx]]
                    # Map column indexes
                    name_col = next((i for i, h in enumerate(headers) if any(k in h for k in ["test", "investigation", "parameter", "analyte"])), 0)
                    val_col = next((i for i, h in enumerate(headers) if any(k in h for k in ["result", "observed", "value"])), 1)
                    unit_col = next((i for i, h in enumerate(headers) if "unit" in h), None)
                    ref_col = next((i for i, h in enumerate(headers) if any(k in h for k in ["ref", "interval", "range"])), None)
                    flag_col = next((i for i, h in enumerate(headers) if any(k in h for k in ["flag", "status"])), None)

                    for row in table[header_idx + 1:]:
                        if not row or len(row) <= max(name_col, val_col):
                            continue
                        name = _clean_str(row[name_col])
                        val_str = _clean_str(row[val_col])
                        if not name or not val_str or any(name.lower().startswith(x) for x in ["test", "total", "page"]):
                            continue

                        num_val = _parse_float(val_str)
                        if num_val is None:
                            continue

                        unit = _clean_str(row[unit_col]) if unit_col is not None and len(row) > unit_col else None
                        ref = _clean_str(row[ref_col]) if ref_col is not None and len(row) > ref_col else None
                        flag = _clean_str(row[flag_col]) if flag_col is not None and len(row) > flag_col else None

                        candidates.append({
                            "raw_marker_name": name,
                            "raw_value": val_str,
                            "numeric_value": num_val,
                            "raw_unit": unit or "",
                            "raw_reference_range": ref or "",
                            "flag": flag or "",
                            "confidence": 0.95,
                        })

            # Strategy 2: Line-based regex parser (Layout B - when tables were not parsed or sparse)
            if not candidates and full_text:
                # Regex for line items: <Name> <Value> <Unit> <Ref Range> [Flag/Status]
                line_regex = re.compile(
                    r"^([A-Za-z0-9\s,\(\)\-\/]+?)\s+([0-9]+(?:\.[0-9]+)?)\s+([a-zA-Z\/\%µμ]+(?:L|dL|mL|fL)?)\s+([0-9\.\-\s]+)?\s*(Normal|High|Low|H|L)?$",
                    re.MULTILINE
                )
                for line in full_text.splitlines():
                    cleaned_line = line.strip()
                    m = line_regex.match(cleaned_line)
                    if m:
                        name, val_str, unit, ref, flag = m.groups()
                        num_val = _parse_float(val_str)
                        if num_val is not None:
                            candidates.append({
                                "raw_marker_name": name.strip(),
                                "raw_value": val_str,
                                "numeric_value": num_val,
                                "raw_unit": unit.strip() if unit else "",
                                "raw_reference_range": ref.strip() if ref else "",
                                "flag": flag.strip() if flag else "",
                                "confidence": 0.90,
                            })

            # Guardrail check on final candidate count
            if not candidates:
                # If document had substantial text but 0 lab candidates were found, it's non-lab
                if len(full_text.strip()) > 100:
                    metadata["is_unsupported_modality"] = True

        return candidates, metadata

    def process_report_extraction(self, report_id: str, db: Session) -> Report:
        """Execute extraction on an uploaded report and stage candidate rows."""
        from app.services.storage import storage_service

        report = db.query(Report).filter(Report.id == report_id).first()
        if not report:
            raise ValueError(f"Report {report_id} not found.")

        pdf_path = storage_service.get_file_path(report.storage_key)
        candidates, metadata = self.extract_from_pdf(pdf_path)

        # Update report metadata if discovered and not yet set
        if not report.lab_name and metadata.get("lab_name"):
            report.lab_name = metadata["lab_name"]
        if not report.collection_date and metadata.get("collection_date"):
            report.collection_date = metadata["collection_date"]

        # Check Modality Guardrail
        if metadata.get("is_unsupported_modality") or (not candidates and report.file_size_bytes > 500):
            # Check if text was empty (scanned image) vs unsupported
            with pdfplumber.open(str(pdf_path)) as pdf:
                page_texts = [p.extract_text() or "" for p in pdf.pages]
                total_text_len = sum(len(t) for t in page_texts)

            if total_text_len < 20:
                # Scanned image document (e.g. Layout C)
                report.status = "ocr_fallback_required"
            else:
                # Quantitative labs absent (e.g. ECG / ultrasound)
                report.status = "unsupported_modality"
            db.commit()
            return report

        # Clear any prior staged extraction rows for this report
        db.query(ExtractionRow).filter(ExtractionRow.report_id == report.id).delete()

        # Insert staged candidate rows
        for c in candidates:
            row = ExtractionRow(
                report_id=report.id,
                raw_marker_name=c["raw_marker_name"],
                raw_value=c["raw_value"],
                numeric_value=c["numeric_value"],
                raw_unit=c.get("raw_unit"),
                raw_reference_range=c.get("raw_reference_range"),
                flag=c.get("flag"),
                confidence=c.get("confidence", 0.95),
                status="needs_review",
            )
            db.add(row)

        report.status = "needs_review"
        db.commit()
        db.refresh(report)
        return report


extraction_service = ExtractionService()

