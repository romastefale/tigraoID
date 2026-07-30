#!/usr/bin/env python3
"""Auditoria estrutural do projeto TigraoID sem iniciar o bot."""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class Finding:
    level: str
    code: str
    message: str


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"Arquivo não está em UTF-8: {path}") from exc


def has_command(source: str, command: str) -> bool:
    pattern = rf"message_handler\s*\(\s*commands\s*=\s*\[[^\]]*['\"]{re.escape(command)}['\"]"
    return bool(re.search(pattern, source, flags=re.DOTALL))


def audit(project: Path) -> list[Finding]:
    findings: list[Finding] = []
    required = ["main.py", "requirements.txt", "Dockerfile"]

    for name in required:
        if not (project / name).is_file():
            findings.append(Finding("error", "missing-file", f"Arquivo obrigatório ausente: {name}"))

    if any(item.level == "error" for item in findings):
        return findings

    main_source = read_text(project / "main.py")
    requirements = read_text(project / "requirements.txt")
    dockerfile = read_text(project / "Dockerfile")

    try:
        tree = ast.parse(main_source, filename="main.py")
    except SyntaxError as exc:
        findings.append(Finding("error", "python-syntax", f"Erro de sintaxe em main.py: {exc}"))
        return findings

    if "pyTelegramBotAPI" not in requirements:
        findings.append(Finding("error", "telegram-dependency", "requirements.txt não declara pyTelegramBotAPI"))

    if not re.search(r"os\.getenv\(\s*['\"]TELEGRAM_TOKEN['\"]\s*\)", main_source):
        findings.append(Finding("error", "token-env", "main.py não lê TELEGRAM_TOKEN via os.getenv"))

    token_literal_patterns = [
        r"TELEGRAM_TOKEN\s*=\s*['\"][^'\"]+['\"]",
        r"\b\d{6,12}:[A-Za-z0-9_-]{20,}\b",
    ]
    if any(re.search(pattern, main_source) for pattern in token_literal_patterns):
        findings.append(Finding("error", "literal-secret", "Possível token do Telegram gravado literalmente"))

    for command in ("start", "trackid", "convert"):
        if not has_command(main_source, command):
            findings.append(Finding("error", "missing-handler", f"Handler obrigatório não encontrado: /{command}"))

    if "infinity_polling" not in main_source:
        findings.append(Finding("error", "polling", "Inicialização por infinity_polling não encontrada"))

    ffmpeg_tokens = ["ffmpeg", "-vn", "-ac", "libopus", "48k", "ogg"]
    missing_ffmpeg = [token for token in ffmpeg_tokens if token not in main_source]
    if missing_ffmpeg:
        findings.append(
            Finding("error", "ffmpeg-contract", "Contrato ffmpeg incompleto; ausentes: " + ", ".join(missing_ffmpeg))
        )

    if "ffmpeg" not in dockerfile.lower():
        findings.append(Finding("error", "docker-ffmpeg", "Dockerfile não instala ffmpeg"))
    if not re.search(r"(?:CMD|ENTRYPOINT).*python.*main\.py", dockerfile, flags=re.IGNORECASE):
        findings.append(Finding("error", "docker-command", "Dockerfile não inicia python main.py"))

    bare_except_count = sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, ast.ExceptHandler) and node.type is None
    )
    if bare_except_count:
        findings.append(
            Finding("warning", "bare-except", f"Encontrado(s) {bare_except_count} bloco(s) except sem tipo")
        )

    if re.search(r"^user_data\s*=\s*\{\s*\}", main_source, flags=re.MULTILINE):
        findings.append(
            Finding("warning", "memory-state", "Estado de usuário está apenas em memória e não suporta múltiplas réplicas")
        )

    if 'parse_mode="HTML"' in main_source and not re.search(r"html\.(?:escape|quote)", main_source):
        findings.append(
            Finding("warning", "html-escaping", "Mensagens HTML parecem usar entrada do usuário sem escape explícito")
        )

    if not findings:
        findings.append(Finding("info", "ok", "Nenhum problema estrutural encontrado"))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", nargs="?", default=".", help="Diretório raiz do projeto")
    parser.add_argument("--json", action="store_true", help="Emitir JSON")
    args = parser.parse_args()

    project = Path(args.project).expanduser().resolve()
    findings = audit(project)

    if args.json:
        print(json.dumps([asdict(item) for item in findings], ensure_ascii=False, indent=2))
    else:
        for item in findings:
            print(f"[{item.level.upper()}] {item.code}: {item.message}")

    return 1 if any(item.level == "error" for item in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
