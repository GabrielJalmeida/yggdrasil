"""Yggdrasil Windows desktop launcher and local API host.

The GUI process manages a separate local API process so stopping/restarting the UI
also stops the server cleanly. The packaged app binds only to loopback.
"""
from __future__ import annotations

import argparse
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tkinter as tk
from tkinter import messagebox, ttk

from desktop.config_store import (
    has_saved_key,
    is_local_base_url,
    load_settings,
    read_api_key,
    remove_api_key,
    save_settings,
    test_connection,
    user_data_dir,
    write_api_key,
)

APP_NAME = "Yggdrasil"


def resource_root() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parents[1]


def api_source_root() -> Path:
    root = resource_root()
    packaged = root / "api"
    return packaged if packaged.is_dir() else root / "services" / "api"


def web_root() -> Path:
    root = resource_root()
    packaged = root / "web"
    return packaged if (packaged / "index.html").is_file() else root / "apps" / "web" / "dist"


def alembic_root() -> Path:
    root = resource_root()
    packaged = root / "alembic"
    return packaged if (packaged / "env.py").is_file() else api_source_root() / "alembic"


def alembic_ini() -> Path:
    root = resource_root()
    packaged = root / "alembic.ini"
    return packaged if packaged.is_file() else api_source_root() / "alembic.ini"


def _sqlite_url(path: Path) -> str:
    # SQLAlchemy's Windows absolute-path URI form is sqlite:///C:/.../file.db.
    return "sqlite:///" + path.resolve().as_posix()


def _choose_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as candidate:
        candidate.bind(("127.0.0.1", 0))
        return int(candidate.getsockname()[1])


