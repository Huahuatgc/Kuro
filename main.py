import asyncio
import json
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlparse

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

from . import kuro_core as core


class OwnerStore:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.owner_map: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            self.owner_map = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self.owner_map = {}

    def _save_locked(self) -> None:
        self.path.write_text(json.dumps(self.owner_map, ensure_ascii=False, indent=2), encoding="utf-8")

    def bind(self, owner_key: str, sid: str) -> None:
        with self.lock:
            self.owner_map[owner_key] = sid
            self._save_locked()

    def get(self, owner_key: str) -> str:
        with self.lock:
            return self.owner_map.get(owner_key, "")


class KuroBridge:
    def __init__(
        self,
        host: str,
        port: int,
        owner_store: OwnerStore,
        public_ip: str = "",
        public_base_url: str = "",
    ):
        self.host = host
        self.port = port
        self.public_ip = public_ip.strip()
        self.public_base_url = public_base_url.strip()
        self.owner_store = owner_store
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def _make_handler(self) -> type[BaseHTTPRequestHandler]:
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "AstrBotKuro/0.2"

            def log_message(self, format: str, *args: Any) -> None:
                return

            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                sid, created = core.get_or_create_session(self)
                if parsed.path != "/":
                    self._send_json(HTTPStatus.NOT_FOUND, {"code": 404, "msg": "not found"}, sid if created else None)
                    return
                owner_key = (parse_qs(parsed.query).get("user") or [""])[0].strip()
                if owner_key:
                    bridge.owner_store.bind(owner_key, sid)
                self._send_html(core.build_html(), sid if created else None)

            def do_POST(self) -> None:
                sid, created = core.get_or_create_session(self)
                try:
                    payload = self._read_json()
                except json.JSONDecodeError:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"code": 400, "msg": "invalid json"}, sid if created else None)
                    return

                with core.SESSIONS_LOCK:
                    session = core.SESSIONS[sid]

                if self.path == "/api/send_sms":
                    mobile = str(payload.get("mobile", "")).strip()
                    gee_test_data = payload.get("geeTestData")
                    if not (mobile.isdigit() and len(mobile) == 11):
                        self._send_json(HTTPStatus.BAD_REQUEST, {"code": 400, "msg": "invalid mobile"}, sid if created else None)
                        return
                    if not isinstance(gee_test_data, dict):
                        self._send_json(HTTPStatus.BAD_REQUEST, {"code": 400, "msg": "invalid geeTestData"}, sid if created else None)
                        return

                    headers = {
                        "source": "h5",
                        "devcode": session["h5_devcode"],
                        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                        "User-Agent": "Mozilla/5.0",
                    }
                    data = {
                        "mobile": mobile,
                        "geeTestData": json.dumps(gee_test_data, ensure_ascii=False),
                    }
                    response = core.post_form(f"{core.KURO_BASE}/user/getSmsCodeForH5", headers, data)
                    self._send_json(HTTPStatus.OK, response, sid if created else None)
                    return

                if self.path == "/api/login":
                    mobile = str(payload.get("mobile", "")).strip()
                    code = str(payload.get("code", "")).strip()
                    if not (mobile.isdigit() and len(mobile) == 11):
                        self._send_json(HTTPStatus.BAD_REQUEST, {"code": 400, "msg": "invalid mobile"}, sid if created else None)
                        return
                    if not (code.isdigit() and len(code) == 6):
                        self._send_json(HTTPStatus.BAD_REQUEST, {"code": 400, "msg": "invalid code"}, sid if created else None)
                        return

                    headers = core.build_rover_base_headers()
                    response = core.post_form(
                        f"{core.KURO_BASE}/user/sdkLogin",
                        headers,
                        {"mobile": mobile, "code": code, "devCode": session["did"]},
                    )
                    if response.get("code") == 200 and isinstance(response.get("data"), dict):
                        data_obj = response["data"]
                        session["token"] = str(data_obj.get("token", ""))
                        session["user_id"] = str(data_obj.get("userId", ""))
                        session["user_name"] = str(data_obj.get("userName", ""))
                        session["login_mode_used"] = "xwuid_style"
                    self._send_json(HTTPStatus.OK, response, sid if created else None)
                    return

                if self.path == "/api/sign/waves":
                    self._send_json(HTTPStatus.OK, core.run_waves_sign(session), sid if created else None)
                    return

                if self.path == "/api/sign/bbs":
                    self._send_json(HTTPStatus.OK, core.run_bbs_sign(session), sid if created else None)
                    return

                self._send_json(HTTPStatus.NOT_FOUND, {"code": 404, "msg": "not found"}, sid if created else None)

            def _send_json(self, status: int, data: dict[str, Any], sid: str | None = None) -> None:
                payload = core.json_bytes(data)
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                if sid:
                    self.send_header("Set-Cookie", f"sid={sid}; Path=/; HttpOnly; SameSite=Lax")
                self.end_headers()
                self.wfile.write(payload)

            def _send_html(self, html: bytes, sid: str | None = None) -> None:
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(html)))
                if sid:
                    self.send_header("Set-Cookie", f"sid={sid}; Path=/; HttpOnly; SameSite=Lax")
                self.end_headers()
                self.wfile.write(html)

            def _read_json(self) -> dict[str, Any]:
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length).decode("utf-8") if length else "{}"
                return json.loads(raw)

        return Handler

    def ensure_started(self) -> None:
        if self._server:
            return
        with self._lock:
            if self._server:
                return
            self._server = ThreadingHTTPServer((self.host, self.port), self._make_handler())
            self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            if not self._server:
                return
            self._server.shutdown()
            self._server.server_close()
            self._server = None
            self._thread = None

    def login_url(self, owner_key: str) -> str:
        self.ensure_started()
        base = self._resolve_public_base()
        return f"{base}/?user={quote(owner_key, safe='')}"

    def _resolve_public_base(self) -> str:
        # Preferred mode: user only sets public IP/domain and plugin auto-fills scheme+port.
        if self.public_ip:
            ip_or_host = self.public_ip.strip().rstrip("/")
            if ip_or_host.startswith(("http://", "https://")):
                return ip_or_host
            if ":" in ip_or_host:
                return f"http://{ip_or_host}"
            return f"http://{ip_or_host}:{self.port}"

        # Backward compatibility for old config.
        if self.public_base_url:
            return self.public_base_url.rstrip("/")
        return f"http://{self.host}:{self.port}"

    def status(self, owner_key: str) -> dict[str, Any]:
        sid = self.owner_store.get(owner_key)
        if not sid:
            return {"logged_in": False, "msg": "未找到登录会话，请先执行 /kuro_login"}
        with core.SESSIONS_LOCK:
            session = dict(core.SESSIONS.get(sid) or {})
        if not session:
            return {"logged_in": False, "msg": "会话不存在，请重新登录"}
        return {
            "logged_in": bool(session.get("token")),
            "userId": session.get("user_id", ""),
            "userName": session.get("user_name", ""),
            "roleId": session.get("waves_role_id", ""),
            "serverId": session.get("waves_server_id", ""),
            "roleName": session.get("waves_role_name", ""),
        }

    def waves_sign(self, owner_key: str) -> dict[str, Any]:
        sid = self.owner_store.get(owner_key)
        if not sid:
            return {"success": False, "msg": "未找到登录会话，请先执行 /kuro_login"}
        with core.SESSIONS_LOCK:
            session = core.SESSIONS.get(sid)
            if not session:
                return {"success": False, "msg": "会话不存在，请重新登录"}
            return core.run_waves_sign(session)

    def bbs_sign(self, owner_key: str) -> dict[str, Any]:
        sid = self.owner_store.get(owner_key)
        if not sid:
            return {"success": False, "msg": "未找到登录会话，请先执行 /kuro_login"}
        with core.SESSIONS_LOCK:
            session = core.SESSIONS.get(sid)
            if not session:
                return {"success": False, "msg": "会话不存在，请重新登录"}
            return core.run_bbs_sign(session)


