from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Tuple

from ..models import Task

# Languages focused on India – order matters for heuristic detection
LANGUAGE_KEYWORDS: Dict[str, List[str]] = {
    "hindi": ["kal", "tak", "karna", "hai", "karo", "aaj"],
    "tamil": ["amma", "illai", "venum", "pannunga", "seyyavendum"],
    "telugu": ["cheyali", "vundi", "ledu", "andi"],
    "kannada": ["maadi", "beku", "illa", "mugiyali"],
    "malayalam": ["cheyyuka", "illa", "venam", "kazhinju"],
    "bengali": ["korte", "hobe", "na", "ajke"],
    "marathi": ["karaycha", "aahe", "pahije"],
    "gujarati": ["karvu", "pade", "nahi"],
    "punjabi": ["karna", "zaroori", "kal", "ajj"],
    "odia": ["karibaku", "darkar"],
    "urdu": ["karna", "hai", "kal"],
    "english": ["task", "complete", "deadline"],
}


@dataclass
class RiskSignal:
    name: str
    score: float
    reason: str


class DepartmentAgent:
    """Base AI agent with department-specific flavor."""

    name: str = "generic"
    specialties: List[str] = []

    def recommend(self, task: Task, context: List[Task]) -> str:
        return "Focus on clear ownership, measurable outcomes, and unblock dependencies early."


class EngineeringAgent(DepartmentAgent):
    name = "engineering"
    specialties = ["velocity", "incidents", "quality"]

    def recommend(self, task: Task, context: List[Task]) -> str:
        return "Prioritize blockers, ensure PRD readiness, and keep cycle time low."


class ProductAgent(DepartmentAgent):
    name = "product"
    specialties = ["discovery", "adoption", "launch"]

    def recommend(self, task: Task, context: List[Task]) -> str:
        return "Validate user need, confirm acceptance criteria, and align launch messaging."


class FinanceAgent(DepartmentAgent):
    name = "finance"
    specialties = ["revenue", "cost", "compliance"]

    def recommend(self, task: Task, context: List[Task]) -> str:
        return "Monitor revenue leakage, reconcile payouts, and stay compliant with GST/TDS timelines."


class OpsAgent(DepartmentAgent):
    name = "ops"
    specialties = ["reliability", "support", "process"]

    def recommend(self, task: Task, context: List[Task]) -> str:
        return "Stabilize processes, keep SLAs green, and broadcast changes to stakeholders."


AGENTS: Dict[str, DepartmentAgent] = {
    "engineering": EngineeringAgent(),
    "product": ProductAgent(),
    "finance": FinanceAgent(),
    "ops": OpsAgent(),
}


def get_agent(department: str) -> DepartmentAgent:
    return AGENTS.get(department.lower(), DepartmentAgent())


def detect_language(text: str) -> str:
    lowered = (text or "").lower()
    for lang, hints in LANGUAGE_KEYWORDS.items():
        if any(hint in lowered for hint in hints):
            return lang
    return "english"


def normalize_multilingual_task(text: str) -> Dict[str, str]:
    """Detect language and return a normalized English summary."""

    language = detect_language(text)
    if language == "english":
        return {"language": language, "normalized": text}

    # Lightweight heuristics; in real system you would translate via NMT provider
    normalized = text
    replacements = {"kal": "tomorrow", "aaj": "today", "karna hai": "must be done"}
    for src, dest in replacements.items():
        normalized = normalized.replace(src, dest)
    return {"language": language, "normalized": normalized}


def estimate_complexity(task: Task) -> float:
    text = f"{task.title} {getattr(task, 'result_text', '')}"
    tokens = text.split()
    return min(1.0, len(tokens) / 120)


def predict_risk_profile(task: Task, related_tasks: Iterable[Task]) -> Dict[str, float | List[str]]:
    """Predict risk attributes such as delay probability and team overload."""

    related_list = list(related_tasks)
    depends_on = getattr(task, "depends_on", []) or []

    dependency_risk = min(1.0, len(depends_on) * 0.15)
    overload_risk = 0.0
    if task.owner_email:
        active_by_owner = [
            t for t in related_list if t.owner_email == task.owner_email and t.status != "completed"
        ]
        overload_risk = min(1.0, max(0, len(active_by_owner) - 3) * 0.2)

    status_penalty = 0.15 if task.status in {"pending", "in_progress"} else 0.05
    complexity = estimate_complexity(task)
    delay_probability = min(1.0, status_penalty + dependency_risk + overload_risk + complexity * 0.4)

    risk_score = round((delay_probability * 0.6 + overload_risk * 0.2 + dependency_risk * 0.2), 3)
    reasons = []
    if dependency_risk > 0.0:
        reasons.append("Multiple dependencies could block delivery")
    if overload_risk > 0.0:
        reasons.append("Owner has several active items; consider load balancing")
    if complexity > 0.5:
        reasons.append("Task description is lengthy/complex; buffer time recommended")
    if not reasons:
        reasons.append("No major risk signals detected; keep monitoring")

    return {
        "risk_score": risk_score,
        "delay_probability": round(delay_probability, 3),
        "dependency_risk": round(dependency_risk, 3),
        "overload_risk": round(overload_risk, 3),
        "complexity_estimate": round(complexity, 3),
        "reasons": reasons,
    }


