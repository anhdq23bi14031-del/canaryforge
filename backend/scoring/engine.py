"""
Behavioral Scoring Engine — scores each trigger event to separate
real attacker activity from scanners, bots, and false positives.

Score interpretation (defaults, configurable in .env):
  < FALSE_POSITIVE_SCORE:    Likely bot/scanner/false positive — suppress alert
  FALSE_POSITIVE_SCORE..ALERT_SCORE_THRESHOLD: Ambiguous — log but hold alert
  >= ALERT_SCORE_THRESHOLD:  High confidence real trigger — fire alert immediately
"""
from dataclasses import dataclass, field
from typing import Optional
import re

from backend.config import settings


# Known bot/scanner User-Agent patterns
BOT_UA_PATTERNS = [
    r"python-requests",
    r"curl/",
    r"wget/",
    r"Go-http-client",
    r"axios/",
    r"node-fetch",
    r"okhttp",
    r"Scrapy",
    r"bot",
    r"crawler",
    r"spider",
    r"scanner",
    r"nmap",
    r"masscan",
    r"nuclei",
    r"shodan",
    r"censys",
]

# Known cloud scanner IP ranges (simplified — in production use an IP DB)
SCANNER_IP_PREFIXES = [
    "66.249.",   # Googlebot
    "157.55.",   # Bingbot
    "40.77.",    # Bingbot
    "54.239.",   # AWS health checks
    "34.64.",    # GCP
]

# High-risk ASNs (simplified)
HIGH_RISK_COUNTRIES = {"CN", "RU", "KP", "IR"}  # Example — tune to your environment


@dataclass
class ScoreResult:
    total: float
    breakdown: dict = field(default_factory=dict)
    is_false_positive: bool = False
    recommendation: str = "monitor"   # monitor | alert | suppress


def score_trigger(
    ip_address: Optional[str],
    user_agent: Optional[str],
    referer: Optional[str],
    headers: Optional[dict],
    geo_country: Optional[str],
    token_type: str,
    extra: Optional[dict] = None,
) -> ScoreResult:
    """
    Score a trigger event and return a risk score with breakdown.
    """
    breakdown = {}
    total = 0.0

    # --- Allowlist check: known-safe IPs/CIDRs never alert ---
    # Useful for excluding your own office IP, security team scanners,
    # monitoring tools, or anything else you KNOW is not an attacker.
    if ip_address and _is_allowlisted(ip_address):
        breakdown["allowlisted_ip"] = 0
        return ScoreResult(
            total=0.0,
            breakdown={"allowlisted_ip": "IP in ALLOWLISTED_IPS — scoring skipped"},
            is_false_positive=True,
            recommendation="suppress",
        )

    # --- Base score: any trigger gets something ---
    breakdown["base"] = 10
    total += 10

    # --- User-Agent analysis ---
    ua = (user_agent or "").lower()
    if not ua:
        breakdown["no_user_agent"] = 15
        total += 15
    elif _matches_bot_pattern(ua):
        breakdown["bot_user_agent"] = -20
        total -= 20
    else:
        # Real browser UA patterns
        if any(b in ua for b in ["mozilla", "chrome", "safari", "firefox", "edge"]):
            breakdown["browser_user_agent"] = 20
            total += 20

    # --- IP analysis ---
    if ip_address:
        if _is_scanner_ip(ip_address):
            breakdown["scanner_ip"] = -25
            total -= 25
        elif _is_tor_or_vpn(ip_address, extra):
            breakdown["tor_vpn"] = 25
            total += 25

    # --- Geo risk ---
    if geo_country and geo_country.upper() in HIGH_RISK_COUNTRIES:
        breakdown["high_risk_country"] = 20
        total += 20

    # --- Token type multiplier ---
    # AWS credential use is the highest signal — very unlikely to be accidental
    if token_type == "aws":
        breakdown["aws_token_multiplier"] = 30
        total += 30
    elif token_type in ("doc", "pdf", "excel"):
        breakdown["document_open"] = 10
        total += 10

    # --- Referer analysis ---
    if referer:
        breakdown["has_referer"] = 5
        total += 5

    # --- Time-of-day (off-hours = higher risk) ---
    from datetime import datetime, timezone
    hour = datetime.now(timezone.utc).hour
    if hour < 6 or hour > 22:
        breakdown["off_hours"] = 10
        total += 10

    total = max(0.0, total)

    fp_threshold = settings.FALSE_POSITIVE_SCORE
    alert_threshold = settings.ALERT_SCORE_THRESHOLD

    is_fp = total < fp_threshold
    if total >= alert_threshold:
        rec = "alert"
    elif total >= fp_threshold:
        rec = "monitor"
    else:
        rec = "suppress"

    return ScoreResult(
        total=round(total, 1),
        breakdown=breakdown,
        is_false_positive=is_fp,
        recommendation=rec,
    )


def _matches_bot_pattern(ua: str) -> bool:
    for pattern in BOT_UA_PATTERNS:
        if re.search(pattern, ua, re.IGNORECASE):
            return True
    return False


def _is_scanner_ip(ip: str) -> bool:
    for prefix in SCANNER_IP_PREFIXES:
        if ip.startswith(prefix):
            return True
    return False


def _is_tor_or_vpn(ip: str, extra: Optional[dict]) -> bool:
    if extra and extra.get("is_tor"):
        return True
    if extra and extra.get("is_vpn"):
        return True
    return False


def _is_allowlisted(ip: str) -> bool:
    """
    Check whether an IP matches any entry in settings.ALLOWLISTED_IPS.
    Supports exact IPs and CIDR ranges (e.g. "203.0.113.0/24").
    """
    if not settings.ALLOWLISTED_IPS:
        return False

    import ipaddress
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False

    for entry in settings.ALLOWLISTED_IPS:
        entry = entry.strip()
        if not entry:
            continue
        try:
            if "/" in entry:
                if addr in ipaddress.ip_network(entry, strict=False):
                    return True
            else:
                if addr == ipaddress.ip_address(entry):
                    return True
        except ValueError:
            continue
    return False