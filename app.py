"""
ZONE SHOP - Text to Speech Web UI
"""

from flask import Flask, render_template, request, send_file, jsonify, redirect, url_for, session
from functools import wraps
import io
import os
import json
import hashlib
import filelock
from datetime import datetime
from viettel_tts import ViettelTTS, VOICES

# Cấu hình ffmpeg path cho pydub (chỉ trên Windows)
if os.name == 'nt':
    FFMPEG_PATH = r"C:\Users\ngoct\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin"
    if os.path.exists(FFMPEG_PATH):
        os.environ["PATH"] += os.pathsep + FFMPEG_PATH

# Import pydub (optional - dùng cho convert MP3)
try:
    from pydub import AudioSegment
    PYDUB_AVAILABLE = True
except ImportError:
    PYDUB_AVAILABLE = False

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", os.urandom(24).hex())

TOKEN = os.getenv("VIETTEL_TOKEN")
if not TOKEN:
    raise ValueError("VIETTEL_TOKEN không được cấu hình trong .env")
tts = ViettelTTS(TOKEN)

AUDIO_DIR = "audio_files"
USERS_FILE = "users.json"
HISTORY_FILE = "history.json"
SETTINGS_FILE = "settings.json"
PROJECTS_FILE = "projects.json"
os.makedirs(AUDIO_DIR, exist_ok=True)


# ============ SETTINGS (Viettel API Quota) ============

def load_settings():
    lock = filelock.FileLock(f"{SETTINGS_FILE}.lock")
    with lock:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        default_settings = {
            "viettel_quota": 50000,
            "viettel_used": 0,
            "updated_at": datetime.now().strftime("%d/%m/%Y %H:%M")
        }
        save_settings(default_settings)
        return default_settings


def save_settings(settings):
    lock = filelock.FileLock(f"{SETTINGS_FILE}.lock")
    with lock:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)


# ============ USER MANAGEMENT ============

def load_users():
    lock = filelock.FileLock(f"{USERS_FILE}.lock")
    with lock:
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        default_users = {
            "admin": {
                "password": hash_password("admin123"),
                "role": "admin",
                "quota": 999999999,
                "used": 0,
                "created_at": datetime.now().strftime("%d/%m/%Y %H:%M")
            }
        }
        save_users(default_users)
        return default_users


def save_users(users):
    lock = filelock.FileLock(f"{USERS_FILE}.lock")
    with lock:
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(users, f, ensure_ascii=False, indent=2)


def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        # Kiểm tra user còn tồn tại không
        users = load_users()
        if session["user"] not in users:
            session.pop("user", None)
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        users = load_users()
        if users.get(session["user"], {}).get("role") != "admin":
            return jsonify({"error": "Không có quyền truy cập"}), 403
        return f(*args, **kwargs)
    return decorated_function


# ============ HISTORY ============

def load_history(username=None):
    lock = filelock.FileLock(f"{HISTORY_FILE}.lock")
    with lock:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
                if username:
                    return [h for h in history if h.get("user") == username]
                return history
    return []


def save_history(history):
    lock = filelock.FileLock(f"{HISTORY_FILE}.lock")
    with lock:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)


# ============ PROJECTS ============

def load_projects(username=None):
    lock = filelock.FileLock(f"{PROJECTS_FILE}.lock")
    with lock:
        if os.path.exists(PROJECTS_FILE):
            with open(PROJECTS_FILE, "r", encoding="utf-8") as f:
                projects = json.load(f)
                if username:
                    return [p for p in projects if p.get("user") == username]
                return projects
    return []


def save_projects(projects):
    lock = filelock.FileLock(f"{PROJECTS_FILE}.lock")
    with lock:
        with open(PROJECTS_FILE, "w", encoding="utf-8") as f:
            json.dump(projects, f, ensure_ascii=False, indent=2)


# ============ AUTH ROUTES ============

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        
        users = load_users()
        if username in users and users[username]["password"] == hash_password(password):
            session["user"] = username
            return redirect(url_for("index"))
        return render_template("login.html", error="Sai tên đăng nhập hoặc mật khẩu")
    
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("login"))


