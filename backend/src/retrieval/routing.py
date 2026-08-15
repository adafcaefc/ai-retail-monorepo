from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.retail_data_bootstrap.semantic_contract import DOC_TYPE_RETRIEVAL_DOMAIN

from .models import (
    RetrievalRequest,
    RouteMode,
    RoutingConfidence,
    RoutingDecision,
    SelectedRoute,
    VectorFilters,
)


@dataclass(frozen=True)
class IntentMatch:
    intent: str
    reason_code: str
    filters: VectorFilters = field(default_factory=VectorFilters)


# Every pattern below carries Indonesian alternatives alongside the English.
# The product ships an EN/ID toggle, and this router is lexical: an Indonesian
# question that matched nothing used to fall through `decide()` all the way to
# the final `else` and come back UNSUPPORTED -- i.e. "kenapa SKU ini berisiko?"
# was refused with the same reason code as `DROP TABLE`. Refusing a user's own
# language is worse than routing it imperfectly, so the vocabulary is bilingual
# rather than English-first with a translation step in front.
#
# The safety patterns matter most here: without Indonesian write verbs, the
# mutation guard only watched one of the two languages the UI invites.
MUTATION_RE = re.compile(
    r"\b(delete|remove|update|change|set|insert|create|drop|alter|truncate|execute|exec|"
    r"hapus|menghapus|dihapus|ubah|mengubah|diubah|ganti|mengganti|diganti|"
    r"perbarui|memperbarui|diperbarui|sisipkan|menyisipkan|tambahkan|menambahkan|"
    r"ditambahkan|kosongkan|mengosongkan|jalankan|menjalankan|eksekusi)\b",
    re.IGNORECASE,
)
UNSAFE_RE = re.compile(
    r"\b(arbitrary\s+sql|run\s+sql|select\s+\*|union\s+select|drop\s+table|"
    r"tell\s+me\s+everything|(?:all|every|entire|full)(?:\s+\w+){0,3}\s+"
    r"(?:data|inventory|sales|records?|rows?|database|tables?|skus?|products?|stores?|vendors?)|"
    r"passwords?|credentials?|secrets?|api\s+keys?|"
    r"jalankan\s+sql|sql\s+bebas|tampilkan\s+semua|"
    r"(?:semua|seluruh|segala)(?:\s+\w+){0,3}\s+"
    r"(?:data|isi|persediaan|stok|penjualan|catatan|baris|basis\s+data|tabel|"
    r"produk|barang|toko|pemasok|vendor)|"
    r"kata\s+sandi|kredensial|kunci\s+api)\b",
    re.IGNORECASE,
)
EXPLANATION_RE = re.compile(
    r"\b(why|diagnos(?:e|is)|recommend|what\s+should|explain|relevant\s+(?:policy|formula|rule))\b|"
    r"\b(kenapa|mengapa|jelaskan|menjelaskan|penjelasan|terangkan|jelasin|"
    r"diagnosa|diagnosis|rekomendasi|rekomendasikan|sarankan|"
    r"sebaiknya|seharusnya|apa\s+yang\s+harus)\b",
    re.IGNORECASE,
)
CURRENT_RE = re.compile(
    r"\b(current|today|now|latest|currently|position|on[ -]?hand|reorder\s+point|\brop\b|"
    r"workforce|forecast|proposed|highest|ranking|count|total|sum)\b|"
    r"\b(saat\s+ini|sekarang|kini|terkini|terbaru|hari\s+ini|posisi|"
    r"stok|persediaan|jumlah|berapa|banyaknya|tertinggi|terendah|peringkat|"
    r"proyeksi|usulan|diusulkan|tenaga\s+kerja|ramalan|prakiraan|"
    r"titik\s+pemesanan(?:\s+ulang)?)\b",
    re.IGNORECASE,
)

