"""
AI Website Auditor & Health Engine — FastAPI Backend (OpenAI Edition)
Author: Omkar | Stack: FastAPI + BeautifulSoup + OpenAI SDK
"""

import json
import os
import re
import time
from datetime import datetime
from typing import Literal, Optional
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

# Automatically load variables from the backend/.env file
load_dotenv()

app = FastAPI(title="Website Health Engine", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize OpenAI client only when API key is available.
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai_client: Optional[AsyncOpenAI] = None
if OPENAI_API_KEY:
    openai_client = AsyncOpenAI(
        api_key=OPENAI_API_KEY,
        base_url=os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1"),
    )

# ── Models ────────────────────────────────────────────────────────────────────

class AuditRequest(BaseModel):
    url: str
    business_context: Optional[str] = "general business website"
    skip_ai: Optional[bool] = False


class SeoData(BaseModel):
    title: Optional[str]
    title_length: int
    meta_description: Optional[str]
    meta_desc_length: int
    h1_tags: list[str]
    h2_tags: list[str]
    h3_tags: list[str]
    canonical_url: Optional[str]
    og_title: Optional[str]
    og_description: Optional[str]
    robots_meta: Optional[str]
    structured_data: bool
    internal_links: int
    external_links: int
    broken_images: int
    alt_missing_images: int
    has_lang_attr: bool
    meta_robots_indexable: bool
    word_count: int


class PerformanceData(BaseModel):
    load_time_ms: float
    page_size_kb: float
    total_images: int
    scripts_count: int
    stylesheets_count: int
    has_viewport_meta: bool
    has_https: bool
    server_response_ms: float
    lazy_images: int
    third_party_scripts: int
    blocking_scripts_head: int
    preconnect_hints: int


class UsabilityData(BaseModel):
    has_favicon: bool
    has_search: bool
    has_contact_info: bool
    mobile_friendly: bool
    has_cta: bool
    nav_links: int
    footer_present: bool
    form_count: int
    missing_form_labels: int
    aria_landmarks: int
    button_count: int


class ScoreBreakdown(BaseModel):
    seo_score: float
    performance_score: float
    usability_score: float
    overall_score: float
    grade: str


class AIRecommendation(BaseModel):
    title: str
    detail: str
    impact: str
    effort: str
    metric: str


class FixSnippet(BaseModel):
    language: str
    snippet: str


class FixPlanItem(BaseModel):
    issue: str
    category: Literal["seo", "performance", "usability", "security", "accessibility", "content"]
    severity: Literal["critical", "high", "medium", "low"]
    why_it_matters: str
    how_to_fix: list[str]
    verification: str
    expected_impact: str
    effort: Literal["low", "medium", "high"]
    owner: Literal["frontend", "backend", "devops", "content", "design"] = "frontend"
    kpi_target: str = "Overall Health Score"
    estimated_score_gain: int = 2
    priority_score: int = 50
    code_example: Optional[FixSnippet] = None


class ImprovementRoadmap(BaseModel):
    immediate: list[str] = Field(default_factory=list)
    sprint: list[str] = Field(default_factory=list)
    backlog: list[str] = Field(default_factory=list)

class ScoreProjection(BaseModel):
    projected_seo_score: float
    projected_performance_score: float
    projected_usability_score: float
    projected_overall_score: float
    projected_grade: str
class AnalysisSummary(BaseModel):
    summary: str
    strengths: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    next_focus: list[str] = Field(default_factory=list)


class AuditReport(BaseModel):
    url: str
    scraped_at: str
    seo: SeoData
    performance: PerformanceData
    usability: UsabilityData
    scores: ScoreBreakdown
    ai_recommendations: list[AIRecommendation]
    fix_plan: list[FixPlanItem]
    developer_tips: list[str]
    improvement_roadmap: ImprovementRoadmap
    automation_scope: str
    critical_issues: list[str]
    quick_wins: list[str]
    raw_gaps: list[str]
    score_projection: ScoreProjection
    execution_checklist: list[str]
    analysis_summary: AnalysisSummary


# ── Async Scraper ─────────────────────────────────────────────────────────────

async def scrape_website(url: str) -> tuple[BeautifulSoup, dict]:
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; WebAuditor/1.0; +https://auditor.dev)"
    }
    t0 = time.time()

    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        resp = await client.get(url, headers=headers)
        server_ms = (time.time() - t0) * 1000

        t1 = time.time()
        soup = BeautifulSoup(resp.text, "lxml")
        parse_ms = (time.time() - t1) * 1000

        meta = {
            "status_code": resp.status_code,
            "page_size_kb": len(resp.content) / 1024,
            "load_time_ms": server_ms + parse_ms,
            "server_response_ms": server_ms,
            "final_url": str(resp.url),
            "content_type": resp.headers.get("content-type", ""),
        }
        return soup, meta


