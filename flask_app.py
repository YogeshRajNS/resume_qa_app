from flask import Flask, render_template, request, redirect, url_for, flash
import requests

app = Flask(__name__)
app.secret_key = "supersecretkey"

FASTAPI_URL = "http://127.0.0.1:8000" 


@app.route("/", methods=["GET", "POST"])
def index():
    resumes = []
    answer = None

    
    try:
        res = requests.get(f"{FASTAPI_URL}/list_resumes")
        if res.status_code == 200:
            resumes = res.json().get("resumes", [])
    except Exception as e:
        flash(f"Error connecting to FastAPI: {e}", "danger")

    
    if request.method == "POST":
        query = request.form.get("query")
        selected_resumes = request.form.getlist("selected_resumes")

        if query and selected_resumes:
            payload = {"resumes": selected_resumes, "query": query}
            res = requests.post(f"{FASTAPI_URL}/query", json=payload)
            if res.status_code == 200:
                print(res.json())
                answer = res.json()
            else:
                flash("Error querying resumes", "danger")

    return render_template("index.html", resumes=resumes, answer=answer)



@app.route("/upload", methods=["POST"])
def upload_resume():
    file = request.files.get("file")
    if not file:
        flash("No file selected", "danger")
        return redirect(url_for("index"))

    files = {"file": (file.filename, file.stream, file.mimetype)}
    res = requests.post(f"{FASTAPI_URL}/upload_file", files=files)
    if res.status_code == 200:
        flash(res.json().get("message"), "success")
    else:
        flash("Upload failed", "danger")

    return redirect(url_for("index"))



@app.route("/delete", methods=["POST"])
def delete_resume():
    selected_resumes = request.form.getlist("selected_resumes")
    if not selected_resumes:
        flash("No resumes selected for deletion", "warning")
        return redirect(url_for("index"))

    payload = {"resumes": selected_resumes}
    res = requests.delete(f"{FASTAPI_URL}/delete_resumes", json=payload)
    if res.status_code == 200:
        flash(f"Deleted: {', '.join(selected_resumes)}", "success")
    else:
        flash("Delete failed", "danger")

    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(port=5000, debug=True)
