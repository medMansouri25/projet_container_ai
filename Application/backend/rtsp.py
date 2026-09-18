"""rtsp.py — Source caméra RTSP pour le Labo, découplée de YOLO/OCR.
--------------------------------------------------------------------
Principe directeur : le RTSP est une simple SOURCE, pas un nouveau pipeline.
Ce module ne connaît ni YOLO ni OCR — son seul rôle est de produire, à partir
d'un flux caméra, soit des frames JPEG pour un aperçu live (MJPEG), soit un
fichier .mp4 réinjecté ensuite dans le pipeline vidéo existant
(labo.stream_video_detection), exactement comme le ferait un upload manuel.

RtspSession : une connexion RTSP + son thread de lecture. `_sessions` (module-
level, protégé par verrou) associe un session_id à chaque session ouverte —
plusieurs connexions en parallèle sont possibles.
"""
import os
import threading
import time
import uuid
from datetime import datetime

# Posé AVANT tout usage d'OpenCV : transport RTSP forcé en TCP (évite les
# flux UDP peu fiables sur Wi-Fi), timeout socket 5 s (évite les blocages
# FFMPEG internes sur un flux qui ne répond plus).
os.environ.setdefault(
    "OPENCV_FFMPEG_CAPTURE_OPTIONS",
    "rtsp_transport;tcp|stimeout;5000000|max_delay;5000000",
)

_OPEN_TIMEOUT = 8.0     # secondes — au-delà, une URL injoignable ne bloque pas la requête
_READ_FAIL_MAX = 30     # lectures ratées consécutives avant de déclarer la connexion perdue


class RtspSession:
    """Connexion à un flux RTSP + boucle de lecture en thread daemon.

    open() : bornée par timeout, distingue explicitement les échecs (timeout
    réseau, flux non disponible, flux ouvert mais aucune image) pour un
    message utile côté utilisateur — jamais d'exception qui remonterait
    jusqu'à casser la requête Flask.
    """

    def __init__(self, url, recordings_dir):
        self.url = url
        self.recordings_dir = recordings_dir
        self.cap = None
        self.connected = False
        self.error = None
        self.width = self.height = None
        self.fps = None

        self._lock = threading.Lock()
        self._frame_jpeg = None
        self._running = False
        self._thread = None

        self._writer = None
        self._recording_name = None
        self._rec_start = None
        self._rec_frames = 0

    # ── Connexion ──────────────────────────────────────────────────────

    def open(self):
        """Retourne (ok: bool, error: str|None). Ouvre cv2.VideoCapture dans
        un thread avec .join(_OPEN_TIMEOUT) : une URL injoignable ne bloque
        jamais la requête HTTP qui a demandé la connexion."""
        import cv2

        result = {}

        def _try_open():
            try:
                result["cap"] = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG)
            except Exception as e:                       # pragma: no cover - defensif
                result["exc"] = str(e)

        t = threading.Thread(target=_try_open, daemon=True)
        t.start()
        t.join(_OPEN_TIMEOUT)

        if t.is_alive():
            return False, f"timeout de connexion ({_OPEN_TIMEOUT:.0f}s) — caméra injoignable ou problème réseau"
        if "exc" in result:
            return False, f"erreur de connexion : {result['exc']}"

        cap = result.get("cap")
        if cap is None or not cap.isOpened():
            return False, "flux RTSP non disponible (adresse invalide, caméra éteinte, ou format non supporté)"

        ok, frame = cap.read()
        if not ok or frame is None:
            cap.release()
            return False, "flux ouvert mais aucune image reçue (codec non supporté)"

        self.cap = cap
        self.height, self.width = frame.shape[:2]
        self.fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
        self._store_frame(frame)

        self.connected = True
        self.error = None
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return True, None

    # ── Boucle de lecture (thread daemon) ─────────────────────────────

    def _loop(self):
        """Lit en continu, stocke la dernière frame encodée en JPEG, écrit
        dans le VideoWriter si un enregistrement est actif. Au-delà de
        _READ_FAIL_MAX lectures ratées consécutives, la session se marque
        déconnectée avec une erreur — sans lever d'exception qui casserait
        le thread silencieusement."""
        fail = 0
        while self._running:
            ok, frame = self.cap.read()
            if not ok or frame is None:
                fail += 1
                if fail >= _READ_FAIL_MAX:
                    self.connected = False
                    self.error = "connexion au flux perdue"
                    break
                continue
            fail = 0
            self._store_frame(frame)
            with self._lock:
                if self._writer is not None:
                    self._writer.write(frame)
                    self._rec_frames += 1
        self._running = False

    def _store_frame(self, frame):
        import cv2
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if ok:
            with self._lock:
                self._frame_jpeg = buf.tobytes()

    def latest_jpeg(self):
        """Dernière frame encodée en JPEG, ou None si rien n'a encore été lu."""
        with self._lock:
            return self._frame_jpeg

    # ── Enregistrement ─────────────────────────────────────────────────

    def start_recording(self):
        """Démarre l'écriture d'un .mp4. Retourne le nom de fichier, ou None
        si un enregistrement est déjà en cours."""
        import cv2

        with self._lock:
            if self._writer is not None:
                return None
            os.makedirs(self.recordings_dir, exist_ok=True)
            name = f"recording_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.mp4"
            path = os.path.join(self.recordings_dir, name)
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            fps = self.fps if self.fps and self.fps > 1 else 15.0
            self._writer = cv2.VideoWriter(path, fourcc, fps, (self.width, self.height))
            self._recording_name = name
            self._rec_start = time.monotonic()
            self._rec_frames = 0
            return name

    def stop_recording(self):
        """Arrête l'enregistrement en cours. Retourne (nom, secondes, frames)
        — nom=None si aucun enregistrement n'était en cours."""
        with self._lock:
            writer = self._writer
            name = self._recording_name
            frames = self._rec_frames
            seconds = round(time.monotonic() - self._rec_start, 1) if self._rec_start else 0.0
            self._writer = None
            self._recording_name = None
            self._rec_start = None
        if writer is not None:
            writer.release()
        return name, seconds, frames

    # ── Statut / fermeture ────────────────────────────────────────────

    def status(self):
        return {
            "connected": self.connected,
            "error": self.error,
            "resolution": f"{self.width}x{self.height}" if self.width else None,
            "fps": round(self.fps, 1) if self.fps else None,
            "recording": self._recording_name is not None,
        }

    def close(self):
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        with self._lock:
            if self._writer is not None:
                self._writer.release()
                self._writer = None
        if self.cap is not None:
            self.cap.release()
        self.connected = False


# ── Registre de sessions (module-level, protégé par verrou) ────────────

_sessions = {}
_sessions_lock = threading.Lock()


def create_session(url, recordings_dir):
    """Ouvre une nouvelle session RTSP. Retourne (session_id, None) ou
    (None, error)."""
    sess = RtspSession(url, recordings_dir)
    ok, error = sess.open()
    if not ok:
        return None, error
    sid = uuid.uuid4().hex[:12]
    with _sessions_lock:
        _sessions[sid] = sess
    return sid, None


def get_session(sid):
    with _sessions_lock:
        return _sessions.get(sid)


def remove_session(sid):
    """Ferme et retire une session (no-op si l'id est déjà inconnu)."""
    with _sessions_lock:
        sess = _sessions.pop(sid, None)
    if sess is not None:
        sess.close()
