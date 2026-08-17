import json
import re
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup
from streamlit_autorefresh import st_autorefresh

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None

APP_TITLE = "⚽ FOOTBALL MARKET MONITOR"
APP_SUBTITLE = "Surveillance pré-match des marchés football"
DEFAULT_THRESHOLD = 1.55
DEFAULT_MARKET = "Double chance 12"
REQUEST_TIMEOUT = 20
AUTO_REFRESH_OPTIONS = {
    "OFF": 0,
    "30 secondes": 30,
    "60 secondes": 60,
    "2 minutes": 120,
    "5 minutes": 300,
}
STATUS_SUCCESS = "success"
STATUS_STALE = "stale"
STATUS_ERROR = "error"
USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/127.0 Mobile Safari/537.36"
)
DATE_TODAY_MODE = "📅 AUJOURD'HUI"
DATE_CUSTOM_MODE = "🗓️ DATE PERSONNALISÉE"


# -----------------------------------------------------------------------------
# Configuration générale
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title=APP_TITLE,
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    :root {
        --bg: #0f172a;
        --card: #111827;
        --card-2: #1f2937;
        --border: rgba(148, 163, 184, 0.22);
        --text: #e5e7eb;
        --muted: #94a3b8;
        --accent: #22c55e;
        --warning: #f59e0b;
        --danger: #ef4444;
        --info: #38bdf8;
    }

    .stApp {
        background: linear-gradient(180deg, #020617 0%, #0f172a 100%);
        color: var(--text);
    }

    .block-container {
        padding-top: 1rem;
        padding-bottom: 2rem;
        max-width: 1200px;
    }

    h1, h2, h3 {
        color: #f8fafc !important;
    }

    .hero {
        background: linear-gradient(135deg, rgba(34,197,94,0.16), rgba(56,189,248,0.10));
        border: 1px solid var(--border);
        border-radius: 20px;
        padding: 1.2rem 1rem;
        margin-bottom: 1rem;
        box-shadow: 0 10px 30px rgba(0,0,0,0.22);
    }

    .hero p {
        margin: 0.2rem 0 0 0;
        color: var(--muted);
        font-size: 1rem;
    }

    .section-card {
        background: rgba(17, 24, 39, 0.82);
        border: 1px solid var(--border);
        border-radius: 18px;
        padding: 1rem;
        margin-bottom: 1rem;
        box-shadow: 0 8px 24px rgba(0,0,0,0.18);
    }

    .status-pill {
        display: inline-block;
        padding: 0.3rem 0.7rem;
        border-radius: 999px;
        font-weight: 600;
        margin-bottom: 0.5rem;
        border: 1px solid var(--border);
    }

    .status-green { background: rgba(34,197,94,0.15); color: #86efac; }
    .status-orange { background: rgba(245,158,11,0.16); color: #fcd34d; }
    .status-red { background: rgba(239,68,68,0.16); color: #fca5a5; }

    .small-note {
        color: var(--muted);
        font-size: 0.92rem;
        line-height: 1.5;
    }

    .metric-box {
        background: rgba(15, 23, 42, 0.7);
        border: 1px solid var(--border);
        border-radius: 16px;
        padding: 0.85rem;
        min-height: 92px;
    }

    .metric-label {
        color: var(--muted);
        font-size: 0.9rem;
        margin-bottom: 0.3rem;
    }

    .metric-value {
        font-size: 1.35rem;
        font-weight: 700;
        color: #f8fafc;
    }

    .stButton > button, .stDownloadButton > button {
        width: 100%;
        min-height: 3rem;
        border-radius: 14px;
        border: 1px solid rgba(56,189,248,0.35);
        background: linear-gradient(135deg, rgba(30,41,59,1), rgba(17,24,39,1));
        color: #f8fafc;
        font-weight: 700;
    }

    .stTabs [data-baseweb="tab-list"] {
        gap: 0.35rem;
        overflow-x: auto;
    }

    .stTabs [data-baseweb="tab"] {
        background: rgba(15, 23, 42, 0.8);
        border-radius: 14px 14px 0 0;
        padding: 0.7rem 1rem;
    }

    .stDataFrame {
        border-radius: 14px;
        overflow: hidden;
    }

    @media (max-width: 768px) {
        .block-container {
            padding-left: 0.8rem;
            padding-right: 0.8rem;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# -----------------------------------------------------------------------------
# Outils généraux
# -----------------------------------------------------------------------------
def init_session_state() -> None:
    defaults = {
        "results": [],
        "all_matches": [],
        "last_success_results": [],
        "last_success_matches": [],
        "last_success_target_date": None,
        "last_fetch_attempt_at": None,
        "last_success_at": None,
        "last_fetch_status": STATUS_ERROR,
        "last_error": None,
        "last_source_url": "",
        "last_source_http_status": None,
        "last_content_type": None,
        "request_counter": 0,
        "last_auto_refresh_tick": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


init_session_state()


def is_valid_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    except Exception:
        return False



def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()



def safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = normalize_text(value).replace(",", ".")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group())
    except Exception:
        return None



def to_display_value(value: Any, unavailable: str = "❌ Donnée indisponible") -> str:
    text = normalize_text(value)
    return text if text else unavailable



def parse_datetime_value(value: Any, timezone_name: Optional[str] = None) -> Optional[datetime]:
    if value is None or value == "":
        return None

    dt_obj: Optional[datetime] = None

    if isinstance(value, datetime):
        dt_obj = value
    elif isinstance(value, pd.Timestamp):
        dt_obj = value.to_pydatetime()
    elif isinstance(value, (int, float)):
        # Heuristique: timestamps en secondes ou millisecondes.
        number = float(value)
        if number > 10_000_000_000:
            number = number / 1000.0
        try:
            dt_obj = datetime.fromtimestamp(number, tz=timezone.utc)
        except Exception:
            dt_obj = None
    else:
        text = normalize_text(value)
        if not text:
            return None
        try:
            parsed = pd.to_datetime(text, utc=False, errors="coerce")
            if pd.isna(parsed):
                return None
            if isinstance(parsed, pd.Series):
                parsed = parsed.iloc[0]
            dt_obj = parsed.to_pydatetime() if isinstance(parsed, pd.Timestamp) else parsed
        except Exception:
            return None

    if dt_obj is None:
        return None

    if timezone_name and dt_obj.tzinfo is None and ZoneInfo is not None:
        try:
            dt_obj = dt_obj.replace(tzinfo=ZoneInfo(timezone_name))
        except Exception:
            pass

    return dt_obj



def extract_date_and_time(raw_date: Any, raw_time: Any, timezone_name: Optional[str]) -> Tuple[Optional[date], str]:
    combined_candidates = []
    if raw_date is not None and raw_time not in (None, ""):
        combined_candidates.append(f"{raw_date} {raw_time}")
    if raw_date is not None:
        combined_candidates.append(raw_date)
    if raw_time is not None:
        combined_candidates.append(raw_time)

    for candidate in combined_candidates:
        dt_obj = parse_datetime_value(candidate, timezone_name)
        if dt_obj:
            time_label = dt_obj.strftime("%H:%M")
            return dt_obj.date(), time_label

    date_only = parse_datetime_value(raw_date, timezone_name)
    if date_only:
        return date_only.date(), date_only.strftime("%H:%M")

    return None, normalize_text(raw_time)



def looks_like_football_event(item: Dict[str, Any]) -> bool:
    blob = normalize_text(json.dumps(item, ensure_ascii=False)).lower()
    football_markers = [
        "football", "soccer", "fixture", "match", "home", "away",
        "team", "tournament", "league", "bookmaker", "odds",
    ]
    score_markers = ["vs", " v ", " - ", "homeTeam", "awayTeam"]
    return any(marker in blob for marker in football_markers) or any(marker in blob for marker in score_markers)



def gather_candidate_event_dicts(data: Any) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []

    def walk(obj: Any) -> None:
        if isinstance(obj, dict):
            keys = {str(k).lower() for k in obj.keys()}
            if len(keys) >= 2 and looks_like_football_event(obj):
                team_keys = {
                    "home_team", "away_team", "hometeam", "awayteam", "home", "away",
                    "participants", "competitors", "teams", "match", "event", "name",
                }
                market_keys = {"markets", "odds", "bookmakers", "selections", "outcomes"}
                if keys.intersection(team_keys) or keys.intersection(market_keys):
                    candidates.append(obj)
            for value in obj.values():
                walk(value)
        elif isinstance(obj, list):
            for entry in obj:
                walk(entry)

    walk(data)
    return candidates



def get_first_value(item: Dict[str, Any], keys: List[str]) -> Any:
    lowered = {str(k).lower(): v for k, v in item.items()}
    for key in keys:
        if key.lower() in lowered:
            return lowered[key.lower()]
    return None



def split_match_name(match_name: str) -> Tuple[str, str]:
    patterns = [r"\s+vs\.?\s+", r"\s+v\s+", r"\s+-\s+", r"\s+–\s+", r"\s+contre\s+"]
    for pattern in patterns:
        parts = re.split(pattern, match_name, flags=re.IGNORECASE)
        if len(parts) == 2:
            return normalize_text(parts[0]), normalize_text(parts[1])
    return "", ""



def extract_team_names(item: Dict[str, Any]) -> Tuple[str, str, str]:
    home = normalize_text(get_first_value(item, ["home_team", "hometeam", "home", "team1", "localteam"]))
    away = normalize_text(get_first_value(item, ["away_team", "awayteam", "away", "team2", "visitorteam"]))
    match_label = normalize_text(get_first_value(item, ["match", "event", "name", "title"]))

    participants = get_first_value(item, ["participants", "competitors", "teams"])
    if (not home or not away) and isinstance(participants, list):
        names = []
        for participant in participants:
            if isinstance(participant, dict):
                name = normalize_text(
                    participant.get("name")
                    or participant.get("team")
                    or participant.get("participant")
                    or participant.get("label")
                )
            else:
                name = normalize_text(participant)
            if name:
                names.append(name)
        if len(names) >= 2:
            home = home or names[0]
            away = away or names[1]
            match_label = match_label or f"{home} vs {away}"

    if (not home or not away) and match_label:
        inferred_home, inferred_away = split_match_name(match_label)
        home = home or inferred_home
        away = away or inferred_away

    if not match_label and home and away:
        match_label = f"{home} vs {away}"

    return home, away, match_label



def normalize_market_name(name: Any) -> str:
    text = normalize_text(name).lower()
    text = text.replace("doublechance", "double chance")
    text = re.sub(r"\s+", " ", text)
    return text



def market_matches_double_chance_12(name: Any, category: Any = None, selection: Any = None) -> bool:
    name_norm = normalize_market_name(name)
    cat_norm = normalize_market_name(category)
    sel_norm = normalize_market_name(selection)

    pool = " | ".join([name_norm, cat_norm, sel_norm])
    direct_patterns = [
        "double chance 12",
        "double chance - 12",
        "double chance: 12",
        "chance double 12",
    ]
    if any(pattern in pool for pattern in direct_patterns):
        return True

    has_double = "double chance" in pool or "chance double" in pool
    has_12 = re.search(r"(^|[^0-9])12([^0-9]|$)", pool) is not None
    return has_double and has_12



def find_market_odds_in_structure(node: Any) -> Tuple[Optional[float], Optional[str]]:
    found_reason = None

    def walk(obj: Any, parent_market: Optional[str] = None, parent_category: Optional[str] = None) -> Optional[float]:
        nonlocal found_reason
        if isinstance(obj, dict):
            market_name = (
                obj.get("market") or obj.get("market_name") or obj.get("marketName")
                or obj.get("name") or obj.get("label") or parent_market
            )
            category_name = (
                obj.get("category") or obj.get("group") or obj.get("type")
                or obj.get("betType") or parent_category
            )
            selection_name = obj.get("selection") or obj.get("outcome") or obj.get("runner") or obj.get("pick")

            if market_matches_double_chance_12(market_name, category_name, selection_name):
                for price_key in ["odds_12", "odds", "price", "value", "decimal", "coefficient", "quote"]:
                    if price_key in obj:
                        price = safe_float(obj.get(price_key))
                        if price is not None:
                            found_reason = normalize_text(market_name or category_name or selection_name)
                            return price

            for list_key in ["outcomes", "selections", "runners", "choices", "bets"]:
                if list_key in obj and isinstance(obj[list_key], list):
                    for outcome in obj[list_key]:
                        if isinstance(outcome, dict):
                            outcome_name = outcome.get("name") or outcome.get("label") or outcome.get("selection")
                            if market_matches_double_chance_12(market_name, category_name, outcome_name):
                                for price_key in ["odds", "price", "value", "decimal", "coefficient", "quote"]:
                                    price = safe_float(outcome.get(price_key))
                                    if price is not None:
                                        found_reason = normalize_text(market_name or category_name or outcome_name)
                                        return price

            for value in obj.values():
                result = walk(value, market_name, category_name)
                if result is not None:
                    return result

        elif isinstance(obj, list):
            for value in obj:
                result = walk(value, parent_market, parent_category)
                if result is not None:
                    return result
        return None

    odds = walk(node)
    return odds, found_reason



def extract_json_candidates_from_html(html: str) -> List[Any]:
    soup = BeautifulSoup(html, "html.parser")
    candidates: List[Any] = []

    for script in soup.find_all("script", attrs={"type": re.compile(r"application/(ld\+json|json)", re.I)}):
        text = script.string or script.get_text(" ", strip=True)
        if not text:
            continue
        try:
            candidates.append(json.loads(text))
        except Exception:
            continue

    for script in soup.find_all("script"):
        text = script.string or script.get_text(" ", strip=True)
        if not text or len(text) < 20:
            continue
        json_match = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
        if not json_match:
            continue
        snippet = json_match.group(1)
        try:
            candidates.append(json.loads(snippet))
        except Exception:
            continue

    return candidates



def fetch_public_source(url: str) -> Dict[str, Any]:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }

    response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()

    content_type = normalize_text(response.headers.get("Content-Type", "")).lower()
    body_text = response.text
    if not body_text or not body_text.strip():
        raise ValueError("Page vide ou contenu vide")

    parsed_json = None
    if "json" in content_type:
        parsed_json = response.json()
    else:
        try:
            parsed_json = response.json()
            content_type = content_type or "application/json"
        except Exception:
            parsed_json = None

    return {
        "url": response.url,
        "status_code": response.status_code,
        "content_type": content_type or "inconnu",
        "text": body_text,
        "json": parsed_json,
    }



def extract_matches(source_payload: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    raw_candidates: List[Dict[str, Any]] = []
    source_json = source_payload.get("json")
    source_text = source_payload.get("text", "")
    content_type = source_payload.get("content_type", "")

    if source_json is not None:
        raw_candidates.extend(gather_candidate_event_dicts(source_json))

    if not raw_candidates and "html" in content_type:
        embedded_json_candidates = extract_json_candidates_from_html(source_text)
        for embedded in embedded_json_candidates:
            raw_candidates.extend(gather_candidate_event_dicts(embedded))

    if not raw_candidates and "html" in content_type:
        soup = BeautifulSoup(source_text, "html.parser")
        for row in soup.select("tr, article, li, div"):
            text = normalize_text(row.get_text(" ", strip=True))
            if not text:
                continue
            if " vs " not in text.lower() and "football" not in text.lower() and "soccer" not in text.lower():
                continue
            data = {
                "name": text,
                "market_blob": text,
            }
            raw_candidates.append(data)

    normalized_matches: List[Dict[str, Any]] = []
    seen_keys = set()

    for candidate in raw_candidates:
        if not isinstance(candidate, dict):
            continue

        home_team, away_team, match_label = extract_team_names(candidate)
        competition = normalize_text(
            get_first_value(candidate, [
                "competition", "league", "tournament", "championship", "season_name", "sport_title"
            ])
        )
        timezone_name = normalize_text(get_first_value(candidate, ["timezone", "tz", "time_zone"]))
        raw_date = get_first_value(candidate, [
            "date", "start_time", "starttime", "start", "starts_at", "kickoff", "kickoff_time",
            "commence_time", "event_date", "utc_time", "scheduled", "begin_at"
        ])
        raw_time = get_first_value(candidate, ["time", "hour", "start_hour"])
        match_date, time_label = extract_date_and_time(raw_date, raw_time, timezone_name or None)

        odds_value, odds_market_name = find_market_odds_in_structure(candidate)

        if odds_value is None:
            market_blob = normalize_text(candidate.get("market_blob"))
            if market_matches_double_chance_12(market_blob):
                odds_value = safe_float(market_blob)
                odds_market_name = DEFAULT_MARKET if odds_value is not None else None

        row = {
            "match": match_label,
            "home_team": home_team,
            "away_team": away_team,
            "competition": competition,
            "date": match_date.strftime("%d/%m/%Y") if match_date else "",
            "time": time_label,
            "timezone": timezone_name,
            "market": DEFAULT_MARKET if odds_value is not None else "",
            "odds_12": odds_value,
            "raw": candidate,
            "market_source_name": odds_market_name or "",
        }

        identity = (
            row["match"],
            row["competition"],
            row["date"],
            row["time"],
            row["odds_12"],
        )
        if identity in seen_keys:
            continue
        seen_keys.add(identity)
        normalized_matches.append(row)

    if not normalized_matches:
        return [], "⚠️ SOURCE NON COMPATIBLE OU STRUCTURE NON RECONNUE"

    return normalized_matches, None



def validate_match(match: Dict[str, Any]) -> Tuple[bool, List[str]]:
    issues = []
    if not normalize_text(match.get("home_team")):
        issues.append("Équipe domicile absente")
    if not normalize_text(match.get("away_team")):
        issues.append("Équipe extérieure absente")
    if not normalize_text(match.get("date")):
        issues.append("Date absente")
    if not normalize_text(match.get("market")):
        issues.append("⚠️ Marché 12 indisponible")
    odds = match.get("odds_12")
    if odds is None:
        issues.append("⚠️ Cote 12 indisponible")
    elif not isinstance(odds, (int, float)):
        issues.append("⚠️ Cote 12 invalide")
    elif odds <= 0:
        issues.append("⚠️ Cote 12 invalide")
    return len(issues) == 0, issues



def resolve_target_date(mode: str, custom_date: date) -> date:
    if mode == DATE_TODAY_MODE:
        return datetime.now().date()
    return custom_date



def filter_today_matches(matches: List[Dict[str, Any]], target_date: date) -> List[Dict[str, Any]]:
    return filter_matches_by_date(matches, target_date)



def filter_matches_by_date(matches: List[Dict[str, Any]], target_date: date) -> List[Dict[str, Any]]:
    filtered = []
    for match in matches:
        match_date = normalize_text(match.get("date"))
        if not match_date:
            continue
        try:
            parsed = datetime.strptime(match_date, "%d/%m/%Y").date()
        except Exception:
            continue
        if parsed == target_date:
            filtered.append(match)
    return filtered



def filter_market(matches: List[Dict[str, Any]], market_name: str) -> List[Dict[str, Any]]:
    market_name = normalize_text(market_name)
    filtered = []
    for match in matches:
        current = normalize_text(match.get("market"))
        if current == market_name:
            filtered.append(match)
    return filtered



def parse_odds(match: Dict[str, Any]) -> Tuple[Optional[float], str]:
    odds = match.get("odds_12")
    if odds is None:
        return None, "⚠️ Cote 12 indisponible"
    if not isinstance(odds, (int, float)) or odds <= 0:
        return None, "⚠️ Cote 12 invalide"
    return float(odds), "OK"



def analyze_matches(matches: List[Dict[str, Any]], threshold: float) -> List[Dict[str, Any]]:
    analyzed = []
    for match in matches:
        is_valid, issues = validate_match(match)
        odds_value, odds_status = parse_odds(match)
        status = "Sous le seuil"
        if odds_value is not None and odds_value >= threshold:
            status = "📊 SEUIL ATTEINT"
        elif odds_value is None:
            status = odds_status

        analyzed.append({
            **match,
            "validation": "✓ Valide" if is_valid else " ; ".join(issues),
            "odds_status": odds_status,
            "threshold": threshold,
            "status": status,
            "threshold_hit": bool(odds_value is not None and odds_value >= threshold),
        })
    return analyzed



def format_results_dataframe(matches: List[Dict[str, Any]]) -> pd.DataFrame:
    if not matches:
        return pd.DataFrame(columns=[
            "Match", "Compétition", "Date", "Heure", "Marché", "Cote 12", "Seuil", "Statut", "Validation"
        ])

    rows = []
    for match in matches:
        rows.append({
            "Match": to_display_value(match.get("match")),
            "Compétition": to_display_value(match.get("competition")),
            "Date": to_display_value(match.get("date")),
            "Heure": to_display_value(match.get("time")),
            "Marché": to_display_value(match.get("market")),
            "Cote 12": match.get("odds_12") if match.get("odds_12") is not None else "❌ Donnée indisponible",
            "Seuil": match.get("threshold"),
            "Statut": to_display_value(match.get("status")),
            "Validation": to_display_value(match.get("validation")),
        })
    return pd.DataFrame(rows)



def display_metrics(total_matches: int, markets_available: int, threshold_hits: int, target_date: date) -> None:
    target_date_str = target_date.strftime("%d/%m/%Y")
    st.markdown(f"### 📅 DATE CIBLE : {target_date_str}")
    col1, col2, col3, col4 = st.columns(4)
    metrics = [
        (col1, "⚽ MATCHS", str(total_matches)),
        (col2, "📊 MARCHÉS 12 DISPONIBLES", str(markets_available)),
        (col3, "🔎 SEUIL ATTEINT", str(threshold_hits)),
        (col4, f"⚽ MATCHS DU {target_date_str}", str(total_matches)),
    ]
    for column, label, value in metrics:
        with column:
            st.markdown(
                f"<div class='metric-box'><div class='metric-label'>{label}</div><div class='metric-value'>{value}</div></div>",
                unsafe_allow_html=True,
            )



def display_results(results: List[Dict[str, Any]], target_date: date) -> None:
    st.markdown("## 📋 MATCHS")

    total_matches = len(results)
    markets_available = sum(1 for item in results if item.get("odds_12") is not None)
    threshold_hits = sum(1 for item in results if item.get("threshold_hit"))

    display_metrics(total_matches, markets_available, threshold_hits, target_date)

    all_df = format_results_dataframe(results)
    threshold_df = format_results_dataframe([item for item in results if item.get("threshold_hit")])

    tab_all, tab_threshold = st.tabs(["📋 TOUS LES MATCHS", "🎯 MATCHS ATTEIGNANT LE SEUIL"])

    with tab_all:
        if total_matches == 0:
            st.info("ℹ️ Aucun match trouvé pour la date sélectionnée.")
        st.dataframe(all_df, use_container_width=True, hide_index=True)

    with tab_threshold:
        if threshold_df.empty:
            st.info("ℹ️ Aucun match n'atteint le seuil configuré.")
        st.dataframe(threshold_df, use_container_width=True, hide_index=True)



def display_optional_statistics(results: List[Dict[str, Any]]) -> None:
    st.markdown("## 📈 STATISTIQUES")
    stats_fields = [
        ("Forme récente", "recent_form"),
        ("Buts marqués", "goals_scored"),
        ("Buts encaissés", "goals_conceded"),
        ("Moyenne de buts", "avg_goals"),
        ("Domicile", "home_record"),
        ("Extérieur", "away_record"),
        ("Victoire", "wins"),
        ("Nul", "draws"),
        ("Défaite", "losses"),
    ]

    rows = []
    has_real_stat = False
    for item in results:
        row = {"Match": to_display_value(item.get("match"))}
        raw = item.get("raw") if isinstance(item.get("raw"), dict) else {}
        for label, key in stats_fields:
            raw_value = raw.get(key)
            if normalize_text(raw_value):
                has_real_stat = True
            row[label] = to_display_value(raw_value)
        rows.append(row)

    if not rows or not has_real_stat:
        st.info("❌ Donnée indisponible")
        return

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)



def display_status() -> None:
    st.markdown("## 🕐 FRAÎCHEUR")
    status = st.session_state.last_fetch_status
    source_url = st.session_state.last_source_url or "❌ Donnée indisponible"
    success_at = st.session_state.last_success_at
    error_message = st.session_state.last_error
    http_status = st.session_state.last_source_http_status
    content_type = st.session_state.last_content_type or "❌ Donnée indisponible"

    if status == STATUS_SUCCESS:
        st.markdown("<div class='status-pill status-green'>🟢 VÉRIFIÉ RÉCEMMENT</div>", unsafe_allow_html=True)
        if success_at:
            st.write(f"Dernière récupération : {success_at}")
        st.write(f"Source : {source_url}")
        st.write(f"Type de contenu : {content_type}")
        if http_status is not None:
            st.write(f"Statut HTTP : {http_status}")
    elif status == STATUS_STALE:
        st.markdown("<div class='status-pill status-orange'>🟠 DERNIÈRES DONNÉES CONNUES</div>", unsafe_allow_html=True)
        if success_at:
            st.write(f"Dernière récupération vérifiée : {success_at}")
        st.write("Les données affichées ne proviennent pas d'une récupération réussie récente.")
        st.write(f"Source : {source_url}")
        if error_message:
            st.warning(error_message)
    else:
        st.markdown("<div class='status-pill status-red'>🔴 DONNÉES NON VÉRIFIABLES</div>", unsafe_allow_html=True)
        st.write(f"Source : {source_url}")
        if error_message:
            st.error(error_message)
        else:
            st.error("🔴 Données non vérifiables actuellement")



def perform_search(source_url: str, date_mode: str, custom_date: date, threshold: float, market_name: str) -> None:
    st.session_state.request_counter += 1
    st.session_state.last_fetch_attempt_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    st.session_state.last_source_url = source_url

    if not source_url.strip():
        st.session_state.last_fetch_status = STATUS_ERROR
        st.session_state.last_error = "URL vide"
        return

    if not is_valid_url(source_url):
        st.session_state.last_fetch_status = STATUS_ERROR
        st.session_state.last_error = "URL invalide"
        return

    target_date = resolve_target_date(date_mode, custom_date)

    try:
        payload = fetch_public_source(source_url)
        st.session_state.last_source_http_status = payload.get("status_code")
        st.session_state.last_content_type = payload.get("content_type")

        extracted_matches, extraction_error = extract_matches(payload)
        if extraction_error:
            raise ValueError(extraction_error)

        valid_date_matches = filter_today_matches(extracted_matches, target_date)
        market_matches = filter_market(valid_date_matches, market_name)
        analyzed = analyze_matches(market_matches, threshold)

        st.session_state.all_matches = extracted_matches
        st.session_state.results = analyzed
        st.session_state.last_success_results = analyzed
        st.session_state.last_success_matches = extracted_matches
        st.session_state.last_success_target_date = target_date.strftime("%d/%m/%Y")
        st.session_state.last_success_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        st.session_state.last_fetch_status = STATUS_SUCCESS
        st.session_state.last_error = None

    except requests.exceptions.Timeout:
        st.session_state.last_error = "Timeout lors de la récupération de la source"
        if st.session_state.last_success_results:
            st.session_state.results = st.session_state.last_success_results
            st.session_state.last_fetch_status = STATUS_STALE
        else:
            st.session_state.last_fetch_status = STATUS_ERROR
    except requests.exceptions.HTTPError as exc:
        st.session_state.last_error = f"Erreur HTTP : {exc}"
        if st.session_state.last_success_results:
            st.session_state.results = st.session_state.last_success_results
            st.session_state.last_fetch_status = STATUS_STALE
        else:
            st.session_state.last_fetch_status = STATUS_ERROR
    except requests.exceptions.RequestException as exc:
        st.session_state.last_error = f"Serveur inaccessible ou erreur réseau : {exc}"
        if st.session_state.last_success_results:
            st.session_state.results = st.session_state.last_success_results
            st.session_state.last_fetch_status = STATUS_STALE
        else:
            st.session_state.last_fetch_status = STATUS_ERROR
    except ValueError as exc:
        st.session_state.last_error = str(exc)
        if st.session_state.last_success_results:
            st.session_state.results = st.session_state.last_success_results
            st.session_state.last_fetch_status = STATUS_STALE
        else:
            st.session_state.last_fetch_status = STATUS_ERROR
    except Exception as exc:
        st.session_state.last_error = f"Erreur parsing : {exc}"
        if st.session_state.last_success_results:
            st.session_state.results = st.session_state.last_success_results
            st.session_state.last_fetch_status = STATUS_STALE
        else:
            st.session_state.last_fetch_status = STATUS_ERROR


# -----------------------------------------------------------------------------
# Interface
# -----------------------------------------------------------------------------
st.markdown(
    f"""
    <div class='hero'>
        <h1>{APP_TITLE}</h1>
        <p>{APP_SUBTITLE}</p>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown("## 🌐 SOURCE")
source_url = st.text_input(
    "Lien de la source publique",
    value=st.session_state.last_source_url,
    placeholder="https://...",
    help="La source fournie par l'utilisateur est la référence principale.",
)

st.markdown("## ⚙️ PARAMÈTRES")
col_params_1, col_params_2 = st.columns(2)
with col_params_1:
    market_name = st.text_input("Marché surveillé", value=DEFAULT_MARKET, disabled=True)
with col_params_2:
    threshold = st.number_input("Cote minimale", min_value=1.01, value=float(DEFAULT_THRESHOLD), step=0.01)

st.markdown("## 📅 DATE DES MATCHS")
date_mode = st.radio(
    "Mode de date",
    options=[DATE_TODAY_MODE, DATE_CUSTOM_MODE],
    horizontal=False,
)

custom_date = st.date_input(
    "Choisir la date des matchs",
    value=datetime.now().date(),
    disabled=date_mode != DATE_CUSTOM_MODE,
)

target_date_preview = resolve_target_date(date_mode, custom_date)
st.info(f"📅 DATE CIBLE : {target_date_preview.strftime('%d/%m/%Y')}")

st.markdown("## 🔄 ACTUALISATION AUTOMATIQUE")
auto_refresh_label = st.selectbox(
    "Fréquence",
    options=list(AUTO_REFRESH_OPTIONS.keys()),
    index=0,
)

auto_refresh_seconds = AUTO_REFRESH_OPTIONS[auto_refresh_label]
auto_refresh_tick = None
if auto_refresh_seconds > 0:
    auto_refresh_tick = st_autorefresh(
        interval=auto_refresh_seconds * 1000,
        key="football_market_monitor_autorefresh",
    )

col_action_1, col_action_2 = st.columns(2)
with col_action_1:
    search_clicked = st.button("🔎 RECHERCHER LES MATCHS", type="primary")
with col_action_2:
    refresh_clicked = st.button("🔄 ACTUALISER MAINTENANT")

should_run = search_clicked or refresh_clicked
if auto_refresh_seconds > 0 and auto_refresh_tick is not None:
    if st.session_state.last_auto_refresh_tick != auto_refresh_tick:
        should_run = True
        st.session_state.last_auto_refresh_tick = auto_refresh_tick

if should_run:
    with st.spinner("Nouvelle récupération, validation et analyse en cours..."):
        perform_search(source_url, date_mode, custom_date, threshold, market_name)

st.markdown("## 🔎 RECHERCHE")
st.caption(
    "Ordre appliqué : nouvelle récupération → validation → filtrage par date → lecture du marché 12 → lecture des cotes → comparaison au seuil."
)

current_target_date = resolve_target_date(date_mode, custom_date)
results_to_display = st.session_state.results if st.session_state.last_fetch_status in {STATUS_SUCCESS, STATUS_STALE} else []
display_target_date = current_target_date

if st.session_state.last_fetch_status == STATUS_STALE and st.session_state.last_success_target_date:
    try:
        display_target_date = datetime.strptime(st.session_state.last_success_target_date, "%d/%m/%Y").date()
    except Exception:
        display_target_date = current_target_date

if st.session_state.last_fetch_status == STATUS_STALE and display_target_date != current_target_date:
    st.warning(
        "Les résultats affichés correspondent à la dernière récupération vérifiée et non à la date cible courante. "
        f"Date des données affichées : {display_target_date.strftime('%d/%m/%Y')}"
    )

display_results(results_to_display, display_target_date)

st.markdown("## 📊 MARCHÉ 12")
if results_to_display:
    market_count = sum(1 for row in results_to_display if row.get("market") == DEFAULT_MARKET)
    st.write(f"📊 MARCHÉS 12 DISPONIBLES : {market_count}")
else:
    if st.session_state.last_fetch_status == STATUS_ERROR:
        st.warning("⚠️ Marché 12 indisponible")
    else:
        st.info("ℹ️ Aucun marché 12 valide trouvé pour la date sélectionnée.")

display_status()
display_optional_statistics(results_to_display)

st.markdown("## ⚠️ INFORMATIONS")
st.warning(
    "Cette application fournit uniquement des informations et observations statistiques sur des données football. "
    "Les données peuvent changer et les informations affichées dépendent de la disponibilité et de l'exactitude de la source."
)

st.markdown(
    "<div class='small-note'>"
    "Règles appliquées : aucune donnée inventée, aucune mise, aucune transaction, aucune automatisation de pari. "
    "Si la source est inaccessible, vide, modifiée ou incompatible, l'application affiche explicitement l'erreur au lieu de supposer une donnée."
    "</div>",
    unsafe_allow_html=True,
)
