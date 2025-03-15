import os
import json
import csv
import io
from flask import Flask, render_template, request, redirect, url_for, flash, Response, session
from werkzeug.utils import secure_filename
import requests
from detector import fetch_instagram_profile_data, predict_profile, DEMO_FAKE_IDS

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "mysecretkey")

UPLOAD_FOLDER = os.path.join("static", "uploads")
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

results_db = []  # for detection history
    # return Response(
    #     output,
    #     mimetype="text/csv",
    #     headers={"Content-Disposition": "attachment;filename=report.csv"}
    # )

def save_users(users):
    with open("users.json", "w") as f:
        json.dump(users, f)

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form["email"].strip()
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]
        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return redirect(url_for("register"))
        users = load_users()
        if email in users:
            flash("Email already registered. Please log in.", "danger")
            return redirect(url_for("login"))
        users[email] = {"password": password}
        save_users(users)
        flash("Registration successful. Please log in.", "success")
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip()
        password = request.form["password"]
        users = load_users()
        if email in users and users[email]["password"] == password:
            session["user"] = email
            flash("Login successful.", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid email or password.", "danger")
            return redirect(url_for("login"))
    return render_template("login.html")

@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        flash("Please log in first.", "danger")
        return redirect(url_for("login"))
    return render_template("dashboard.html", email=session["user"])

@app.route("/logout")
def logout():
    session.pop("user", None)
    flash("Logged out successfully.", "success")
    return redirect(url_for("login"))

@app.route("/")
def index():
    if "user" not in session:
        return redirect(url_for("login"))
    return render_template("index.html")

@app.route("/submit_profile", methods=["POST"])
def submit_profile():
    if "user" not in session:
        flash("Please log in first.", "danger")
        return redirect(url_for("login"))
    
    profile_url = request.form.get("profile_url", "").strip()
    if not profile_url:
        flash("Please enter a profile URL.", "danger")
        return redirect(url_for("index"))
    
    # 1. Fetch data
    profile_data = fetch_instagram_profile_data(profile_url)
    if profile_data is None:
        flash("Could not parse username. Ensure URL is correct.", "danger")
        return redirect(url_for("index"))
    
    username = profile_data.get("username", "")
    profile_pic_url = profile_data.get("profile_pic_url")
    if not profile_pic_url:
        flash("Could not find profile picture.", "danger")
        return redirect(url_for("index"))
    
    filename = secure_filename(username + ".jpg")
    image_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    try:
        resp = requests.get(profile_pic_url, timeout=10)
        if resp.status_code == 200:
            with open(image_path, "wb") as f:
                f.write(resp.content)
        else:
            raise Exception(f"Status code {resp.status_code}")
    except Exception as e:
        flash(f"Error downloading profile picture: {str(e)}", "danger")
        return redirect(url_for("index"))
    
    form_data = {
        "username": username,
        "fullname": profile_data.get("fullname", ""),
        "bio": profile_data.get("bio", ""),
        "profile_url": profile_url
    }

    # 2. If it's a demo fake ID, skip ML, store in results, render fake_result:
    if username.lower() in DEMO_FAKE_IDS:
        explanation = "This is a demo fake account. Exhibits characteristics of a fake profile."
        suspicion_score = 100  # Always 100% for demo fake
        verdict = "Fake"
        
        # Record in results_db for reporting
        results_db.append({
            "username": username,
            "fullname": form_data["fullname"],
            "suspicion_score": suspicion_score,
            "verdict": verdict,
            "explanation": explanation
        })
        
        return render_template("fake_result.html",
                               profile_url=profile_url,
                               image_url="https://via.placeholder.com/150?text=Fake",
                               suspicion_score=suspicion_score,
                               verdict=verdict,
                               explanation=explanation,
                               form_data=form_data)
    
    # 3. Otherwise do normal ML detection:
    ml_result = predict_profile(form_data, image_path)
    percentage = ml_result["score"] * 100
    
    results_db.append({
        "username": username,
        "fullname": form_data["fullname"],
        "suspicion_score": percentage,
        "verdict": ml_result["verdict"],
        "explanation": ml_result["reason"]
    })
    
    return render_template(
        "result.html",
        profile_url=profile_url,
        image_url=url_for("static", filename="uploads/" + filename),
        suspicion_score=percentage,
        verdict=ml_result["verdict"],
        explanation=ml_result["reason"],
        form_data=form_data
    )

@app.route("/report")
def report():
    if "user" not in session:
        flash("Please log in first.", "danger")
        return redirect(url_for("login"))
    try:
        with open("model_accuracies.json", "r") as f:
            accuracies = json.load(f)
    except:
        accuracies = {}
    return render_template("report.html", profiles=results_db, accuracies=accuracies)

@app.route("/delete/<int:index>")
def delete_report(index):
    if "user" not in session:
        flash("Please log in first.", "danger")
        return redirect(url_for("login"))
    try:
        results_db.pop(index)
        flash("Report entry deleted successfully.", "success")
    except:
        flash("Invalid report index.", "danger")
    return redirect(url_for("report"))

@app.route("/download_report")
def download_report():
    if "user" not in session:
        flash("Please log in first.", "danger")
        return redirect(url_for("login"))
    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(["Username", "Full Name", "Suspicion Score (%)", "Verdict", "Explanation"])
    for entry in results_db:
        cw.writerow([
            entry["username"],
            entry["fullname"],
            entry["suspicion_score"],
            entry["verdict"],
            entry["explanation"]
        ])
    output = si.getvalue()
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=report.csv"}
    )

if __name__ == "__main__":
    app.run(debug=True)