def fmt_waves_result(payload: dict[str, Any]) -> str:
    if not payload.get("success"):
        return f"鸣潮签到失败\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    context = payload.get("context") or {}
    result = payload.get("result", "-")
    label = {"signed": "签到成功", "already_signed": "今日已签到"}.get(result, result)
    return "\n".join(
        [
            f"鸣潮签到: {label}",
            f"角色: {context.get('roleName', '-')}",
            f"roleId: {context.get('roleId', '-')}",
            f"serverId: {context.get('serverId', '-')}",
        ]
    )


def fmt_bbs_result(payload: dict[str, Any]) -> str:
    if not payload.get("success"):
        return f"社区任务失败\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    data = (payload.get("taskResponse") or {}).get("data") or {}
    daily = data.get("dailyTask") or []
    pending = [
        f"{task.get('remark', '-')}: {task.get('completeTimes', 0)}/{task.get('needActionTimes', 0)}"
        for task in daily
        if task.get("completeTimes") != task.get("needActionTimes")
    ]
    actions = [
        f"{name}: {value.get('code')}"
        for name, value in (payload.get("actions") or {}).items()
        if isinstance(value, dict) and "code" in value
    ]
    lines = [
        "社区任务执行完成",
        f"今日库洛币: {data.get('currentDailyGold', '-')}/{data.get('maxDailyGold', '-')}",
        "未完成任务:" if pending else "今日任务已全部完成",
    ]
    if pending:
        lines.extend(pending)
    if actions:
        lines.append("本次执行:")
        lines.extend(actions)
    return "\n".join(lines)


