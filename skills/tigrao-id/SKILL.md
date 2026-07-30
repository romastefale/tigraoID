---
name: tigrao-id
description: Manter, revisar, depurar, testar, adaptar e implantar o bot Telegram TigraoID do repositório romastefale/tigraoID. Usar quando a solicitação mencionar TigraoID, TRACK ID, os comandos /start, /trackid ou /convert, conversão de vídeo para mensagem de voz OGG/Opus com ffmpeg, pyTelegramBotAPI, TELEGRAM_TOKEN, Railway, Docker ou alterações no fluxo interativo do bot. Aplicar também para auditorias de segurança, correções de concorrência e estado por usuário, tratamento de mídia do Telegram, criação de branches e pull requests, e verificação de compatibilidade entre main.py, requirements.txt, Dockerfile, apt.txt e Procfile.
---

# Tigrao ID

## Objetivo

Evoluir o bot sem quebrar os contratos funcionais existentes. Tratar o repositório GitHub `romastefale/tigraoID` como fonte de verdade e usar esta skill como procedimento de manutenção, validação e implantação.

## Fluxo obrigatório

1. Classificar a solicitação como análise, correção, nova funcionalidade, implantação ou diagnóstico.
2. Consultar `references/architecture.md` antes de alterar comportamento ou infraestrutura.
3. Obter metadados do repositório e confirmar a branch padrão. Ler, no mínimo, `README.md`, `main.py`, `requirements.txt` e `Dockerfile`; ler `apt.txt` e `Procfile` quando a tarefa envolver deploy.
4. Identificar o contrato afetado e registrar invariantes que devem permanecer válidos.
5. Para escrita no GitHub, criar branch separada a partir da branch padrão. Não gravar diretamente em `main`, salvo ordem explícita do usuário.
6. Fazer a menor alteração coerente. Não refatorar áreas não relacionadas apenas por conveniência.
7. Executar as verificações da seção **Validação**.
8. Apresentar resumo, arquivos alterados, verificações executadas, variáveis de ambiente e riscos residuais. Criar pull request quando houver alterações no repositório.

## Contratos funcionais

Preservar estes comportamentos, exceto quando o usuário pedir mudança explícita:

- `/start`: reiniciar o fluxo e apresentar os comandos disponíveis.
- `/trackid`: coletar música, álbum opcional, artista e capa opcional; aceitar capa como foto, vídeo ou GIF/animação; gerar prévia editável.
- `/convert`: aceitar vídeo, documento com MIME `video/*` ou animação; converter para OGG/Opus mono e enviar como mensagem de voz.
- Configuração: ler o token apenas da variável `TELEGRAM_TOKEN`.
- Execução: iniciar o bot por polling e manter `ffmpeg` disponível no ambiente de implantação.

## Regras de implementação

### Telegram e estado

- Indexar estado pelo identificador do usuário e considerar isolamento entre chats, reentrância e concorrência.
- Limpar handlers pendentes ao reiniciar ou redirecionar o fluxo.
- Tratar mensagens sem texto, mídia inválida, callbacks repetidos e arquivos indisponíveis.
- Escapar conteúdo inserido em mensagens HTML. Preservar links deliberadamente aceitos somente após validação.
- Evitar `except:` e exceções silenciosas. Capturar exceções específicas, registrar contexto técnico sem segredos e enviar mensagem segura ao usuário.
- Não persistir token, `file_id` sensível, mídia baixada ou dados pessoais além do necessário.

### Conversão de mídia

- Usar diretório temporário e garantir remoção automática.
- Invocar `ffmpeg` sem shell e verificar código de retorno e existência do arquivo de saída.
- Manter, como padrão, áudio mono, codec `libopus`, bitrate `48k`, contêiner OGG e remoção da trilha de vídeo.
- Adicionar limites de tamanho, duração e tempo de processamento quando a mudança puder receber mídia não confiável.
- Não incluir o conteúdo de `stderr` do ffmpeg em mensagens ao usuário; usar somente em logs sanitizados.

### Dependências e deploy

- Manter a dependência Python declarada e compatível com o código.
- Garantir que a imagem Docker instale `ffmpeg`, copie dependências antes do código para aproveitar cache e execute `python main.py`.
- Tratar `Dockerfile` como opção principal de Railway. Usar `apt.txt` e `Procfile` apenas como alternativa compatível.
- Nunca inserir `TELEGRAM_TOKEN` em Dockerfile, commits, logs, exemplos ou testes.

### Operações GitHub

- Confirmar permissão de escrita antes de criar branch ou arquivos.
- Preferir branch `feat/...`, `fix/...` ou `chore/...` conforme o tipo de mudança.
- Usar commits pequenos e descritivos.
- Criar pull request com: contexto, alteração, validação e riscos.
- Não fazer merge, habilitar auto-merge ou excluir arquivos sem solicitação explícita.

## Validação

Executar, conforme aplicável:

```bash
python -m py_compile main.py
python scripts/audit_tigrao_id.py /caminho/do/projeto
ffmpeg -version
```

Para mudanças de comportamento, complementar com testes unitários que simulem objetos de mensagem e chamadas do bot. Não iniciar polling real durante testes. Considerar a validação reprovada se houver erro de sintaxe, ausência de variável de ambiente, perda de handler obrigatório, comando ffmpeg incompatível ou segredo literal.

## Formato da resposta

Usar esta estrutura para tarefas de manutenção:

```markdown
## Resultado
[Resumo do que foi analisado ou alterado]

## Arquivos
- `arquivo`: alteração e motivo

## Verificação
- [comando ou teste]: [resultado]

## Configuração
- Variáveis e dependências necessárias

## Riscos residuais
- Risco conhecido ou "Nenhum identificado"
```

## Recursos

- Ler `references/architecture.md` para o estado atual, invariantes e riscos conhecidos.
- Executar `scripts/audit_tigrao_id.py` para validar estruturalmente uma cópia local do projeto antes de concluir.
