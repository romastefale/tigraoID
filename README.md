# Telegram bot com /convert

Este projeto adiciona o comando `/convert`, que recebe vídeo e devolve áudio no formato de voz do Telegram.

## Arquivos
- `main.py` — bot atualizado
- `requirements.txt` — dependências Python
- `Dockerfile` — instala `ffmpeg` e sobe o bot
- `apt.txt` — alternativa simples para Railway/Nixpacks
- `Procfile` — opção de execução sem Docker

## Deploy no Railway
A forma mais estável é com `Dockerfile`.

Variável necessária:
- `TELEGRAM_TOKEN`

## Como usar
- `/start` para o fluxo normal
- `/convert` para enviar um vídeo e receber o áudio convertido em voz