# These terms identify a safe Retail/business-information question that may
# need a metric combination or horizon not represented by the fixed Phase 6
# capabilities. It is still a gate for adaptive planning, not a general-
# purpose natural-language SQL classifier; unsafe requests are rejected before
# this gate is considered.
ADAPTIVE_RETAIL_RE = re.compile(
    r"\b(retail\w*|sku\w*|product\w*|store\w*|vendor\w*|category\w*|"
    r"brand\w*|promotion\w*|inventory\w*|stock\w*|replenish\w*|demand\w*|"
    r"sales\w*|forecast\w*|basket\w*|mape|accuracy\w*|backtest\w*|margin\w*|"
    r"revenue\w*|purchase\w*|order\w*|assortment\w*|pricing\w*|markdown\w*|"
    r"gmroi|sell[- ]through\w*|service\s+level\w*|fill\s+rate\w*|otif|"
    r"lead\s+time\w*|days\s+(?:of\s+)?cover\w*|working\s+capital\w*|"
    r"staffing\w*|workforce\w*|labor\w*|labour\w*)\b|"
    r"\b(barang|produk|toko|gerai|pemasok|kategori|merek|promosi|diskon|"
    r"persediaan|stok|penjualan|permintaan|ramalan|prakiraan|akurasi|"
    r"margin|pendapatan|omzet|pembelian|pesanan|assortment|harga|"
    r"penurunan\s+harga|tingkat\s+layanan|waktu\s+tunggu|hari\s+cakupan|"
    r"modal\s+kerja|tenaga\s+kerja|karyawan|staf)\b",
    re.IGNORECASE,
)
ADAPTIVE_COMPLEXITY_RE = re.compile(
    r"\b(forecast|backtest(?:ed)?|mape|accuracy|basket|trend|compare|"
    r"projection|next\s+\d+\s+(?:day|week|month)s?|over\s+the\s+next|"
    r"by\s+(?:sku|product|store|category|vendor|brand)|across|"
    r"by|per|between|versus|vs|combine|including|using|calculate|"
    r"calculate\s+the|analy[sz]e|history|historical|average|total|sum|"
    r"highest|lowest|best|top|rank(?:ed|ing)?)\b|"
    r"\b(bandingkan|perbandingan|tren|proyeksi|ramalan|prakiraan|akurasi|"
    r"riwayat|historis|rata-rata|jumlah|gabungkan|hitung|hitungkan|"
    r"analisa|analisis|tertinggi|terendah|terbaik|teratas|peringkat|"
    r"per|setiap|antara|selama|sepanjang|"
    r"\d+\s+(?:hari|minggu|bulan|kuartal|tahun)\s+(?:ke\s+depan|terakhir))\b",
    re.IGNORECASE,
)
FAST_PATH_INSUFFICIENT_RE = re.compile(
    r"\b(backtest(?:ed)?|mape|accuracy|basket|trend|compare|comparison|projection|"
    r"next\s+\d+\s+(?:day|week|month)s?|over\s+the\s+next|across|combine|"
    r"including|analy[sz]e|by|per|between|versus|vs|forecast|demand|"
    r"sales|margin|revenue|gmroi|sell[- ]through|service\s+level|"
    r"highest|lowest|best|top|rank(?:ed|ing)?)\b",
    re.IGNORECASE,
)

RANKING_DIMENSION_RE = re.compile(
    r"\b(?:by|per|across)\s+(?:store|stores|category|categories|vendor|vendors|"
    r"brand|brands|legal\s+entit(?:y|ies))\b|"
    r"\b(?:stores|categories|vendors|brands|legal\s+entit(?:y|ies))\b",
    re.IGNORECASE,
)
ENTITY_REQUIRED_CAPABILITIES = {
    "sku.lookup",
    "sku.inventory_current",
    "sku.replenishment_current",
    "store.lookup",
    "store_sku.snapshot",
    "vendor.lookup",
    "category.lookup",
    "brand.lookup",
    "legal_entity.lookup",
    "promotion.lookup",
    "workforce.current",
    "sales.monthly",
    "trade_agreement.by_vendor",
}
CANONICAL_ENTITY_RE = re.compile(
    r"\b(?:[A-Z]{3}-\d{3}|[A-Z]{3}-C\d{2}|S\d{3}|V\d{4}|(?:PRM|PROMO)-?\d{2,5})\b"
)


