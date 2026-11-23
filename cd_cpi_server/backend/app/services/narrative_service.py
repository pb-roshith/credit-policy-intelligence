"""
Narrative Service — orchestrates section narrative generation via Mistral Agents.

Pipeline per section:
    1. Moderation gate (user-provided inputs)
    2. Orchestration pre-flight (MCP summaries → document selection strategy)
    3. Deal context + relevant PostgreSQL table selection
    4. Generation via section agent (structured tables + PDF library RAG)
    5. Accuracy evaluation

- Single section: full pipeline for one section
- Draft all: PDF summaries and tables fetched ONCE, then reused across 16 sections
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Callable
from datetime import datetime, timezone

from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.models.deal import Deal, Section, AuditEntry
from app.models.library_file import LibraryFile
from app.models.user import User
from app.services.mistral_library_service import MistralLibraryService
from app.services.narrative_version_service import NarrativeVersionService
from app.services.moderation_service import ModerationService
from app.services.orchestration_service import OrchestrationService, OrchestrationResult
from app.services.mcp_service import MCPClientService
from app.services.url_scraper_service import scrape_urls
from app.telemetry import get_tracer, set_span_attributes, trace_span

logger = logging.getLogger(__name__)


SECTION_TABLE_SUFFIXES: dict[str, tuple[str, ...]] = {
    "executive_summary": (
        "section2_customer_information",
        "section3_customer_financial_information_historical",
        "section3a_customer_facilities",
        "section3b_credit_committee_resolution",
    ),
    "client_overview": (
        "section2_customer_information",
        "section2_ownership_structure",
    ),
    "relationship_summary": (
        "credit_bank_statements",
        "section3a_customer_facilities",
        "section3a_other_financial_institution_exposure",
    ),
    "industry_analysis": ("section2_customer_information",),
    "financial_analysis": (
        "credit_income_statement",
        "credit_balance_sheet",
        "section3_customer_financial_information_historical",
    ),
    "ratio_analysis": (
        "credit_income_statement",
        "credit_balance_sheet",
        "credit_cashflow_statement",
        "section3_customer_financial_information_historical",
    ),
    "cash_flow_analysis": (
        "credit_cashflow_statement",
        "credit_bank_statements",
        "credit_projected_financials",
    ),
    "qualitative_assessment": (
        "section2_customer_information",
        "section2_ownership_structure",
        "section3b_documentation_security_exceptions",
    ),
    "credit_risk_assessment": (
        "section3_customer_financial_information_historical",
        "section3a_other_financial_institution_exposure",
        "section3b_documentation_security_exceptions",
        "section3b_covenant_description",
    ),
    "facility_structure": (
        "section3a_customer_facilities",
        "section3a_other_financial_institution_exposure",
    ),
    "policy_mapping": (
        "section3b_documentation_security_exceptions",
        "section3b_covenant_description",
        "section3b_credit_committee_resolution",
    ),
    "collateral_and_security": (
        "credit_net_worth_statement",
        "section3a_collateral_guarantee_information",
    ),
    "covenants_and_conditions": (
        "section3b_covenant_description",
        "section3b_documentation_security_exceptions",
    ),
    "esg_analysis": ("section2_customer_information",),
    "key_risks_and_mitigants": (
        "section3_customer_financial_information_historical",
        "section3a_collateral_guarantee_information",
        "section3b_documentation_security_exceptions",
        "section3b_covenant_description",
    ),
    "appendix": (),
}


def structured_context_for_section(
    structured_data: dict[str, object],
    section_key: str,
) -> str:
    """Select and size the PostgreSQL tables relevant to one section."""
    all_tables = structured_data.get("tables")
    if not isinstance(all_tables, dict) or not all_tables:
        return ""
    suffixes = SECTION_TABLE_SUFFIXES.get(section_key)
    if suffixes is None:
        return ""
    selected = {
        name: rows
        for name, rows in all_tables.items()
        if not suffixes or any(name.endswith(suffix) for suffix in suffixes)
    }
    if not selected:
        return ""
    rendered = json.dumps(
        {
            "company": structured_data.get("company"),
            "tables": selected,
        },
        default=str,
        indent=2,
    )
    max_chars = min(settings.MAX_GROUNDING_CHARS // 2, 60_000)
    if len(rendered) > max_chars:
        rendered = rendered[:max_chars] + "\n[Structured data truncated]"
    return rendered


def source_urls_for_section(section: Section) -> list[str]:
    if not section.source_urls:
        return []
    try:
        parsed = json.loads(section.source_urls)
    except (json.JSONDecodeError, TypeError):
        return []
    return [str(url) for url in parsed if isinstance(url, str)] if isinstance(parsed, list) else []


class NarrativeService:
    """Orchestrates narrative generation using section-specific Mistral agents."""

    @staticmethod
    def _owner_key(db: Session, deal: Deal) -> str:
        owner = db.get(User, deal.owner_user_id)
        if not owner:
            raise ValueError("The deal owner no longer exists.")
        return owner.user_id

    # ── Single Section Generation ──────────────────────────────────

    @staticmethod
    async def generate_section(
        db: Session,
        deal_id: str,
        section_id: str,
        custom_instructions: str | None = None,
    ) -> Section | None:
        deal = db.get(Deal, deal_id)
        if not deal:
            return None
        async with MistralLibraryService.agent_library_scope(
            db, MistralLibraryService.library_ids_for_deal(deal)
        ):
            return await NarrativeService._generate_section_with_configured_agents(
                db, deal_id, section_id, custom_instructions
            )

    @staticmethod
    async def _generate_section_with_configured_agents(
        db: Session,
        deal_id: str,
        section_id: str,
        custom_instructions: str | None = None,
    ) -> Section | None:
        """
        Generate narrative for a single section using the full pipeline:
        moderation → orchestration → context optimization → generation → accuracy.
        """
        deal = (
            db.query(Deal)
            .options(
                joinedload(Deal.sections),
                joinedload(Deal.library_files),
            )
            .filter(Deal.id == deal_id)
            .first()
        )
        if not deal:
            return None

        section = next((s for s in deal.sections if s.id == section_id), None)
        if not section:
            return None

        # Update custom instructions if provided
        if custom_instructions is not None:
            section.custom_instructions = custom_instructions

        total_start = time.time()
        tracer = get_tracer()

        # Start pipeline-level parent span — all child spans nest under this
        span_ctx = None
        span = None
        if tracer:
            span_ctx = tracer.start_as_current_span("generate_section_pipeline")
            span = span_ctx.__enter__()
            set_span_attributes(span,
                operation="generate_section_pipeline",
                deal_id=deal_id,
                section_id=section_id,
                section_key=section.section_key,
                section_title=section.title,
                customer=deal.customer or "",
                has_custom_instructions=str(bool(section.custom_instructions)),
                has_output_template=str(bool(section.output_template)),
            )

        with trace_span(
            "user_request",
            deal_id=deal_id,
            section_id=section_id,
            section_key=section.section_key,
        ) as request_span:
            set_span_attributes(request_span, result="accepted")

        moderation_metrics = {
            "name": "Moderation",
            "model": "mistral-moderation-latest",
            "status": "skipped",
            "latency_ms": None,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        }

        # ── Step 1: Moderation Gate ──────────────────────────────
        moderation_required = bool(section.custom_instructions or section.output_template)
        with trace_span(
            "moderation_gate",
            section_id=section_id,
            required=moderation_required,
        ) as moderation_span:
            if moderation_required:
                moderation = await ModerationService.moderate_section_inputs(
                    custom_instructions=section.custom_instructions,
                    output_template=section.output_template,
                )
                section.moderation_status = "safe" if moderation.is_safe else "flagged"
                section.moderation_details = json.dumps(moderation.to_dict())
                moderation_metrics.update(
                    {
                        "status": "success" if moderation.is_safe else "flagged",
                        "latency_ms": round(moderation.latency_ms),
                        "input_tokens": moderation.input_tokens,
                        "output_tokens": moderation.output_tokens,
                        "total_tokens": moderation.total_tokens,
                    }
                )
                set_span_attributes(
                    moderation_span,
                    result="safe" if moderation.is_safe else "flagged",
                )

                if not moderation.is_safe:
                    db.commit()
                    db.refresh(section)
                    flagged = ", ".join(moderation.flagged_categories)
                    raise ValueError(
                        f"Content moderation failed for '{section.title}'. "
                        f"Flagged categories: {flagged}. "
                        f"Please review and edit your custom instructions or output template."
                    )
            else:
                section.moderation_status = None
                section.moderation_details = None
                set_span_attributes(moderation_span, result="skipped")

        # ── Step 2: Orchestration Pre-flight ─────────────────────
        orch_start = time.time()
        with trace_span(
            "orchestration_preflight",
            deal_id=deal_id,
            section_id=section_id,
        ) as orchestration_span:
            orchestration = await NarrativeService._run_orchestration(
                deal=deal,
                section=section,
                db=db,
            )
            set_span_attributes(
                orchestration_span,
                result="completed",
                confidence=orchestration.confidence,
            )
        orch_ms = (time.time() - orch_start) * 1000
        orchestration_metrics = {
            "name": "Orchestration Agent",
            "model": settings.MISTRAL_AGENT_MODEL,
            "status": "success",
            "latency_ms": round(orch_ms),
            "input_tokens": orchestration.input_tokens,
            "output_tokens": orchestration.output_tokens,
            "total_tokens": orchestration.total_tokens,
        }

        # ── Step 3: Build Section-Specific Deal Context ──────────
        with trace_span(
            "context_assembly",
            deal_id=deal_id,
            section_id=section_id,
            customer=deal.customer,
        ) as context_span:
            deal_context = OrchestrationService.build_deal_context_for_section(
                deal, section.section_key
            )
            owner_key = NarrativeService._owner_key(db, deal)
            structured_data = await MCPClientService.get_structured_data_cached(
                deal.customer, owner_key
            )
            structured_context = structured_context_for_section(
                structured_data,
                section.section_key,
            )
            web_context, url_scrape_details = await scrape_urls(
                source_urls_for_section(section)
            )
            section.url_scrape_details = json.dumps(url_scrape_details)
            set_span_attributes(
                context_span,
                result="completed",
                deal_context_chars=len(deal_context),
                structured_context_chars=len(structured_context or ""),
                web_context_chars=len(web_context),
            )

        # ── Step 4: Generate via Mistral Agent ───────────────────
        agent_id = MistralLibraryService.get_global_agent_id(db, section.section_key)
        if not agent_id:
            raise ValueError(f"Global agent for {section.section_key} not initialized")

        gen_start = time.time()
        generation_metrics: dict[str, object] = {}
        content = await MistralLibraryService.generate_with_agent(
            agent_id=agent_id,
            section_title=section.title,
            section_description=section.description,
            expected_output=section.expected_output,
            deal_context=deal_context,
            structured_data=structured_context,
            orchestration_strategy=orchestration.to_strategy_text(),
            custom_instructions=section.custom_instructions,
            output_template=section.output_template,
            metrics_out=generation_metrics,
            web_context=web_context,
        )
        gen_ms = (time.time() - gen_start) * 1000

        # Preserve the current draft before regeneration, then save the new one.
        with trace_span(
            "narrative_version_staging",
            deal_id=deal_id,
            section_id=section_id,
        ) as staging_span:
            NarrativeVersionService.ensure_current(db, section)
            section.generated_content = content
            section.original_generated_content = content
            section.state = "ready"
            section.orchestration_strategy = orchestration.to_strategy_text()
            staged_version = NarrativeVersionService.create(
                db,
                section,
                content,
                "generated",
                f"Mistral Agent: {section.section_key}",
            )
            set_span_attributes(
                staging_span,
                result="staged",
                version_id=staged_version.id,
            )

        # ── Step 5: Accuracy Evaluation ──────────────────────────
        acc_start = time.time()
        has_docs = bool(MistralLibraryService.library_ids_for_deal(deal))
        accuracy = await MistralLibraryService.evaluate_accuracy(
            generated_content=content,
            section_title=section.title,
            has_library_docs=has_docs,
        )
        acc_ms = (time.time() - acc_start) * 1000

        if accuracy:
            section.accuracy_score = accuracy["score"]
            section.accuracy_details = json.dumps(accuracy)
        else:
            section.accuracy_score = None
            section.accuracy_details = None

        confidence_from_judge = bool(
            accuracy and accuracy.get("confidence_source") == "observability_judge"
        )
        judge_metrics = (
            accuracy.get("judge_observability")
            if accuracy and accuracy.get("judge_observability")
            else accuracy.get("observability", {})
            if confidence_from_judge
            else {
                "name": "Confidence Judge",
                "model": "Mistral Observability Judge",
                "status": "fallback" if accuracy else "not_scored",
                "latency_ms": None,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "token_usage_available": False,
            }
        )
        claim_evaluator_metrics = (
            accuracy.get("claim_evaluator_observability") if accuracy else None
        ) or {
                "name": "Claim Classification Evaluator",
                "model": settings.MISTRAL_MODEL,
                "status": "not_evaluated",
                "latency_ms": None,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
            }
        section.observability_details = json.dumps(
            {
                "moderation": moderation_metrics,
                "orchestration": orchestration_metrics,
                "section_agent": generation_metrics,
                "judge": judge_metrics,
                "claim_evaluator": claim_evaluator_metrics,
            }
        )

        # ── Audit + Timing ───────────────────────────────────────
        total_ms = (time.time() - total_start) * 1000
        mode = "few-shot" if section.custom_instructions else "zero-shot"
        has_template = " with template" if section.output_template else ""
        doc_count = deal.company_document_count + len(deal.library_files)
        accuracy_tag = f", accuracy={accuracy['score']}%" if accuracy else ""

        timing_tag = ""
        if settings.ENABLE_TIMING_METRICS:
            timing_tag = (
                f", timing: orch={orch_ms:.0f}ms "
                f"gen={gen_ms:.0f}ms "
                f"acc={acc_ms:.0f}ms "
                f"total={total_ms:.0f}ms"
            )

        with trace_span(
            "commit_and_audit",
            deal_id=deal_id,
            section_id=section_id,
        ) as commit_span:
            audit = AuditEntry(
                deal_id=deal_id,
                action="narrative.generated",
                subject=(
                    f"{section.title} ({mode}{has_template}, "
                    f"{doc_count} library docs, "
                    f"orch_conf={orchestration.confidence:.1f}"
                    f"{accuracy_tag}{timing_tag})"
                ),
                user=f"Mistral Agent: {section.section_key}",
            )
            db.add(audit)

            # Update deal status
            mandatory = [s for s in deal.sections if not s.optional]
            ready_count = sum(1 for s in mandatory if s.state == "ready")
            if deal.status == "Draft" and ready_count > 0:
                deal.status = "In Progress"

            db.commit()
            db.refresh(section)
            set_span_attributes(
                commit_span,
                result="committed",
                audit_id=audit.id,
                deal_status=deal.status,
            )

        # Close the pipeline span with final metrics
        if span:
            set_span_attributes(span,
                result="success",
                content_length=str(len(content)),
                accuracy_score=str(accuracy["score"]) if accuracy else "N/A",
                orchestration_confidence=str(orchestration.confidence),
                total_ms=str(round(total_ms)),
            )
        if span_ctx:
            span_ctx.__exit__(None, None, None)

        return section, orchestration.to_strategy_text()

    # ── Draft All (Parallel) ───────────────────────────────────────

    @staticmethod
    async def draft_all(
        db: Session,
        deal_id: str,
        progress_callback: Callable[[str, str, str, str], None] | None = None,
    ) -> list[dict]:
        deal = db.get(Deal, deal_id)
        if not deal:
            return []
        async with MistralLibraryService.agent_library_scope(
            db, MistralLibraryService.library_ids_for_deal(deal)
        ):
            return await NarrativeService._draft_all_with_configured_agents(
                db, deal_id, progress_callback
            )

    @staticmethod
    async def _draft_all_with_configured_agents(
        db: Session,
        deal_id: str,
        progress_callback: Callable[[str, str, str, str], None] | None = None,
    ) -> list[dict]:
        """
        Generate narratives for ALL sections in parallel.

        Optimizations:
        - MCP summaries fetched ONCE and shared across all 16 sections
        - Dual semaphores: orchestration(5) and generation(3)
        - Accuracy evaluation runs with orchestration semaphore (lightweight)
        """
        deal = (
            db.query(Deal)
            .options(
                joinedload(Deal.sections),
                joinedload(Deal.library_files),
            )
            .filter(Deal.id == deal_id)
            .first()
        )
        if not deal:
            return []

        owner_key = NarrativeService._owner_key(db, deal)

        await MistralLibraryService.sync_agents_to_libraries(
            db,
            MistralLibraryService.library_ids_for_deal(deal),
        )
        has_docs = bool(MistralLibraryService.library_ids_for_deal(deal))
        batch_start = time.time()
        tracer = get_tracer()

        # Start batch-level parent span
        batch_span_ctx = None
        batch_span = None
        if tracer:
            batch_span_ctx = tracer.start_as_current_span("draft_all_pipeline")
            batch_span = batch_span_ctx.__enter__()
            set_span_attributes(batch_span,
                operation="draft_all_pipeline",
                deal_id=deal_id,
                customer=deal.customer or "",
                section_count=str(len(deal.sections)),
                has_library_docs=str(has_docs),
                gen_semaphore=str(settings.GENERATION_SEMAPHORE),
                orch_semaphore=str(settings.ORCHESTRATION_SEMAPHORE),
            )

        # ── Pre-fetch MCP summaries ONCE for the entire batch ────
        mcp_summaries = ""
        if settings.ORCHESTRATION_ENABLED and deal.customer:
            try:
                mcp_summaries = await MCPClientService.get_document_summaries_cached(
                    company_name=deal.customer,
                    owner_user_id=owner_key,
                )
                logger.info(
                    f"Fetched MCP summaries for '{deal.customer}' "
                    f"({len(mcp_summaries)} chars)"
                )
            except Exception as e:
                logger.warning(f"MCP summary fetch failed: {e}")
                mcp_summaries = ""

        # Fetch all PostgreSQL tables once; each section receives a relevant subset.
        structured_data: dict[str, object] = {}
        if deal.customer:
            try:
                structured_data = (
                    await MCPClientService.get_structured_data_cached(
                        deal.customer, owner_key
                    )
                )
                logger.info(
                    "Fetched %s structured tables (%s rows) for '%s'",
                    structured_data.get("table_count", 0),
                    structured_data.get("row_count", 0),
                    deal.customer,
                )
            except Exception as e:
                logger.warning("Structured table fetch failed: %s", e)

        # ── Get orchestration agent ID ───────────────────────────
        orch_agent_id = MistralLibraryService.get_global_agent_id(db, "orchestration")

        # ── Dual semaphores ──────────────────────────────────────
        orch_semaphore = asyncio.Semaphore(settings.ORCHESTRATION_SEMAPHORE)
        gen_semaphore = asyncio.Semaphore(settings.GENERATION_SEMAPHORE)
        eval_semaphore = asyncio.Semaphore(settings.ORCHESTRATION_SEMAPHORE)

        async def _generate_one(section: Section) -> dict:
            """Full pipeline for one section (runs as async task)."""
            section_start = time.time()
            orch_ms = gen_ms = acc_ms = 0.0

            def report(status: str, stage: str) -> None:
                if progress_callback:
                    progress_callback(section.id, section.title, status, stage)

            try:
                # ── Moderation Gate ──
                with trace_span(
                    "user_request",
                    deal_id=deal_id,
                    section_id=section.id,
                    section_key=section.section_key,
                    mode="draft_all",
                ) as request_span:
                    set_span_attributes(request_span, result="accepted")

                moderation_metrics = {
                    "name": "Moderation",
                    "model": "mistral-moderation-latest",
                    "status": "skipped",
                    "latency_ms": None,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "total_tokens": 0,
                }

                moderation_required = bool(
                    section.custom_instructions or section.output_template
                )
                with trace_span(
                    "moderation_gate",
                    section_id=section.id,
                    required=moderation_required,
                ) as moderation_span:
                    if moderation_required:
                        report("running", "Checking content moderation")
                        moderation = await ModerationService.moderate_section_inputs(
                            custom_instructions=section.custom_instructions,
                            output_template=section.output_template,
                        )
                        section.moderation_status = (
                            "safe" if moderation.is_safe else "flagged"
                        )
                        section.moderation_details = json.dumps(moderation.to_dict())
                        moderation_metrics.update(
                            {
                                "status": (
                                    "success" if moderation.is_safe else "flagged"
                                ),
                                "latency_ms": round(moderation.latency_ms),
                                "input_tokens": moderation.input_tokens,
                                "output_tokens": moderation.output_tokens,
                                "total_tokens": moderation.total_tokens,
                            }
                        )
                        set_span_attributes(
                            moderation_span,
                            result="safe" if moderation.is_safe else "flagged",
                        )

                        if not moderation.is_safe:
                            flagged = ", ".join(moderation.flagged_categories)
                            raise ValueError(f"Moderation failed: {flagged}")
                    else:
                        set_span_attributes(moderation_span, result="skipped")

                # ── Orchestration (lightweight, semaphore=5) ──
                t0 = time.time()
                report("waiting", "Waiting for orchestration")
                with trace_span(
                    "orchestration_preflight",
                    deal_id=deal_id,
                    section_id=section.id,
                ) as orchestration_span:
                    async with orch_semaphore:
                        report("running", "Selecting source documents")
                        orchestration = await OrchestrationService.select_documents_for_section(
                            deal=deal,
                            section=section,
                            document_summaries=mcp_summaries,
                            orch_agent_id=orch_agent_id,
                        )
                    set_span_attributes(
                        orchestration_span,
                        result="completed",
                        confidence=orchestration.confidence,
                    )
                orch_ms = (time.time() - t0) * 1000
                orchestration_metrics = {
                    "name": "Orchestration Agent",
                    "model": settings.MISTRAL_AGENT_MODEL,
                    "status": "success",
                    "latency_ms": round(orch_ms),
                    "input_tokens": orchestration.input_tokens,
                    "output_tokens": orchestration.output_tokens,
                    "total_tokens": orchestration.total_tokens,
                }

                # ── Deal Context ──
                with trace_span(
                    "context_assembly",
                    deal_id=deal_id,
                    section_id=section.id,
                    customer=deal.customer,
                ) as context_span:
                    deal_context = OrchestrationService.build_deal_context_for_section(
                        deal, section.section_key
                    )
                    structured_context = structured_context_for_section(
                        structured_data,
                        section.section_key,
                    )
                    web_context, url_scrape_details = await scrape_urls(
                        source_urls_for_section(section)
                    )
                    section.url_scrape_details = json.dumps(url_scrape_details)
                    set_span_attributes(
                        context_span,
                        result="completed",
                        deal_context_chars=len(deal_context),
                        structured_context_chars=len(structured_context or ""),
                        web_context_chars=len(web_context),
                    )

                # ── Generation (heavy, semaphore=3) ──
                agent_id = MistralLibraryService.get_global_agent_id(
                    db, section.section_key
                )
                if not agent_id:
                    raise ValueError(f"No global agent found for {section.section_key}")

                t0 = time.time()
                generation_metrics: dict[str, object] = {}
                report("waiting", "Waiting for narrative agent")
                async with gen_semaphore:
                    report("running", "Generating narrative")
                    content = await MistralLibraryService.generate_with_agent(
                        agent_id=agent_id,
                        section_title=section.title,
                        section_description=section.description,
                        expected_output=section.expected_output,
                        deal_context=deal_context,
                        structured_data=structured_context,
                        orchestration_strategy=orchestration.to_strategy_text(),
                        custom_instructions=section.custom_instructions,
                        output_template=section.output_template,
                        metrics_out=generation_metrics,
                        web_context=web_context,
                    )
                gen_ms = (time.time() - t0) * 1000

                # ── Accuracy Evaluation (lightweight, semaphore=5) ──
                accuracy = None
                t0 = time.time()
                report("waiting", "Waiting for accuracy review")
                async with eval_semaphore:
                    report("running", "Evaluating accuracy")
                    accuracy = await MistralLibraryService.evaluate_accuracy(
                        generated_content=content,
                        section_title=section.title,
                        has_library_docs=has_docs,
                    )
                acc_ms = (time.time() - t0) * 1000
                confidence_from_judge = bool(
                    accuracy
                    and accuracy.get("confidence_source") == "observability_judge"
                )
                judge_metrics = (
                    accuracy.get("judge_observability")
                    if accuracy and accuracy.get("judge_observability")
                    else accuracy.get("observability", {})
                    if confidence_from_judge
                    else {
                        "name": "Confidence Judge",
                        "model": "Mistral Observability Judge",
                        "status": "fallback" if accuracy else "not_scored",
                        "latency_ms": None,
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "total_tokens": 0,
                        "token_usage_available": False,
                    }
                )
                claim_evaluator_metrics = (
                    accuracy.get("claim_evaluator_observability")
                    if accuracy
                    else None
                ) or {
                        "name": "Claim Classification Evaluator",
                        "model": settings.MISTRAL_MODEL,
                        "status": "not_evaluated",
                        "latency_ms": None,
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "total_tokens": 0,
                    }

                total_ms = (time.time() - section_start) * 1000
                logger.info(
                    f"[draft-all] {section.section_key}: "
                    f"orch={orch_ms:.0f}ms gen={gen_ms:.0f}ms "
                    f"acc={acc_ms:.0f}ms total={total_ms:.0f}ms"
                )
                report("completed", "Completed")

                return {
                    "section_id": section.id,
                    "section_key": section.section_key,
                    "title": section.title,
                    "generated_content": content,
                    "state": "ready",
                    "success": True,
                    "agent": f"Mistral Agent: {section.section_key}",
                    "accuracy": accuracy,
                    "orchestration_strategy": orchestration.to_strategy_text(),
                    "observability": {
                        "moderation": moderation_metrics,
                        "orchestration": orchestration_metrics,
                        "section_agent": generation_metrics,
                        "judge": judge_metrics,
                        "claim_evaluator": claim_evaluator_metrics,
                    },
                    "timing": {
                        "orchestration_ms": round(orch_ms),
                        "generation_ms": round(gen_ms),
                        "accuracy_ms": round(acc_ms),
                        "total_ms": round(total_ms),
                    },
                }
            except Exception:
                logger.exception("Failed to draft section %s", section.section_key)
                report("failed", "Section generation failed.")
                return {
                    "section_id": section.id,
                    "section_key": section.section_key,
                    "title": section.title,
                    "generated_content": "[Section generation failed.]",
                    "state": "pending",
                    "success": False,
                    "agent": "N/A",
                    "accuracy": None,
                    "orchestration_strategy": None,
                    "timing": None,
                }

        # ── Run all 16 sections concurrently ─────────────────────
        tasks = [_generate_one(section) for section in deal.sections]
        results = await asyncio.gather(*tasks)

        # ── Persist all results to DB ────────────────────────────
        for result in results:
            section = next(
                (s for s in deal.sections if s.id == result["section_id"]), None
            )
            if section:
                with trace_span(
                    "narrative_version_staging",
                    deal_id=deal_id,
                    section_id=section.id,
                    mode="draft_all",
                ) as staging_span:
                    NarrativeVersionService.ensure_current(db, section)
                    section.generated_content = result["generated_content"]
                    section.original_generated_content = result["generated_content"]
                    staged_version = None
                    if result["success"]:
                        section.state = "ready"
                        staged_version = NarrativeVersionService.create(
                            db,
                            section,
                            result["generated_content"],
                            "generated",
                            f"Mistral Agent: {section.section_key}",
                        )
                    accuracy = result.get("accuracy")
                    if accuracy:
                        section.accuracy_score = accuracy["score"]
                        section.accuracy_details = json.dumps(accuracy)
                    else:
                        section.accuracy_score = None
                        section.accuracy_details = None

                    section.orchestration_strategy = result.get("orchestration_strategy")
                    section.observability_details = json.dumps(
                        result.get("observability") or {}
                    )
                    set_span_attributes(
                        staging_span,
                        result="staged" if result["success"] else "failed",
                        version_id=staged_version.id if staged_version else "N/A",
                    )

        # Update deal status
        mandatory = [s for s in deal.sections if not s.optional]
        ready_count = sum(1 for s in mandatory if s.state == "ready")
        if ready_count > 0:
            deal.status = "In Progress"
        if ready_count == len(mandatory):
            deal.status = "In Progress"  # All ready, can submit

        # Batch audit entry with timing
        batch_ms = (time.time() - batch_start) * 1000
        succeeded = sum(1 for r in results if r["success"])

        timing_tag = ""
        if settings.ENABLE_TIMING_METRICS:
            timing_tag = f", total_batch={batch_ms:.0f}ms"

        with trace_span(
            "commit_and_audit",
            deal_id=deal_id,
            mode="draft_all",
        ) as commit_span:
            audit = AuditEntry(
                deal_id=deal_id,
                action="narrative.draft_all",
                subject=(
                    f"Generated {succeeded}/{len(results)} sections "
                    f"(orchestrated + Library RAG, "
                    f"gen_sem={settings.GENERATION_SEMAPHORE}, "
                    f"orch_sem={settings.ORCHESTRATION_SEMAPHORE}"
                    f"{timing_tag})"
                ),
                user="Agent System",
            )
            db.add(audit)
            db.commit()
            set_span_attributes(
                commit_span,
                result="committed",
                audit_id=audit.id,
                succeeded=succeeded,
                failed=len(results) - succeeded,
            )

        # Close the batch-level span with summary
        if batch_span:
            set_span_attributes(batch_span,
                result="completed",
                succeeded=str(succeeded),
                failed=str(len(results) - succeeded),
                total_batch_ms=str(round(batch_ms)),
            )
        if batch_span_ctx:
            batch_span_ctx.__exit__(None, None, None)

        return list(results)

    # ── Orchestration Helper ───────────────────────────────────────

    @staticmethod
    async def _run_orchestration(
        deal: Deal,
        section: Section,
        db: Session,
    ) -> OrchestrationResult:
        """
        Run orchestration for a single section.
        Fetches MCP summaries (cached) and calls OrchestrationService.
        """
        if not settings.ORCHESTRATION_ENABLED:
            return OrchestrationResult(
                strategy_summary="Orchestration disabled.",
                confidence=0.0,
            )

        # Fetch MCP summaries (cached — won't hit MCP repeatedly)
        mcp_summaries = ""
        if deal.customer:
            try:
                mcp_summaries = await MCPClientService.get_document_summaries_cached(
                    company_name=deal.customer,
                    owner_user_id=NarrativeService._owner_key(db, deal),
                )
            except Exception as e:
                logger.warning(f"MCP summary fetch failed: {e}")

        # Get orchestration agent ID
        orch_agent_id = MistralLibraryService.get_global_agent_id(db, "orchestration")

        return await OrchestrationService.select_documents_for_section(
            deal=deal,
            section=section,
            document_summaries=mcp_summaries,
            orch_agent_id=orch_agent_id,
        )
