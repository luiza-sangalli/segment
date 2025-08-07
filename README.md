# Webhook Segment

Um webhook simples e robusto para receber eventos do Segment, construído com FastAPI e pronto para deploy no Railway.

## 🚀 Funcionalidades

- **Webhook endpoint** para receber eventos do Segment
- **Health check** para monitoramento
- **Logging estruturado** de todos os eventos
- **Processamento específico** por tipo de evento (track, identify, page, screen)
- **Endpoint de teste** para validação
- **Containerizado** com Docker
- **Pronto para Railway** com configuração otimizada

## 📋 Endpoints

- `GET /` - Health check básico
- `GET /health` - Health check para Railway
- `POST /webhook/segment` - Endpoint principal para eventos do Segment
- `POST /webhook/test` - Endpoint de teste

## 🛠 Instalação Local

### Pré-requisitos

- Python 3.11+
- pip

### Passos

1. Clone o repositório:
```bash
git clone <seu-repositorio>
cd webhook-segment
```

2. Crie um ambiente virtual:
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# ou
venv\Scripts\activate  # Windows
```

3. Instale as dependências:
```bash
pip install -r requirements.txt
```

4. Execute a aplicação:
```bash
python main.py
```

A aplicação estará disponível em `http://localhost:8000`

## 🚂 Deploy no Railway

### Método 1: Deploy direto (Recomendado)

1. Acesse [Railway.app](https://railway.app)
2. Faça login com sua conta GitHub
3. Clique em "New Project"
4. Selecione "Deploy from GitHub repo"
5. Escolha este repositório
6. O Railway detectará automaticamente o `Dockerfile` e fará o deploy

### Método 2: CLI do Railway

1. Instale a CLI do Railway:
```bash
npm install -g @railway/cli
```

2. Faça login:
```bash
railway login
```

3. Inicialize o projeto:
```bash
railway init
```

4. Faça o deploy:
```bash
railway up
```

### Configuração no Railway

O Railway utilizará automaticamente:
- `Dockerfile` para build da imagem
- `railway.json` para configurações específicas
- Porta automática via variável de ambiente `PORT`

## 🔧 Configuração do Segment

Após o deploy no Railway, você receberá uma URL como `https://seu-app.railway.app`.

Configure o webhook no Segment:

1. Acesse seu workspace no Segment
2. Vá em Settings > Destinations
3. Adicione um webhook destination
4. Configure a URL: `https://seu-app.railway.app/webhook/segment`
5. Selecione os eventos que deseja receber

## 📊 Tipos de Eventos Suportados

### Track Events
Eventos de ações do usuário (cliques, compras, etc.)
```json
{
  "type": "track",
  "event": "Button Clicked",
  "userId": "user123",
  "properties": {
    "button_name": "signup",
    "page": "homepage"
  }
}
```

### Identify Events
Eventos de identificação de usuário
```json
{
  "type": "identify",
  "userId": "user123",
  "traits": {
    "name": "João Silva",
    "email": "joao@example.com"
  }
}
```

### Page Events
Eventos de visualização de página
```json
{
  "type": "page",
  "name": "Home",
  "userId": "user123",
  "properties": {
    "url": "https://example.com",
    "title": "Homepage"
  }
}
```

### Screen Events
Eventos de visualização de tela (mobile)
```json
{
  "type": "screen",
  "name": "Profile Screen",
  "userId": "user123",
  "properties": {
    "version": "1.2.0"
  }
}
```

## 🧪 Testando o Webhook

### Teste local
```bash
curl -X POST http://localhost:8000/webhook/test \
  -H "Content-Type: application/json" \
  -d '{"test": true, "message": "Hello webhook!"}'
```

### Teste no Railway
```bash
curl -X POST https://seu-app.railway.app/webhook/test \
  -H "Content-Type: application/json" \
  -d '{"test": true, "message": "Hello webhook!"}'
```

## 📝 Logs

A aplicação registra todos os eventos recebidos. No Railway, você pode visualizar os logs em tempo real no dashboard.

## 🔒 Segurança

Para produção, considere adicionar:

- **Autenticação** via headers ou tokens
- **Validação de assinatura** dos webhooks do Segment
- **Rate limiting** para prevenir abuso
- **HTTPS** (automático no Railway)

## 📦 Estrutura do Projeto

```
webhook-segment/
├── main.py              # Aplicação principal
├── requirements.txt     # Dependências Python
├── Dockerfile          # Configuração Docker
├── railway.json        # Configuração Railway
├── .gitignore          # Arquivos ignorados pelo Git
└── README.md           # Esta documentação
```

## 🤝 Contribuição

1. Faça um fork do projeto
2. Crie uma branch para sua feature (`git checkout -b feature/nova-feature`)
3. Commit suas mudanças (`git commit -am 'Adiciona nova feature'`)
4. Push para a branch (`git push origin feature/nova-feature`)
5. Abra um Pull Request

## 📄 Licença

Este projeto está sob a licença MIT. Veja o arquivo `LICENSE` para mais detalhes.

## 🆘 Suporte

Se você encontrar algum problema ou tiver dúvidas:

1. Verifique os logs da aplicação
2. Teste os endpoints de health check
3. Abra uma issue no GitHub

---

Desenvolvido com ❤️ usando FastAPI e Railway