def _fast_path_is_insufficient(text: str, capabilities: list[str]) -> bool:
    signals = set(FAST_PATH_INSUFFICIENT_RE.findall(text))
    # The fixed monthly-sales capability already covers a bounded history for
    # one resolved legal entity.  "sales" alone is therefore not an adaptive
    # combination signal; sales plus another signal still escalates.
    if capabilities == ["sales.monthly"]:
        signals.discard("sales")
    return bool(signals)


def _fast_path_lacks_entity_reference(request: RetrievalRequest, capabilities: list[str]) -> bool:
    """Do not treat an entity-bound Phase 6 lookup as an aggregate query."""
    if not set(capabilities) & ENTITY_REQUIRED_CAPABILITIES:
        return False
    return not request.entity_hints and not CANONICAL_ENTITY_RE.search(request.query)


def _planner_required(text: str, *, has_current: bool) -> bool:
    """Return whether a safe informational Retail request needs planning.

    A current-state word is not enough on its own: the existing SQL router
    must get first refusal. This helper only runs after all fixed capabilities
    have failed to match, and it intentionally requires both Retail vocabulary
    and an analytical/multi-requirement signal.
    """
    if not ADAPTIVE_RETAIL_RE.search(text) or not ADAPTIVE_COMPLEXITY_RE.search(text):
        return False
    # Forecast/accuracy and horizon questions are planner candidates even
    # without an explicit current-state word. Other analytical requests need
    # a present/future business context signal to avoid routing generic prose.
    return True


