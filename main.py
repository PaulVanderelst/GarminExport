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

GARMIN_USERNAME = "paul.vanderelst@hotmail.com"
GARMIN_PASSWORD = "Polar7500"

BASE_URL = "https://SitePaul.pythonanywhere.com"
DOWNLOAD_URL = f"{BASE_URL}/download/garmin_activities.csv"
UPLOAD_URL = f"{BASE_URL}/upload"

SESSION_FILE = Path("garmin_session.pkl")
LOCK_FILE = "/tmp/garmin_job.lock"
LOCAL_CSV = "garmin_activities.csv"


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
        response = requests.get(DOWNLOAD_URL, timeout=30)

        if response.status_code == 200:
            with open(LOCAL_CSV, "wb") as f:
                f.write(response.content)
            print("Existing CSV downloaded")
        else:
            print("No existing CSV found, starting fresh")

    except Exception as e:
        print(f"Download failed: {e}")


def load_existing_activity_ids():
    ids = set()

    if not os.path.exists(LOCAL_CSV):
        return ids

    with open(LOCAL_CSV, newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        for row in reader:
            ids.add(row["Activity ID"])

    print(f"{len(ids)} existing activities loaded")
    return ids


# ======================
# GARMIN AUTH
# ======================

def get_garmin_client():
    client = garminconnect.Garmin(GARMIN_USERNAME, GARMIN_PASSWORD)

    if SESSION_FILE.exists():
        try:
            with open(SESSION_FILE, "rb") as f:
                client = pickle.load(f)
            print("Reusing saved session")
            return client
        except Exception:
            print("Session invalid")

    for attempt in range(5):
        try:
            client.login()

            with open(SESSION_FILE, "wb") as f:
                pickle.dump(client, f)

            print("Login successful")
            return client

        except garminconnect.GarminConnectTooManyRequestsError:
            wait = 60 * (2 ** attempt)
            print(f"Rate limited, retry in {wait}s")
            time.sleep(wait)

        except Exception as e:
            print(e)
            time.sleep(5)

    raise Exception("Garmin login failed")


# ======================
# FETCH NEW ACTIVITIES
# ======================

def fetch_new_activities(existing_ids):
    client = get_garmin_client()

    start = 0
    limit = 20
    new_activities = []
    stop = False

    while not stop:
        activities = client.get_activities(start, limit)

        if not activities:
            break

        for activity in activities:
            activity_id = str(activity.get("activityId"))

            if activity_id in existing_ids:
                stop = True
                break

            new_activities.append(activity)

        start += limit

    print(f"{len(new_activities)} new activities found")
    return new_activities


# ======================
# MERGE + SAVE CSV
# ======================

def merge_and_save(new_activities):
    rows = []

    # Load existing data
    if os.path.exists(LOCAL_CSV):
        with open(LOCAL_CSV, newline="", encoding="utf-8") as file:
            reader = csv.reader(file)
            rows = list(reader)

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

    # Append new activities (chronological order)
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

    with open(LOCAL_CSV, "w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerows(rows)

    print("CSV updated")


# ======================
# UPLOAD
# ======================

def upload_csv():
    try:
        with open(LOCAL_CSV, "rb") as file:
            response = requests.post(
                UPLOAD_URL,
                files={"file": file},
                timeout=30
            )

        if response.status_code == 200:
            print("Upload successful")
        else:
            print(f"Upload failed: {response.text}")

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
            print("Nothing to update")
            return

        merge_and_save(new_activities)
        upload_csv()

    finally:
        release_lock()


if __name__ == "__main__":
    main()
