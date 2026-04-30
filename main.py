import os
import time
import csv
import pickle
import sys
import requests
import garminconnect
from pathlib import Path

# ======================
# CONFIG
# ======================

GARMIN_USERNAME = "Paul.vanderelst@hotmail.com"
GARMIN_PASSWORD = "Polar7500"

BASE_URL = "https://SitePaul.pythonanywhere.com"
DOWNLOAD_URL = f"{BASE_URL}/download/garmin_activities.csv"
UPLOAD_URL = f"{BASE_URL}/upload"

SESSION_FILE = Path("garmin_session.pkl")
LOCK_FILE = "/tmp/garmin_job.lock"

LOCAL_CSV = "garmin_activities.csv"

MAX_LOGIN_ATTEMPTS = 3
PAGE_LIMIT = 20


# ======================
# LOCK
# ======================

def acquire_lock():
    if os.path.exists(LOCK_FILE):
        print("Job already running — exiting.")
        sys.exit(0)
    open(LOCK_FILE, "w").close()


def release_lock():
    if os.path.exists(LOCK_FILE):
        os.remove(LOCK_FILE)


# ======================
# DOWNLOAD EXISTING CSV
# ======================

def download_existing_csv():
    try:
        r = requests.get(DOWNLOAD_URL, timeout=30)

        if r.status_code == 200:
            with open(LOCAL_CSV, "wb") as f:
                f.write(r.content)
            print("Existing CSV downloaded")
        else:
            print("No existing CSV found — starting fresh")

    except Exception as e:
        print(f"Download error: {e}")


def load_existing_activity_ids():
    ids = set()

    if not os.path.exists(LOCAL_CSV):
        return ids

    with open(LOCAL_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ids.add(str(row["Activity ID"]))

    print(f"{len(ids)} existing activities loaded")
    return ids


# ======================
# GARMIN AUTH (SAFE)
# ======================

def get_garmin_client():
    client = garminconnect.Garmin(GARMIN_USERNAME, GARMIN_PASSWORD)

    # reuse session
    if SESSION_FILE.exists():
        try:
            with open(SESSION_FILE, "rb") as f:
                client = pickle.load(f)
            print("Reusing Garmin session")
            return client
        except Exception:
            print("Session invalid — relogin required")

    for attempt in range(MAX_LOGIN_ATTEMPTS):
        try:
            client.login()

            with open(SESSION_FILE, "wb") as f:
                pickle.dump(client, f)

            print("Garmin login successful")
            return client

        except garminconnect.GarminConnectTooManyRequestsError:
            print("🚫 Garmin rate limit (login) — aborting login")
            return None

        except Exception as e:
            print(f"Login error: {e}")
            time.sleep(5)

    print("❌ Garmin login failed after retries")
    return None


# ======================
# FETCH INCREMENTAL DATA
# ======================

def fetch_new_activities(existing_ids):
    client = get_garmin_client()

    if client is None:
        print("Skipping Garmin fetch (no session)")
        return []

    start = 0
    new_activities = []

    while True:
        try:
            activities = client.get_activities(start, PAGE_LIMIT)
        except garminconnect.GarminConnectTooManyRequestsError:
            print("🚫 Rate limit during fetch — stopping early")
            break
        except Exception as e:
            print(f"Fetch error: {e}")
            break

        if not activities:
            break

        for activity in activities:
            aid = str(activity.get("activityId"))

            if aid in existing_ids:
                print("Reached already known activities — stopping")
                return new_activities

            new_activities.append(activity)

        start += PAGE_LIMIT

    print(f"{len(new_activities)} new activities found")
    return new_activities


# ======================
# MERGE CSV
# ======================

def merge_and_save(new_activities):
    rows = []

    if os.path.exists(LOCAL_CSV):
        with open(LOCAL_CSV, newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))

    header = [
        "Activity ID",
        "Activity Name",
        "Start Time",
        "Duration (s)",
        "Distance (m)",
        "Average Speed (m/s)",
        "Calories"
    ]

    if not rows:
        rows.append(header)

    for activity in reversed(new_activities):
        rows.append([
            activity.get("activityId"),
            activity.get("activityName"),
            activity.get("startTimeLocal"),
            activity.get("duration"),
            activity.get("distance"),
            activity.get("averageSpeed"),
            activity.get("calories")
        ])

    with open(LOCAL_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerows(rows)

    print("CSV updated successfully")


# ======================
# UPLOAD
# ======================

def upload_csv():
    try:
        with open(LOCAL_CSV, "rb") as f:
            r = requests.post(UPLOAD_URL, files={"file": f}, timeout=30)

        if r.status_code == 200:
            print("Upload successful")
        else:
            print(f"Upload failed: {r.text}")

    except Exception as e:
        print(f"Upload error: {e}")


# ======================
# MAIN
# ======================

def main():
    acquire_lock()

    try:
        download_existing_csv()
        existing_ids = load_existing_activity_ids()

        new_activities = fetch_new_activities(existing_ids)

        if not new_activities:
            print("No update needed")
            return

        merge_and_save(new_activities)
        upload_csv()

    finally:
        release_lock()


if __name__ == "__main__":
    main()