def extract_seo(soup: BeautifulSoup, base_url: str) -> SeoData:
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else None
    html_tag = soup.find("html")

    meta_desc_tag = soup.find("meta", attrs={"name": re.compile("description", re.I)})
    meta_desc = meta_desc_tag.get("content", "").strip() if meta_desc_tag else None

    h1s = [h.get_text(strip=True) for h in soup.find_all("h1")]
    h2s = [h.get_text(strip=True) for h in soup.find_all("h2")][:5]
    h3s = [h.get_text(strip=True) for h in soup.find_all("h3")][:5]

    canonical = soup.find("link", attrs={"rel": "canonical"})
    canonical_url = canonical.get("href") if canonical else None

    og_title = soup.find("meta", property="og:title")
    og_desc = soup.find("meta", property="og:description")

    robots = soup.find("meta", attrs={"name": re.compile("robots", re.I)})
    robots_meta = robots.get("content") if robots else None
    robots_indexable = True if not robots_meta else ("noindex" not in robots_meta.lower())

    has_structured = bool(soup.find("script", attrs={"type": "application/ld+json"}))
    word_count = len(re.findall(r"\w+", soup.get_text(" ", strip=True)))

    all_links = soup.find_all("a", href=True)
    internal = sum(1 for a in all_links if urlparse(a["href"]).netloc in ("", urlparse(base_url).netloc))
    external = len(all_links) - internal

    all_imgs = soup.find_all("img")
    alt_missing = sum(1 for img in all_imgs if not img.get("alt"))

    return SeoData(
        title=title,
        title_length=len(title) if title else 0,
        meta_description=meta_desc,
        meta_desc_length=len(meta_desc) if meta_desc else 0,
        h1_tags=h1s,
        h2_tags=h2s,
        h3_tags=h3s,
        canonical_url=canonical_url,
        og_title=og_title.get("content") if og_title else None,
        og_description=og_desc.get("content") if og_desc else None,
        robots_meta=robots_meta,
        structured_data=has_structured,
        internal_links=internal,
        external_links=external,
        broken_images=0,
        alt_missing_images=alt_missing,
        has_lang_attr=bool(html_tag and html_tag.get("lang")),
        meta_robots_indexable=robots_indexable,
        word_count=word_count,
    )


def extract_performance(soup: BeautifulSoup, meta: dict) -> PerformanceData:
    imgs = soup.find_all("img")
    scripts = soup.find_all("script", src=True)
    styles = soup.find_all("link", rel=lambda v: v and "stylesheet" in v)
    viewport = soup.find("meta", attrs={"name": "viewport"})
    lazy_images = sum(1 for img in imgs if str(img.get("loading", "")).lower() == "lazy")
    base_domain = urlparse(meta["final_url"]).netloc
    third_party_scripts = sum(
        1 for script in scripts if urlparse(script.get("src", "")).netloc not in ("", base_domain)
    )
    head = soup.find("head")
    head_scripts = head.find_all("script", src=True) if head else []
    blocking_head_scripts = sum(
        1
        for script in head_scripts
        if not script.has_attr("defer")
        and not script.has_attr("async")
        and str(script.get("type", "")).lower() not in ("application/ld+json", "module")
    )
    preconnect_hints = len(
        soup.find_all(
            "link",
            rel=lambda v: v and "preconnect" in (v if isinstance(v, str) else " ".join(v)).lower(),
        )
    )

    return PerformanceData(
        load_time_ms=round(meta["load_time_ms"], 1),
        page_size_kb=round(meta["page_size_kb"], 1),
        total_images=len(imgs),
        scripts_count=len(scripts),
        stylesheets_count=len(styles),
        has_viewport_meta=bool(viewport),
        has_https=meta["final_url"].startswith("https"),
        server_response_ms=round(meta["server_response_ms"], 1),
        lazy_images=lazy_images,
        third_party_scripts=third_party_scripts,
        blocking_scripts_head=blocking_head_scripts,
        preconnect_hints=preconnect_hints,
    )


def extract_usability(soup: BeautifulSoup) -> UsabilityData:
    favicon = soup.find(
        "link",
        rel=lambda v: v and "icon" in (v if isinstance(v, str) else " ".join(v)).lower(),
    )
    search = bool(
        soup.find("input", attrs={"type": re.compile("search", re.I)})
        or soup.find(attrs={"placeholder": re.compile("search", re.I)})
    )
    contact = bool(soup.find(string=re.compile(r"(contact|email|phone|tel:|\+\d)", re.I)))
    viewport = soup.find("meta", attrs={"name": "viewport"})
    cta_keywords = re.compile(r"(get started|sign up|try free|buy now|book|demo|contact us|learn more)", re.I)
    cta = bool(soup.find("a", string=cta_keywords) or soup.find("button", string=cta_keywords))
    nav = soup.find("nav") or soup.find(attrs={"role": "navigation"})
    nav_links = len(nav.find_all("a")) if nav else 0
    footer = bool(soup.find("footer"))
    forms = len(soup.find_all("form"))
    button_count = len(soup.find_all("button")) + len(
        soup.find_all("a", attrs={"role": re.compile("button", re.I)})
    )

    form_fields = soup.find_all(["input", "textarea", "select"])
    missing_form_labels = 0
    for field in form_fields:
        input_type = str(field.get("type", "")).lower()
        if input_type in {"hidden", "submit", "button", "reset", "image"}:
            continue
        has_label = bool(field.get("aria-label") or field.get("title"))
        if not has_label and field.get("id"):
            has_label = bool(soup.find("label", attrs={"for": field.get("id")}))
        if not has_label and field.find_parent("label"):
            has_label = True
        if not has_label:
            missing_form_labels += 1

    landmark_signals = {
        "header": bool(soup.find("header")),
        "nav": bool(soup.find("nav") or soup.find(attrs={"role": "navigation"})),
        "main": bool(soup.find("main") or soup.find(attrs={"role": "main"})),
        "footer": bool(soup.find("footer") or soup.find(attrs={"role": "contentinfo"})),
        "search": bool(soup.find(attrs={"role": "search"})),
    }
    aria_landmarks = sum(1 for v in landmark_signals.values() if v)

    return UsabilityData(
        has_favicon=bool(favicon),
        has_search=search,
        has_contact_info=contact,
        mobile_friendly=bool(viewport),
        has_cta=cta,
        nav_links=nav_links,
        footer_present=footer,
        form_count=forms,
        missing_form_labels=missing_form_labels,
        aria_landmarks=aria_landmarks,
        button_count=button_count,
    )


# ── Scoring Engine ────────────────────────────────────────────────────────────