def _semantic_intent(text: str) -> IntentMatch | None:
    rules: tuple[tuple[re.Pattern[str], IntentMatch], ...] = (
        (
            re.compile(r"\b(which|what)\s+(product|sku)|perishable\s+fruit|product\s+is\b", re.I),
            IntentMatch("sku_semantics", "BUSINESS_ENTITY_INTENT", VectorFilters(retrieval_domain="business_entity", doc_type="sku")),
        ),
        (
            re.compile(
                r"\b(d365|dynamics\s*365|field\s+map|data\s+source\s+map|maps?\s+to|comes?\s+from)\b|"
                r"\b(pemetaan\s+(?:field|kolom|data)|berasal\s+dari|asalnya\s+dari|sumber\s+datanya)\b",
                re.I,
            ),
            IntentMatch("integration_mapping", "INTEGRATION_MAPPING_INTENT", VectorFilters(retrieval_domain="integration")),
        ),
        (
            re.compile(
                r"\b(approv(?:e|es|al|er)|high[- ]value\s+(?:purchase|purchasing|order))\b|"
                r"\b(persetujuan|menyetujui|disetujui|otorisasi|"
                r"pembelian\s+(?:besar|bernilai\s+tinggi))\b",
                re.I,
            ),
            IntentMatch("approval_rule", "GOVERNANCE_INTENT", VectorFilters(retrieval_domain="governance", doc_type="approval_rule")),
        ),
        (
            re.compile(r"\b(which|what)\s+agent|agent\s+(?:handles|responsib|role)\b", re.I),
            IntentMatch("agent_responsibility", "AGENT_CONFIGURATION_INTENT", VectorFilters(retrieval_domain="agent_configuration", doc_type="agent_spec")),
        ),
        (
            re.compile(
                r"\b(formula|calculated|calculation|how\s+is\b|derive[ds]?)\b|"
                r"\b(rumus|perhitungan|dihitung|menghitungnya|diturunkan)\b",
                re.I,
            ),
            IntentMatch("formula", "FORMULA_INTENT", VectorFilters(retrieval_domain="business_rule", doc_type="formula")),
        ),
        (
            re.compile(
                r"\b(what\s+does|what\s+is\s+the\s+meaning|definition|define|terminology|mean\??$)\b|"
                r"\b(apa\s+(?:itu|arti|maksud)|artinya|maksudnya|definisi|istilah|pengertian)\b",
                re.I,
            ),
            IntentMatch("definition", "DEFINITION_INTENT", VectorFilters(retrieval_domain="business_rule", doc_type="terminology")),
        ),
        (
            re.compile(r"\b(model\s+parameter|parameter\s+meaning)\b", re.I),
            IntentMatch("model_parameter", "MODEL_PARAMETER_INTENT", VectorFilters(retrieval_domain="business_rule", doc_type="model_parameter")),
        ),
        (
            re.compile(r"\b(commercial\s+terms|vendor\s+(?:meaning|context|semantics))\b", re.I),
            IntentMatch("vendor_semantics", "BUSINESS_ENTITY_INTENT", VectorFilters(retrieval_domain="business_entity", doc_type="vendor")),
        ),
        (
            re.compile(r"\b(store\s+(?:meaning|semantics)|which\s+store\b)", re.I),
            IntentMatch("store_semantics", "BUSINESS_ENTITY_INTENT", VectorFilters(retrieval_domain="business_entity", doc_type="store")),
        ),
        (
            re.compile(r"\b(category\s+(?:meaning|semantics)|which\s+category\b)", re.I),
            IntentMatch("category_semantics", "BUSINESS_ENTITY_INTENT", VectorFilters(retrieval_domain="business_entity", doc_type="category")),
        ),
        (
            re.compile(r"\b(brand\s+event|event\s+context)\b", re.I),
            IntentMatch("brand_event", "OPERATIONAL_CONTEXT_INTENT", VectorFilters(retrieval_domain="operational_context", doc_type="brand_event")),
        ),
        (
            re.compile(r"\b(promotion\s+(?:policy|mechanism|rule))\b", re.I),
            IntentMatch("promotion_policy", "OPERATIONAL_POLICY_INTENT", VectorFilters(retrieval_domain="operational_policy", doc_type="promotion")),
        ),
        (
            re.compile(r"\b(workbook\s+(?:overview|documentation)|documentation)\b", re.I),
            IntentMatch("documentation", "DOCUMENTATION_INTENT", VectorFilters(retrieval_domain="documentation", doc_type="workbook_overview")),
        ),
        (
            re.compile(
                r"\b(business\s+rule|policy|risk|days[ -]of[ -]supply)\b|"
                r"\b(aturan\s+bisnis|kebijakan|risiko|berisiko|hari\s+cakupan)\b",
                re.I,
            ),
            IntentMatch("business_rule", "BUSINESS_RULE_INTENT", VectorFilters(retrieval_domain="business_rule")),
        ),
    )
    for pattern, match in rules:
        if pattern.search(text):
            return match
    return None


# Indonesian retail vocabulary folded onto the English keys `_sql_capabilities`
# already matches on, so one lookup table serves both languages instead of a
# second parallel chain of `if` branches that would drift out of sync.
_ID_SQL_SYNONYMS = (
    ("persediaan", "inventory"),
    ("stok", "inventory"),
    ("posisi stok", "stock position"),
    ("sisa stok", "on hand"),
    ("di tangan", "on hand"),
    ("titik pemesanan ulang", "reorder point"),
    ("titik pemesanan", "reorder point"),
    ("hari cakupan", "days of supply"),
    ("pengisian ulang", "replenish"),
    ("pengisian", "replenish"),
    ("diusulkan", "proposed"),
    ("usulan", "proposed"),
    ("jumlah pesanan", "order quantity"),
    ("tenaga kerja", "workforce"),
    ("karyawan", "staff"),
    ("penjualan bulanan", "monthly sales"),
    ("riwayat penjualan", "sales history"),
    ("perjanjian dagang", "trade agreement"),
    ("pemasok", "vendor"),
    ("waktu tunggu", "lead time"),
    ("kategori", "category"),
    ("merek", "brand"),
    ("entitas hukum", "legal entity"),
    ("toko", "store"),
    ("gerai", "store"),
    ("barang", "sku"),
    ("produk", "product"),
    ("promosi", "promotion"),
    ("diskon", "discount"),
    ("harga", "price"),
    ("biaya", "cost"),
    ("berisiko", "at-risk"),
    ("tertinggi", "highest"),
    ("teratas", "top"),
    ("peringkat", "ranking"),
    ("saat ini", "current"),
    ("sekarang", "current"),
    ("terkini", "current"),
    ("terbaru", "latest"),
    ("rincian", "details"),
    ("detail", "details"),
)


