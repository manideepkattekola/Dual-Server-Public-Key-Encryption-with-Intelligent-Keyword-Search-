import hashlib
import os
import re
import csv
import tempfile
from datetime import datetime
from io import StringIO
from sqlalchemy import text
from time import perf_counter

from flask import (
    Flask,
    Response,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from werkzeug.utils import secure_filename

from cloud_storage import CloudStorage
from crypto_utils import CryptoUtils
from database import Document, DownloadEvent, KeywordCiphertext, User, db
from ds_peks import BackServer, DualServerPEKS, FrontServer
from file_processor import FileProcessor

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "replace-this-secret-in-production")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///cloud_storage.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = "uploads"
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
db.init_app(app)

crypto_utils = CryptoUtils()
file_processor = FileProcessor()
cloud_storage = CloudStorage(app.config["UPLOAD_FOLDER"])

# Hidden backend simulation: Front Server (FS) and Back Server (BS)
ds_peks = DualServerPEKS()
front_server = FrontServer()
back_server = BackServer()
front_server.setup_keys()
back_server.setup_keys()
ds_peks.set_servers(front_server, back_server)

ALLOWED_EXTENSIONS = {"txt", "pdf", "docx", "doc"}


def _short(value, length=14):
    text_value = str(value)
    if len(text_value) <= length:
        return text_value
    return f"{text_value[:length]}..."


def _add_trace(trace, phase, detail, payload=None, started_at=None):
    entry = {
        "phase": phase,
        "detail": detail,
    }
    if payload is not None:
        entry["payload"] = payload
    if started_at is not None:
        entry["elapsed_ms"] = int((perf_counter() - started_at) * 1000)
    trace.append(entry)


def _build_download_trace(document, actor):
    provider, _ = cloud_storage._parse_ref(document.file_path)
    return [
        {
            "phase": "Request Validation",
            "detail": f"Authorize {actor} request and validate access to document id={document.id}.",
            "payload": {"owner_id": document.owner_id, "filename": document.original_filename},
        },
        {
            "phase": "Encrypted File Retrieval",
            "detail": "Fetch encrypted binary from configured cloud backend.",
            "payload": {"provider": provider, "file_ref": _short(document.file_path, 40)},
        },
        {
            "phase": "AES Key Recovery",
            "detail": "Recover the file AES key from wrapped key material.",
            "payload": {"encrypted_key_fingerprint": _short(document.encrypted_key)},
        },
        {
            "phase": "File Decryption",
            "detail": "Decrypt encrypted binary using AES-CBC with recovered key and stored IV.",
            "payload": {"iv_fingerprint": _short(document.iv)},
        },
        {
            "phase": "Secure Stream",
            "detail": "Stream original plaintext file to browser and purge temporary files.",
        },
    ]


def _ensure_schema():
    db.create_all()

    documents_columns = [row[1] for row in db.session.execute(text("PRAGMA table_info(documents)"))]
    if "selected_keywords_enc" not in documents_columns:
        db.session.execute(text("ALTER TABLE documents ADD COLUMN selected_keywords_enc TEXT"))

    users_columns = [row[1] for row in db.session.execute(text("PRAGMA table_info(users)"))]
    if "name" not in users_columns:
        db.session.execute(text("ALTER TABLE users ADD COLUMN name VARCHAR(120)"))
    if "email" not in users_columns:
        db.session.execute(text("ALTER TABLE users ADD COLUMN email VARCHAR(200)"))
    if "mobile" not in users_columns:
        db.session.execute(text("ALTER TABLE users ADD COLUMN mobile VARCHAR(30)"))

    db.session.commit()


with app.app_context():
    _ensure_schema()


def _is_allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _hash_password(password):
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def _is_valid_email(email):
    return re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email or "") is not None


def _is_valid_mobile(mobile):
    return re.match(r"^[0-9+\-\s]{7,20}$", mobile or "") is not None