def compute_scores(seo: SeoData, perf: PerformanceData, usab: UsabilityData) -> ScoreBreakdown:
    seo_pts = 100.0
    if not seo.title:
        seo_pts -= 20
    elif seo.title_length < 30 or seo.title_length > 60:
        seo_pts -= 8
    if not seo.meta_description:
        seo_pts -= 15
    elif seo.meta_desc_length < 120 or seo.meta_desc_length > 160:
        seo_pts -= 5
    if len(seo.h1_tags) == 0:
        seo_pts -= 15
    elif len(seo.h1_tags) > 1:
        seo_pts -= 8
    if len(seo.h2_tags) == 0:
        seo_pts -= 5
    if not seo.canonical_url:
        seo_pts -= 5
    if not seo.og_title:
        seo_pts -= 5
    if not seo.structured_data:
        seo_pts -= 7
    if seo.alt_missing_images > 0:
        seo_pts -= min(10, seo.alt_missing_images * 2)
    if not seo.has_lang_attr:
        seo_pts -= 4
    if not seo.meta_robots_indexable:
        seo_pts -= 25
    if seo.word_count < 250:
        seo_pts -= 6
    elif seo.word_count < 500:
        seo_pts -= 3
    seo_score = max(0, min(100, seo_pts))

    perf_pts = 100.0
    if perf.load_time_ms > 5000:
        perf_pts -= 30
    elif perf.load_time_ms > 3000:
        perf_pts -= 20
    elif perf.load_time_ms > 2000:
        perf_pts -= 10
    elif perf.load_time_ms > 1000:
        perf_pts -= 5
    if perf.page_size_kb > 3000:
        perf_pts -= 20
    elif perf.page_size_kb > 1500:
        perf_pts -= 10
    elif perf.page_size_kb > 800:
        perf_pts -= 5
    if not perf.has_https:
        perf_pts -= 20
    if not perf.has_viewport_meta:
        perf_pts -= 10
    if perf.scripts_count > 15:
        perf_pts -= 10
    elif perf.scripts_count > 10:
        perf_pts -= 5
    if perf.blocking_scripts_head > 2:
        perf_pts -= 10
    elif perf.blocking_scripts_head > 0:
        perf_pts -= 5
    if perf.third_party_scripts > 8:
        perf_pts -= 8
    elif perf.third_party_scripts > 4:
        perf_pts -= 4
    if perf.total_images >= 4 and perf.lazy_images < max(1, perf.total_images // 2):
        perf_pts -= 6
    if perf.third_party_scripts > 0 and perf.preconnect_hints == 0:
        perf_pts -= 3
    perf_score = max(0, min(100, perf_pts))

    usab_pts = 100.0
    if not usab.has_favicon:
        usab_pts -= 5
    if not usab.mobile_friendly:
        usab_pts -= 25
    if not usab.has_cta:
        usab_pts -= 20
    if not usab.footer_present:
        usab_pts -= 10
    if not usab.has_contact_info:
        usab_pts -= 15
    if usab.nav_links == 0:
        usab_pts -= 15
    elif usab.nav_links < 3:
        usab_pts -= 5
    if not usab.has_search:
        usab_pts -= 5
    if usab.missing_form_labels > 0:
        usab_pts -= min(12, usab.missing_form_labels * 3)
    if usab.aria_landmarks < 2:
        usab_pts -= 8
    if usab.button_count == 0:
        usab_pts -= 5
    usab_score = max(0, min(100, usab_pts))

    overall = (seo_score * 0.4) + (perf_score * 0.4) + (usab_score * 0.2)
    grade = "A" if overall >= 90 else "B" if overall >= 75 else "C" if overall >= 60 else "D" if overall >= 45 else "F"

    return ScoreBreakdown(
        seo_score=round(seo_score, 1),
        performance_score=round(perf_score, 1),
        usability_score=round(usab_score, 1),
        overall_score=round(overall, 1),
        grade=grade,
    )


def build_gaps(seo: SeoData, perf: PerformanceData, usab: UsabilityData) -> list[str]:
    gaps = []
    if not seo.title:
        gaps.append("Missing page title tag")
    elif seo.title_length < 30:
        gaps.append(f"Title too short ({seo.title_length} chars, ideal 50-60)")
    elif seo.title_length > 60:
        gaps.append(f"Title too long ({seo.title_length} chars, ideal 50-60)")
    if not seo.meta_description:
        gaps.append("Missing meta description")
    if len(seo.h1_tags) == 0:
        gaps.append("No H1 heading found")
    elif len(seo.h1_tags) > 1:
        gaps.append(f"Multiple H1 tags found ({len(seo.h1_tags)}), should be 1")
    if not seo.structured_data:
        gaps.append("No structured data (JSON-LD) detected")
    if seo.alt_missing_images > 0:
        gaps.append(f"{seo.alt_missing_images} images missing alt text")
    if not seo.meta_robots_indexable:
        gaps.append("Robots meta appears to block indexing (contains noindex)")
    if not seo.has_lang_attr:
        gaps.append("Missing <html lang='...'> attribute")
    if seo.word_count < 250:
        gaps.append(f"Thin content detected ({seo.word_count} words, target >500)")
    if perf.load_time_ms > 3000:
        gaps.append(f"Slow page load: {perf.load_time_ms:.0f}ms (target <2000ms)")
    if perf.page_size_kb > 1500:
        gaps.append(f"Heavy page: {perf.page_size_kb:.0f}KB (target <800KB)")
    if not perf.has_https:
        gaps.append("Site not served over HTTPS")
    if not perf.has_viewport_meta:
        gaps.append("Missing viewport meta tag (mobile rendering broken)")
    if perf.blocking_scripts_head > 0:
        gaps.append(f"{perf.blocking_scripts_head} render-blocking script(s) in <head>")
    if perf.third_party_scripts > 4:
        gaps.append(f"High third-party script load ({perf.third_party_scripts} external scripts)")
    if perf.total_images >= 4 and perf.lazy_images < max(1, perf.total_images // 2):
        gaps.append("Most images are not lazy-loaded")
    if not usab.has_cta:
        gaps.append("No clear call-to-action detected")
    if not usab.has_contact_info:
        gaps.append("No contact info visible on page")
    if not usab.has_favicon:
        gaps.append("Missing favicon")
    if usab.missing_form_labels > 0:
        gaps.append(f"{usab.missing_form_labels} form field(s) missing accessible labels")
    if usab.aria_landmarks < 2:
        gaps.append("Insufficient semantic landmarks (main/nav/footer/header roles)")
    return gaps


def build_fix_plan(seo: SeoData, perf: PerformanceData, usab: UsabilityData) -> list[FixPlanItem]:
    plan: list[FixPlanItem] = []

    if not seo.title:
        plan.append(
            FixPlanItem(
                issue="Missing page title tag",
                category="seo",
                severity="critical",
                why_it_matters="Missing titles weaken ranking signals and reduce search click-through.",
                how_to_fix=[
                    "Add one descriptive <title> in <head>.",
                    "Keep it around 50-60 characters.",
                    "Use unique titles per page.",
                ],
                verification="Confirm title exists in source and rerun audit.",
                expected_impact="Improved SERP visibility and CTR.",
                effort="low",
                code_example=FixSnippet(language="html", snippet="<title>AI Website Audit Tool for SEO and Speed | AuditFlow</title>"),
            )
        )
    elif seo.title_length < 30 or seo.title_length > 60:
        plan.append(
            FixPlanItem(
                issue=f"Title length outside best practice ({seo.title_length} chars)",
                category="seo",
                severity="medium",
                why_it_matters="Very short or long titles reduce clarity and may be truncated in SERPs.",
                how_to_fix=[
                    "Rewrite title to roughly 50-60 characters.",
                    "Lead with core keyword intent.",
                    "Avoid stuffing repeated terms.",
                ],
                verification="Validate updated title length in audit output.",
                expected_impact="Cleaner snippets and stronger topic targeting.",
                effort="low",
            )
        )

    if not seo.meta_description:
        plan.append(
            FixPlanItem(
                issue="Missing meta description",
                category="seo",
                severity="high",
                why_it_matters="Missing descriptions can lower organic click-through quality.",
                how_to_fix=[
                    "Add unique description around 140-160 characters.",
                    "Highlight user benefit and action language.",
                    "Align with page intent and title.",
                ],
                verification="Confirm meta description tag and rerun audit.",
                expected_impact="Higher CTR from search results.",
                effort="low",
                code_example=FixSnippet(
                    language="html",
                    snippet="<meta name=\"description\" content=\"Audit SEO, performance, and UX with fix-ready developer recommendations.\" />",
                ),
            )
        )

    if len(seo.h1_tags) == 0:
        plan.append(
            FixPlanItem(
                issue="No H1 heading found",
                category="seo",
                severity="high",
                why_it_matters="Missing H1 weakens page hierarchy for users and crawlers.",
                how_to_fix=[
                    "Add one page-level H1 near top content.",
                    "Align H1 with title intent.",
                    "Use H2/H3 for supporting sections.",
                ],
                verification="Confirm exactly one H1 in DOM and rerun audit.",
                expected_impact="Clearer semantic structure and ranking relevance.",
                effort="low",
            )
        )
    elif len(seo.h1_tags) > 1:
        plan.append(
            FixPlanItem(
                issue=f"Multiple H1 tags found ({len(seo.h1_tags)})",
                category="seo",
                severity="medium",
                why_it_matters="Multiple H1s can dilute primary page intent.",
                how_to_fix=[
                    "Keep one primary H1.",
                    "Convert secondary H1s to H2/H3.",
                    "Re-check heading order.",
                ],
                verification="Audit confirms single H1 after changes.",
                expected_impact="More consistent content hierarchy.",
                effort="low",
            )
        )

    if not seo.structured_data:
        plan.append(
            FixPlanItem(
                issue="No structured data (JSON-LD) detected",
                category="seo",
                severity="medium",
                why_it_matters="Schema markup improves machine readability and rich-result eligibility.",
                how_to_fix=[
                    "Add relevant schema.org JSON-LD.",
                    "Include required fields for chosen schema type.",
                    "Validate with structured data testing tools.",
                ],
                verification="Check JSON-LD script presence and validator results.",
                expected_impact="Potential rich SERP enhancements.",
                effort="medium",
            )
        )

    if seo.alt_missing_images > 0:
        plan.append(
            FixPlanItem(
                issue=f"{seo.alt_missing_images} images missing alt text",
                category="accessibility",
                severity="medium",
                why_it_matters="Alt text improves accessibility and image relevance.",
                how_to_fix=[
                    "Add meaningful alt text to content images.",
                    "Use alt='' only for decorative assets.",
                    "Avoid keyword stuffing in alt copy.",
                ],
                verification="Rerun audit until missing-alt count drops.",
                expected_impact="Improved accessibility and image SEO.",
                effort="low",
            )
        )

    if not seo.meta_robots_indexable:
        plan.append(
            FixPlanItem(
                issue="Robots meta prevents indexing (noindex detected)",
                category="seo",
                severity="critical",
                why_it_matters="Noindex can fully block discoverability for key pages.",
                how_to_fix=[
                    "Remove noindex from public ranking pages.",
                    "Limit noindex to private or utility routes.",
                    "Request reindexing for corrected URLs.",
                ],
                verification="Search Console URL inspection reports page is indexable.",
                expected_impact="Restored organic visibility.",
                effort="low",
            )
        )

    if not seo.has_lang_attr:
        plan.append(
            FixPlanItem(
                issue="Missing html lang attribute",
                category="seo",
                severity="medium",
                why_it_matters="Language metadata improves accessibility and locale relevance.",
                how_to_fix=[
                    "Add lang attribute to root html element.",
                    "Use locale-specific code where needed.",
                    "Keep lang aligned with content language.",
                ],
                verification="Page source includes valid html lang attribute.",
                expected_impact="Better accessibility and geo-language alignment.",
                effort="low",
                code_example=FixSnippet(language="html", snippet="<html lang=\"en\">"),
            )
        )

    if seo.word_count < 250:
        plan.append(
            FixPlanItem(
                issue=f"Thin page content ({seo.word_count} words)",
                category="content",
                severity="medium",
                why_it_matters="Thin pages often miss intent depth and underperform in rankings.",
                how_to_fix=[
                    "Expand with intent-focused sections and FAQs.",
                    "Add internal links to supporting resources.",
                    "Strengthen proof points and benefit statements.",
                ],
                verification="Track increased word count and engagement after release.",
                expected_impact="Higher topical authority and time on page.",
                effort="medium",
            )
        )

    if perf.load_time_ms > 3000:
        plan.append(
            FixPlanItem(
                issue=f"Slow page load ({perf.load_time_ms:.0f}ms)",
                category="performance",
                severity="high",
                why_it_matters="Slow pages increase bounce rate and reduce conversion.",
                how_to_fix=[
                    "Compress media and lazy-load non-critical assets.",
                    "Defer non-essential JS/CSS.",
                    "Enable caching plus Brotli/Gzip.",
                ],
                verification="Lighthouse/WebPageTest shows improved load timing.",
                expected_impact="Lower bounce and better conversion retention.",
                effort="medium",
            )
        )

    if perf.page_size_kb > 1500:
        plan.append(
            FixPlanItem(
                issue=f"Heavy page weight ({perf.page_size_kb:.0f}KB)",
                category="performance",
                severity="high",
                why_it_matters="Heavy payloads delay rendering and hurt mobile experiences.",
                how_to_fix=[
                    "Convert images to WebP/AVIF.",
                    "Trim unused JS/CSS and split bundles.",
                    "Remove low-value third-party scripts.",
                ],
                verification="Audit confirms reduced transfer size.",
                expected_impact="Faster first paint and improved mobile performance.",
                effort="medium",
            )
        )

    if not perf.has_https:
        plan.append(
            FixPlanItem(
                issue="Site not served over HTTPS",
                category="security",
                severity="critical",
                why_it_matters="HTTP harms trust, privacy, and search reliability.",
                how_to_fix=[
                    "Enable SSL/TLS certificate.",
                    "Redirect HTTP traffic to HTTPS.",
                    "Update canonical/sitemap links to HTTPS.",
                ],
                verification="Site resolves securely with forced HTTPS.",
                expected_impact="Higher trust and stronger SEO baseline.",
                effort="high",
            )
        )

    if not perf.has_viewport_meta:
        plan.append(
            FixPlanItem(
                issue="Missing viewport meta tag",
                category="usability",
                severity="high",
                why_it_matters="Without viewport config, mobile rendering and readability degrade.",
                how_to_fix=[
                    "Add viewport meta tag in head.",
                    "Test responsive breakpoints.",
                    "Adjust spacing and touch targets for mobile.",
                ],
                verification="Mobile viewport renders correctly after audit.",
                expected_impact="Improved mobile usability and engagement.",
                effort="low",
                code_example=FixSnippet(
                    language="html",
                    snippet="<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />",
                ),
            )
        )

    if perf.blocking_scripts_head > 0:
        plan.append(
            FixPlanItem(
                issue=f"{perf.blocking_scripts_head} render-blocking script(s) in head",
                category="performance",
                severity="high",
                why_it_matters="Render-blocking scripts delay first paint and LCP.",
                how_to_fix=[
                    "Use defer/async on non-critical head scripts.",
                    "Move script loading below primary content where possible.",
                    "Keep only essential bootstrapping synchronous.",
                ],
                verification="Diagnostics show fewer render-blocking scripts.",
                expected_impact="Better LCP and faster visual readiness.",
                effort="low",
                code_example=FixSnippet(language="html", snippet="<script src=\"/assets/app.js\" defer></script>"),
            )
        )

    if perf.third_party_scripts > 4:
        plan.append(
            FixPlanItem(
                issue=f"High third-party script load ({perf.third_party_scripts})",
                category="performance",
                severity="medium",
                why_it_matters="Excess third-party JS increases runtime overhead and instability.",
                how_to_fix=[
                    "Remove low-value integrations.",
                    "Delay non-critical widgets until interaction.",
                    "Use preconnect for required third-party hosts.",
                ],
                verification="Third-party script count and JS blocking time drop.",
                expected_impact="Lower JS cost and smoother interactions.",
                effort="medium",
            )
        )

    if perf.total_images >= 4 and perf.lazy_images < max(1, perf.total_images // 2):
        plan.append(
            FixPlanItem(
                issue="Insufficient image lazy-loading coverage",
                category="performance",
                severity="medium",
                why_it_matters="Loading all images eagerly slows the initial viewport.",
                how_to_fix=[
                    "Apply loading='lazy' to below-the-fold images.",
                    "Reserve eager loading for above-the-fold media.",
                    "Use responsive srcset and sizes.",
                ],
                verification="Lazy-image ratio increases in audit results.",
                expected_impact="Reduced startup payload and improved speed perception.",
                effort="low",
                code_example=FixSnippet(
                    language="html",
                    snippet="<img src=\"/assets/feature.webp\" loading=\"lazy\" alt=\"Feature preview\" />",
                ),
            )
        )

    if not usab.has_cta:
        plan.append(
            FixPlanItem(
                issue="No clear call-to-action detected",
                category="content",
                severity="high",
                why_it_matters="Users without a clear next step are less likely to convert.",
                how_to_fix=[
                    "Add one primary CTA above the fold.",
                    "Add supporting CTA near key sections.",
                    "Use high-contrast action-focused copy.",
                ],
                verification="CTA elements are visible and measurable in funnel tracking.",
                expected_impact="Higher conversion flow into signup/contact paths.",
                effort="low",
            )
        )

    if not usab.has_contact_info:
        plan.append(
            FixPlanItem(
                issue="No contact info visible on page",
                category="usability",
                severity="medium",
                why_it_matters="Missing trust/contact elements can block high-intent conversions.",
                how_to_fix=[
                    "Add support email/phone in header or footer.",
                    "Create clear contact page with form.",
                    "Place contact links near CTA areas.",
                ],
                verification="Contact details are visible and crawlable in page markup.",
                expected_impact="Improved trust and lead quality.",
                effort="low",
            )
        )

    if not usab.has_favicon:
        plan.append(
            FixPlanItem(
                issue="Missing favicon",
                category="usability",
                severity="low",
                why_it_matters="Favicons improve product polish and brand recognition.",
                how_to_fix=[
                    "Generate favicon assets for common sizes.",
                    "Reference icon tags in head.",
                    "Verify rendering across browsers.",
                ],
                verification="Favicon appears in tabs and bookmarks.",
                expected_impact="Improved perceived quality and recognition.",
                effort="low",
            )
        )

    if usab.missing_form_labels > 0:
        plan.append(
            FixPlanItem(
                issue=f"{usab.missing_form_labels} form field(s) missing accessible labels",
                category="accessibility",
                severity="high",
                why_it_matters="Unlabeled controls hurt accessibility and conversion completion.",
                how_to_fix=[
                    "Associate each control with a visible label.",
                    "Use aria-label only as a fallback.",
                    "Confirm keyboard and screen-reader form flow.",
                ],
                verification="Accessibility tools no longer flag unlabeled controls.",
                expected_impact="Higher accessibility compliance and form completion rate.",
                effort="medium",
                code_example=FixSnippet(
                    language="html",
                    snippet="<label for=\"workEmail\">Work email</label>\n<input id=\"workEmail\" type=\"email\" />",
                ),
            )
        )

    if usab.aria_landmarks < 2:
        plan.append(
            FixPlanItem(
                issue="Insufficient semantic landmarks for navigation",
                category="usability",
                severity="medium",
                why_it_matters="Landmarks improve navigation for assistive technologies and content comprehension.",
                how_to_fix=[
                    "Use semantic layout containers (header/nav/main/footer).",
                    "Add ARIA roles only where semantic tags are unavailable.",
                    "Keep one primary main region per page.",
                ],
                verification="Screen-reader landmark navigation detects expected regions.",
                expected_impact="Better navigability and usability for all users.",
                effort="low",
            )
        )

    if not plan:
        plan.append(
            FixPlanItem(
                issue="No critical technical blockers detected",
                category="seo",
                severity="low",
                why_it_matters="Continuous optimization prevents regressions and maintains growth.",
                how_to_fix=[
                    "Monitor Core Web Vitals and SEO trends weekly.",
                    "Run audits after every major release.",
                    "Automate metadata/markup checks in CI.",
                ],
                verification="Recurring audits remain stable or improve over time.",
                expected_impact="Sustained technical health.",
                effort="low",
            )
        )

    return plan


def build_default_roadmap(fix_plan: list[FixPlanItem]) -> ImprovementRoadmap:
    immediate = [x.issue for x in fix_plan if x.severity in ("critical", "high")][:5]
    sprint = [x.issue for x in fix_plan if x.severity == "medium"][:5]
    backlog = [x.issue for x in fix_plan if x.severity == "low"][:5]

    if not immediate and fix_plan:
        immediate = [fix_plan[0].issue]
    if not sprint and len(fix_plan) > 1:
        sprint = [x.issue for x in fix_plan[1:3]]
    if not backlog and len(fix_plan) > 3:
        backlog = [x.issue for x in fix_plan[3:6]]

    return ImprovementRoadmap(immediate=immediate, sprint=sprint, backlog=backlog)


def grade_for_score(overall_score: float) -> str:
    return "A" if overall_score >= 90 else "B" if overall_score >= 75 else "C" if overall_score >= 60 else "D" if overall_score >= 45 else "F"


def owner_for_category(category: str) -> Literal["frontend", "backend", "devops", "content", "design"]:
    mapping = {
        "seo": "frontend",
        "performance": "frontend",
        "usability": "design",
        "accessibility": "frontend",
        "security": "devops",
        "content": "content",
    }
    return mapping.get(category, "frontend")  # type: ignore[return-value]


def kpi_for_category(category: str) -> str:
    mapping = {
        "seo": "Organic CTR / Impressions",
        "performance": "LCP / Page Load Time",
        "usability": "Conversion Rate / Bounce Rate",
        "accessibility": "Accessibility Error Count",
        "security": "HTTPS Coverage",
        "content": "Conversion CTR",
    }
    return mapping.get(category, "Overall Health Score")


def enrich_fix_plan(fix_plan: list[FixPlanItem], scores: ScoreBreakdown) -> list[FixPlanItem]:
    severity_weight = {"critical": 40, "high": 30, "medium": 20, "low": 10}
    effort_bonus = {"low": 8, "medium": 4, "high": 0}
    gain_map = {"critical": 9, "high": 7, "medium": 4, "low": 2}
    pressure_by_category = {
        "seo": 100 - scores.seo_score,
        "content": 100 - scores.seo_score,
        "performance": 100 - scores.performance_score,
        "security": 100 - scores.performance_score,
        "usability": 100 - scores.usability_score,
        "accessibility": 100 - scores.usability_score,
    }

    ranked: list[FixPlanItem] = []
    for item in fix_plan:
        pressure = pressure_by_category.get(item.category, 30)
        priority_score = int(min(100, severity_weight[item.severity] + effort_bonus[item.effort] + (pressure * 0.5)))
        estimated_gain = min(12, gain_map[item.severity] + (2 if item.effort == "low" else 0))
        ranked.append(
            item.model_copy(
                update={
                    "owner": owner_for_category(item.category),
                    "kpi_target": kpi_for_category(item.category),
                    "estimated_score_gain": estimated_gain,
                    "priority_score": priority_score,
                }
            )
        )

    return sorted(ranked, key=lambda x: (x.priority_score, x.estimated_score_gain), reverse=True)


def build_score_projection(scores: ScoreBreakdown, fix_plan: list[FixPlanItem]) -> ScoreProjection:
    seo_gain = 0.0
    perf_gain = 0.0
    usab_gain = 0.0

    top_items = fix_plan[:6]
    for item in top_items:
        gain = float(item.estimated_score_gain)
        if item.category in {"seo", "content"}:
            seo_gain += gain
        elif item.category in {"performance", "security"}:
            perf_gain += gain
        elif item.category in {"usability", "accessibility"}:
            usab_gain += gain

    projected_seo = min(100.0, scores.seo_score + seo_gain)
    projected_perf = min(100.0, scores.performance_score + perf_gain)
    projected_usab = min(100.0, scores.usability_score + usab_gain)
    projected_overall = (projected_seo * 0.4) + (projected_perf * 0.4) + (projected_usab * 0.2)

    return ScoreProjection(
        projected_seo_score=round(projected_seo, 1),
        projected_performance_score=round(projected_perf, 1),
        projected_usability_score=round(projected_usab, 1),
        projected_overall_score=round(projected_overall, 1),
        projected_grade=grade_for_score(projected_overall),
    )


def build_execution_checklist(fix_plan: list[FixPlanItem]) -> list[str]:
    checklist = [
        f"{item.issue} — Owner: {item.owner} — KPI: {item.kpi_target}"
        for item in fix_plan[:6]
    ]
    if checklist:
        return checklist
    return ["No urgent implementation tasks. Monitor performance and rerun audits after releases."]


def build_analysis_summary(
    scores: ScoreBreakdown,
    seo: SeoData,
    perf: PerformanceData,
    usab: UsabilityData,
    fix_plan: list[FixPlanItem],
    gaps: list[str],
) -> AnalysisSummary:
    strengths: list[str] = []
    risks: list[str] = []
    next_focus: list[str] = []

    if scores.seo_score >= 80:
        strengths.append(f"SEO baseline is solid at {scores.seo_score}/100.")
    if scores.performance_score >= 80:
        strengths.append(f"Performance baseline is strong at {scores.performance_score}/100.")
    if scores.usability_score >= 80:
        strengths.append(f"Usability baseline is healthy at {scores.usability_score}/100.")
    if seo.meta_robots_indexable:
        strengths.append("Page appears indexable for search engines (no noindex signal).")
    if perf.has_https:
        strengths.append("Target URL resolves over HTTPS.")
    if usab.mobile_friendly:
        strengths.append("Viewport tag indicates mobile-friendly rendering support.")

    for item in fix_plan[:4]:
        if item.severity in ("critical", "high"):
            risks.append(item.issue)
    if not risks and gaps:
        risks = gaps[:3]

    top_priorities = sorted(fix_plan[:8], key=lambda x: (x.priority_score, x.estimated_score_gain), reverse=True)
    next_focus = [
        f"{item.issue} (Owner: {item.owner}, KPI: {item.kpi_target})"
        for item in top_priorities[:3]
    ]

    if not strengths:
        strengths.append("No standout technical strengths were detected yet; focus on quick wins first.")
    if not risks:
        risks.append("No severe technical risks detected in this snapshot.")
    if not next_focus:
        next_focus.append("Run recurring audits after each release to catch regressions early.")

    summary = (
        f"Current health grade is {scores.grade} with {scores.overall_score}/100 overall. "
        f"Highest impact gains will come from the top {min(3, len(top_priorities))} prioritized fixes."
    )
    return AnalysisSummary(summary=summary, strengths=strengths[:5], risks=risks[:5], next_focus=next_focus[:5])

def normalize_ai_recommendations(raw: object, gaps: list[str], business_context: str) -> list[AIRecommendation]:
    recommendations: list[AIRecommendation] = []
    if isinstance(raw, list):
        for item in raw[:4]:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title", "")).strip()
            detail = str(item.get("detail", "")).strip()
            if not title or not detail:
                continue
            recommendations.append(
                AIRecommendation(
                    title=title,
                    detail=detail,
                    impact=str(item.get("impact", "Medium")),
                    effort=str(item.get("effort", "Medium")),
                    metric=str(item.get("metric", "Conversion Rate")),
                )
            )
    if recommendations:
        return recommendations

    if not gaps:
        return [
            AIRecommendation(
                title="Maintain momentum",
                detail="No severe blockers detected. Keep monitoring Core Web Vitals and metadata quality after each release.",
                impact="Low",
                effort="Low",
                metric="Stability",
            )
        ]

    fallback: list[AIRecommendation] = []
    for i, gap in enumerate(gaps[:3]):
        fallback.append(
            AIRecommendation(
                title=f"Fix: {gap[:70]}{'…' if len(gap) > 70 else ''}",
                detail=f"Resolve this issue and rerun the audit to raise technical quality for your {business_context}.",
                impact="High" if i == 0 else "Medium",
                effort="Low" if i < 2 else "Medium",
                metric="Overall Health Score",
            )
        )
    return fallback


def normalize_tips(raw: object, fix_plan: list[FixPlanItem]) -> list[str]:
    if isinstance(raw, list):
        cleaned = [str(x).strip() for x in raw if str(x).strip()]
        if cleaned:
            return cleaned[:8]
    if fix_plan:
        tactical = []
        for item in fix_plan[:5]:
            tactical.append(
                f"Prioritize '{item.issue}' and verify with: {item.verification}."
            )
        tactical.append("Track KPI movement weekly and tie each shipped fix to one measurable outcome.")
        return tactical[:8]

    tips = [
        "Re-run this audit after each deployment and compare score trend instead of a single snapshot.",
        "Prioritize high-severity issues first; they usually unlock the biggest conversion gain.",
        "Track one KPI per fix (CTR, bounce rate, LCP, conversions) to prove impact.",
        "Bundle related fixes into release checkpoints so you can isolate what improved results.",
    ]
    snippet_items = [x for x in fix_plan if x.code_example is not None]
    if snippet_items:
        tips.append("Apply provided code snippets in staging first, then validate with Lighthouse before production rollout.")
    return tips[:8]


def normalize_roadmap(raw: object, fix_plan: list[FixPlanItem]) -> ImprovementRoadmap:
    default = build_default_roadmap(fix_plan)
    if not isinstance(raw, dict):
        return default

    immediate = [str(x).strip() for x in raw.get("immediate", []) if str(x).strip()][:6]
    sprint = [str(x).strip() for x in raw.get("sprint", []) if str(x).strip()][:6]
    backlog = [str(x).strip() for x in raw.get("backlog", []) if str(x).strip()][:6]

    return ImprovementRoadmap(
        immediate=immediate or default.immediate,
        sprint=sprint or default.sprint,
        backlog=backlog or default.backlog,
    )


# ── OpenAI Recommendation Engine ──────────────────────────────────────────────

async def get_ai_guidance(
    gaps: list[str],
    fix_plan: list[FixPlanItem],
    scores: ScoreBreakdown,
    business_context: str,
    skip_ai: bool = False,
) -> tuple[list[AIRecommendation], list[str], ImprovementRoadmap]:
    fallback_recs = normalize_ai_recommendations([], gaps, business_context)
    fallback_tips = normalize_tips([], fix_plan)
    fallback_roadmap = build_default_roadmap(fix_plan)

    if skip_ai or os.getenv("SKIP_AI", "").lower() in ("1", "true", "yes"):
        return fallback_recs, fallback_tips, fallback_roadmap
    if openai_client is None:
        return fallback_recs, fallback_tips, fallback_roadmap

    MODEL_NAME = os.getenv("OPENAI_MODEL_NAME", "gpt-4o")
    gaps_text = "\n".join(f"- {g}" for g in gaps[:12]) if gaps else "- No major gaps detected."
    fix_preview = "\n".join(
        f"- [P{item.priority_score}|{item.severity.upper()}|{item.category}] {item.issue} -> KPI: {item.kpi_target}"
        for item in fix_plan[:10]
    )

    prompt = f"""You are a staff-level web growth engineer and technical SEO lead.
Analyze the audit findings and generate developer-focused, implementation-ready guidance.

Business context: {business_context}
Scores: SEO {scores.seo_score}/100, Performance {scores.performance_score}/100, Usability {scores.usability_score}/100, Overall {scores.overall_score}/100 (Grade {scores.grade})

Raw gaps:
{gaps_text}

Rule-based fix draft:
{fix_preview}

Return STRICT JSON in this shape:
{{
  "recommendations": [
    {{
      "title": "Short action title",
      "detail": "2-3 sentences with what to change and why it matters",
      "impact": "High|Medium|Low",
      "effort": "High|Medium|Low",
      "metric": "Metric likely to improve"
    }}
  ],
  "developer_tips": [
    "Concrete implementation tip for developers"
  ],
  "roadmap": {{
    "immediate": ["High priority items to ship now"],
    "sprint": ["Items for this sprint"],
    "backlog": ["Longer-term opportunities"]
  }}
}}

Rules:
- recommendations: exactly 3 items
- developer_tips: 4 to 8 practical tips
- Keep everything specific, tactical, and measurable
- Do not include markdown or prose outside JSON
"""

    try:
        response = await openai_client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            max_tokens=1400,
            temperature=0.15,
        )
        text = (response.choices[0].message.content or "").strip() or "{}"
        parsed_json = json.loads(text)

        recommendations = normalize_ai_recommendations(parsed_json.get("recommendations", []), gaps, business_context)
        developer_tips = normalize_tips(parsed_json.get("developer_tips", []), fix_plan)
        roadmap = normalize_roadmap(parsed_json.get("roadmap", {}), fix_plan)
        return recommendations, developer_tips, roadmap
    except Exception:
        return fallback_recs, fallback_tips, fallback_roadmap


# ── Endpoint ──────────────────────────────────────────────────────────────────

@app.post("/audit", response_model=AuditReport)
async def audit_website(req: AuditRequest):
    url = req.url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        soup, meta = await scrape_website(url)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Could not reach {url}: {e}")

    seo = extract_seo(soup, url)
    perf = extract_performance(soup, meta)
    usab = extract_usability(soup)
    scores = compute_scores(seo, perf, usab)
    gaps = build_gaps(seo, perf, usab)
    fix_plan = enrich_fix_plan(build_fix_plan(seo, perf, usab), scores)
    score_projection = build_score_projection(scores, fix_plan)
    execution_checklist = build_execution_checklist(fix_plan)
    analysis_summary = build_analysis_summary(
        scores=scores,
        seo=seo,
        perf=perf,
        usab=usab,
        fix_plan=fix_plan,
        gaps=gaps,
    )

    critical = [x.issue for x in fix_plan if x.severity in ("critical", "high")][:8]
    quick_wins = [x.issue for x in fix_plan if x.effort == "low"][:8]

    ai_recs, developer_tips, roadmap = await get_ai_guidance(
        gaps=gaps,
        fix_plan=fix_plan,
        scores=scores,
        business_context=req.business_context or "general business website",
        skip_ai=bool(req.skip_ai),
    )

    return AuditReport(
        url=url,
        scraped_at=datetime.utcnow().isoformat() + "Z",
        seo=seo,
        performance=perf,
        usability=usab,
        scores=scores,
        ai_recommendations=ai_recs,
        fix_plan=fix_plan,
        developer_tips=developer_tips,
        improvement_roadmap=roadmap,
        automation_scope="AuditFlow cannot directly edit third-party websites. It generates implementation-ready fixes, code snippets, and prioritized developer guidance for you to apply.",
        critical_issues=critical,
        quick_wins=quick_wins,
        raw_gaps=gaps,
        score_projection=score_projection,
        execution_checklist=execution_checklist,
        analysis_summary=analysis_summary,
    )


@app.get("/health")
def health():
    return {"status": "ok", "service": "Website Health Engine v2.0"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
