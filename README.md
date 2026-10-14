# 🚀 Excelnt AI - OpenAI Compatible Proxy & Key Extractor

Um proxy local ultraleve e ferramenta de extração de credenciais para utilizar os modelos do gateway **Excelnt AI** em qualquer ferramenta compatível com OpenAI (como **Pencil**, **Cursor**, **Cline**, **Roo Code**, **LibreChat**, scripts Python, etc.).

---

## 📌 Por que este proxy é necessário?

O gateway `excelnt.ai` possui uma regra de proteção (WAF) que bloqueia chamadas de ferramentas externas. Quando a requisição não possui o cabeçalho `User-Agent: Excelnt/1.0.24` (específico da extensão oficial do VS Code), o servidor deliberadamente simula um erro falso de sobrecarga:

```json
503: {"message":"The server is currently experiencing high load and could not process your request. Please retry in a few moments.","type":"server_error","code":"server_overloaded"}
```

Este proxy local resolve esse problema de forma transparente:
1. Você aponta seu cliente (Pencil, Cursor, etc.) para o proxy local (`http://127.0.0.1:5050/v1`).
2. O proxy injeta automaticamente os cabeçalhos esperados pelo gateway (`User-Agent`, `Referer`, etc.).
3. **Injeção de Idioma (PT-BR):** Injeta automaticamente uma regra no prompt de sistema forçando o modelo a responder SEMPRE em Português do Brasil no chat (mesmo que o Pencil ou Cursor enviem instruções nativas em inglês).
4. **Fallback Automático de Modelos:** Se o modelo solicitado estiver sob sobrecarga (erro 503, 504 ou 429), o proxy tenta automaticamente os próximos modelos configurados no seu `.env` sem travar seu agente.
5. Repassa as requisições (com suporte completo a **Streaming SSE** e **Tool Calling**) e devolve as respostas com status **200 OK**.

---

## 🔑 Como Localizar a sua API Key no VS Code

Após instalar a extensão **Excelnt** no VS Code e realizar o login, você pode obter a sua chave de duas formas:

### Método 1: Automático (via script Python)
Este script lê o armazenamento seguro do VS Code no Windows (`state.vscdb`), descriptografa a chave usando a chave mestre DPAPI/AES-GCM do Chromium e exibe no terminal:

```bash
pip install -r requirements.txt
python extract_key.py
```

Saída esperada:
```text
==================================================
    LOCALIZADOR DE CREDENCIAIS - EXCELNT AI
==================================================

[SUCESSO] Credenciais localizadas na extensão:
API Key:     <SUA_CHAVE_AQUI>
Base URL:    https://excelnt.ai/v1
Model ID:    deepseek-v4.1-flash
==================================================
```

---

### Método 2: Pela Interface do VS Code (Sem código)
1. No VS Code, abra a barra lateral da extensão **Excelnt**.
2. Clique no ícone de **Configurações (Engrenagem)** no canto superior direito do painel da extensão.
3. Role até o final e clique no botão **Export Settings** (Exportar Configurações).
4. Salve o arquivo `excelnt-settings.json`.
5. Abra esse arquivo no editor e procure pelo campo `"excelntApiKey"`. O valor exibido é a sua chave de API.

---

## 🛠️ Como Iniciar o Proxy

O proxy foi construído com a biblioteca padrão do Python e não requer bibliotecas externas pesadas:

```bash
python proxy.py
```

O terminal exibirá:
```text
==================================================
   PROXY EXCELNT AI ATIVO EM: http://127.0.0.1:5050/v1
==================================================
```

O proxy agora estará escutando localmente na porta `5050`.

### ⚙️ Configuração via `.env` (Fallback de Modelos e Idioma)
Você pode criar ou editar o arquivo `.env` na mesma pasta do proxy (use o `.env.example` como base) para definir os modelos de contingência:

```env
# Modelos de fallback automático em ordem de prioridade
EXCELNT_FALLBACK_MODELS=deepseek-v4.1-flash,mimo-v2.6-flash,mimo-v2.6-pro,glm-5.3-flash,ling-flash-3.1,mimo-v2.5,gemini-3.7-flash,claude-sonnet-4-6

# Regra injetada automaticamente para o modelo sempre responder em português:
EXCELNT_SYSTEM_INSTRUCTION=Responda SEMPRE no chat em Português do Brasil (PT-BR) para o usuário.

# Porta local do proxy
EXCELNT_PORT=5050

# Máximo de tentativas de fallback antes de repassar erro
EXCELNT_MAX_FALLBACKS=5
```

---

## 🎨 Como Configurar no Pencil (pen.dev / Cosmo)

No Pencil, vá nas configurações de inteligência artificial (Model / Provider Settings):

1. **Provider Type:** `OpenAI Chat Completions` (ou Custom OpenAI)
2. **Base URL:**
   ```text
   http://127.0.0.1:5050/v1
   ```
3. **API Key:** Sua chave extraída (`sk_live...`)
4. **Model ID:** Escolha um dos modelos abaixo:
   - `deepseek-v4.1-flash` *(Muito rápido e estável)*
   - `claude-sonnet-4-6` *(Excelente para código e arquitetura de componentes)*
   - `claude-opus-4-6` *(Modelo mais avançado da Anthropic)*
   - `gemini-3.7-flash` *(Ótima velocidade do ecossistema Google)*
5. **Context Window:** `1000000` (ou `200000` para Claude)
6. **Max Tokens:** `64000`
7. Clique em **Add Provider** ou **Save**.
8. Abra uma nova conversa no Cosmo (`+ New`) e comece a criar!

---

## 💻 Como Configurar em Outras Ferramentas

### Python (SDK Oficial `openai`)
```python
from openai import OpenAI

client = OpenAI(
    api_key="SUA_CHAVE_AQUI",
    base_url="http://127.0.0.1:5050/v1"
)

response = client.chat.completions.create(
    model="deepseek-v4.1-flash",
    messages=[{"role": "user", "content": "Olá!"}]
)

print(response.choices[0].message.content)
```

### Cursor / Cline / Roo Code / LibreChat
- **API Base URL:** `http://127.0.0.1:5050/v1`
- **API Key:** `SUA_CHAVE_AQUI`
- **Model:** `deepseek-v4.1-flash` ou `claude-sonnet-4-6`

---

## 📋 Modelos Suportados no Gateway

| Model ID | Provedor Base | Context Window | Max Output |
| :--- | :--- | :--- | :--- |
| `deepseek-v4.1-flash` | DeepSeek | 1.048.576 | 64.000 |
| `deepseek-v4-flash` | DeepSeek | 1.048.576 | 64.000 |
| `claude-sonnet-4-6` | Anthropic | 200.000 | 64.000 |
| `claude-opus-4-6` | Anthropic | 200.000 | 64.000 |
| `claude-haiku-4-5` | Anthropic | 200.000 | 64.000 |
| `gemini-3.7-flash` | Google | 1.048.576 | 65.536 |
| `gemini-3.8-flash` | Google | 1.048.576 | 65.536 |
| `gpt-5.5` | OpenAI | 258.000 | 128.000 |

---

## 📄 Licença
Distribuído sob a licença MIT. Sinta-se livre para compartilhar e estender!