def risk_level(score: float) -> str:
    if score >= 0.75:
        return "critical"
    if score >= 0.5:
        return "high"
    if score >= 0.25:
        return "medium"
    return "low"


def evaluate_task_risk(task: Task, tasks: List[Task]) -> Tuple[float, str, List[str]]:
    profile = predict_risk_profile(task, tasks)
    return profile["risk_score"], risk_level(profile["risk_score"]), profile["reasons"]


def classify_priority(task: Task) -> str:
    """Score tasks using impact, urgency, dependencies, and alignment."""

    metadata = getattr(task, "metadata_json", {}) or {}
    impact = float(metadata.get("impact", 0.5))
    urgency = float(metadata.get("urgency", 0.5))
    okr_alignment = float(metadata.get("okr_alignment", 0.5))
    user_importance = float(metadata.get("user_importance", 0.5))
    dependency_penalty = 0.1 * len(getattr(task, "depends_on", []) or [])

    score = impact * 0.3 + urgency * 0.3 + okr_alignment * 0.2 + user_importance * 0.15
    score -= dependency_penalty
    score = max(0.0, min(1.0, score))

    if score >= 0.8:
        return "CRITICAL"
    if score >= 0.6:
        return "HIGH"
    if score >= 0.35:
        return "MEDIUM"
    return "LOW"


def build_execution_plan(tasks: List[Task]) -> Dict[str, object]:
    total = len(tasks)
    completed = len([t for t in tasks if t.status == "completed"])
    in_progress = len([t for t in tasks if t.status == "in_progress"])

    return {
        "summary": f"{completed}/{total} tasks done; {in_progress} currently in progress",
        "actionable": [
            "Focus on high-priority items first",
            "Resolve blockers with highest dependency risk",
            "Communicate ETAs to stakeholders daily",
        ],
    }


def suggest_load_balance(tasks: List[Task]) -> List[Dict[str, object]]:
    squads: Dict[str, List[Task]] = {}
    for task in tasks:
        squads.setdefault(task.squad or "unassigned", []).append(task)

    suggestions = []
    for squad, squad_tasks in squads.items():
        active = [t for t in squad_tasks if t.status != "completed"]
        completed = [t for t in squad_tasks if t.status == "completed"]
        load_factor = len(active)
        suggestions.append(
            {
                "squad": squad,
                "active": len(active),
                "completed": len(completed),
                "suggestion": "Rebalance work" if load_factor > 5 else "Load healthy",
            }
        )
    return suggestions


def summarize_sprint_health(tasks: List[Task]) -> Dict[str, object]:
    if not tasks:
        return {"status": "green", "message": "No tasks found"}

    risks = [evaluate_task_risk(t, tasks)[0] for t in tasks]
    avg_risk = sum(risks) / len(risks)
    return {
        "status": risk_level(avg_risk),
        "avg_risk_score": round(avg_risk, 3),
        "notes": "Increase check-ins" if avg_risk > 0.5 else "On track",
    }


def generate_project_breakdown(title: str, squad: Optional[str] = None) -> Dict[str, object]:
    normalized = normalize_multilingual_task(title)
    base_tasks = [
        "Define scope and success metrics",
        "Draft PRD / requirements",
        "Design customer journey",
        "Set up analytics and logging",
        "Implement core experience",
        "QA with automation + manual checks",
        "Launch to pilot cohort",
        "Publish learnings and next iteration plan",
    ]

    return {
        "input_language": normalized["language"],
        "normalized_title": normalized["normalized"],
        "suggested_squad": squad or "cross-functional",
        "tasks": [
            {
                "title": f"{normalized['normalized']} – {step}",
                "status": "pending",
            }
            for step in base_tasks
        ],
    }


def generate_compliance_actions(company_name: Optional[str] = None) -> List[str]:
    prefix = company_name or "the company"
    return [
        f"{prefix}: File monthly GST returns (GSTR-1/GSTR-3B) on time",
        f"{prefix}: Reconcile TDS deductions and issue Form 16A to vendors",
        f"{prefix}: Track MCA annual filings and board meeting minutes",
        f"{prefix}: Validate Startup India registration benefits and renewals",
        f"{prefix}: Ensure vendor payments follow agreed credit cycles",
    ]


__all__ = [
    "AGENTS",
    "EngineeringAgent",
    "ProductAgent",
    "FinanceAgent",
    "OpsAgent",
    "get_agent",
    "evaluate_task_risk",
    "classify_priority",
    "build_execution_plan",
    "suggest_load_balance",
    "summarize_sprint_health",
    "generate_project_breakdown",
    "generate_compliance_actions",
    "normalize_multilingual_task",
]