def _sql_capabilities(text: str) -> tuple[str, list[str]]:
    lowered = text.lower()
    # Longest first, so "posisi stok" is not consumed by "stok".
    for indonesian, english in sorted(_ID_SQL_SYNONYMS, key=lambda pair: -len(pair[0])):
        if indonesian in lowered:
            lowered += " " + english
    if re.search(r"highest|top|ranking|ranked", lowered) and "replenish" in lowered:
        return "replenishment_ranking", ["replenishment.top_candidates"]
    if re.search(r"highest|top|ranking|ranked|at[- ]risk", lowered) and "inventory" in lowered:
        return "inventory_risk_ranking", ["inventory.at_risk"]
    if "workforce" in lowered or re.search(r"\bfte\b|staff(?:ing)?", lowered):
        return "workforce_current", ["workforce.current"]
    if "replenish" in lowered or "proposed" in lowered or "order quantity" in lowered:
        return "replenishment_current", ["sku.replenishment_current"]
    if "store" in lowered and "sku" in lowered and any(value in lowered for value in ("snapshot", "current", "inventory", "forecast")):
        return "store_sku_current", ["store_sku.snapshot"]
    if any(value in lowered for value in ("inventory", "reorder point", "on hand", "on-hand", "days of supply", "stock position")) or re.search(r"\bdays[- ]of[- ]supply\b|\brop\b", lowered):
        return "inventory_current", ["sku.inventory_current"]
    if "monthly sales" in lowered or "sales history" in lowered:
        return "monthly_sales", ["sales.monthly"]
    if "promotion" in lowered and any(value in lowered for value in ("current", "configuration", "value", "discount")):
        return "promotion_lookup", ["promotion.lookup"]
    if "trade agreement" in lowered or "current vendor terms" in lowered:
        return "trade_agreement", ["trade_agreement.by_vendor"]
    if "vendor" in lowered and any(value in lowered for value in ("current", "performance", "otif", "lead time", "moq")):
        return "vendor_lookup", ["vendor.lookup"]
    if "category" in lowered and any(value in lowered for value in ("lookup", "details", "current", "exact")):
        return "category_lookup", ["category.lookup"]
    if "brand" in lowered and any(value in lowered for value in ("lookup", "details", "current", "exact")):
        return "brand_lookup", ["brand.lookup"]
    if "legal entity" in lowered and any(value in lowered for value in ("lookup", "details", "current", "exact")):
        return "legal_entity_lookup", ["legal_entity.lookup"]
    if "store" in lowered and any(value in lowered for value in ("lookup", "details", "which", "current")):
        return "store_lookup", ["store.lookup"]
    if re.search(r"\b(price|cost|margin)\b", lowered) and re.search(r"\b(current|exact|latest)\b", lowered):
        return "sku_lookup", ["sku.lookup"]
    if re.search(r"\bsku\b|\bitem\b|\bproduct\b", lowered) and any(value in lowered for value in ("lookup", "master", "current details", "exact")):
        return "sku_lookup", ["sku.lookup"]
    return "unsupported_structured", []


