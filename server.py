import base64
import io
import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib import error, parse, request
from zoneinfo import ZoneInfo

import numpy as np
from PIL import Image, ImageOps
from flask import Flask, jsonify, request as flask_request, send_from_directory
from flask_cors import CORS


def load_local_env() -> None:
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_local_env()

APP_TZ = ZoneInfo("Asia/Kolkata")
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "student-faces")
SUPABASE_STUDENTS_TABLE = os.getenv("SUPABASE_STUDENTS_TABLE", "students")
SUPABASE_ATTENDANCE_TABLE = os.getenv("SUPABASE_ATTENDANCE_TABLE", "attendance_records")
FACE_MATCH_THRESHOLD = float(os.getenv("FACE_MATCH_THRESHOLD", "50"))
APP_PORT = int(os.getenv("APP_PORT", "5050"))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UI_DIR = os.path.join(BASE_DIR, "ui")

app = Flask(__name__, static_folder=UI_DIR, static_url_path="")
CORS(app)


class SupabaseError(Exception):
    pass


class SupabaseClient:
    def __init__(self, url: str, service_role_key: str):
        self.url = url
        self.service_role_key = service_role_key
        self.opener = request.build_opener(request.ProxyHandler({}))

    def _headers(
        self,
        *,
        bearer_token: Optional[str] = None,
        extra: Optional[Dict[str, str]] = None,
        json_body: bool = True,
    ) -> Dict[str, str]:
        headers = {
            "apikey": self.service_role_key,
            "Authorization": f"Bearer {bearer_token or self.service_role_key}",
            "Accept": "application/json",
        }
        if json_body:
            headers["Content-Type"] = "application/json"
        if extra:
            headers.update(extra)
        return headers

    def request_json(
        self,
        method: str,
        path: str,
        *,
        body: Optional[Any] = None,
        query: Optional[Dict[str, Any]] = None,
        bearer_token: Optional[str] = None,
        extra_headers: Optional[Dict[str, str]] = None,
        json_body: bool = True,
    ) -> Any:
        url = f"{self.url}{path}"
        if query:
            encoded = parse.urlencode(query, doseq=True)
            url = f"{url}?{encoded}"
        payload = None
        if body is not None:
            payload = json.dumps(body).encode("utf-8") if json_body else body
        req = request.Request(
            url,
            data=payload,
            headers=self._headers(
                bearer_token=bearer_token,
                extra=extra_headers,
                json_body=json_body,
            ),
            method=method,
        )
        try:
            with self.opener.open(req, timeout=30) as response:
                raw = response.read().decode("utf-8")
                if not raw:
                    return {}
                try:
                    return json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise SupabaseError(self._humanize_response_error(raw)) from exc
        except error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="ignore")
            try:
                details = json.loads(raw)
            except json.JSONDecodeError:
                details = {"message": self._humanize_response_error(raw or str(exc))}
            raise SupabaseError(details.get("msg") or details.get("message") or str(details))
        except error.URLError as exc:
            raise SupabaseError(f"Could not reach Supabase: {exc.reason}")

    def request_bytes(
        self,
        method: str,
        path: str,
        *,
        body: Optional[bytes] = None,
        bearer_token: Optional[str] = None,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> bytes:
        req = request.Request(
            f"{self.url}{path}",
            data=body,
            headers=self._headers(
                bearer_token=bearer_token,
                extra=extra_headers,
                json_body=False,
            ),
            method=method,
        )
        try:
            with self.opener.open(req, timeout=30) as response:
                return response.read()
        except error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="ignore")
            raise SupabaseError(self._humanize_response_error(raw or str(exc)))
        except error.URLError as exc:
            raise SupabaseError(f"Could not reach Supabase: {exc.reason}")

    @staticmethod
    def _humanize_response_error(raw: str) -> str:
        lower = raw.lower()
        if "<html" in lower or "<!doctype html" in lower:
            return "Supabase returned an HTML page instead of the API response. Check SUPABASE_URL in .env and use the Project URL from Supabase Settings > API, for example https://your-project-ref.supabase.co"
        return raw

    def table_select(
        self,
        table: str,
        *,
        columns: str = "*",
        filters: Optional[Dict[str, str]] = None,
        order: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        query: Dict[str, Any] = {"select": columns}
        if filters:
            query.update(filters)
        if order:
            query["order"] = order
        if limit is not None:
            query["limit"] = limit
        return self.request_json("GET", f"/rest/v1/{table}", query=query)

    def table_insert(self, table: str, payload: Any) -> List[Dict[str, Any]]:
        return self.request_json(
            "POST",
            f"/rest/v1/{table}",
            body=payload,
            extra_headers={"Prefer": "return=representation"},
        )

    def table_patch(self, table: str, payload: Dict[str, Any], *, filters: Dict[str, str]) -> List[Dict[str, Any]]:
        return self.request_json(
            "PATCH",
            f"/rest/v1/{table}",
            body=payload,
            query=filters,
            extra_headers={"Prefer": "return=representation"},
        )

    def create_auth_user(self, email: str, password: str, user_metadata: Dict[str, Any]) -> Dict[str, Any]:
        return self.request_json(
            "POST",
            "/auth/v1/admin/users",
            body={
                "email": email,
                "password": password,
                "email_confirm": True,
                "user_metadata": user_metadata,
            },
        )

    def sign_in_password(self, email: str, password: str) -> Dict[str, Any]:
        return self.request_json(
            "POST",
            "/auth/v1/token",
            body={"email": email, "password": password},
            query={"grant_type": "password"},
        )

    def get_authenticated_user(self, access_token: str) -> Dict[str, Any]:
        return self.request_json("GET", "/auth/v1/user", bearer_token=access_token)

    def upload_file(self, object_path: str, file_bytes: bytes, content_type: str) -> Dict[str, Any]:
        safe_path = parse.quote(object_path, safe="/")
        return self.request_json(
            "POST",
            f"/storage/v1/object/{SUPABASE_BUCKET}/{safe_path}",
            body=file_bytes,
            extra_headers={"Content-Type": content_type, "x-upsert": "true"},
            json_body=False,
        )

    def download_file(self, object_path: str) -> bytes:
        safe_path = parse.quote(object_path, safe="/")
        return self.request_bytes("GET", f"/storage/v1/object/{SUPABASE_BUCKET}/{safe_path}")


supabase = SupabaseClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY) if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY else None


