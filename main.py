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

PYTHONANYWHERE_UPLOAD_URL = "https://SitePaul.pythonanywhere.com/upload"

SESSION_FILE = Path("garmin_session.pkl")
LOCK_FILE = "/tmp/garmin_job.lock"


# ======================
# LOCK (CRON SAFETY)
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
# GARMIN AUTH (SAFE)
# ======================

def get_garmin_client():
    client = garminconnect.Garmin(GARMIN_USERNAME, GARMIN_PASSWORD)

    # Try reuse session
    if SESSION_FILE.exists():
        try:
            with open(SESSION_FILE, "rb") as f:
                client = pickle.load(f)
            print("Reusing saved Garmin session")
            return client
        except Exception:
            print("Saved session invalid — re-authenticating")

    # Fresh login with exponential backoff
    for attempt in range(5):
        try:
            client.login()

            with open(SESSION_FILE, "wb") as f:
                pickle.dump(client, f)

            print("Login successful (session cached)")
            return client

        except garminconnect.GarminConnectTooManyRequestsError:
            wait = 60 * (2 ** attempt)
            print(f"Rate limited by Garmin — retrying in {wait}s")
            time.sleep(wait)

        except Exception as e:
            print(f"Login error: {e}")
            time.sleep(5)

    raise Exception("Failed to authenticate after multiple attempts")


# ======================
# EXPORT ACTIVITIES
# ======================

def export_garmin_activities():
    try:
        client = get_garmin_client()

        # keep range moderate to reduce load
        activities = client.get_activities(0, 200)

        output_file = "garmin_activities.csv"

        with open(output_file, "w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)

            writer.writerow([
                "Activity ID",
                "Activity Name",
                "Start Time",
                "Duration (s)",
                "Distance (m)",
                "Average Speed (m/s)",
                "Calories"
            ])

            for activity in activities:
                writer.writerow([
                    activity.get("activityId"),
                    activity.get("activityName"),
                    activity.get("startTimeLocal"),
                    activity.get("duration"),
                    activity.get("distance"),
                    activity.get("averageSpeed"),
                    activity.get("calories")
                ])

        print(f"Export complete: {len(activities)} activities")

        upload_to_pythonanywhere(output_file)

    except Exception as e:
        print(f"Export failed: {e}")


# ======================
# UPLOAD
# ======================

def upload_to_pythonanywhere(file_path):
    try:
        with open(file_path, "rb") as file:
            response = requests.post(
                PYTHONANYWHERE_UPLOAD_URL,
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

if __name__ == "__main__":
    acquire_lock()
    try:
        export_garmin_activities()
    finally:
        release_lock()
