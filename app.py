import os, csv, io, json, secrets, string



from functools import wraps



from datetime import datetime, timezone



from urllib.parse import quote







import requests



import psycopg



from psycopg.rows import dict_row



from flask import Flask, render_template, request, redirect, url_for, session, flash, abort, make_response



from dotenv import load_dotenv







load_dotenv()



app = Flask(__name__)



app.secret_key = os.environ.get("FLASK_SECRET_KEY", "change-this-before-deployment-" + secrets.token_hex(16))



SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")



SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")



DATABASE_URL = os.environ.get("DATABASE_URL", "")



ADMIN_EMAILS = {e.strip().lower() for e in os.environ.get("ADMIN_EMAILS", "").split(",") if e.strip()}



app.config["ADMIN_EMAILS"] = ADMIN_EMAILS







def db():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not configured.")

    try:
        conn = psycopg.connect(
            DATABASE_URL,
            row_factory=dict_row,
            connect_timeout=20
        )
        app.logger.info("PostgreSQL connection successful")
        return conn
    except psycopg.OperationalError:
        app.logger.exception("PostgreSQL connection failed")
        raise






def log_event(event_type, email=None, creator_id=None, test_id=None, details=None):



          try:



                    with db() as conn:



                              conn.execute("""INSERT INTO platform_events(event_type,email,creator_id,test_id,details)



                                                                      VALUES (%s,%s,%s,%s,%s)""",



                                                                (event_type, email, creator_id, test_id, json.dumps(details or {})))



          except Exception:



                    app.logger.exception("Could not write platform event")







def creator_required(fn):



          @wraps(fn)



          def wrapper(*args, **kwargs):



                    if not session.get("creator_id"):



                              return redirect(url_for("login", next=request.path))



                    return fn(*args, **kwargs)



          return wrapper







def admin_required(fn):



          @wraps(fn)



          def wrapper(*args, **kwargs):



                    if not session.get("creator_id"):



                              return redirect(url_for("login"))



                    if (session.get("email") or "").lower() not in ADMIN_EMAILS:



                              abort(403)



                    return fn(*args, **kwargs)



          return wrapper







def owned_test(test_id, creator_id=None):



          creator_id = creator_id or session.get("creator_id")



          with db() as conn:



                    row = conn.execute("SELECT * FROM tests WHERE id=%s AND creator_id=%s", (test_id, creator_id)).fetchone()



          if not row:



                    abort(404)



          return row







def make_code(n=9):



          alphabet = string.ascii_uppercase + string.digits



          return ''.join(secrets.choice(alphabet) for _ in range(n))







@app.route("/")



def index():



          return render_template("index.html")







