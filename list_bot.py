#!/usr/bin/env python3
"""Publie les listes chronologiques à partir des fichiers produits par les deux bots."""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

import requests

STATE_FILE = Path("list_bot_state.json")
TIMEOUT_SECONDS = 30

SOURCES = [
    {
        "key": "montpellier",
        "label": "Montpellier — rayon de 200 km",
        "url": (
            "https://raw.githubusercontent.com/allancatoire3-boop/"
            "beach-tennis-discord-bot/main/current_tournaments.json"
        ),
        "webhook_env": "DISCORD_WEBHOOK_MONTPELLIER_URL",
    },
    {
        "key": "france",
        "label": "France métropolitaine et Corse",
        "url": (
            "https://raw.githubusercontent.com/allancatoire3-boop/"
            "beach-tennis-france-discord-bot/main/current_tournaments_france.json"
        ),
        "webhook_env": "DISCORD_WEBHOOK_FRANCE_URL",
    },
]


class BotError(RuntimeError):
    pass


def tournament_id(card: dict[str, Any]) -> str:
    value = card.get("idHomologation")
    if value:
        return str(value)
    return "|".join(str(card.get(key, "")) for key in (
        "libelleTournoi", "dateDebut", "dateFin", "ville", "club"
    ))


def first_text(value: Any, default: str = "Non précisé") -> str:
    if value is None or value == "":
        return default
    if isinstance(value, dict):
        for key in ("libelle", "nom", "name", "ville"):
            if value.get(key):
                return str(value[key])
        return default
    if isinstance(value, list):
        values = [first_text(item, "") for item in value]
        return ", ".join(item for item in values if item) or default
    return str(value)


def parse_date(raw: Any) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw)[:10])
    except ValueError:
        return None


def french_date(raw: Any) -> str:
    value = parse_date(raw)
    if value is None:
        return "Date non précisée"
    months = (
        "janvier", "février", "mars", "avril", "mai", "juin",
        "juillet", "août", "septembre", "octobre", "novembre", "décembre",
    )
    return f"{value.day} {months[value.month - 1]} {value.year}"


def is_upcoming(card: dict[str, Any]) -> bool:
    # Un tournoi reste affiché jusqu'à sa date de fin incluse.
    end = parse_date(card.get("dateFin")) or parse_date(card.get("dateDebut"))
    return end is not None and end >= date.today()


def fetch_cards(url: str) -> list[dict[str, Any]]:
    # Le paramètre évite de recevoir une ancienne copie mise en cache.
    response = requests.get(
        url,
        params={"t": int(time.time())},
        headers={"User-Agent": "BeachTennisListsNotifier/1.0"},
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, list):
        raise BotError(f"Format inattendu à l'adresse {url}")
    return [card for card in data if isinstance(card, dict)]


def load_state() -> dict[str, Any]:
    if not STATE_FILE.exists():
        return {"sources": {}}
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise BotError(f"Impossible de lire {STATE_FILE}: {exc}") from exc
    return data if isinstance(data, dict) else {"sources": {}}


def save_state(state: dict[str, Any]) -> None:
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def tournament_line(index: int, card: dict[str, Any]) -> str:
    start = french_date(card.get("dateDebut"))
    end_value = parse_date(card.get("dateFin"))
    start_value = parse_date(card.get("dateDebut"))
    if end_value and start_value and end_value != start_value:
        dates = f"{start} → {french_date(card.get('dateFin'))}"
    else:
        dates = start

    title = first_text(card.get("libelleTournoi"), "Tournoi de Beach Tennis")
    city = first_text(card.get("ville"))
    return f"**{index}. {dates}**\n{title} — {city}"


def make_chunks(cards: list[dict[str, Any]], label: str) -> list[str]:
    header = (
        f"📅 **Liste actualisée des tournois — {label}**\n"
        f"_Mise à jour du {french_date(date.today().isoformat())}_\n\n"
    )
    lines = [tournament_line(index, card) for index, card in enumerate(cards, 1)]

    if not lines:
        return [header + "Aucun tournoi à venir actuellement."]

    chunks: list[str] = []
    current = header
    for line in lines:
        addition = line + "\n\n"
        if len(current) + len(addition) > 1900:
            chunks.append(current.rstrip())
            current = f"📅 **Suite — {label}**\n\n" + addition
        else:
            current += addition
    chunks.append(current.rstrip())
    return chunks


def post_list(webhook_url: str, label: str, cards: list[dict[str, Any]]) -> None:
    for content in make_chunks(cards, label):
        response = requests.post(
            webhook_url,
            json={
                "username": "Listes Beach Tennis",
                "content": content,
                "allowed_mentions": {"parse": []},
            },
            timeout=TIMEOUT_SECONDS,
        )
        if response.status_code == 429:
            retry_after = float(response.json().get("retry_after", 1))
            time.sleep(min(retry_after, 30))
            response = requests.post(
                webhook_url,
                json={
                    "username": "Listes Beach Tennis",
                    "content": content,
                    "allowed_mentions": {"parse": []},
                },
                timeout=TIMEOUT_SECONDS,
            )
        response.raise_for_status()
        time.sleep(1)


def main() -> int:
    state = load_state()
    source_states = state.setdefault("sources", {})
    errors: list[str] = []

    for source in SOURCES:
        key = source["key"]
        try:
            cards = fetch_cards(source["url"])
            if not cards:
                print(f"{key}: fichier vide, vérification reportée.")
                continue

            upcoming = [card for card in cards if is_upcoming(card)]
            upcoming.sort(key=lambda card: str(card.get("dateDebut", "")))
            current_ids = {tournament_id(card) for card in cards}

            saved = source_states.setdefault(
                key, {"initialized": False, "ids": []}
            )
            seen = {str(item) for item in saved.get("ids", [])}

            if not saved.get("initialized", False):
                saved["initialized"] = True
                saved["ids"] = sorted(current_ids)
                print(
                    f"{key}: initialisation avec {len(current_ids)} tournoi(s), "
                    "aucune liste publiée."
                )
                continue

            new_ids = current_ids - seen
            if new_ids:
                webhook_url = os.getenv(source["webhook_env"], "").strip()
                if not webhook_url:
                    raise BotError(
                        f"Secret {source['webhook_env']} absent dans GitHub Actions."
                    )
                post_list(webhook_url, source["label"], upcoming)
                print(
                    f"{key}: {len(new_ids)} nouveau(x) tournoi(s), "
                    f"liste de {len(upcoming)} tournoi(s) publiée."
                )
            else:
                print(f"{key}: aucun nouveau tournoi, aucune publication.")

            saved["ids"] = sorted(seen | current_ids)
        except (requests.RequestException, BotError) as exc:
            errors.append(f"{key}: {exc}")

    save_state(state)
    if errors:
        raise BotError("; ".join(errors))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BotError as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        sys.exit(1)