@app.route("/register")
def register():
    # Chuyển hướng về trang login - chỉ admin mới tạo được tài khoản
    return redirect(url_for("login"))


# ============ MAIN ROUTES ============

@app.route("/")
@login_required
def index():
    users = load_users()
    user_data = users.get(session["user"], None)
    
    # Nếu user không tồn tại (đã bị xóa), logout
    if user_data is None:
        session.pop("user", None)
        return redirect(url_for("login"))
    
    voices = [
        {"code": code, "name": v.name, "region": v.region, "gender": v.gender,
         "display": f"{v.name} ({v.region}, {v.gender})"}
        for code, v in VOICES.items()
    ]
    history = load_history(session["user"])
    return render_template("index.html", 
                           voices=voices, 
                           history=history,
                           user=session["user"],
                           user_data=user_data)


@app.route("/synthesize", methods=["POST"])
@login_required
def synthesize():
    try:
        text = request.form.get("text", "").strip()
        voice = request.form.get("voice", "hn-quynhanh")
        speed = float(request.form.get("speed", 1.0))
        save_to_history = request.form.get("save_history") == "true"

        if not text:
            return jsonify({"error": "Vui lòng nhập văn bản"}), 400
        
        # Validate voice code
        if voice not in VOICES:
            return jsonify({"error": "Giọng đọc không hợp lệ"}), 400
        
        # Validate speed
        if not (0.5 <= speed <= 2.0):
            return jsonify({"error": "Tốc độ phải từ 0.5 đến 2.0"}), 400

        # Kiểm tra quota user
        users = load_users()
        user_data = users.get(session["user"], {})
        user_remaining = user_data.get("quota", 0) - user_data.get("used", 0)
        
        if len(text) > user_remaining:
            return jsonify({"error": f"Không đủ quota cá nhân. Còn lại: {user_remaining:,} ký tự"}), 400

        # Kiểm tra quota Viettel AI
        settings = load_settings()
        viettel_remaining = settings.get("viettel_quota", 0) - settings.get("viettel_used", 0)
        
        if len(text) > viettel_remaining:
            return jsonify({"error": f"Hết quota Viettel AI. Còn lại: {viettel_remaining:,} ký tự. Liên hệ admin để nạp thêm."}), 400

        audio_data = tts.synthesize(text=text, voice=voice, speed=speed)

        # Cập nhật quota user đã dùng
        users[session["user"]]["used"] = user_data.get("used", 0) + len(text)
        save_users(users)
        
        # Cập nhật viettel_used (tự động track)
        settings["viettel_used"] = settings.get("viettel_used", 0) + len(text)
        settings["updated_at"] = datetime.now().strftime("%d/%m/%Y %H:%M")
        save_settings(settings)

        if save_to_history:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{session['user']}_{timestamp}_{voice}.wav"
            filepath = os.path.join(AUDIO_DIR, filename)
            with open(filepath, "wb") as f:
                f.write(audio_data)

            history = load_history()
            history.insert(0, {
                "id": timestamp,
                "user": session["user"],
                "filename": filename,
                "text": text[:100] + "..." if len(text) > 100 else text,
                "full_text": text,
                "chars": len(text),
                "voice": voice,
                "voice_name": VOICES[voice].name,
                "created_at": datetime.now().strftime("%d/%m/%Y %H:%M"),
            })
            # Giữ tối đa 100 items và dọn dẹp file cũ
            if len(history) > 100:
                old_items = history[100:]
                for item in old_items:
                    old_filepath = os.path.join(AUDIO_DIR, item.get("filename", ""))
                    if os.path.exists(old_filepath):
                        try:
                            os.remove(old_filepath)
                        except:
                            pass
                history = history[:100]
            save_history(history)

        return send_file(io.BytesIO(audio_data), mimetype="audio/wav", download_name="output.wav")
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/convert-mp3", methods=["POST"])
@login_required
def convert_to_mp3():
    """File từ Viettel đã là MP3, trả về trực tiếp"""
    try:
        if 'audio' not in request.files:
            return jsonify({"error": "Không có file audio"}), 400
        
        audio_file = request.files['audio']
        # File từ Viettel đã là MP3, trả về trực tiếp
        return send_file(audio_file, mimetype="audio/mpeg", as_attachment=True, download_name="zoneshop_audio.mp3")
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/user/quota")
@login_required
def get_user_quota():
    users = load_users()
    user_data = users.get(session["user"], {})
    return jsonify({
        "quota": user_data.get("quota", 0),
        "used": user_data.get("used", 0),
        "remaining": user_data.get("quota", 0) - user_data.get("used", 0)
    })