@app.route("/signin", methods=["GET"])
def signin():
    return render_template("signin.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()

        if not email or "@" not in email:
            flash("Enter a valid email address.", "error")
            return render_template("signup.html")

        if not SUPABASE_URL or not SUPABASE_ANON_KEY:
            flash("Supabase Auth is not configured. Check your .env file.", "error")
            return render_template("signup.html")

        try:
            response = requests.post(
                f"{SUPABASE_URL}/auth/v1/otp",
                headers={
                    "apikey": SUPABASE_ANON_KEY,
                    "Content-Type": "application/json",
                },
                json={"email": email, "create_user": True},
                timeout=15,
            )

            if response.status_code >= 400:
                app.logger.warning("OTP request failed: %s", response.text[:300])
                flash("Could not send OTP. Check Supabase Auth email settings.", "error")
                return render_template("signup.html")

            session["pending_email"] = email
            session.pop("verified_email", None)
            session.pop("pending_auth_token", None)
            flash("OTP sent. Check your inbox and spam folder.", "success")
            return redirect(url_for("verify_otp"))

        except requests.RequestException:
            app.logger.exception("OTP request failed")
            flash("Could not contact the authentication service. Try again.", "error")

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    if not email or "@" not in email or not password:
        flash("Enter a valid email address and password.", "error")
        return redirect(url_for("signin"))

    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        flash("Supabase Auth is not configured. Check your .env file.", "error")
        return redirect(url_for("signin"))

    try:
        response = requests.post(
            f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
            headers={
                "apikey": SUPABASE_ANON_KEY,
                "Content-Type": "application/json",
            },
            json={"email": email, "password": password},
            timeout=15,
        )
        data = response.json()

        if response.status_code >= 400 or not data.get("user"):
            flash("Email or password is incorrect. If this is your first visit, create an account first.", "error")
            return redirect(url_for("signin"))

        user = data["user"]
        session.clear()
        session["creator_id"] = user["id"]
        session["email"] = user.get("email", email).lower()
        log_event("creator_login", session["email"], session["creator_id"], details={"method": "password"})
        return redirect(request.args.get("next") or url_for("dashboard"))

    except (requests.RequestException, ValueError):
        app.logger.exception("Password login failed")
        flash("Could not contact the authentication service. Try again.", "error")
        return redirect(url_for("signin"))


@app.route("/verify-otp", methods=["GET", "POST"])

def verify_otp():

    email = session.get("pending_email")

    if not email:

        return redirect(url_for("login"))



    if request.method == "POST":

        token = request.form.get("otp", "").strip()

        if not token:

            flash("Enter the OTP from your email.", "error")

            return render_template("verify_otp.html", email=email)

        try:

            response = requests.post(

                f"{SUPABASE_URL}/auth/v1/verify",

                headers={"apikey": SUPABASE_ANON_KEY, "Content-Type": "application/json"},

                json={"email": email, "token": token, "type": "email"},

                timeout=15,

            )

            data = response.json()

            if response.status_code >= 400 or not data.get("user") or not data.get("access_token"):

                flash("That OTP is invalid or expired. Request a new one and try again.", "error")

                return render_template("verify_otp.html", email=email)



            user = data["user"]

            session["verified_email"] = user.get("email", email).lower()

            # Temporary token used only to set the initial password after OTP verification.

            session["pending_auth_token"] = data["access_token"]

            session.pop("pending_email", None)

            return redirect(url_for("create_password"))

        except (requests.RequestException, ValueError):

            app.logger.exception("OTP verification failed")

            flash("Could not verify OTP. Please try again.", "error")

    return render_template("verify_otp.html", email=email)





@app.route("/create-password", methods=["GET", "POST"])

def create_password():

    email = session.get("verified_email")

    access_token = session.get("pending_auth_token")

    if not email or not access_token:

        return redirect(url_for("login"))



    if request.method == "POST":

        password = request.form.get("password", "")

        confirm = request.form.get("confirm_password", "")

        if len(password) < 8:

            flash("Use a password with at least 8 characters.", "error")

        elif password != confirm:

            flash("The passwords do not match.", "error")

        else:

            try:

                response = requests.put(

                    f"{SUPABASE_URL}/auth/v1/user",

                    headers={

                        "apikey": SUPABASE_ANON_KEY,

                        "Authorization": f"Bearer {access_token}",

                        "Content-Type": "application/json",

                    },

                    json={"password": password},

                    timeout=15,

                )

                data = response.json()

                if response.status_code >= 400 or not data.get("id"):

                    app.logger.warning("Password setup failed: %s", response.text[:300])

                    flash("Could not set your password. Please verify your email again.", "error")

                else:

                    user_id = data["id"]

                    session.clear()

                    session["creator_id"] = user_id

                    session["email"] = data.get("email", email).lower()

                    log_event("creator_login", session["email"], user_id, details={"method": "otp_signup"})

                    return redirect(url_for("dashboard"))

            except (requests.RequestException, ValueError):

                app.logger.exception("Password setup failed")

                flash("Could not contact the authentication service. Try again.", "error")

    return render_template("create_password.html", email=email)





@app.route("/auth/google")

def google_login():

    if not SUPABASE_URL or not SUPABASE_ANON_KEY:

        flash("Supabase Auth is not configured.", "error")

        return redirect(url_for("login"))

    callback_url = url_for("google_callback", _external=True)

    auth_url = (

        f"{SUPABASE_URL}/auth/v1/authorize?provider=google"

        f"&redirect_to={quote(callback_url, safe='')}"

    )

    return redirect(auth_url)





@app.route("/auth/google/callback")

def google_callback():

    return render_template("google_callback.html")





@app.route("/auth/google/session", methods=["POST"])

def google_session():

    payload = request.get_json(silent=True) or {}

    access_token = payload.get("access_token", "")

    if not access_token:

        return {"ok": False, "error": "Missing access token"}, 400

    try:

        response = requests.get(

            f"{SUPABASE_URL}/auth/v1/user",

            headers={"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {access_token}"},

            timeout=15,

        )

        data = response.json()

        if response.status_code >= 400 or not data.get("id") or not data.get("email"):

            return {"ok": False, "error": "Google sign-in could not be verified"}, 401

        session.clear()

        session["creator_id"] = data["id"]

        session["email"] = data["email"].lower()

        log_event("creator_login", session["email"], session["creator_id"], details={"method": "google"})

        return {"ok": True, "redirect": url_for("dashboard")}

    except (requests.RequestException, ValueError):

        app.logger.exception("Google session verification failed")

        return {"ok": False, "error": "Authentication service unavailable"}, 503





@app.route("/logout")



def logout():



          session.clear()



          return redirect(url_for("index"))







@app.route("/dashboard")



@creator_required



def dashboard():



          with db() as conn:



                    tests = conn.execute("""SELECT t.*, (SELECT COUNT(*) FROM attempts a WHERE a.test_id=t.id) AS attempts



                                                                                FROM tests t WHERE creator_id=%s ORDER BY created_at DESC""",



                                                                          (session["creator_id"],)).fetchall()



          return render_template("dashboard.html", tests=tests)







@app.route("/tests/new", methods=["GET", "POST"])



@creator_required



def new_test():



          if request.method == "POST":



                    title = request.form.get("title", "").strip()



                    description = request.form.get("description", "").strip()



                    duration = max(1, min(600, int(request.form.get("duration", "30") or 30)))



                    max_attempts = max(1, min(100, int(request.form.get("max_attempts", "1") or 1)))



                    if not title:



                              flash("Test title is required.", "error")



                              return render_template("new_test.html")



                    code = make_code()



                    with db() as conn:



                              test = conn.execute("""INSERT INTO tests(creator_id,title,description,duration_minutes,max_attempts,share_code)



                                                                                         VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",



                                                                                (session["creator_id"], title, description, duration, max_attempts, code)).fetchone()



                    log_event("test_created", session["email"], session["creator_id"], test["id"])



                    return redirect(url_for("edit_test", test_id=test["id"]))



          return render_template("new_test.html")







@app.route("/tests/<int:test_id>/edit", methods=["GET", "POST"])



@creator_required



def edit_test(test_id):



          test = owned_test(test_id)



          if request.method == "POST":



                    title = request.form.get("title", "").strip()



                    description = request.form.get("description", "").strip()



                    duration = max(1, min(600, int(request.form.get("duration", "30") or 30)))



                    max_attempts = max(1, min(100, int(request.form.get("max_attempts", "1") or 1)))



                    with db() as conn:



                              conn.execute("""UPDATE tests SET title=%s,description=%s,duration_minutes=%s,max_attempts=%s WHERE id=%s AND creator_id=%s""",



                                                                (title, description, duration, max_attempts, test_id, session["creator_id"]))



                    return redirect(url_for("edit_test", test_id=test_id))



          with db() as conn:



                    questions = conn.execute("SELECT * FROM questions WHERE test_id=%s ORDER BY position,id", (test_id,)).fetchall()



                    for q in questions:



                              q["options"] = conn.execute("SELECT * FROM options WHERE question_id=%s ORDER BY position,id", (q["id"],)).fetchall()



          return render_template("edit_test.html", test=test, questions=questions)







@app.route("/tests/<int:test_id>/questions", methods=["POST"])



@creator_required



def add_question(test_id):



          owned_test(test_id)



          text = request.form.get("question_text", "").strip()



          kind = request.form.get("kind", "single")



          if not text:



                    flash("Question text is required.", "error")



                    return redirect(url_for("edit_test", test_id=test_id))



          raw_options = [x.strip() for x in request.form.getlist("option_text") if x.strip()]



          correct = set(request.form.getlist("correct"))



          if len(raw_options) < 2 or not correct:



                    flash("Add at least two options and select the correct answer(s).", "error")



                    return redirect(url_for("edit_test", test_id=test_id))



          if kind == "single" and len(correct) > 1:



                    flash("Single-choice questions can have only one correct answer.", "error")



                    return redirect(url_for("edit_test", test_id=test_id))



          marks = float(request.form.get("marks", "1") or 1)



          negative = float(request.form.get("negative_marks", "0") or 0)



          with db() as conn:



                    pos = conn.execute("SELECT COALESCE(MAX(position),0)+1 AS p FROM questions WHERE test_id=%s", (test_id,)).fetchone()["p"]



                    q = conn.execute("""INSERT INTO questions(test_id,question_text,kind,marks,negative_marks,position)



                                                                      VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",



                                                                (test_id, text, kind, marks, negative, pos)).fetchone()



                    for i, opt in enumerate(raw_options):



                              conn.execute("INSERT INTO options(question_id,option_text,is_correct,position) VALUES (%s,%s,%s,%s)",



                                                                (q["id"], opt, str(i) in correct, i+1))



          return redirect(url_for("edit_test", test_id=test_id))







@app.route("/questions/<int:question_id>/delete", methods=["POST"])



@creator_required



def delete_question(question_id):



          with db() as conn:



                    q = conn.execute("""SELECT q.id,q.test_id FROM questions q JOIN tests t ON t.id=q.test_id



                                                                      WHERE q.id=%s AND t.creator_id=%s""", (question_id, session["creator_id"])).fetchone()



                    if not q:



                              abort(404)



                    conn.execute("DELETE FROM questions WHERE id=%s", (question_id,))



          return redirect(url_for("edit_test", test_id=q["test_id"]))







@app.route("/tests/<int:test_id>/publish", methods=["POST"])



@creator_required



def publish_test(test_id):



          test = owned_test(test_id)



          with db() as conn:



                    count = conn.execute("SELECT COUNT(*) AS n FROM questions WHERE test_id=%s", (test_id,)).fetchone()["n"]



                    if count < 1:



                              flash("Add at least one question before publishing.", "error")



                              return redirect(url_for("edit_test", test_id=test_id))



                    published = not test["is_published"]



                    conn.execute("UPDATE tests SET is_published=%s WHERE id=%s", (published, test_id))



          if published:



                    log_event("test_published", session["email"], session["creator_id"], test_id)



          return redirect(url_for("edit_test", test_id=test_id))







@app.route("/tests/<int:test_id>/settings", methods=["POST"])



@creator_required



def test_settings(test_id):



          owned_test(test_id)



          with db() as conn:



                    conn.execute("""UPDATE tests SET shuffle_questions=%s,show_score=%s,show_correct_answers=%s,terminate_on_violation=%s



                                                                WHERE id=%s AND creator_id=%s""",



                                                      ("shuffle_questions" in request.form, "show_score" in request.form,



                                                       "show_correct_answers" in request.form, "terminate_on_violation" in request.form,



                                                       test_id, session["creator_id"]))



          return redirect(url_for("edit_test", test_id=test_id))







@app.route("/t/<share_code>", methods=["GET", "POST"])



def attend_test(share_code):



          with db() as conn:



                    test = conn.execute("SELECT * FROM tests WHERE share_code=%s AND is_published=TRUE", (share_code,)).fetchone()



          if not test:



                    abort(404)



          if request.method == "POST":



                    name = request.form.get("student_name", "").strip()



                    candidate_id = request.form.get("candidate_id", "").strip()



                    if not name or not candidate_id:



                              flash("Enter your name and candidate/roll number.", "error")



                              return render_template("attend_intro.html", test=test)



                    with db() as conn:



                              count = conn.execute("SELECT COUNT(*) AS n FROM attempts WHERE test_id=%s AND candidate_id=%s",



                                                                                    (test["id"], candidate_id)).fetchone()["n"]



                              if count >= test["max_attempts"]:



                                        flash("The allowed attempt limit for this candidate has been reached.", "error")



                                        return render_template("attend_intro.html", test=test)



                              attempt = conn.execute("""INSERT INTO attempts(test_id,student_name,candidate_id,started_at,status)



                                                                                               VALUES (%s,%s,%s,NOW(),'in_progress') RETURNING id""",



                                                                                         (test["id"], name, candidate_id)).fetchone()



                    session.setdefault("student_attempts", {})



                    session["student_attempts"][str(attempt["id"])] = secrets.token_urlsafe(24)



                    log_event("student_attempt_started", None, test["creator_id"], test["id"])



                    return redirect(url_for("exam", attempt_id=attempt["id"], token=session["student_attempts"][str(attempt["id"])]))



          return render_template("attend_intro.html", test=test)







def get_attempt(attempt_id, token):



          stored = session.get("student_attempts", {}).get(str(attempt_id))



          if not stored or not secrets.compare_digest(stored, token or ""):



                    abort(403)



          with db() as conn:



                    attempt = conn.execute("""SELECT a.*,t.title,t.duration_minutes,t.shuffle_questions,t.show_score,



                                                                                     t.show_correct_answers,t.terminate_on_violation,t.id AS tid



                                                                                     FROM attempts a JOIN tests t ON t.id=a.test_id WHERE a.id=%s""",



                                                                               (attempt_id,)).fetchone()



          if not attempt:



                    abort(404)



          return attempt







@app.route("/exam/<int:attempt_id>")



def exam(attempt_id):



          token = request.args.get("token", "")



          attempt = get_attempt(attempt_id, token)



          if attempt["status"] != "in_progress":



                    return redirect(url_for("student_result", attempt_id=attempt_id, token=token))



          with db() as conn:



                    questions = conn.execute("SELECT * FROM questions WHERE test_id=%s ORDER BY position,id", (attempt["tid"],)).fetchall()



                    if attempt["shuffle_questions"]:



                              import random



                              random.shuffle(questions)



                    for q in questions:



                              q["options"] = conn.execute("SELECT id,option_text FROM options WHERE question_id=%s ORDER BY position,id", (q["id"],)).fetchall()



                              q["saved"] = conn.execute("SELECT option_id FROM responses WHERE attempt_id=%s AND question_id=%s",



                                                                                               (attempt_id, q["id"])).fetchall()



                              q["saved_ids"] = [str(x["option_id"]) for x in q["saved"]]



          return render_template("exam.html", attempt=attempt, questions=questions, token=token)







@app.route("/exam/<int:attempt_id>/save", methods=["POST"])



def save_response(attempt_id):



          data = request.get_json(silent=True) or {}



          token = data.get("token", "")



          attempt = get_attempt(attempt_id, token)



          if attempt["status"] != "in_progress":



                    return {"ok": False, "error": "Attempt is not active"}, 409



          qid = int(data.get("question_id", 0))



          selected = [int(x) for x in data.get("option_ids", [])]



          with db() as conn:



                    q = conn.execute("SELECT id FROM questions WHERE id=%s AND test_id=%s", (qid, attempt["tid"])).fetchone()



                    if not q:



                              return {"ok": False, "error": "Invalid question"}, 400



                    valid = conn.execute("SELECT id FROM options WHERE question_id=%s", (qid,)).fetchall()



                    valid_ids = {x["id"] for x in valid}



                    if any(x not in valid_ids for x in selected):



                              return {"ok": False, "error": "Invalid option"}, 400



                    conn.execute("DELETE FROM responses WHERE attempt_id=%s AND question_id=%s", (attempt_id, qid))



                    for oid in selected:



                              conn.execute("INSERT INTO responses(attempt_id,question_id,option_id) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",



                                                                (attempt_id, qid, oid))



          return {"ok": True}







@app.route("/exam/<int:attempt_id>/event", methods=["POST"])



def exam_event(attempt_id):



          data = request.get_json(silent=True) or {}



          attempt = get_attempt(attempt_id, data.get("token", ""))



          event_type = str(data.get("event", "unknown"))[:80]



          with db() as conn:



                    conn.execute("INSERT INTO security_events(attempt_id,event_type,details) VALUES (%s,%s,%s)",



                                                      (attempt_id, event_type, json.dumps({"visibility": data.get("visibility")})))



                    if attempt["terminate_on_violation"] and event_type in {"tab_hidden", "fullscreen_exit", "window_blur"}:



                              conn.execute("UPDATE attempts SET status='terminated',submitted_at=NOW() WHERE id=%s AND status='in_progress'", (attempt_id,))



          return {"ok": True, "terminated": bool(attempt["terminate_on_violation"] and event_type in {"tab_hidden","fullscreen_exit","window_blur"})}







@app.route("/exam/<int:attempt_id>/submit", methods=["POST"])



def submit_exam(attempt_id):



          data = request.get_json(silent=True) or {}



          token = data.get("token", "")



          attempt = get_attempt(attempt_id, token)



          with db() as conn:



                    if attempt["status"] == "in_progress":



                              rows = conn.execute("""SELECT q.id AS qid,q.marks,q.negative_marks,o.id AS oid,o.is_correct,



                                                                                         r.option_id AS chosen



                                                                                         FROM questions q JOIN options o ON o.question_id=q.id



                                                                                         LEFT JOIN responses r ON r.question_id=q.id AND r.option_id=o.id AND r.attempt_id=%s



                                                                                         WHERE q.test_id=%s ORDER BY q.id,o.id""", (attempt_id, attempt["tid"])).fetchall()



                              byq = {}



                              for r in rows:



                                        item = byq.setdefault(r["qid"], {"marks": float(r["marks"]), "negative": float(r["negative_marks"]), "correct": set(), "chosen": set()})



                                        if r["is_correct"]: item["correct"].add(r["oid"])



                                        if r["chosen"] is not None: item["chosen"].add(r["oid"])



                              score = 0.0



                              maximum = 0.0



                              for item in byq.values():



                                        maximum += item["marks"]



                                        if item["chosen"] == item["correct"] and item["correct"]:



                                                  score += item["marks"]



                                        elif item["chosen"]:



                                                  score -= item["negative"]



                              score = max(0, score)



                              conn.execute("UPDATE attempts SET status='submitted',submitted_at=NOW(),score=%s,max_score=%s WHERE id=%s",



                                                                (score, maximum, attempt_id))



          return {"ok": True, "redirect": url_for("student_result", attempt_id=attempt_id, token=token)}







@app.route("/result/<int:attempt_id>")



def student_result(attempt_id):



          token = request.args.get("token", "")



          attempt = get_attempt(attempt_id, token)



          with db() as conn:



                    test = conn.execute("SELECT show_score,show_correct_answers FROM tests WHERE id=%s", (attempt["tid"],)).fetchone()



          return render_template("student_result.html", attempt=attempt, test=test)







@app.route("/tests/<int:test_id>/results")



@creator_required



def results(test_id):



          test = owned_test(test_id)



          with db() as conn:



                    attempts = conn.execute("""SELECT a.* FROM attempts a WHERE a.test_id=%s



                                                                                         ORDER BY a.score DESC NULLS LAST,a.submitted_at ASC NULLS LAST""", (test_id,)).fetchall()



          return render_template("results.html", test=test, attempts=attempts)







@app.route("/tests/<int:test_id>/results.csv")



@creator_required



def results_csv(test_id):



          test = owned_test(test_id)



          with db() as conn:



                    rows = conn.execute("""SELECT student_name,candidate_id,status,score,max_score,started_at,submitted_at



                                                                               FROM attempts WHERE test_id=%s ORDER BY score DESC NULLS LAST""", (test_id,)).fetchall()



          output = io.StringIO()



          writer = csv.writer(output)



          writer.writerow(["Name","Candidate ID","Status","Score","Maximum Score","Started At","Submitted At"])



          for row in rows:



                    writer.writerow([row["student_name"],row["candidate_id"],row["status"],row["score"],row["max_score"],row["started_at"],row["submitted_at"]])



          response = make_response(output.getvalue())



          response.headers["Content-Type"] = "text/csv; charset=utf-8"



          response.headers["Content-Disposition"] = f'attachment; filename="shadow_test_{test_id}_results.csv"'



          return response







@app.route("/admin")



@admin_required



def admin_dashboard():



          with db() as conn:



                    summary = {



                              "creators": conn.execute("SELECT COUNT(DISTINCT creator_id) AS n FROM tests").fetchone()["n"],



                              "logins": conn.execute("SELECT COUNT(*) AS n FROM platform_events WHERE event_type='creator_login'").fetchone()["n"],



                              "tests": conn.execute("SELECT COUNT(*) AS n FROM tests").fetchone()["n"],



                              "published": conn.execute("SELECT COUNT(*) AS n FROM tests WHERE is_published=TRUE").fetchone()["n"],



                              "attempts": conn.execute("SELECT COUNT(*) AS n FROM attempts").fetchone()["n"],



                    }



                    events = conn.execute("SELECT * FROM platform_events ORDER BY created_at DESC LIMIT 200").fetchall()



          return render_template("admin.html", summary=summary, events=events)







@app.route("/admin/events.csv")



@admin_required



def admin_csv():



          with db() as conn:



                    rows = conn.execute("SELECT created_at,event_type,email,creator_id,test_id,details FROM platform_events ORDER BY created_at DESC").fetchall()



          output = io.StringIO()



          writer = csv.writer(output)



          writer.writerow(["Date","Event","Email","Creator ID","Test ID","Details"])



          for r in rows:



                    writer.writerow([r["created_at"],r["event_type"],r["email"],r["creator_id"],r["test_id"],r["details"]])



          response = make_response(output.getvalue())



          response.headers["Content-Type"] = "text/csv; charset=utf-8"



          response.headers["Content-Disposition"] = 'attachment; filename="shadow_platform_analytics.csv"'



          return response







@app.errorhandler(403)



def forbidden(_):



          return render_template("error.html", code=403, message="You do not have permission to access this page."), 403







@app.errorhandler(404)



def not_found(_):



          return render_template("error.html", code=404, message="The page or test could not be found."), 404







if __name__ == "__main__":



          app.run(debug=os.environ.get("FLASK_DEBUG", "0") == "1")