def _merge_filters(request: RetrievalRequest, inferred: VectorFilters) -> VectorFilters:
    domain = inferred.retrieval_domain
    doc_type = inferred.doc_type
    if request.retrieval_domain and domain and request.retrieval_domain != domain:
        raise ValueError(
            f"Requested retrieval_domain {request.retrieval_domain!r} conflicts with "
            f"inferred {domain!r}"
        )
    if request.doc_type and doc_type and request.doc_type != doc_type:
        raise ValueError(
            f"Requested doc_type {request.doc_type!r} conflicts with inferred {doc_type!r}"
        )
    domain = request.retrieval_domain or domain
    doc_type = request.doc_type or doc_type
    if doc_type:
        expected = DOC_TYPE_RETRIEVAL_DOMAIN[doc_type]
        if domain and domain != expected:
            raise ValueError(
                f"Document type {doc_type!r} is incompatible with domain {domain!r}"
            )
        domain = domain or expected
    return VectorFilters(retrieval_domain=domain, doc_type=doc_type)


class DeterministicRouter:
    """Bounded lexical router; confidence is categorical, never probabilistic."""

    def decide(self, request: RetrievalRequest) -> RoutingDecision:
        text = " ".join(request.query.split())
        if not text:
            return RoutingDecision(
                selected_route=SelectedRoute.UNSUPPORTED,
                confidence=RoutingConfidence.HIGH,
                reason_codes=["EMPTY_QUERY"],
                recognized_intent="empty_query",
            )
        if MUTATION_RE.search(text) or UNSAFE_RE.search(text):
            return RoutingDecision(
                selected_route=SelectedRoute.UNSUPPORTED,
                confidence=RoutingConfidence.HIGH,
                reason_codes=["UNSUPPORTED_MUTATION" if MUTATION_RE.search(text) else "UNSUPPORTED_STRUCTURED_INTENT"],
                recognized_intent="unsupported_write_or_arbitrary_query",
            )

        semantic = _semantic_intent(text)
        sql_intent, capabilities = _sql_capabilities(text)
        has_current = bool(CURRENT_RE.search(text))
        has_explanation = bool(EXPLANATION_RE.search(text))
        inferred_filters = semantic.filters if semantic else VectorFilters()
        filters = _merge_filters(request, inferred_filters)
        ranking_capability = bool(
            capabilities
            and capabilities[0] in {"inventory.at_risk", "replenishment.top_candidates"}
        )
        ranking_needs_adaptive = ranking_capability and bool(RANKING_DIMENSION_RE.search(text))
        fast_path_insufficient = bool(
            capabilities
            and _fast_path_is_insufficient(text, capabilities)
            and ADAPTIVE_RETAIL_RE.search(text)
            and not (ranking_capability and not ranking_needs_adaptive)
        )
        # Semantic definition/formula/entity questions keep their Phase 6
        # VECTOR route even when a Retail noun also matches a broad SQL
        # keyword. Only an otherwise-structured request is considered for
        # aggregate planning here.
        missing_fast_path_entity = (
            semantic is None
            and _fast_path_lacks_entity_reference(request, capabilities)
        )

        auto_route = SelectedRoute.UNSUPPORTED
        reasons: list[str] = []
        intent = semantic.intent if semantic else sql_intent
        if ranking_capability and not ranking_needs_adaptive and not fast_path_insufficient:
            auto_route = SelectedRoute.SQL
            reasons = ["CURRENT_STATE_INTENT"]
            intent = sql_intent
        elif fast_path_insufficient or missing_fast_path_entity:
            auto_route = SelectedRoute.PLANNER_REQUIRED
            intent = "adaptive_retail_query"
            reasons = ["PLANNER_REQUIRED"]
            if fast_path_insufficient:
                reasons.append("FAST_PATH_INSUFFICIENT")
            if missing_fast_path_entity:
                reasons.append("FAST_PATH_REQUIRES_ENTITY")
        elif capabilities and (has_explanation or (semantic and has_current)):
            auto_route = SelectedRoute.HYBRID
            reasons = ["CURRENT_PLUS_EXPLANATION", "CURRENT_STATE_INTENT"]
            if semantic:
                reasons.append(semantic.reason_code)
            if not filters.retrieval_domain:
                filters = VectorFilters(retrieval_domain="business_rule")
        elif semantic and has_current and _planner_required(text, has_current=has_current):
            auto_route = SelectedRoute.PLANNER_REQUIRED
            intent = "adaptive_retail_query"
            reasons = ["PLANNER_REQUIRED"]
        elif semantic and not has_current:
            auto_route = SelectedRoute.VECTOR
            reasons = [semantic.reason_code]
        elif capabilities:
            auto_route = SelectedRoute.SQL
            reasons = ["CURRENT_STATE_INTENT"]
            if re.search(r"[A-Za-z]{3}-\d{3}|S\d{3}|V\d{4}", text, re.I):
                reasons.append("EXACT_ENTITY_LOOKUP")
        elif semantic:
            auto_route = SelectedRoute.VECTOR
            reasons = [semantic.reason_code]
        elif request.retrieval_domain or request.doc_type:
            auto_route = SelectedRoute.VECTOR
            intent = "explicit_semantic_filter"
            reasons = ["EXPLICIT_VECTOR_FILTER"]
        elif _planner_required(text, has_current=has_current):
            auto_route = SelectedRoute.PLANNER_REQUIRED
            intent = "adaptive_retail_query"
            reasons = ["PLANNER_REQUIRED"]
        else:
            reasons = ["UNSUPPORTED_STRUCTURED_INTENT"]

        route = auto_route
        if request.route_mode != RouteMode.AUTO:
            requested = SelectedRoute(request.route_mode.value.upper())
            if requested == SelectedRoute.SQL and (
                not capabilities or (semantic is not None and not has_current)
            ):
                route = SelectedRoute.UNSUPPORTED
                reasons = ["UNSUPPORTED_STRUCTURED_CAPABILITY"]
            elif requested == SelectedRoute.VECTOR and not (semantic or request.retrieval_domain or request.doc_type):
                route = SelectedRoute.UNSUPPORTED
                reasons = ["INVALID_ROUTE_OVERRIDE"]
            elif requested == SelectedRoute.HYBRID and not capabilities:
                route = SelectedRoute.UNSUPPORTED
                reasons = ["UNSUPPORTED_STRUCTURED_CAPABILITY", "INVALID_ROUTE_OVERRIDE"]
            elif requested == SelectedRoute.VECTOR and auto_route == SelectedRoute.PLANNER_REQUIRED:
                # Adaptive execution has already policy-validated a bounded
                # semantic requirement and supplies an explicit domain/type.
                # Permit that branch to force semantic retrieval even when
                # the natural-language evidence query contains planner words
                # such as "forecast" or "compare".  An unfiltered vector
                # override remains rejected below this condition.
                if request.retrieval_domain or request.doc_type:
                    route = requested
                    reasons = [*reasons, "EXPLICIT_ROUTE_OVERRIDE"]
                else:
                    route = SelectedRoute.UNSUPPORTED
                    reasons = ["UNSUPPORTED_STRUCTURED_CAPABILITY"]
            elif requested == SelectedRoute.SQL and auto_route == SelectedRoute.PLANNER_REQUIRED:
                route = SelectedRoute.UNSUPPORTED
                reasons = ["UNSUPPORTED_STRUCTURED_CAPABILITY"]
            else:
                route = requested
                reasons = [*reasons, "EXPLICIT_ROUTE_OVERRIDE"]

        confidence = (
            RoutingConfidence.HIGH
            if route != SelectedRoute.UNSUPPORTED and (semantic or capabilities)
            else RoutingConfidence.LOW
        )
        return RoutingDecision(
            selected_route=route,
            confidence=confidence,
            reason_codes=list(dict.fromkeys(reasons)),
            recognized_intent=intent,
            selected_sql_capabilities=capabilities if route in {SelectedRoute.SQL, SelectedRoute.HYBRID} else [],
            selected_vector_filters=filters if route in {SelectedRoute.VECTOR, SelectedRoute.HYBRID} else VectorFilters(),
            fallback_allowed=False,
        )