def _record_download_event(document_id, accessor_id):
    db.session.add(DownloadEvent(document_id=document_id, accessor_id=accessor_id))
    db.session.commit()


def _safe_iso_to_dt(value, end_of_day=False):
    if not value:
        return None
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
        if end_of_day:
            return parsed.replace(hour=23, minute=59, second=59)
        return parsed
    except ValueError:
        return None


def _build_owner_analytics_query(owner_id, filters):
    query = (
        db.session.query(DownloadEvent, Document, User)
        .join(Document, DownloadEvent.document_id == Document.id)
        .join(User, DownloadEvent.accessor_id == User.id)
        .filter(Document.owner_id == owner_id)
    )

    if filters.get("accessor"):
        query = query.filter(User.username == filters["accessor"])

    if filters.get("file_name"):
        query = query.filter(Document.original_filename == filters["file_name"])

    if filters.get("start_dt"):
        query = query.filter(DownloadEvent.downloaded_at >= filters["start_dt"])

    if filters.get("end_dt"):
        query = query.filter(DownloadEvent.downloaded_at <= filters["end_dt"])

    return query


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        mobile = request.form.get("mobile", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "")

        if role not in {"owner", "user"}:
            flash("Invalid role selected.", "danger")
            return redirect(url_for("register"))

        if not username or not password or not name or not email or not mobile:
            flash("Name, email, mobile, username, and password are required.", "danger")
            return redirect(url_for("register"))

        if not _is_valid_email(email):
            flash("Please enter a valid email address.", "danger")
            return redirect(url_for("register"))

        if not _is_valid_mobile(mobile):
            flash("Please enter a valid mobile number.", "danger")
            return redirect(url_for("register"))

        existing = User.query.filter_by(username=username).first()
        if existing:
            flash("Username already exists!", "danger")
            return redirect(url_for("register"))

        user = User(
            username=username,
            name=name,
            email=email,
            mobile=mobile,
            password_hash=_hash_password(password),
            role=role,
        )
        db.session.add(user)
        db.session.commit()
        flash("Registration successful! Please login.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = User.query.filter_by(username=username).first()
        if user and user.password_hash == _hash_password(password):
            session["user_id"] = user.id
            session["username"] = user.username
            session["role"] = user.role
            if user.role == "owner":
                return redirect(url_for("owner_dashboard"))
            return redirect(url_for("user_dashboard"))

        flash("Invalid credentials!", "danger")

    return render_template("login.html")


@app.route("/owner/dashboard")
def owner_dashboard():
    if "user_id" not in session or session.get("role") != "owner":
        return redirect(url_for("login"))

    filters = {
        "start_date": request.args.get("start_date", "").strip(),
        "end_date": request.args.get("end_date", "").strip(),
        "accessor": request.args.get("accessor", "").strip(),
        "file_name": request.args.get("file_name", "").strip(),
    }
    filters["start_dt"] = _safe_iso_to_dt(filters["start_date"])
    filters["end_dt"] = _safe_iso_to_dt(filters["end_date"], end_of_day=True)

    documents = Document.query.filter_by(owner_id=session["user_id"]).order_by(Document.created_at.desc()).all()
    for document in documents:
        document.display_keywords = crypto_utils.decrypt_keywords_metadata(document.selected_keywords_enc)

    owner_download_logs = _build_owner_analytics_query(session["user_id"], filters).order_by(DownloadEvent.downloaded_at.desc()).all()

    download_rows = []
    file_download_counts = {}
    accessor_summary = {}
    for event, document, accessor in owner_download_logs:
        download_rows.append(
            {
                "doc_name": document.original_filename,
                "accessor_name": accessor.name or accessor.username,
                "accessor_username": accessor.username,
                "accessor_role": accessor.role,
                "accessed_at": event.downloaded_at,
            }
        )

        file_download_counts[document.original_filename] = file_download_counts.get(document.original_filename, 0) + 1
        accessor_summary[accessor.username] = accessor_summary.get(accessor.username, 0) + 1

    top_files = sorted(file_download_counts.items(), key=lambda item: item[1], reverse=True)[:5]
    top_accessors = sorted(accessor_summary.items(), key=lambda item: item[1], reverse=True)[:5]

    stats = {
        "total_files": len(documents),
        "total_downloads": len(download_rows),
        "unique_accessors": len(accessor_summary),
        "owner_downloads": len([row for row in download_rows if row["accessor_role"] == "owner"]),
        "user_downloads": len([row for row in download_rows if row["accessor_role"] == "user"]),
        "top_files": top_files,
        "top_accessors": top_accessors,
    }

    accessor_options = sorted({row["accessor_username"] for row in download_rows})
    file_options = sorted({doc.original_filename for doc in documents})

    return render_template(
        "owner_dashboard.html",
        documents=documents,
        username=session.get("username", ""),
        dropbox_enabled=cloud_storage.is_dropbox_enabled,
        cloud_status=cloud_storage.status_message,
        upload_trace=session.pop("last_upload_trace", None),
        download_rows=download_rows,
        stats=stats,
        filters=filters,
        accessor_options=accessor_options,
        file_options=file_options,
    )


@app.route("/owner/analytics/export")
def export_owner_analytics_csv():
    if "user_id" not in session or session.get("role") != "owner":
        return redirect(url_for("login"))

    filters = {
        "start_date": request.args.get("start_date", "").strip(),
        "end_date": request.args.get("end_date", "").strip(),
        "accessor": request.args.get("accessor", "").strip(),
        "file_name": request.args.get("file_name", "").strip(),
    }
    filters["start_dt"] = _safe_iso_to_dt(filters["start_date"])
    filters["end_dt"] = _safe_iso_to_dt(filters["end_date"], end_of_day=True)

    rows = _build_owner_analytics_query(session["user_id"], filters).order_by(DownloadEvent.downloaded_at.desc()).all()

    stream = StringIO()
    writer = csv.writer(stream)
    writer.writerow([
        "file_name",
        "accessor_name",
        "accessor_username",
        "accessor_role",
        "accessed_at",
    ])

    for event, document, accessor in rows:
        writer.writerow(
            [
                document.original_filename,
                accessor.name or accessor.username,
                accessor.username,
                accessor.role,
                event.downloaded_at.strftime("%Y-%m-%d %H:%M:%S"),
            ]
        )

    csv_data = stream.getvalue()
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"owner_download_analytics_{timestamp}.csv"
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.route("/owner/upload", methods=["POST"])
def upload_file():
    if "user_id" not in session or session.get("role") != "owner":
        return redirect(url_for("login"))

    upload = request.files.get("file")
    if not upload or upload.filename == "":
        flash("No file selected!", "danger")
        return redirect(url_for("owner_dashboard"))

    if not _is_allowed_file(upload.filename):
        flash("Only PDF, DOCX, DOC, and TXT files are allowed.", "danger")
        return redirect(url_for("owner_dashboard"))

    original_filename = secure_filename(upload.filename)
    temp_original_path = os.path.join(
        app.config["UPLOAD_FOLDER"], f"tmp_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}_{original_filename}"
    )
    temp_encrypted_path = os.path.join(
        app.config["UPLOAD_FOLDER"], f"enc_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}_{original_filename}.bin"
    )
    flow_trace = []
    started_at = perf_counter()

    try:
        upload.save(temp_original_path)
        _add_trace(
            flow_trace,
            "Input Capture",
            "Accepted owner upload request and persisted temporary source file.",
            payload={"filename": original_filename, "size_bytes": os.path.getsize(temp_original_path)},
            started_at=started_at,
        )

        file_text = file_processor.extract_text(temp_original_path)
        _add_trace(
            flow_trace,
            "Text Extraction",
            "Extracted textual content from uploaded document (PDF/TXT/DOCX parser).",
            payload={"text_length": len(file_text)},
            started_at=started_at,
        )

        keywords = file_processor.extract_keywords(file_text, top_k=5)
        _add_trace(
            flow_trace,
            "Keyword Set Construction",
            "Built top-5 keyword set after stopword filtering and frequency ranking.",
            payload={"selected_keywords": keywords},
            started_at=started_at,
        )

        aes_key = crypto_utils.generate_aes_key()
        iv = crypto_utils.generate_iv()
        _add_trace(
            flow_trace,
            "AES Material Generation",
            "Generated random AES-256 key and IV for file encryption.",
            payload={"aes_key_fingerprint": _short(aes_key.hex()), "iv_fingerprint": _short(iv.hex())},
            started_at=started_at,
        )

        crypto_utils.encrypt_file(temp_original_path, temp_encrypted_path, aes_key, iv)
        _add_trace(
            flow_trace,
            "File Encryption",
            "Encrypted file using AES-CBC; plaintext never uploaded to cloud.",
            payload={"encrypted_size_bytes": os.path.getsize(temp_encrypted_path)},
            started_at=started_at,
        )

        encrypted_key = crypto_utils.encrypt_aes_key(aes_key)
        encrypted_selected_keywords = crypto_utils.encrypt_keywords_metadata(keywords)
        iv_text = crypto_utils.iv_to_text(iv)
        _add_trace(
            flow_trace,
            "Key Wrapping",
            "Wrapped AES key and encrypted owner-visible keyword metadata for secure storage.",
            payload={
                "wrapped_key_fingerprint": _short(encrypted_key),
                "keyword_metadata_fingerprint": _short(encrypted_selected_keywords),
            },
            started_at=started_at,
        )

        keyword_trace = []
        encrypted_keyword_rows = []
        for keyword in keywords:
            c1, c2, c3 = ds_peks.generate_peks_ciphertext(keyword)
            encrypted_keyword_rows.append((c1, c2, c3, keyword))
            keyword_trace.append({"keyword": keyword, "c1": _short(c1), "c2": _short(c2), "c3": _short(c3)})

        _add_trace(
            flow_trace,
            "DS-PEKS Keyword Encryption",
            "Encrypted each selected keyword into ciphertext tuple (c1,c2,c3); plaintext keywords are not stored in searchable index.",
            payload={"keyword_ciphertexts": keyword_trace},
            started_at=started_at,
        )

        cloud_ref = cloud_storage.upload_file(temp_encrypted_path, f"encrypted_{original_filename}.bin")
        _add_trace(
            flow_trace,
            "Cloud Upload",
            "Uploaded encrypted binary to configured cloud backend reference.",
            payload={"cloud_ref": cloud_ref},
            started_at=started_at,
        )

        document = Document(
            owner_id=session["user_id"],
            filename=f"encrypted_{original_filename}.bin",
            original_filename=original_filename,
            file_path=cloud_ref,
            encrypted_key=encrypted_key,
            selected_keywords_enc=encrypted_selected_keywords,
            iv=iv_text,
        )
        db.session.add(document)
        db.session.flush()

        for c1, c2, c3, _keyword in encrypted_keyword_rows:
            db.session.add(
                KeywordCiphertext(
                    document_id=document.id,
                    c1=c1,
                    c2=c2,
                    c3=c3,
                )
            )

        db.session.commit()
        _add_trace(
            flow_trace,
            "Database Persistence",
            "Persisted document metadata, wrapped AES key, and DS-PEKS ciphertext tuples into SQLite.",
            payload={"document_id": document.id, "ciphertext_rows": len(encrypted_keyword_rows)},
            started_at=started_at,
        )

        _add_trace(
            flow_trace,
            "Upload Complete",
            "End-to-end secure upload pipeline completed successfully.",
            started_at=started_at,
        )
        session["last_upload_trace"] = flow_trace

        flash(
            f"File uploaded securely. {len(keywords)} keywords were encrypted via DS-PEKS and stored as ciphertext.",
            "success",
        )
    except Exception as exc:
        db.session.rollback()
        _add_trace(
            flow_trace,
            "Upload Failed",
            "Pipeline terminated with an exception.",
            payload={"error": str(exc)},
            started_at=started_at,
        )
        session["last_upload_trace"] = flow_trace
        flash(f"Upload failed: {exc}", "danger")
    finally:
        if os.path.exists(temp_original_path):
            os.remove(temp_original_path)
        if os.path.exists(temp_encrypted_path):
            os.remove(temp_encrypted_path)

    return redirect(url_for("owner_dashboard"))


def _stream_decrypted_document(document):
    encrypted_temp = tempfile.NamedTemporaryFile(delete=False, suffix=".bin")
    encrypted_temp.close()
    decrypted_temp = tempfile.NamedTemporaryFile(delete=False, suffix=f"_{document.original_filename}")
    decrypted_temp.close()

    cloud_storage.download_file(document.file_path, encrypted_temp.name)

    aes_key = crypto_utils.decrypt_aes_key(document.encrypted_key)
    iv_bytes = crypto_utils.iv_from_text(document.iv)
    crypto_utils.decrypt_file(encrypted_temp.name, decrypted_temp.name, aes_key, iv_bytes)
    if os.path.exists(encrypted_temp.name):
        os.remove(encrypted_temp.name)

    response = send_file(decrypted_temp.name, as_attachment=True, download_name=document.original_filename)

    @response.call_on_close
    def cleanup_decrypted_file():
        if os.path.exists(decrypted_temp.name):
            os.remove(decrypted_temp.name)

    return response


@app.route("/owner/download/<int:doc_id>")
def owner_download_file(doc_id):
    if "user_id" not in session or session.get("role") != "owner":
        return redirect(url_for("login"))

    document = Document.query.get_or_404(doc_id)
    if document.owner_id != session["user_id"]:
        flash("Unauthorized access!", "danger")
        return redirect(url_for("owner_dashboard"))

    return render_template(
        "download_flow.html",
        role="owner",
        doc=document,
        flow_trace=_build_download_trace(document, "owner"),
        file_url=url_for("owner_download_file_stream", doc_id=doc_id),
    )


@app.route("/owner/download/file/<int:doc_id>")
def owner_download_file_stream(doc_id):
    if "user_id" not in session or session.get("role") != "owner":
        return redirect(url_for("login"))

    document = Document.query.get_or_404(doc_id)
    if document.owner_id != session["user_id"]:
        flash("Unauthorized access!", "danger")
        return redirect(url_for("owner_dashboard"))

    _record_download_event(document.id, session["user_id"])

    return _stream_decrypted_document(document)


@app.route("/owner/delete/<int:doc_id>")
def delete_file(doc_id):
    if "user_id" not in session or session.get("role") != "owner":
        return redirect(url_for("login"))

    document = Document.query.get_or_404(doc_id)
    if document.owner_id != session["user_id"]:
        flash("Unauthorized access!", "danger")
        return redirect(url_for("owner_dashboard"))

    try:
        cloud_storage.delete_file(document.file_path)
        db.session.delete(document)
        db.session.commit()
        flash("File deleted from cloud and database.", "success")
    except Exception as exc:
        db.session.rollback()
        flash(f"Delete failed: {exc}", "danger")

    return redirect(url_for("owner_dashboard"))


@app.route("/user/dashboard")
def user_dashboard():
    if "user_id" not in session or session.get("role") != "user":
        return redirect(url_for("login"))
    return render_template("user_dashboard.html", username=session.get("username", ""))


@app.route("/user/search", methods=["POST"])
def search_files():
    if "user_id" not in session or session.get("role") != "user":
        return redirect(url_for("login"))

    keyword = request.form.get("keyword", "").strip()
    if not keyword:
        flash("Please enter a keyword.", "warning")
        return redirect(url_for("user_dashboard"))

    search_trace = []
    started_at = perf_counter()
    _add_trace(
        search_trace,
        "Keyword Input",
        "Accepted search keyword from data user.",
        payload={"keyword": keyword},
        started_at=started_at,
    )

    trapdoor = ds_peks.generate_trapdoor(keyword)
    _add_trace(
        search_trace,
        "Trapdoor Generation",
        "Generated DS-PEKS trapdoor tuple for secure search tokenization.",
        payload={"trapdoor_fs": _short(trapdoor[0]), "trapdoor_bs": _short(trapdoor[1])},
        started_at=started_at,
    )

    matched_document_ids = set()
    all_ciphertexts = KeywordCiphertext.query.all()
    _add_trace(
        search_trace,
        "Ciphertext Scan Initialization",
        "Loaded encrypted keyword tuples from DB for FS/BS collaborative test.",
        payload={"ciphertext_count": len(all_ciphertexts)},
        started_at=started_at,
    )

    fs_pass_count = 0
    bs_match_count = 0
    sample_checks = []

    for row in all_ciphertexts:
        ciphertext = (row.c1, row.c2, row.c3)

        # Front Server simulation
        cits = front_server.front_test(front_server.secret_key, ciphertext, trapdoor)
        if cits is None:
            if len(sample_checks) < 5:
                sample_checks.append({"document_id": row.document_id, "fs": "no-pass", "bs": "skipped"})
            continue

        fs_pass_count += 1

        # Back Server simulation
        match = back_server.back_test(back_server.secret_key, cits)
        if match == 1:
            matched_document_ids.add(row.document_id)
            bs_match_count += 1

        if len(sample_checks) < 5:
            sample_checks.append(
                {
                    "document_id": row.document_id,
                    "fs": "pass",
                    "bs": "match" if match == 1 else "no-match",
                }
            )

    _add_trace(
        search_trace,
        "Front Server Processing",
        "Front Server mixed ciphertext + trapdoor and produced CITS only for valid FS checks.",
        payload={"fs_pass_count": fs_pass_count},
        started_at=started_at,
    )

    _add_trace(
        search_trace,
        "Back Server Verification",
        "Back Server verified CITS using BS secret key and returned binary match decisions.",
        payload={"bs_match_count": bs_match_count, "sample_checks": sample_checks},
        started_at=started_at,
    )

    documents = (
        Document.query.filter(Document.id.in_(matched_document_ids)).order_by(Document.created_at.desc()).all()
        if matched_document_ids
        else []
    )

    _add_trace(
        search_trace,
        "Search Complete",
        "Collected matched document list without exposing plaintext keywords to servers.",
        payload={"matched_documents": len(documents)},
        started_at=started_at,
    )

    return render_template(
        "search_results.html",
        documents=documents,
        keyword=keyword,
        username=session.get("username", ""),
        search_trace=search_trace,
    )


@app.route("/user/download/<int:doc_id>")
def user_download_file(doc_id):
    if "user_id" not in session or session.get("role") != "user":
        return redirect(url_for("login"))

    document = Document.query.get_or_404(doc_id)
    return render_template(
        "download_flow.html",
        role="user",
        doc=document,
        flow_trace=_build_download_trace(document, "user"),
        file_url=url_for("user_download_file_stream", doc_id=doc_id),
    )


@app.route("/user/download/file/<int:doc_id>")
def user_download_file_stream(doc_id):
    if "user_id" not in session or session.get("role") != "user":
        return redirect(url_for("login"))

    document = Document.query.get_or_404(doc_id)
    _record_download_event(document.id, session["user_id"])
    return _stream_decrypted_document(document)


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully!", "success")
    return redirect(url_for("index"))


if __name__ == "__main__":
    with app.app_context():
        _ensure_schema()
    app.run(debug=True, port=5000)