def _start_backend_process(port: int, token: str) -> subprocess.Popen[bytes]:
    root_dir = user_data_dir()
    logs_dir = root_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    (root_dir / "data").mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / "runtime.log"
    env = os.environ.copy()
    env.update({
        "PYTHON_DOTENV_DISABLED": "1",
        "YGGDRASIL_DESKTOP_MODE": "1",
        "YGGDRASIL_DESKTOP_TOKEN": token,
        "YGGDRASIL_USER_DATA_DIR": str(root_dir),
        "YGGDRASIL_WEB_ROOT": str(web_root()),
        "DATABASE_URL": _sqlite_url(root_dir / "data" / "yggdrasil.db"),
        "FRONTEND_ORIGINS": f"http://127.0.0.1:{port}",
        "AI_PROVIDER": "disabled",
        "AI_API_KEY": "",
        "AI_BASE_URL": "https://generativelanguage.googleapis.com",
        "AI_MODEL": "",
        "AI_REASONING_EFFORT": "low",
        "AI_TIMEOUT_SECONDS": "90",
    })
    settings = load_settings()
    if settings.get("ai_enabled") is True:
        api_key = read_api_key()
        base_url = str(settings.get("ai_base_url", ""))
        model = str(settings.get("ai_model", "")).strip()
        # The API repeats its own URL/credential checks. Fail closed before starting if
        # an enabled remote endpoint has no key or a model was removed.
        if model and (api_key or is_local_base_url(base_url)):
            env["AI_PROVIDER"] = "openai-compatible"
            env["AI_API_KEY"] = api_key or ""
            env["AI_BASE_URL"] = base_url
            env["AI_MODEL"] = model
            env["AI_REASONING_EFFORT"] = str(settings.get("ai_reasoning_effort", "low"))
    api_path = api_source_root()
    if not getattr(sys, "frozen", False):
        env["PYTHONPATH"] = str(api_path) + os.pathsep + env.get("PYTHONPATH", "")
    if getattr(sys, "frozen", False):
        command = [sys.executable, "--server", "--port", str(port)]
    else:
        command = [sys.executable, str(Path(__file__).resolve()), "--server", "--port", str(port)]
    log_handle = open(log_file, "ab", buffering=0)
    try:
        process = subprocess.Popen(
            command,
            cwd=root_dir,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        log_handle.close()
        raise
    # Keep the file handle alive for the child stream; it is attached to the Popen object.
    setattr(process, "_yggdrasil_log_handle", log_handle)
    return process


def run_server(port: int) -> int:
    """Child-process entry point. Performs database migration before health is ready."""
    os.environ["PYTHON_DOTENV_DISABLED"] = "1"
    api_path = api_source_root()
    if str(api_path) not in sys.path:
        sys.path.insert(0, str(api_path))
    data_root = user_data_dir()
    data_root.mkdir(parents=True, exist_ok=True)
    (data_root / "data").mkdir(parents=True, exist_ok=True)
    (data_root / "logs").mkdir(parents=True, exist_ok=True)
    import logging

    logging.basicConfig(
        filename=str(data_root / "logs" / "runtime.log"),
        level=logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    from alembic import command
    from alembic.config import Config

    config_file = alembic_ini()
    migrations = alembic_root()
    if not config_file.is_file() or not (migrations / "env.py").is_file():
        raise RuntimeError("Arquivos de migração não estão presentes no pacote.")
    migration_config = Config(str(config_file))
    migration_config.set_main_option("script_location", migrations.as_posix())
    database_url = os.environ["DATABASE_URL"]
    migration_config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    command.upgrade(migration_config, "head")

    import uvicorn
    from app.desktop_runtime import set_shutdown_callback
    from app.main import app

    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False,
        server_header=False,
        date_header=True,
    )
    server = uvicorn.Server(config)
    set_shutdown_callback(lambda: setattr(server, "should_exit", True))
    server.run()
    return 0


class AISettingsWindow:
    def __init__(self, owner: "YggdrasilLauncher") -> None:
        self.owner = owner
        self.window = tk.Toplevel(owner.root)
        self.window.title("Configurar IA · Yggdrasil")
        self.window.resizable(False, False)
        self.window.transient(owner.root)
        self.window.grab_set()
        config = load_settings()
        self.enabled = tk.BooleanVar(value=bool(config.get("ai_enabled")))
        self.base_url = tk.StringVar(value=str(config.get("ai_base_url", "")))
        self.model = tk.StringVar(value=str(config.get("ai_model", "")))
        self.reasoning = tk.StringVar(value=str(config.get("ai_reasoning_effort", "low")))
        self.key = tk.StringVar(value="")
        self.status = tk.StringVar(value=(
            "Há uma chave protegida salva no Windows. Deixe o campo vazio para mantê-la."
            if has_saved_key() else "A chave é opcional apenas para provedores locais que não exigem autenticação."
        ))
        self._build()

    def _build(self) -> None:
        frame = ttk.Frame(self.window, padding=16)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(1, weight=1)
        ttk.Label(frame, text="A IA é opcional. O grafo e as skills determinísticas funcionam sem chave.", wraplength=460).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))
        ttk.Checkbutton(frame, text="Habilitar perguntas com IA", variable=self.enabled).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 10))
        ttk.Label(frame, text="URL base do provedor").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=self.base_url, width=54).grid(row=2, column=1, sticky="ew", pady=4)
        ttk.Label(frame, text="Modelo").grid(row=3, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=self.model, width=54).grid(row=3, column=1, sticky="ew", pady=4)
        ttk.Label(frame, text="Chave da API").grid(row=4, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=self.key, show="•", width=54).grid(row=4, column=1, sticky="ew", pady=4)
        ttk.Label(frame, text="Nível de raciocínio").grid(row=5, column=0, sticky="w", pady=4)
        ttk.Combobox(frame, textvariable=self.reasoning, state="readonly", values=("low", "medium", "high"), width=12).grid(row=5, column=1, sticky="w", pady=4)
        ttk.Label(frame, textvariable=self.status, wraplength=470).grid(row=6, column=0, columnspan=2, sticky="w", pady=(8, 12))
        buttons = ttk.Frame(frame)
        buttons.grid(row=7, column=0, columnspan=2, sticky="ew")
        ttk.Button(buttons, text="Testar conexão", command=self.test).pack(side="left")
        ttk.Button(buttons, text="Remover chave salva", command=self.clear_key).pack(side="left", padx=(8, 0))
        ttk.Button(buttons, text="Salvar", command=self.save).pack(side="right")
        ttk.Button(buttons, text="Cancelar", command=self.window.destroy).pack(side="right", padx=(0, 8))

    def _current_key(self) -> str | None:
        entered = self.key.get().strip()
        if entered:
            return entered
        return read_api_key()

    def test(self) -> None:
        ok, message = test_connection(self.base_url.get().strip(), self.model.get().strip(), self._current_key())
        self.status.set(message)
        if ok:
            messagebox.showinfo("Teste da IA", message, parent=self.window)
        else:
            messagebox.showwarning("Teste da IA", message, parent=self.window)

    def clear_key(self) -> None:
        if not messagebox.askyesno("Remover chave", "Remover a chave protegida deste usuário do Windows?", parent=self.window):
            return
        remove_api_key()
        self.key.set("")
        current = load_settings()
        if current.get("ai_enabled") is True and not is_local_base_url(str(current.get("ai_base_url", ""))):
            current["ai_enabled"] = False
            save_settings(current)
        self.status.set("Chave removida. A configuração externa foi desabilitada para não reter a chave no processo ativo.")
        self.window.destroy()
        self.owner.on_ai_settings_saved()

    def save(self) -> None:
        try:
            config = {
                "ai_enabled": self.enabled.get(),
                "ai_base_url": self.base_url.get().strip(),
                "ai_model": self.model.get().strip(),
                "ai_reasoning_effort": self.reasoning.get().strip(),
            }
            api_key = self._current_key()
            if self.enabled.get():
                if not config["ai_model"]:
                    raise ValueError("Informe o identificador do modelo.")
                if not api_key and not is_local_base_url(str(config["ai_base_url"])):
                    raise ValueError("Informe a chave da API para o provedor externo.")
            if self.key.get().strip():
                write_api_key(self.key.get().strip())
            save_settings(config)
            self.status.set("Configuração salva localmente.")
        except (OSError, RuntimeError, ValueError) as exc:
            messagebox.showerror("Não foi possível salvar", str(exc), parent=self.window)
            return
        self.window.destroy()
        self.owner.on_ai_settings_saved()