def ensure_supabase() -> SupabaseClient:
    if not supabase:
        raise SupabaseError("Supabase is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")
    return supabase


def now_ist() -> datetime:
    return datetime.now(APP_TZ)


def today_iso() -> str:
    return now_ist().strftime("%Y-%m-%d")


def current_time_iso() -> str:
    return now_ist().strftime("%H:%M:%S")


def json_error(message: str, status: int = 400):
    return jsonify({"success": False, "message": message}), status


def decode_data_url(data_url: str) -> bytes:
    if not data_url or "," not in data_url:
        raise ValueError("Invalid image payload")
    return base64.b64decode(data_url.split(",", 1)[1])


def infer_image_extension(data_url: str) -> str:
    prefix = data_url.split(",", 1)[0].lower()
    if "png" in prefix:
        return "png"
    if "webp" in prefix:
        return "webp"
    return "jpg"


def student_face_object_paths(roll_no: str, count: int = 5) -> List[str]:
    return [f"{roll_no}/faces/face_{index + 1}.jpg" for index in range(count)]


def student_profile_object_path(roll_no: str, extension: str) -> str:
    return f"{roll_no}/profile/profile.{extension}"


def normalize_text(value: Optional[str]) -> str:
    return (value or "").strip()


def first_or_none(rows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    return rows[0] if rows else None


def load_student_by_roll(roll_no: str) -> Optional[Dict[str, Any]]:
    client = ensure_supabase()
    rows = client.table_select(
        SUPABASE_STUDENTS_TABLE,
        filters={"roll_no": f"eq.{roll_no}"},
        limit=1,
    )
    return first_or_none(rows)


def load_student_by_email(email: str) -> Optional[Dict[str, Any]]:
    client = ensure_supabase()
    rows = client.table_select(
        SUPABASE_STUDENTS_TABLE,
        filters={"email": f"eq.{email}"},
        limit=1,
    )
    return first_or_none(rows)


def preprocess_image(image_bytes: bytes, *, size: int = 160) -> Dict[str, Any]:
    with Image.open(io.BytesIO(image_bytes)) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        width, height = image.size
        if width == 0 or height == 0:
            raise ValueError("Image is empty")
        side = min(width, height)
        left = (width - side) / 2
        top = (height - side) / 2
        image = image.crop((left, top, left + side, top + side))
        image = image.resize((size, size), Image.Resampling.LANCZOS)
        grayscale = ImageOps.grayscale(image)

    raw_array = np.asarray(grayscale, dtype=np.float32)
    normalized = raw_array / 255.0
    centered = normalized - float(normalized.mean())
    scale = float(centered.std()) or 1e-6
    normalized = centered / scale

    center_crop = grayscale.crop((size * 0.18, size * 0.10, size * 0.82, size * 0.88)).resize(
        (96, 96),
        Image.Resampling.LANCZOS,
    )
    center_array = np.asarray(center_crop, dtype=np.float32)
    center_norm = center_array / 255.0
    center_centered = center_norm - float(center_norm.mean())
    center_scale = float(center_centered.std()) or 1e-6
    center_norm = center_centered / center_scale

    reduced = grayscale.resize((17, 16), Image.Resampling.LANCZOS)
    reduced_array = np.asarray(reduced, dtype=np.float32)
    dhash_bits = reduced_array[:, 1:] > reduced_array[:, :-1]

    ahash_small = grayscale.resize((16, 16), Image.Resampling.LANCZOS)
    ahash_array = np.asarray(ahash_small, dtype=np.float32)
    ahash_bits = ahash_array > float(ahash_array.mean())

    center_hash_small = center_crop.resize((16, 16), Image.Resampling.LANCZOS)
    center_hash_array = np.asarray(center_hash_small, dtype=np.float32)
    center_hash_bits = center_hash_array > float(center_hash_array.mean())

    histogram, _ = np.histogram(raw_array, bins=32, range=(0, 255), density=True)
    center_histogram, _ = np.histogram(center_array, bins=32, range=(0, 255), density=True)

    return {
        "raw": raw_array,
        "normalized": normalized,
        "center_normalized": center_norm,
        "hash": dhash_bits,
        "ahash": ahash_bits,
        "center_hash": center_hash_bits,
        "histogram": histogram,
        "center_histogram": center_histogram,
    }


def compare_faces(reference: Dict[str, Any], probe: Dict[str, Any]) -> float:
    cosine = float(np.mean(reference["normalized"] * probe["normalized"]))
    cosine_score = max(0.0, min((cosine + 1.0) / 2.0, 1.0))

    center_cosine = float(np.mean(reference["center_normalized"] * probe["center_normalized"]))
    center_cosine_score = max(0.0, min((center_cosine + 1.0) / 2.0, 1.0))

    hamming_distance = np.count_nonzero(reference["hash"] != probe["hash"])
    hash_score = 1.0 - (hamming_distance / reference["hash"].size)

    ahash_distance = np.count_nonzero(reference["ahash"] != probe["ahash"])
    ahash_score = 1.0 - (ahash_distance / reference["ahash"].size)

    center_hash_distance = np.count_nonzero(reference["center_hash"] != probe["center_hash"])
    center_hash_score = 1.0 - (center_hash_distance / reference["center_hash"].size)

    hist_score = float(np.minimum(reference["histogram"], probe["histogram"]).sum())
    hist_score = max(0.0, min(hist_score, 1.0))

    center_hist_score = float(np.minimum(reference["center_histogram"], probe["center_histogram"]).sum())
    center_hist_score = max(0.0, min(center_hist_score, 1.0))

    confidence = (
        center_cosine_score * 0.34
        + cosine_score * 0.18
        + center_hash_score * 0.18
        + hash_score * 0.10
        + ahash_score * 0.08
        + center_hist_score * 0.08
        + hist_score * 0.04
    ) * 100.0
    return round(confidence, 2)


def mirrored_image_bytes(image_bytes: bytes) -> bytes:
    with Image.open(io.BytesIO(image_bytes)) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        flipped = ImageOps.mirror(image)
        output = io.BytesIO()
        flipped.save(output, format="JPEG", quality=95)
        return output.getvalue()


def compute_student_stats(student: Dict[str, Any]) -> Dict[str, Any]:
    client = ensure_supabase()
    roll_no = student["roll_no"]

    attendance_rows = client.table_select(
        SUPABASE_ATTENDANCE_TABLE,
        columns="attendance_date",
        filters={"roll_no": f"eq.{roll_no}"},
        order="attendance_date.desc",
    )
    present_count = len(attendance_rows)

    all_days = client.table_select(
        SUPABASE_ATTENDANCE_TABLE,
        columns="attendance_date",
    )
    total_days = len({row["attendance_date"] for row in all_days if row.get("attendance_date")})
    absent_count = max(total_days - present_count, 0)
    percentage = round((present_count / total_days) * 100, 2) if total_days else 0.0

    return {
        "present": present_count,
        "absent": absent_count,
        "percentage": percentage,
    }


def serialize_student(student: Dict[str, Any], *, include_stats: bool = False) -> Dict[str, Any]:
    payload = {
        "id": student.get("id"),
        "name": student.get("full_name") or f'{student.get("first_name", "")} {student.get("last_name", "")}'.strip(),
        "roll_no": student.get("roll_no"),
        "dept": student.get("department"),
        "department": student.get("department"),
        "year": student.get("year"),
        "email": student.get("email"),
        "phone": student.get("phone"),
    }
    if include_stats:
        payload.update(compute_student_stats(student))
    return payload


def mark_attendance(student: Dict[str, Any], confidence: float) -> Dict[str, Any]:
    client = ensure_supabase()
    attendance_date = today_iso()

    existing = client.table_select(
        SUPABASE_ATTENDANCE_TABLE,
        filters={
            "roll_no": f"eq.{student['roll_no']}",
            "attendance_date": f"eq.{attendance_date}",
        },
        limit=1,
    )
    if existing:
        return {"already_marked": True, "record": existing[0]}

    inserted = client.table_insert(
        SUPABASE_ATTENDANCE_TABLE,
        [
            {
                "student_id": student.get("id"),
                "roll_no": student["roll_no"],
                "full_name": student.get("full_name"),
                "department": student.get("department"),
                "year": student.get("year"),
                "attendance_date": attendance_date,
                "attendance_time": current_time_iso(),
                "status": "present",
                "confidence": confidence,
            }
        ],
    )
    return {"already_marked": False, "record": inserted[0] if inserted else {}}


@app.route("/api/register", methods=["POST"])
def register_student():
    try:
        client = ensure_supabase()
        data = flask_request.get_json(force=True) or {}

        roll_no = normalize_text(data.get("studentId"))
        first_name = normalize_text(data.get("firstName"))
        last_name = normalize_text(data.get("lastName"))
        email = normalize_text(data.get("email")).lower()
        phone = normalize_text(data.get("phone"))
        dob = normalize_text(data.get("dob"))
        gender = normalize_text(data.get("gender"))
        department = normalize_text(data.get("dept"))
        year = normalize_text(data.get("year"))
        password = data.get("password", "")
        emergency_name = normalize_text(data.get("emergencyName"))
        emergency_phone = normalize_text(data.get("emergencyPhone"))
        address = normalize_text(data.get("address"))
        profile_photo = data.get("profilePhoto")
        face_images = data.get("faceImages") or []

        if not all([roll_no, first_name, email, password]):
            return json_error("Roll number, first name, email, and password are required.")
        if len(password) < 8:
            return json_error("Password must be at least 8 characters.")
        if len(face_images) < 5:
            return json_error("Please capture or upload all 5 face images.")
        if load_student_by_roll(roll_no):
            return json_error("This roll number is already registered.")
        if load_student_by_email(email):
            return json_error("This email is already registered.")

        auth_user = client.create_auth_user(
            email,
            password,
            {
                "roll_no": roll_no,
                "full_name": f"{first_name} {last_name}".strip(),
            },
        )
        auth_user_id = auth_user.get("id") or auth_user.get("user", {}).get("id")
        if not auth_user_id:
            raise SupabaseError("Supabase auth user could not be created.")

        profile_path = None
        if profile_photo:
            extension = infer_image_extension(profile_photo)
            profile_path = student_profile_object_path(roll_no, extension)
            client.upload_file(profile_path, decode_data_url(profile_photo), f"image/{extension}")

        saved_face_paths = []
        for index, face_data in enumerate(face_images[:5]):
            object_path = student_face_object_paths(roll_no)[index]
            client.upload_file(object_path, decode_data_url(face_data), "image/jpeg")
            saved_face_paths.append(object_path)

        full_name = f"{first_name} {last_name}".strip()
        inserted = client.table_insert(
            SUPABASE_STUDENTS_TABLE,
            [
                {
                    "id": auth_user_id,
                    "user_id": auth_user_id,
                    "roll_no": roll_no,
                    "first_name": first_name,
                    "last_name": last_name,
                    "full_name": full_name,
                    "email": email,
                    "phone": phone,
                    "dob": dob or None,
                    "gender": gender or None,
                    "department": department or None,
                    "year": year or None,
                    "emergency_name": emergency_name or None,
                    "emergency_phone": emergency_phone or None,
                    "address": address or None,
                    "profile_image_path": profile_path,
                    "face_images_count": len(saved_face_paths),
                    "registered_at": now_ist().isoformat(),
                }
            ],
        )

        return jsonify(
            {
                "success": True,
                "message": f"Registration completed for {full_name}.",
                "student": serialize_student(inserted[0] if inserted else {"roll_no": roll_no, "full_name": full_name}),
                "face_images_saved": len(saved_face_paths),
            }
        )
    except (SupabaseError, ValueError) as exc:
        return json_error(str(exc), 400)
    except Exception as exc:
        return json_error(str(exc), 500)


@app.route("/api/login", methods=["POST"])
def login_student():
    try:
        client = ensure_supabase()
        data = flask_request.get_json(force=True) or {}
        roll_no = normalize_text(data.get("rollNo"))
        password = data.get("password", "")

        if not roll_no or not password:
            return json_error("Roll number and password are required.")

        student = load_student_by_roll(roll_no)
        if not student:
            return json_error("Student not found. Please register first.", 404)

        session = client.sign_in_password(student["email"], password)
        access_token = session.get("access_token")
        if not access_token:
            return json_error("Login failed. Please check your credentials.", 401)

        student_payload = serialize_student(student, include_stats=True)
        student_payload["access_token"] = access_token

        return jsonify(
            {
                "success": True,
                "message": f"Welcome {student_payload['name']}. Camera verification required to mark attendance.",
                "student": student_payload,
            }
        )
    except SupabaseError as exc:
        return json_error(str(exc), 401)
    except Exception as exc:
        return json_error(str(exc), 500)


@app.route("/api/recognize", methods=["POST"])
def recognize_and_mark():
    try:
        client = ensure_supabase()
        data = flask_request.get_json(force=True) or {}
        roll_no = normalize_text(data.get("rollNo"))
        image_data = data.get("image")
        access_token = data.get("accessToken", "")

        if not roll_no or not image_data or not access_token:
            return json_error("rollNo, accessToken, and image are required.")

        token_user = client.get_authenticated_user(access_token)
        student = load_student_by_roll(roll_no)
        if not student:
            return json_error("Student not found.", 404)
        if token_user.get("id") not in {student.get("user_id"), student.get("id")}:
            return json_error("This session does not match the selected student.", 403)

        probe_bytes = decode_data_url(image_data)
        probe = preprocess_image(probe_bytes)
        mirrored_probe = preprocess_image(mirrored_image_bytes(probe_bytes))
        best_confidence = 0.0

        for object_path in student_face_object_paths(roll_no, int(student.get("face_images_count") or 5)):
            try:
                reference = preprocess_image(client.download_file(object_path))
            except SupabaseError:
                continue
            confidence = max(
                compare_faces(reference, probe),
                compare_faces(reference, mirrored_probe),
            )
            if confidence > best_confidence:
                best_confidence = confidence

        if best_confidence < FACE_MATCH_THRESHOLD:
            return jsonify(
                {
                    "success": False,
                    "message": "Face did not match the registered images clearly enough.",
                    "confidence": round(best_confidence, 2),
                }
            )

        attendance_result = mark_attendance(student, best_confidence)
        student_payload = serialize_student(student, include_stats=True)

        return jsonify(
            {
                "success": True,
                "message": "Attendance verified successfully.",
                "student": student_payload,
                "confidence": round(best_confidence, 2),
                "already_marked": attendance_result["already_marked"],
            }
        )
    except (SupabaseError, ValueError) as exc:
        return json_error(str(exc), 400)
    except Exception as exc:
        return json_error(str(exc), 500)


@app.route("/api/students", methods=["GET"])
def get_all_students():
    try:
        client = ensure_supabase()
        rows = client.table_select(
            SUPABASE_STUDENTS_TABLE,
            order="registered_at.desc",
        )
        students = [serialize_student(row) for row in rows]
        return jsonify({"success": True, "students": students, "total": len(students)})
    except SupabaseError as exc:
        return json_error(str(exc), 400)
    except Exception as exc:
        return json_error(str(exc), 500)


@app.route("/api/attendance/today", methods=["GET"])
def get_today_attendance():
    try:
        client = ensure_supabase()
        rows = client.table_select(
            SUPABASE_ATTENDANCE_TABLE,
            filters={"attendance_date": f"eq.{today_iso()}"},
            order="attendance_time.asc",
        )
        entries = [
            {
                "roll_no": row.get("roll_no"),
                "name": row.get("full_name"),
                "time": row.get("attendance_time"),
                "department": row.get("department"),
                "dept": row.get("department"),
                "year": row.get("year"),
                "confidence": row.get("confidence"),
            }
            for row in rows
        ]
        return jsonify({"success": True, "entries": entries, "total": len(entries), "date": today_iso()})
    except SupabaseError as exc:
        return json_error(str(exc), 400)
    except Exception as exc:
        return json_error(str(exc), 500)


@app.route("/api/student/<roll_no>", methods=["GET"])
def get_student_details(roll_no: str):
    try:
        student = load_student_by_roll(roll_no)
        if not student:
            return json_error("Student not found.", 404)
        stats = compute_student_stats(student)
        return jsonify(
            {
                "success": True,
                "student": {
                    **serialize_student(student),
                    "first_name": student.get("first_name"),
                    "last_name": student.get("last_name"),
                    "registered_at": student.get("registered_at"),
                    "face_images_count": student.get("face_images_count", 0),
                },
                "attendance_stats": {
                    "total_present": stats["present"],
                    "total_days": stats["present"] + stats["absent"],
                    "percentage": stats["percentage"],
                },
            }
        )
    except SupabaseError as exc:
        return json_error(str(exc), 400)
    except Exception as exc:
        return json_error(str(exc), 500)


@app.route("/api/health", methods=["GET"])
def health_check():
    configured = bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)
    return jsonify(
        {
            "status": "ok",
            "timestamp": now_ist().isoformat(),
            "supabase_configured": configured,
            "bucket": SUPABASE_BUCKET,
            "face_match_threshold": FACE_MATCH_THRESHOLD,
        }
    )


