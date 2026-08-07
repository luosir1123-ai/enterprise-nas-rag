from __future__ import annotations

import re
import unicodedata
from pathlib import PurePath


BUSINESS_METADATA_VERSION = "deterministic-v1"
MODEL_PATTERNS = (
    re.compile(r"(?<![A-Za-z0-9])([A-Za-z]{1,8}[-_][A-Za-z0-9][A-Za-z0-9_-]{1,30})(?![A-Za-z0-9])"),
    re.compile(r"(?<![A-Za-z0-9])([A-Za-z]{1,5}[0-9][A-Za-z0-9]{0,10})(?![A-Za-z0-9])"),
)
MODEL_EXCLUSIONS = {"A3", "A4", "A5", "V1", "V2", "V3", "V4", "V5"}
MODEL_PREFIX_EXCLUSIONS = ("EN", "IEC", "FCC", "UKCA", "ROHS")
YEAR_RE = re.compile(r"(?<!\d)(20[0-3]\d)(?!\d)")
COMPACT_DATE_RE = re.compile(r"(?<!\d)(20[0-3]\d)(0[1-9]|1[0-2])(?:[0-3]\d)?(?!\d)")
PREFIX_DATE_RE = re.compile(r"(?<!\d)(20[0-3]\d)(0[1-9]|1[0-2])(?:[0-3]\d)\d+")
SEPARATED_DATE_RE = re.compile(r"(?<!\d)(20[0-3]\d)[._/\-年](0?[1-9]|1[0-2])(?:月|[._/\-][0-3]?\d)?(?!\d)")
SEASON_RULES = (
    ("spring", re.compile(r"(?:\bspring\b|春季|春款)", re.IGNORECASE)),
    ("summer", re.compile(r"(?:\bsummer\b|夏季|夏款)", re.IGNORECASE)),
    ("fall", re.compile(r"(?:\bfall\b|\bautumn\b|秋季|秋款)", re.IGNORECASE)),
    ("winter", re.compile(r"(?:\bwinter\b|冬季|冬款)", re.IGNORECASE)),
)
DOCUMENT_TYPE_RULES = (
    ("specification", ("规格书", "specification", "datasheet", "spec sheet", "spec-sheet")),
    ("certification", ("认证", "证书", "certificate", "certification", "cb报告", "cb report", "test report", "测试报告")),
    ("quotation", ("报价", "quotation", "quote", "price list", "pricelist")),
    ("bom", ("bom", "bill of material", "物料清单")),
    ("catalog", ("catalog", "catalogue", "产品目录", "产品册")),
    ("drawing", ("图纸", "drawing", "cad", "2d", "3d")),
    ("manual", ("说明书", "manual", "user guide", "quick start")),
    ("contract", ("合同", "contract", "agreement")),
    ("claim", ("理赔", "claim")),
    ("tracker", ("tracker", "tracking", "跟进表", "追踪表")),
    ("brochure", ("宣传册", "brochure", "flyer", "leaflet")),
)
AUTHORITY_BY_DOCUMENT_TYPE = {
    "specification": (100, 25, 35),
    "certification": (90, 10, 10),
    "quotation": (45, 100, 80),
    "bom": (85, 75, 85),
    "catalog": (65, 55, 95),
    "drawing": (90, 10, 20),
    "manual": (80, 15, 20),
    "contract": (60, 85, 70),
    "claim": (55, 50, 50),
    "tracker": (50, 65, 75),
    "brochure": (35, 25, 40),
    "other": (50, 50, 50),
}
VERSION_RE = re.compile(r"(?<![A-Za-z0-9])((?:v(?:er(?:sion)?)?|rev)[._ -]?\d+(?:[._-]\d+)*)", re.IGNORECASE)


def normalized_text(value: str) -> str:
    return unicodedata.normalize("NFKC", str(value or ""))


def extract_models(value: str) -> list[str]:
    text = normalized_text(value)
    models = []
    for pattern in MODEL_PATTERNS:
        for match in pattern.finditer(text):
            model = match.group(1).upper().replace("_", "-")
            if (
                model in MODEL_EXCLUSIONS
                or model in models
                or not any(character.isdigit() for character in model)
                or any(model.startswith(prefix) for prefix in MODEL_PREFIX_EXCLUSIONS)
            ):
                continue
            models.append(model)
    return models


def infer_document_type(value: str) -> str:
    text = normalized_text(value).casefold()
    for document_type, keywords in DOCUMENT_TYPE_RULES:
        if any(keyword.casefold() in text for keyword in keywords):
            return document_type
    return "other"


def infer_business_metadata(relative_path: str, kb_key: str = "") -> dict:
    path_text = normalized_text(relative_path).replace("\\", "/").strip("/")
    filename = PurePath(path_text).name
    parent_path = str(PurePath(path_text).parent)
    searchable = f"{filename} {parent_path}"
    models = extract_models(filename) or extract_models(parent_path)

    year = ""
    month = ""
    for source in (filename, parent_path):
        date_match = COMPACT_DATE_RE.search(source) or PREFIX_DATE_RE.search(source) or SEPARATED_DATE_RE.search(source)
        years = list(dict.fromkeys(match.group(1) for match in YEAR_RE.finditer(source)))
        if date_match or years:
            year = date_match.group(1) if date_match else years[0]
            month = date_match.group(2).zfill(2) if date_match else ""
            break
    season = ""
    for source in (filename, parent_path):
        season = next((name for name, pattern in SEASON_RULES if pattern.search(source)), "")
        if season:
            break
    document_type = infer_document_type(filename)
    if document_type == "other":
        document_type = infer_document_type(parent_path)
    technical, price, sales_cost = AUTHORITY_BY_DOCUMENT_TYPE[document_type]
    if document_type == "catalog" and "有成本" in filename:
        price = max(price, 70)
        sales_cost = 100
    version_match = VERSION_RE.search(searchable)

    return {
        "business_metadata_version": BUSINESS_METADATA_VERSION,
        "business_metadata_source": "filename_and_nas_path",
        "document_type": document_type,
        "model": models[0] if models else "",
        "models": models,
        "year": year,
        "doc_year": year,
        "month": month,
        "season": season,
        "business_version": version_match.group(1).upper() if version_match else "",
        "authority_level": max(technical, price, sales_cost),
        "authority_technical": technical,
        "authority_price": price,
        "authority_sales_cost": sales_cost,
        "authority_policy_version": "v1",
        "business_scope": kb_key,
    }
