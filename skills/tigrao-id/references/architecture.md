# Arquitetura do TigraoID

## Sumário

1. Estado atual
2. Fluxo TRACK ID
3. Fluxo de conversão
4. Implantação
5. Riscos conhecidos
6. Critérios de aceite

## Estado atual

O projeto é um bot Python baseado em `pyTelegramBotAPI`, executado por long polling. O arquivo `main.py` concentra handlers, estado em memória e integração com `ffmpeg`. A configuração obrigatória é `TELEGRAM_TOKEN`.

Arquivos de infraestrutura:

- `requirements.txt`: dependência do Telegram.
- `Dockerfile`: Python 3.11 slim, instalação de `ffmpeg` e execução de `main.py`.
- `apt.txt`: instalação alternativa de `ffmpeg` em plataformas compatíveis.
- `Procfile`: processo worker `python main.py`.

## Fluxo TRACK ID

1. Receber `/trackid`.
2. Reiniciar handlers pendentes e marcar modo `musica`.
3. Coletar nome da música.
4. Coletar álbum, permitindo pular.
5. Coletar artista.
6. Coletar capa como foto, vídeo ou animação, permitindo pular.
7. Gerar mensagem HTML com prévia e botões para confirmar ou editar campos.

O texto da música pode conter entidade `text_link`. Ao alterar essa lógica, considerar que offsets de entidades do Telegram são baseados em UTF-16, enquanto índices Python usam pontos de código; emojis antes da entidade podem deslocar índices. Preferir utilitários da biblioteca ou conversão explícita de offsets.

## Fluxo de conversão

1. Receber `/convert`.
2. Aceitar `video`, documento com MIME iniciado por `video/` ou `animation`.
3. Baixar o arquivo do Telegram.
4. Gravar entrada em diretório temporário.
5. Executar `ffmpeg` com remoção de vídeo, canal mono, `libopus`, `48k` e OGG.
6. Enviar o arquivo resultante com `send_voice`.

Contrato de comando equivalente:

```text
ffmpeg -y -i INPUT -vn -ac 1 -c:a libopus -b:a 48k -f ogg OUTPUT.ogg
```

## Implantação

Preferir Docker no Railway. Definir `TELEGRAM_TOKEN` como variável secreta da plataforma. Não adicionar o valor ao repositório. Verificar a disponibilidade do executável `ffmpeg` dentro da imagem, não apenas na máquina de desenvolvimento.

## Riscos conhecidos

- Estado global em memória é perdido no restart e não escala com múltiplas réplicas.
- Handlers sequenciais podem se cruzar quando o usuário inicia outro comando no meio do fluxo.
- Capturas genéricas de exceção ocultam falhas e dificultam diagnóstico.
- Conteúdo do usuário inserido em `parse_mode="HTML"` pode quebrar markup ou permitir formatação indevida sem escape.
- Download e conversão sem limites explícitos podem consumir memória, CPU e tempo excessivos.
- Polling simultâneo com o mesmo token em mais de uma instância causa conflito.

## Critérios de aceite

Uma mudança é aceitável quando:

- `main.py` compila.
- Os três comandos obrigatórios permanecem registrados, salvo mudança solicitada.
- Nenhum token literal aparece no código ou nos arquivos de deploy.
- A conversão continua gerando OGG/Opus mono aceito por `send_voice`.
- O Dockerfile instala `ffmpeg` e inicia o bot.
- Erros operacionais retornam mensagens seguras e deixam detalhes técnicos apenas em logs sanitizados.