@app.route("/", methods=["GET"])
def serve_index():
    return send_from_directory(UI_DIR, "index.html")


@app.route("/register.html", methods=["GET"])
def serve_register_alias():
    return send_from_directory(os.path.join(UI_DIR, "pages"), "register.html")


@app.route("/register", methods=["GET"])
def serve_register_route():
    return send_from_directory(UI_DIR, "index.html")


@app.route("/attendance.html", methods=["GET"])
def serve_attendance_alias():
    return send_from_directory(os.path.join(UI_DIR, "pages"), "attendance.html")


@app.route("/attendance", methods=["GET"])
def serve_attendance_route():
    return send_from_directory(UI_DIR, "index.html")


@app.route("/<path:path>", methods=["GET"])
def serve_ui(path: str):
    if path.startswith("api/"):
        return json_error("API route not found.", 404)
    return send_from_directory(UI_DIR, path)


if __name__ == "__main__":
    print("\n" + "=" * 64)
    print("FACE ATTENDANCE SYSTEM - SUPABASE BACKEND")
    print("=" * 64)
    print(f"Supabase configured: {'yes' if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY else 'no'}")
    print(f"Server URL: http://localhost:{APP_PORT}")
    print("Endpoints:")
    print("  POST /api/register")
    print("  POST /api/login")
    print("  POST /api/recognize")
    print("  GET  /api/students")
    print("  GET  /api/attendance/today")
    print("  GET  /api/student/<roll_no>")
    print("  GET  /api/health")
    print("=" * 64 + "\n")
    app.run(debug=False, use_reloader=False, host="0.0.0.0", port=APP_PORT)
