import os
import csv
import json
from pathlib import Path
from datetime import date, timedelta
from garminconnect import Garmin

EMAIL    = os.environ["GARMIN_EMAIL"]
PASSWORD = os.environ["GARMIN_PASSWORD"]

OUTPUT = Path("data/activities.csv")
OUTPUT.parent.mkdir(parents=True, exist_ok=True)

# Colonnes à conserver dans le CSV
FIELDS = [
    "activityId", "activityName", "activityType",
    "startTimeLocal", "distance", "duration",
    "averageHR", "maxHR", "calories",
    "averageSpeed", "maxSpeed", "elevationGain",
]

def fetch_new_activities(client: Garmin, existing_ids: set) -> list[dict]:
    """Récupère les activités des 30 derniers jours non encore enregistrées."""
    start = date.today() - timedelta(days=30)
    activities = client.get_activities_by_date(start.isoformat(), date.today().isoformat())
    new = []
    for act in activities:
        aid = str(act.get("activityId", ""))
        if aid and aid not in existing_ids:
            row = {f: act.get(f, "") for f in FIELDS}
            # Normalise le type d'activité (dict → string)
            if isinstance(row["activityType"], dict):
                row["activityType"] = row["activityType"].get("typeKey", "")
            new.append(row)
    return new

def load_existing(path: Path) -> tuple[list[dict], set]:
    if not path.exists():
        return [], set()
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    ids = {r["activityId"] for r in rows}
    return rows, ids

def save_csv(path: Path, rows: list[dict]):
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

def main():
    client = Garmin(EMAIL, PASSWORD)
    client.login()

    existing_rows, existing_ids = load_existing(OUTPUT)
    new_rows = fetch_new_activities(client, existing_ids)

    if new_rows:
        print(f"✅ {len(new_rows)} nouvelle(s) activité(s) trouvée(s)")
        all_rows = existing_rows + new_rows
        # Tri par date décroissante
        all_rows.sort(key=lambda r: r.get("startTimeLocal", ""), reverse=True)
        save_csv(OUTPUT, all_rows)
    else:
        print("ℹ️  Aucune nouvelle activité.")

if __name__ == "__main__":
    main()