@app.route("/user/change-password", methods=["POST"])
@login_required
def change_password():
    try:
        data = request.json
        current_password = data.get("current_password", "")
        new_password = data.get("new_password", "")
        
        if len(new_password) < 6:
            return jsonify({"error": "Mật khẩu mới phải có ít nhất 6 ký tự"}), 400
        
        users = load_users()
        user_data = users.get(session["user"], {})
        
        if user_data.get("password") != hash_password(current_password):
            return jsonify({"error": "Mật khẩu hiện tại không đúng"}), 400
        
        users[session["user"]]["password"] = hash_password(new_password)
        save_users(users)
        return jsonify({"success": True, "message": "Đổi mật khẩu thành công"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============ ADMIN ROUTES ============

@app.route("/admin")
@admin_required
def admin_panel():
    users = load_users()
    settings = load_settings()
    return render_template("admin.html", users=users, settings=settings, current_user=session["user"])


@app.route("/admin/users", methods=["GET"])
@admin_required
def get_users():
    users = load_users()
    return jsonify([
        {"username": k, **{key: v for key, v in val.items() if key != "password"}}
        for k, val in users.items()
    ])


@app.route("/admin/user/<username>/quota", methods=["POST"])
@admin_required
def set_user_quota(username):
    try:
        new_quota = int(request.json.get("quota", 0))
        users = load_users()
        settings = load_settings()
        
        if username not in users:
            return jsonify({"error": "User không tồn tại"}), 404
        
        # Admin không bị giới hạn quota
        if users[username].get("role") == "admin":
            users[username]["quota"] = new_quota
            save_users(users)
            return jsonify({"success": True, "quota": new_quota})
        
        # Tính quota đã cấp cho các user khác (không tính admin và user hiện tại)
        total_allocated_others = sum(
            u.get("quota", 0) for name, u in users.items() 
            if name != username and u.get("role") != "admin"
        )
        users_used = sum(u.get("used", 0) for u in users.values())
        
        # Tính hạn mức còn lại từ Viettel
        viettel_quota = settings.get("viettel_quota", 50000)
        viettel_used = settings.get("viettel_used", 0)
        viettel_remaining = viettel_quota - viettel_used
        
        # Còn có thể cấp = Hạn mức còn lại - Quota chưa dùng của users khác
        available = viettel_remaining - (total_allocated_others - users_used) + users[username].get("used", 0)
        
        if new_quota > available:
            return jsonify({"error": f"Không đủ quota. Còn có thể cấp tối đa: {available:,} ký tự"}), 400
        
        users[username]["quota"] = new_quota
        save_users(users)
        return jsonify({"success": True, "quota": new_quota})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/admin/user/<username>/reset", methods=["POST"])
@admin_required
def reset_user_usage(username):
    users = load_users()
    if username not in users:
        return jsonify({"error": "User không tồn tại"}), 404
    users[username]["used"] = 0
    save_users(users)
    return jsonify({"success": True})


@app.route("/admin/user/<username>/password", methods=["POST"])
@admin_required
def reset_user_password(username):
    try:
        new_password = request.json.get("password", "")
        if len(new_password) < 6:
            return jsonify({"error": "Mật khẩu phải có ít nhất 6 ký tự"}), 400
        
        users = load_users()
        if username not in users:
            return jsonify({"error": "User không tồn tại"}), 404
        
        users[username]["password"] = hash_password(new_password)
        save_users(users)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/admin/user/<username>", methods=["DELETE"])
@admin_required
def delete_user(username):
    if username == "admin":
        return jsonify({"error": "Không thể xóa admin"}), 400
    users = load_users()
    if username not in users:
        return jsonify({"error": "User không tồn tại"}), 404
    del users[username]
    save_users(users)
    return jsonify({"success": True})


@app.route("/admin/user/create", methods=["POST"])
@admin_required
def create_user():
    try:
        data = request.json
        username = data.get("username", "").strip()
        password = data.get("password", "")
        quota = int(data.get("quota", 10000))
        role = data.get("role", "user")
        
        if len(username) < 3 or len(password) < 6:
            return jsonify({"error": "Username >= 3 ký tự, Password >= 6 ký tự"}), 400
        
        users = load_users()
        settings = load_settings()
        
        if username in users:
            return jsonify({"error": "Username đã tồn tại"}), 400
        
        # Kiểm tra quota còn có thể cấp (không tính admin)
        if role != "admin":
            total_allocated = sum(u.get("quota", 0) for u in users.values() if u.get("role") != "admin")
            viettel_quota = settings.get("viettel_quota", 50000)
            available = viettel_quota - total_allocated
            
            if quota > available:
                return jsonify({"error": f"Không đủ quota. Còn có thể cấp tối đa: {available:,} ký tự"}), 400
        
        users[username] = {
            "password": hash_password(password),
            "role": role,
            "quota": quota,
            "used": 0,
            "created_at": datetime.now().strftime("%d/%m/%Y %H:%M")
        }
        save_users(users)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============ VIETTEL QUOTA MANAGEMENT ============

@app.route("/admin/viettel-quota", methods=["GET"])
@admin_required
def get_viettel_quota():
    settings = load_settings()
    users = load_users()
    
    # Tính toán từ users - không tính admin vào quota allocation
    total_quota_allocated = sum(u.get("quota", 0) for name, u in users.items() if u.get("role") != "admin")
    users_used = sum(u.get("used", 0) for u in users.values())  # Tổng users đã dùng
    
    viettel_quota = settings.get("viettel_quota", 50000)
    viettel_used = settings.get("viettel_used", 0)  # Từ Viettel AI dashboard
    viettel_remaining = viettel_quota - viettel_used
    
    # Còn có thể cấp = Hạn mức còn lại - Quota chưa dùng của users
    available_to_allocate = viettel_remaining - (total_quota_allocated - users_used)
    
    return jsonify({
        "viettel_quota": viettel_quota,
        "viettel_used": viettel_used,
        "viettel_remaining": viettel_remaining,
        "total_allocated": total_quota_allocated,
        "users_used": users_used,
        "available_to_allocate": available_to_allocate
    })


@app.route("/admin/viettel-quota", methods=["POST"])
@admin_required
def update_viettel_quota():
    try:
        data = request.json
        settings = load_settings()
        
        if "viettel_quota" in data:
            settings["viettel_quota"] = int(data["viettel_quota"])
        if "viettel_used" in data:
            settings["viettel_used"] = int(data["viettel_used"])
        
        settings["updated_at"] = datetime.now().strftime("%d/%m/%Y %H:%M")
        save_settings(settings)
        return jsonify({"success": True, "settings": settings})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============ OTHER ROUTES ============

@app.route("/demo/<voice>")
@login_required
def demo_voice(voice):
    try:
        if voice not in VOICES:
            return jsonify({"error": "Giọng không hợp lệ"}), 400

        demo_dir = os.path.join(AUDIO_DIR, "demos")
        os.makedirs(demo_dir, exist_ok=True)
        cache_file = os.path.join(demo_dir, f"{voice}.wav")

        if os.path.exists(cache_file):
            return send_file(cache_file, mimetype="audio/wav")

        v = VOICES[voice]
        demo_text = f"Xin chào, tôi là {v.name}, giọng {v.gender.lower()} {v.region}."
        audio_data = tts.synthesize(text=demo_text, voice=voice, speed=1.0)

        with open(cache_file, "wb") as f:
            f.write(audio_data)

        return send_file(io.BytesIO(audio_data), mimetype="audio/wav")
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/history")
@login_required
def get_history():
    return jsonify(load_history(session["user"]))


@app.route("/history/<file_id>")
@login_required
def get_history_audio(file_id):
    for item in load_history(session["user"]):
        if item["id"] == file_id:
            filepath = os.path.join(AUDIO_DIR, item["filename"])
            if os.path.exists(filepath):
                return send_file(filepath, mimetype="audio/wav")
    return jsonify({"error": "File không tồn tại"}), 404


@app.route("/history/<file_id>/download")
@login_required
def download_history_audio(file_id):
    for item in load_history(session["user"]):
        if item["id"] == file_id:
            filepath = os.path.join(AUDIO_DIR, item["filename"])
            if os.path.exists(filepath):
                # File từ Viettel đã là MP3, chỉ đổi tên
                mp3_filename = item["filename"].replace(".wav", ".mp3")
                return send_file(filepath, mimetype="audio/mpeg", as_attachment=True, download_name=mp3_filename)
    return jsonify({"error": "File không tồn tại"}), 404


@app.route("/history/<file_id>", methods=["DELETE"])
@login_required
def delete_history_item(file_id):
    history = load_history()
    for i, item in enumerate(history):
        if item["id"] == file_id and item.get("user") == session["user"]:
            filepath = os.path.join(AUDIO_DIR, item["filename"])
            if os.path.exists(filepath):
                os.remove(filepath)
            history.pop(i)
            save_history(history)
            return jsonify({"success": True})
    return jsonify({"error": "Không tìm thấy"}), 404


# ============ PROJECT ROUTES ============

@app.route("/projects")
@login_required
def get_projects():
    return jsonify(load_projects(session["user"]))


@app.route("/project/create", methods=["POST"])
@login_required
def create_project():
    try:
        data = request.json
        name = data.get("name", "").strip()
        
        if not name:
            return jsonify({"error": "Tên dự án không được để trống"}), 400
        
        projects = load_projects()
        project_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Tạo thư mục cho project
        project_dir = os.path.join(AUDIO_DIR, "projects", session["user"], project_id)
        os.makedirs(project_dir, exist_ok=True)
        
        projects.append({
            "id": project_id,
            "user": session["user"],
            "name": name,
            "description": data.get("description", ""),
            "clips": [],
            "created_at": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "updated_at": datetime.now().strftime("%d/%m/%Y %H:%M")
        })
        save_projects(projects)
        return jsonify({"success": True, "project_id": project_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/project/<project_id>")
@login_required
def get_project(project_id):
    for project in load_projects(session["user"]):
        if project["id"] == project_id:
            return jsonify(project)
    return jsonify({"error": "Dự án không tồn tại"}), 404


@app.route("/project/<project_id>", methods=["PUT"])
@login_required
def update_project(project_id):
    try:
        data = request.json
        projects = load_projects()
        
        for project in projects:
            if project["id"] == project_id and project["user"] == session["user"]:
                if "name" in data:
                    project["name"] = data["name"]
                if "description" in data:
                    project["description"] = data["description"]
                project["updated_at"] = datetime.now().strftime("%d/%m/%Y %H:%M")
                save_projects(projects)
                return jsonify({"success": True})
        
        return jsonify({"error": "Dự án không tồn tại"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/project/<project_id>", methods=["DELETE"])
@login_required
def delete_project(project_id):
    try:
        projects = load_projects()
        
        for i, project in enumerate(projects):
            if project["id"] == project_id and project["user"] == session["user"]:
                # Xóa tất cả file audio của project
                project_dir = os.path.join(AUDIO_DIR, "projects", session["user"], project_id)
                if os.path.exists(project_dir):
                    import shutil
                    shutil.rmtree(project_dir)
                
                projects.pop(i)
                save_projects(projects)
                return jsonify({"success": True})
        
        return jsonify({"error": "Dự án không tồn tại"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/project/<project_id>/clip", methods=["POST"])
@login_required
def add_clip_to_project(project_id):
    try:
        text = request.form.get("text", "").strip()
        voice = request.form.get("voice", "hn-quynhanh")
        speed = float(request.form.get("speed", 1.0))
        clip_name = request.form.get("clip_name", "")

        if not text:
            return jsonify({"error": "Vui lòng nhập văn bản"}), 400
        
        if voice not in VOICES:
            return jsonify({"error": "Giọng đọc không hợp lệ"}), 400

        # Kiểm tra quota
        users = load_users()
        user_data = users.get(session["user"], {})
        user_remaining = user_data.get("quota", 0) - user_data.get("used", 0)
        
        if len(text) > user_remaining:
            return jsonify({"error": f"Không đủ quota. Còn lại: {user_remaining:,} ký tự"}), 400

        settings = load_settings()
        viettel_remaining = settings.get("viettel_quota", 0) - settings.get("viettel_used", 0)
        
        if len(text) > viettel_remaining:
            return jsonify({"error": f"Hết quota Viettel AI. Còn lại: {viettel_remaining:,} ký tự"}), 400

        # Tìm project
        projects = load_projects()
        project = None
        project_idx = -1
        
        for i, p in enumerate(projects):
            if p["id"] == project_id and p["user"] == session["user"]:
                project = p
                project_idx = i
                break
        
        if not project:
            return jsonify({"error": "Dự án không tồn tại"}), 404

        # Tạo audio
        audio_data = tts.synthesize(text=text, voice=voice, speed=speed)

        # Cập nhật quota
        users[session["user"]]["used"] = user_data.get("used", 0) + len(text)
        save_users(users)
        
        settings["viettel_used"] = settings.get("viettel_used", 0) + len(text)
        settings["updated_at"] = datetime.now().strftime("%d/%m/%Y %H:%M")
        save_settings(settings)

        # Lưu file
        clip_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"{clip_id}_{voice}.wav"
        project_dir = os.path.join(AUDIO_DIR, "projects", session["user"], project_id)
        os.makedirs(project_dir, exist_ok=True)
        filepath = os.path.join(project_dir, filename)
        
        with open(filepath, "wb") as f:
            f.write(audio_data)

        # Thêm clip vào project
        clip = {
            "id": clip_id,
            "name": clip_name or f"Clip {len(project['clips']) + 1}",
            "text": text,
            "voice": voice,
            "voice_name": VOICES[voice].name,
            "speed": speed,
            "filename": filename,
            "chars": len(text),
            "order": len(project["clips"]),
            "created_at": datetime.now().strftime("%d/%m/%Y %H:%M")
        }
        
        projects[project_idx]["clips"].append(clip)
        projects[project_idx]["updated_at"] = datetime.now().strftime("%d/%m/%Y %H:%M")
        save_projects(projects)

        return jsonify({"success": True, "clip": clip})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/project/<project_id>/clip/<clip_id>")
@login_required
def get_clip_audio(project_id, clip_id):
    for project in load_projects(session["user"]):
        if project["id"] == project_id:
            for clip in project["clips"]:
                if clip["id"] == clip_id:
                    filepath = os.path.join(AUDIO_DIR, "projects", session["user"], project_id, clip["filename"])
                    if os.path.exists(filepath):
                        return send_file(filepath, mimetype="audio/wav")
    return jsonify({"error": "File không tồn tại"}), 404


@app.route("/project/<project_id>/clip/<clip_id>/download")
@login_required
def download_clip_audio(project_id, clip_id):
    """Tải clip dưới dạng MP3"""
    for project in load_projects(session["user"]):
        if project["id"] == project_id:
            for clip in project["clips"]:
                if clip["id"] == clip_id:
                    filepath = os.path.join(AUDIO_DIR, "projects", session["user"], project_id, clip["filename"])
                    if os.path.exists(filepath):
                        # File từ Viettel đã là MP3
                        mp3_filename = f"{clip['name']}.mp3"
                        return send_file(filepath, mimetype="audio/mpeg", as_attachment=True, download_name=mp3_filename)
    return jsonify({"error": "File không tồn tại"}), 404


@app.route("/project/<project_id>/download")
@login_required
def download_project(project_id):
    """Tải toàn bộ dự án - ghép tất cả clips thành 1 file MP3"""
    for project in load_projects(session["user"]):
        if project["id"] == project_id:
            if not project["clips"]:
                return jsonify({"error": "Dự án chưa có clip nào"}), 400
            
            # Nếu chỉ có 1 clip, tải trực tiếp
            if len(project["clips"]) == 1:
                clip = project["clips"][0]
                filepath = os.path.join(AUDIO_DIR, "projects", session["user"], project_id, clip["filename"])
                if os.path.exists(filepath):
                    safe_name = "".join(c for c in project["name"] if c.isalnum() or c in (' ', '-', '_')).strip()
                    return send_file(filepath, mimetype="audio/mpeg", as_attachment=True, download_name=f"{safe_name}.mp3")
            
            # Nhiều clips - cần pydub để ghép
            if not PYDUB_AVAILABLE:
                return jsonify({"error": "Chức năng ghép audio chưa khả dụng. Vui lòng tải từng clip."}), 400
            
            try:
                combined = AudioSegment.empty()
                silence = AudioSegment.silent(duration=500)
                
                for clip in project["clips"]:
                    filepath = os.path.join(AUDIO_DIR, "projects", session["user"], project_id, clip["filename"])
                    if os.path.exists(filepath):
                        audio = AudioSegment.from_file(filepath)
                        if len(combined) > 0:
                            combined += silence
                        combined += audio
                
                mp3_buffer = io.BytesIO()
                combined.export(mp3_buffer, format="mp3", bitrate="192k")
                mp3_buffer.seek(0)
                
                safe_name = "".join(c for c in project["name"] if c.isalnum() or c in (' ', '-', '_')).strip()
                return send_file(mp3_buffer, mimetype="audio/mpeg", as_attachment=True, download_name=f"{safe_name}.mp3")
            except Exception as e:
                return jsonify({"error": str(e)}), 500
    
    return jsonify({"error": "Dự án không tồn tại"}), 404


@app.route("/project/<project_id>/clip/<clip_id>", methods=["DELETE"])
@login_required
def delete_clip(project_id, clip_id):
    try:
        projects = load_projects()
        
        for i, project in enumerate(projects):
            if project["id"] == project_id and project["user"] == session["user"]:
                for j, clip in enumerate(project["clips"]):
                    if clip["id"] == clip_id:
                        # Xóa file
                        filepath = os.path.join(AUDIO_DIR, "projects", session["user"], project_id, clip["filename"])
                        if os.path.exists(filepath):
                            os.remove(filepath)
                        
                        projects[i]["clips"].pop(j)
                        projects[i]["updated_at"] = datetime.now().strftime("%d/%m/%Y %H:%M")
                        save_projects(projects)
                        return jsonify({"success": True})
        
        return jsonify({"error": "Không tìm thấy"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/project/<project_id>/reorder", methods=["POST"])
@login_required
def reorder_clips(project_id):
    try:
        data = request.json
        clip_ids = data.get("clip_ids", [])
        
        projects = load_projects()
        
        for i, project in enumerate(projects):
            if project["id"] == project_id and project["user"] == session["user"]:
                # Sắp xếp lại clips theo thứ tự mới
                clips_dict = {c["id"]: c for c in project["clips"]}
                new_clips = []
                for order, cid in enumerate(clip_ids):
                    if cid in clips_dict:
                        clips_dict[cid]["order"] = order
                        new_clips.append(clips_dict[cid])
                
                projects[i]["clips"] = new_clips
                projects[i]["updated_at"] = datetime.now().strftime("%d/%m/%Y %H:%M")
                save_projects(projects)
                return jsonify({"success": True})
        
        return jsonify({"error": "Dự án không tồn tại"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/project/<project_id>/export")
@login_required
def export_project(project_id):
    try:
        import zipfile
        from io import BytesIO
        
        for project in load_projects(session["user"]):
            if project["id"] == project_id:
                # Tạo zip file
                zip_buffer = BytesIO()
                project_dir = os.path.join(AUDIO_DIR, "projects", session["user"], project_id)
                
                with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                    for clip in project["clips"]:
                        filepath = os.path.join(project_dir, clip["filename"])
                        if os.path.exists(filepath):
                            # Đặt tên file theo thứ tự và tên clip
                            arcname = f"{clip['order']+1:02d}_{clip['name']}.wav"
                            zip_file.write(filepath, arcname)
                
                zip_buffer.seek(0)
                return send_file(
                    zip_buffer,
                    mimetype='application/zip',
                    as_attachment=True,
                    download_name=f"{project['name']}.zip"
                )
        
        return jsonify({"error": "Dự án không tồn tại"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    print(f"Server: http://localhost:{port}")
    print("Admin: admin / admin123")
    app.run(debug=debug, host="0.0.0.0", port=port)