@register("astrbot_plugin_kuro_sign", "Kuro Sign", "本地网页登录获取 Kuro token 并执行签到", "0.2.1")
class KuroSignPlugin(Star):
    def __init__(self, context: Context, config: dict | None = None):
        super().__init__(context)
        self.config = config or {}
        plugin_dir = Path(__file__).resolve().parent
        owner_store = OwnerStore(plugin_dir / "data" / "owner_map.json")
        host = str(self._cfg("host", "0.0.0.0"))
        public_ip = str(self._cfg("public_ip", "")).strip()
        if public_ip and host in ("127.0.0.1", "localhost"):
            # Public URL is configured but bind address is local-only: auto-fix.
            host = "0.0.0.0"
        self.bridge = KuroBridge(
            host=host,
            port=int(self._cfg("port", 8765)),
            owner_store=owner_store,
            public_ip=public_ip,
            public_base_url=str(self._cfg("public_base_url", "")),
        )

    def _cfg(self, key: str, default: Any) -> Any:
        if isinstance(self.config, dict):
            return self.config.get(key, default)
        getter = getattr(self.config, "get", None)
        if callable(getter):
            return getter(key, default)
        return default

    def _owner_key(self, event: AstrMessageEvent) -> str:
        return str(getattr(event, "unified_msg_origin", "") or event.get_sender_id())

    @filter.command("kuro_login")
    async def kuro_login(self, event: AstrMessageEvent):
        url = await asyncio.to_thread(self.bridge.login_url, self._owner_key(event))
        yield event.plain_result(
            "打开下面的登录页完成 GeeTest、短信验证码和登录:\n"
            f"{url}\n\n"
            "登录成功后可继续执行 /kuro_status、/kuro_waves_sign、/kuro_bbs_sign"
        )

    @filter.command("kuro_status")
    async def kuro_status(self, event: AstrMessageEvent):
        payload = await asyncio.to_thread(self.bridge.status, self._owner_key(event))
        if not payload.get("logged_in"):
            yield event.plain_result(payload.get("msg", "未登录"))
            return
        yield event.plain_result(
            "\n".join(
                [
                    "当前登录状态正常",
                    f"userId: {payload.get('userId', '-')}",
                    f"userName: {payload.get('userName', '-')}",
                    f"roleName: {payload.get('roleName', '-')}",
                    f"roleId: {payload.get('roleId', '-')}",
                ]
            )
        )

    @filter.command("kuro_waves_sign")
    async def kuro_waves_sign(self, event: AstrMessageEvent):
        payload = await asyncio.to_thread(self.bridge.waves_sign, self._owner_key(event))
        yield event.plain_result(fmt_waves_result(payload))

    @filter.command("kuro_bbs_sign")
    async def kuro_bbs_sign(self, event: AstrMessageEvent):
        payload = await asyncio.to_thread(self.bridge.bbs_sign, self._owner_key(event))
        yield event.plain_result(fmt_bbs_result(payload))

    async def terminate(self):
        logger.info("stopping kuro sign local server")
        await asyncio.to_thread(self.bridge.stop)