class YggdrasilLauncher:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Yggdrasil")
        self.root.geometry("540x300")
        self.root.minsize(500, 280)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.status = tk.StringVar(value="Preparando o ambiente local…")
        self.address = tk.StringVar(value="A interface será aberta no navegador padrão.")
        self.process: subprocess.Popen[bytes] | None = None
        self.port: int | None = None
        self.token: str | None = None
        self._starting = False
        self._build()
        self.root.after(250, self.start_server)

    def _build(self) -> None:
        outer = ttk.Frame(self.root, padding=20)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Yggdrasil", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(outer, text="Mapa estático de repositórios · execução local", foreground="#526579").pack(anchor="w", pady=(0, 16))
        ttk.Label(outer, textvariable=self.status, wraplength=490).pack(anchor="w", pady=(0, 5))
        ttk.Label(outer, textvariable=self.address, wraplength=490).pack(anchor="w", pady=(0, 16))
        row = ttk.Frame(outer)
        row.pack(fill="x")
        self.open_button = ttk.Button(row, text="Abrir Yggdrasil", command=self.open_browser, state="disabled")
        self.open_button.pack(side="left")
        ttk.Button(row, text="Configurar IA", command=self.configure_ai).pack(side="left", padx=(8, 0))
        ttk.Button(row, text="Abrir dados locais", command=self.open_data_folder).pack(side="left", padx=(8, 0))
        ttk.Button(row, text="Sair e encerrar", command=self.close).pack(side="right")
        ttk.Label(outer, text="O aplicativo não expõe serviços à rede local. A chave de IA, se configurada, fica protegida pelo Windows.", wraplength=490, foreground="#526579").pack(anchor="w", side="bottom", pady=(18, 0))

    def start_server(self, *, open_after: bool = True) -> None:
        if self._starting:
            return
        if self.process is not None and self.process.poll() is None:
            if open_after:
                self.open_browser()
            return
        if not (web_root() / "index.html").is_file():
            self.status.set("Os arquivos da interface não foram encontrados. Gere o pacote usando desktop/build-windows.ps1.")
            messagebox.showerror("Pacote incompleto", self.status.get(), parent=self.root)
            return
        self._starting = True
        self.open_button.configure(state="disabled")
        self.status.set("Inicializando o banco local e verificando a API…")
        self.address.set("Aguardando o health check.")
        try:
            # Reuse the current loopback port when restarting after an IA settings
            # change. Open browser tabs can then refresh the rotated bootstrap token
            # instead of pointing at a port that no longer exists.
            if self.port is None:
                self.port = _choose_port()
            self.token = secrets.token_urlsafe(32)
            user_data_dir().mkdir(parents=True, exist_ok=True)
            (user_data_dir() / "desktop-port.txt").write_text(str(self.port), encoding="ascii")
            self.process = _start_backend_process(self.port, self.token)
        except Exception:
            self._starting = False
            self.status.set("Não foi possível iniciar o servidor local.")
            messagebox.showerror("Falha na inicialização", f"Confira os logs em {user_data_dir() / 'logs' / 'runtime.log'}.", parent=self.root)
            return
        threading.Thread(target=self._wait_for_health, args=(open_after,), daemon=True).start()

    def _wait_for_health(self, open_after: bool) -> None:
        deadline = time.monotonic() + 35
        last_reason = ""
        while time.monotonic() < deadline:
            process = self.process
            if process is None or process.poll() is not None:
                last_reason = "O processo do servidor encerrou antes de ficar saudável."
                break
            try:
                request = urllib.request.Request(
                    f"http://127.0.0.1:{self.port}/api/v1/health",
                    headers={"X-Yggdrasil-Token": self.token or ""},
                )
                with urllib.request.urlopen(request, timeout=1.2) as response:
                    if response.status == 200:
                        payload = response.read(4096).decode("utf-8", "replace")
                        if '"status":"ok"' in payload.replace(" ", ""):
                            self.root.after(0, lambda: self._server_ready(open_after))
                            return
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_reason = type(exc).__name__
            time.sleep(0.35)
        self.root.after(0, lambda: self._server_failed(last_reason))

    def _server_ready(self, open_after: bool) -> None:
        self._starting = False
        self.open_button.configure(state="normal")
        self.status.set("Servidor local pronto. O banco SQLite foi inicializado/atualizado.")
        self.address.set(f"Endereço local: http://127.0.0.1:{self.port}")
        if open_after and os.getenv("YGGDRASIL_SMOKE_TEST_NO_BROWSER") != "1":
            self.open_browser()

    def _server_failed(self, reason: str) -> None:
        self._starting = False
        process = self.process
        self.status.set("A inicialização não terminou corretamente.")
        self.address.set(f"Diagnóstico: {reason or 'falha não identificada'}")
        if process is not None and process.poll() is None:
            self.stop_server()
        messagebox.showerror("Yggdrasil não iniciou", f"Veja {user_data_dir() / 'logs' / 'runtime.log'} para o diagnóstico local. Nenhuma chave é gravada nesse log.", parent=self.root)

    def open_browser(self) -> None:
        if not self.port or self.process is None or self.process.poll() is not None:
            self.start_server(open_after=True)
            return
        webbrowser.open_new_tab(f"http://127.0.0.1:{self.port}/")

    def configure_ai(self) -> None:
        AISettingsWindow(self)

    def on_ai_settings_saved(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self.status.set("Configuração salva. Reiniciando a API para aplicar as opções de IA…")
            self.stop_server()
            self.start_server(open_after=True)
        else:
            self.status.set("Configuração salva. A IA será aplicada na próxima inicialização.")

    def open_data_folder(self) -> None:
        target = user_data_dir()
        target.mkdir(parents=True, exist_ok=True)
        try:
            if os.name == "nt":
                os.startfile(str(target))  # type: ignore[attr-defined]
            else:
                webbrowser.open(target.as_uri())
        except OSError:
            messagebox.showinfo("Dados locais", str(target), parent=self.root)

    def stop_server(self) -> None:
        process = self.process
        if process is None:
            return
        if process.poll() is None and self.port and self.token:
            try:
                request = urllib.request.Request(
                    f"http://127.0.0.1:{self.port}/api/v1/desktop/shutdown",
                    data=b"{}",
                    headers={"Content-Type": "application/json", "X-Yggdrasil-Token": self.token},
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=2):
                    pass
            except Exception:
                pass
            try:
                process.wait(timeout=7)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
        handle = getattr(process, "_yggdrasil_log_handle", None)
        if handle is not None:
            try:
                handle.close()
            except OSError:
                pass
        self.process = None
        try:
            (user_data_dir() / "desktop-port.txt").unlink()
        except FileNotFoundError:
            pass
        self.open_button.configure(state="disabled")

    def close(self) -> None:
        self.status.set("Encerrando o servidor local…")
        self.stop_server()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--server", action="store_true")
    parser.add_argument("--port", type=int, default=0)
    args, _unknown = parser.parse_known_args()
    if args.server:
        if not 0 < args.port < 65536:
            return 2
        return run_server(args.port)
    YggdrasilLauncher().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
