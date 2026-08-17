import os
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd
import requests
import streamlit as st

try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None


APP_TITLE = "⚽ FOOTBALL MARKET MONITOR"
APP_SUBTITLE = "Surveillance pré-match des marchés football"
API_BASE = "https://api.the-odds-api.com/v4"
DEFAULT_THRESHOLD = 1.55
DEFAULT_REGION = "eu"
REQUEST_TIMEOUT = 20
MAX_EVENTS_PER_REFRESH = 20

st.set_page_config(
    page_title=APP_TITLE,
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    .stApp { background: linear-gradient(180deg,#020617 0%,#0f172a 100%); }
    .block-container { max-width: 1200px; padding-top: 1rem; }
    .hero {
        background: linear-gradient(135deg,rgba(34,197,94,.16),rgba(56,189,248,.10));
        border:1px solid rgba(148,163,184,.22); border-radius:20px;
        padding:1.2rem 1rem; margin-bottom:1rem;
    }
    .hero p { color:#94a3b8; margin:.2rem 0 0; }
    .note { color:#94a3b8; line-height:1.5; }
    </style>
    """,
    unsafe_allow_html=True,
)


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split()).strip()


def safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(str(value).replace(",", "."))
    except Exception:
        return None


def parse_api_key() -> str:
    # Priority: Streamlit Secrets, then environment variable.
    try:
        key = st.secrets.get("THE_ODDS_API_KEY", "")
    except Exception:
        key = ""
    return normalize_text(key) or normalize_text(os.getenv("THE_ODDS_API_KEY", ""))


def api_get(path: str, api_key: str, params: Optional[Dict[str, Any]] = None) -> requests.Response:
    query = dict(params or {})
    query["apiKey"] = api_key
    return requests.get(
        f"{API_BASE}{path}",
        params=query,
        timeout=REQUEST_TIMEOUT,
        headers={"Accept": "application/json", "User-Agent": "FootballMarketMonitor/2.0"},
    )


@st.cache_data(ttl=300, show_spinner=False)
def get_soccer_sports(api_key: str) -> List[Dict[str, Any]]:
    response = api_get("/sports/", api_key, {"all": "false"})
    response.raise_for_status()
    data = response.json()
    sports = []
    for item in data:
        group = normalize_text(item.get("group")).lower()
        key = normalize_text(item.get("key"))
        if "soccer" in group and key:
            sports.append(
                {
                    "key": key,
                    "title": normalize_text(item.get("title")) or key,
                    "group": normalize_text(item.get("group")),
                }
            )
    return sports


def get_events(api_key: str, sport_key: str) -> List[Dict[str, Any]]:
    response = api_get(f"/sports/{sport_key}/events/", api_key, {"dateFormat": "iso"})
    response.raise_for_status()
    data = response.json()
    return data if isinstance(data, list) else []


def event_date(value: Any, timezone_name: str = "UTC") -> Optional[date]:
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if timezone_name != "UTC" and ZoneInfo is not None:
            dt = dt.astimezone(ZoneInfo(timezone_name))
        return dt.date()
    except Exception:
        return None


def get_event_double_chance(
    api_key: str,
    sport_key: str,
    event_id: str,
    region: str,
) -> Dict[str, Any]:
    response = api_get(
        f"/sports/{sport_key}/events/{event_id}/odds",
        api_key,
        {
            "regions": region,
            "markets": "double_chance",
            "dateFormat": "iso",
            "oddsFormat": "decimal",
        },
    )
    response.raise_for_status()
    data = response.json()
    return data if isinstance(data, dict) else {}


def find_12_outcomes(event_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    found: List[Dict[str, Any]] = []

    for bookmaker in event_data.get("bookmakers", []) or []:
        bookmaker_name = normalize_text(bookmaker.get("title")) or normalize_text(bookmaker.get("key"))
        for market in bookmaker.get("markets", []) or []:
            if normalize_text(market.get("key")).lower() != "double_chance":
                continue

            for outcome in market.get("outcomes", []) or []:
                name = normalize_text(outcome.get("name"))
                compact = name.lower().replace(" ", "").replace("-", "")
                # Accept common representations of Double Chance 12.
                if compact in {"12", "1or2", "1ou2", "homeoraway", "homeaway"}:
                    price = safe_float(outcome.get("price"))
                    if price is not None:
                        found.append(
                            {
                                "bookmaker": bookmaker_name,
                                "odds": price,
                                "market": "Double chance 12",
                                "last_update": market.get("last_update") or bookmaker.get("last_update"),
                            }
                        )

    return found


def analyze(
    api_key: str,
    sport_key: str,
    target_date: date,
    threshold: float,
    region: str,
    timezone_name: str,
) -> Dict[str, Any]:
    events = get_events(api_key, sport_key)

    dated_events = []
    for event in events:
        d = event_date(event.get("commence_time"), timezone_name)
        if d == target_date:
            dated_events.append(event)

    rows: List[Dict[str, Any]] = []
    checked = 0

    for event in dated_events[:MAX_EVENTS_PER_REFRESH]:
        checked += 1
        try:
            details = get_event_double_chance(api_key, sport_key, event["id"], region)
            outcomes = find_12_outcomes(details)

            best = None
            for item in outcomes:
                if best is None or item["odds"] > best["odds"]:
                    best = item

            rows.append(
                {
                    "Date": event_date(event.get("commence_time"), timezone_name),
                    "Heure": str(event.get("commence_time", ""))[11:16],
                    "Match": f"{normalize_text(event.get('home_team'))} — {normalize_text(event.get('away_team'))}",
                    "Marché": "Double chance 12",
                    "Cote 12": best["odds"] if best else None,
                    "Bookmaker": best["bookmaker"] if best else "❌ Donnée indisponible",
                    "Seuil atteint": "✅ Oui" if best and best["odds"] >= threshold else "❌ Non",
                }
            )
        except requests.HTTPError as exc:
            rows.append(
                {
                    "Date": event_date(event.get("commence_time"), timezone_name),
                    "Heure": str(event.get("commence_time", ""))[11:16],
                    "Match": f"{normalize_text(event.get('home_team'))} — {normalize_text(event.get('away_team'))}",
                    "Marché": "Double chance 12",
                    "Cote 12": None,
                    "Bookmaker": f"Erreur API: {exc.response.status_code if exc.response is not None else 'HTTP'}",
                    "Seuil atteint": "❌ Indisponible",
                }
            )

    df = pd.DataFrame(rows)
    if not df.empty:
        df["Cote 12"] = pd.to_numeric(df["Cote 12"], errors="coerce")
        df = df.sort_values(["Seuil atteint", "Cote 12"], ascending=[False, False], na_position="last")

    return {
        "events_found": len(dated_events),
        "events_checked": checked,
        "rows": rows,
        "dataframe": df,
    }


def main() -> None:
    st.markdown(
        f"""
        <div class="hero">
            <h1>{APP_TITLE}</h1>
            <p>{APP_SUBTITLE}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.info(
        "Cette version utilise une API d'odds autorisée au lieu de récupérer directement "
        "winner.bet. Elle n'essaie pas de contourner un blocage HTTP 403."
    )

    api_key = parse_api_key()

    with st.container():
        st.subheader("🔐 Source de données")
        if not api_key:
            st.warning(
                "Aucune clé API détectée. Ajoute THE_ODDS_API_KEY dans "
                "Streamlit → Settings → Secrets avant de lancer une recherche."
            )
            st.markdown(
                "La clé n'est pas demandée dans le code et ne doit pas être publiée sur GitHub."
            )
            st.stop()

        try:
            sports = get_soccer_sports(api_key)
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "HTTP"
            st.error(f"Impossible d'accéder à l'API (HTTP {status}). Vérifie ta clé API.")
            st.stop()
        except Exception as exc:
            st.error(f"Erreur lors du chargement des compétitions : {exc}")
            st.stop()

        if not sports:
            st.error("Aucune compétition de football disponible pour cette clé API.")
            st.stop()

        sport_labels = {f"{s['title']} — {s['key']}": s["key"] for s in sports}
        selected_label = st.selectbox("Compétition / sport", list(sport_labels.keys()))
        sport_key = sport_labels[selected_label]

        col1, col2, col3 = st.columns(3)
        with col1:
            target_date = st.date_input("📅 Date cible", value=date.today())
        with col2:
            threshold = st.number_input(
                "🎯 Cote minimale",
                min_value=1.01,
                max_value=100.0,
                value=DEFAULT_THRESHOLD,
                step=0.01,
            )
        with col3:
            region = st.selectbox(
                "🌍 Région des bookmakers",
                ["eu", "uk", "au", "us", "us2"],
                index=0,
            )

        timezone_name = st.selectbox(
            "🕐 Fuseau horaire pour la date",
            ["UTC", "Africa/Kinshasa", "Africa/Lubumbashi", "Europe/Paris"],
            index=1,
        )

        st.caption(
            f"Le marché surveillé est **Double chance 12**. "
            f"Maximum {MAX_EVENTS_PER_REFRESH} matchs vérifiés par actualisation."
        )

        if st.button("🔎 Rechercher les matchs", type="primary", use_container_width=True):
            with st.spinner("Récupération des matchs et des cotes…"):
                try:
                    result = analyze(
                        api_key=api_key,
                        sport_key=sport_key,
                        target_date=target_date,
                        threshold=threshold,
                        region=region,
                        timezone_name=timezone_name,
                    )
                    st.session_state["result"] = result
                    st.session_state["last_run"] = datetime.now(timezone.utc)
                except requests.HTTPError as exc:
                    status = exc.response.status_code if exc.response is not None else "HTTP"
                    st.error(f"Erreur API HTTP {status}. Vérifie la clé, la compétition et les marchés disponibles.")
                    st.stop()
                except Exception as exc:
                    st.error(f"Erreur : {exc}")
                    st.stop()

    result = st.session_state.get("result")
    if not result:
        st.markdown(
            '<p class="note">Choisis une compétition et une date, puis appuie sur '
            '<b>Rechercher les matchs</b>.</p>',
            unsafe_allow_html=True,
        )
        return

    df = result["dataframe"]

    st.subheader("📊 Statistiques")
    c1, c2, c3 = st.columns(3)
    c1.metric("Matchs trouvés", result["events_found"])
    c2.metric("Matchs vérifiés", result["events_checked"])
    c3.metric(
        "Atteignant le seuil",
        int((df["Seuil atteint"] == "✅ Oui").sum()) if not df.empty else 0,
    )

    if df.empty:
        st.warning(
            "Aucune donnée Double chance 12 n'a été récupérée pour cette date. "
            "Cela peut signifier que le marché n'est pas disponible pour les bookmakers "
            "sélectionnés ou que la compétition ne fournit pas ce marché."
        )
        return

    st.subheader("⚽ Tous les matchs")
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.subheader(f"🎯 Matchs avec cote ≥ {threshold:.2f}")
    qualified = df[df["Cote 12"].notna() & (df["Cote 12"] >= threshold)].copy()

    if qualified.empty:
        st.info("Aucun match récupéré n'atteint le seuil configuré.")
    else:
        st.dataframe(qualified, use_container_width=True, hide_index=True)

    st.caption(
        "⚠️ Les cotes sont des informations de marché et peuvent changer. "
        "Une cote ou une sélection ne garantit jamais un gain."
    )


if __name__ == "__main__":
    main()
