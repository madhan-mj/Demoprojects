import os
import re
import joblib
import requests
from PIL import Image
import instaloader

# Try to load ML models (optional)
try:
    svm_model = joblib.load("svm_model.pkl")
    nn_model = joblib.load("nn_model.pkl")
    rf_model = joblib.load("rf_model.pkl")
    MODELS_LOADED = True
except:
    MODELS_LOADED = False

# Demo fake IDs for demonstration.
DEMO_FAKE_IDS = {"fakeprofile1", "spamaccount", "quickmoneyguru"}

def fetch_instagram_profile_data(profile_url):
    """Fetches public Instagram profile data or returns dummy data."""
    m = re.search(r"instagram\.com/([^/?]+)", profile_url)
    if not m:
        return None
    username = m.group(1)

    L = instaloader.Instaloader(sleep=True,
                                download_comments=False,
                                download_videos=False,
                                download_video_thumbnails=False)
    login_user = os.environ.get("INSTALOADER_USERNAME")
    login_pass = os.environ.get("INSTALOADER_PASSWORD")
    if login_user and login_pass:
        try:
            L.login(login_user, login_pass)
        except Exception as e:
            print("Error logging in:", e)
    try:
        profile = instaloader.Profile.from_username(L.context, username)
        return {
            "username": profile.username,
            "fullname": profile.full_name,
            "bio": profile.biography,
            "profile_pic_url": profile.profile_pic_url,
        }
    except Exception as e:
        print("Error fetching profile:", e)
        # fallback dummy data
        return {
            "username": username,
            "fullname": "Demo Public Account",
            "bio": "Cannot fetch real data; using fallback.",
            "profile_pic_url": "https://via.placeholder.com/150?text=Demo"
        }

def extract_features(profile_data, image_path):
    username = profile_data.get("username", "")
    fullname = profile_data.get("fullname", "")
    bio = profile_data.get("bio", "")
    username_length = len(username)
    fullname_length = len(fullname)
    email_suspicious = 0
    bio_length = len(bio)
    try:
        with Image.open(image_path) as img:
            image_width, image_height = img.size
    except:
        image_width, image_height = 0, 0
    return [username_length, fullname_length, email_suspicious, bio_length, image_width, image_height]

def predict_profile(profile_data, image_path):
    """Uses ML models (if loaded) or dummy logic to produce a detection result."""
    if MODELS_LOADED:
        features = extract_features(profile_data, image_path)
        svm_prob = svm_model.predict_proba([features])[0][1]
        nn_prob = nn_model.predict_proba([features])[0][1]
        rf_prob = rf_model.predict_proba([features])[0][1]
        raw_avg = (svm_prob + nn_prob + rf_prob) / 3.0
        multiplier = 1.2
        adjusted_score = min(raw_avg * multiplier, 1.0)
        verdict = "Fake" if adjusted_score >= 0.5 else "Legit"
        explanation = (
            f"SVM: {svm_prob:.2f}, NN: {nn_prob:.2f}, RF: {rf_prob:.2f}. "
            f"Average: {raw_avg:.2f}, final score: {adjusted_score:.2f}."
        )
        return {
            "score": round(adjusted_score, 2),
            "verdict": verdict,
            "reason": explanation,
        }
    else:
        # dummy logic if no models:
        return {
            "score": 0.3,
            "verdict": "Legit",
            "reason": "No ML models loaded; defaulting to 'Legit'."
        }
