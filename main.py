from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
import json
import os
from datetime import datetime
import logging
from typing import Dict, Any
from starlette.middleware.base import BaseHTTPMiddleware
from collections import defaultdict

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Webhook Segment",
    description="Webhook para receber eventos do Segment",
    version="1.0.0"
)

# Middleware para logar todas as requisições
class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Log da requisição
        logger.info(f"🌐 {request.method} {request.url.path} - Headers: {dict(request.headers)}")
        
        response = await call_next(request)
        
        # Log da resposta
        logger.info(f"📤 {response.status_code} para {request.method} {request.url.path}")
        
        return response

app.add_middleware(LoggingMiddleware)

# CONFIGURAÇÕES DE FILTROS
FILTER_CONFIG = {
    # Tipos de eventos aceitos
    "allowed_event_types": ["track", "identify", "page", "screen"],
    
    # Eventos track específicos que você quer processar
    "allowed_track_events": [
        "Button Clicked",
        "Purchase Completed", 
        "User Signup",
        "Page Viewed",
        "Product Added",
        "Checkout Started"
        # Adicione os eventos que você quer processar
    ],
    
    # Filtros por propriedades
    "required_properties": {
        # "track": ["userId"],  # Track events devem ter userId
        # "identify": ["userId", "traits"]  # Identify deve ter userId e traits
    },
    
    # Filtrar por valores específicos
    "property_filters": {
        # Exemplo: só processar eventos de usuários premium
        # "traits.plan": ["premium", "enterprise"],
        # "properties.environment": ["production"]
    },
    
    # Ignorar eventos de teste/desenvolvimento
    "ignore_test_events": True,
    "test_patterns": ["test", "debug", "dev", "local"],
    
    # Filtrar por data - apenas eventos de hoje
    "filter_by_date": True,
    "date_field": "timestamp",  # Campo que contém a data do evento
    "max_age_hours": 24  # Máximo 24 horas (dia atual)
}

@app.get("/")
async def root():
    """Endpoint de health check com informações das rotas"""
    return {
        "message": "Webhook Segment está funcionando!",
        "timestamp": datetime.now().isoformat(),
        "status": "healthy",
        "available_endpoints": {
            "GET /": "Health check",
            "GET /health": "Health check para Railway",
            "POST /webhook/segment": "Endpoint principal para eventos do Segment",
            "POST /webhook/test": "Endpoint de teste",
            "GET /webhook/filters": "Ver configurações de filtro",
            "POST /webhook/filters": "Atualizar filtros",
            "GET /webhook/recent": "Ver últimos eventos recebidos",
            "GET /webhook/stats": "Estatísticas dos eventos"
        },
        "correct_webhook_url": "https://segment-production.up.railway.app/webhook/segment"
    }

@app.get("/health")
async def health_check():
    """Endpoint de health check para Railway"""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}

@app.post("/webhook/segment")
async def segment_webhook(request: Request):
    """
    Endpoint principal para receber webhooks do Segment
    """
    try:
        # Obter o body da requisição
        body = await request.body()
        
        # Tentar fazer parse do JSON
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            logger.error("Erro ao fazer parse do JSON")
            raise HTTPException(status_code=400, detail="Invalid JSON")
        
        # Log do evento recebido
        logger.info(f"Evento recebido do Segment: {json.dumps(data, indent=2)}")
        
        # Armazenar evento para visualização
        store_recent_event(data)
        
        # FILTROS - Verificar se deve processar o evento
        if not should_process_event(data):
            logger.info(f"Evento filtrado e ignorado: {data.get('type', 'unknown')}")
            return JSONResponse(
                status_code=200,
                content={
                    "status": "filtered",
                    "message": "Evento filtrado conforme regras configuradas",
                    "timestamp": datetime.now().isoformat()
                }
            )
        
        # Processar o evento baseado no tipo
        event_type = data.get("type", "unknown")
        
        if event_type == "track":
            result = await process_track_event(data)
        elif event_type == "identify":
            result = await process_identify_event(data)
        elif event_type == "page":
            result = await process_page_event(data)
        elif event_type == "screen":
            result = await process_screen_event(data)
        else:
            result = await process_unknown_event(data)
        
        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "message": "Evento processado com sucesso",
                "event_type": event_type,
                "timestamp": datetime.now().isoformat(),
                "result": result
            }
        )
        
    except Exception as e:
        logger.error(f"Erro ao processar webhook: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")

def should_process_event(data: Dict[str, Any]) -> bool:
    """
    Determina se o evento deve ser processado com base nos filtros configurados
    """
    event_type = data.get("type", "").lower()
    
    # 1. Verificar tipo de evento permitido
    if event_type not in FILTER_CONFIG["allowed_event_types"]:
        logger.info(f"Tipo de evento não permitido: {event_type}")
        return False
    
    # 2. Para eventos track, verificar se o evento específico é permitido
    if event_type == "track":
        event_name = data.get("event", "")
        allowed_events = FILTER_CONFIG["allowed_track_events"]
        
        # Se lista vazia, aceitar todos os track events
        if allowed_events and event_name not in allowed_events:
            logger.info(f"Evento track não permitido: {event_name}")
            return False
    
    # 3. Ignorar eventos de teste se configurado
    if FILTER_CONFIG["ignore_test_events"]:
        test_patterns = FILTER_CONFIG["test_patterns"]
        
        # Verificar em diferentes campos se contém padrões de teste
        fields_to_check = [
            data.get("event", ""),
            data.get("userId", ""),
            str(data.get("properties", {})),
            str(data.get("traits", {}))
        ]
        
        for field in fields_to_check:
            field_lower = str(field).lower()
            if any(pattern in field_lower for pattern in test_patterns):
                logger.info(f"Evento de teste ignorado: {field}")
                return False
    
    # 4. Verificar propriedades obrigatórias
    required_props = FILTER_CONFIG["required_properties"].get(event_type, [])
    for prop in required_props:
        if prop not in data or not data[prop]:
            logger.info(f"Propriedade obrigatória ausente: {prop}")
            return False
    
    # 5. Aplicar filtros por valores específicos
    property_filters = FILTER_CONFIG["property_filters"]
    for filter_path, allowed_values in property_filters.items():
        value = get_nested_value(data, filter_path)
        if value and value not in allowed_values:
            logger.info(f"Valor não permitido para {filter_path}: {value}")
            return False
    
    # 6. Filtrar por data - apenas eventos de hoje
    if FILTER_CONFIG["filter_by_date"]:
        if not is_event_from_today(data):
            logger.info("Evento ignorado: não é do dia de hoje")
            return False
    
    return True

def get_nested_value(data: Dict[str, Any], path: str) -> Any:
    """
    Obter valor aninhado usando notação de ponto (ex: 'traits.plan')
    """
    keys = path.split('.')
    value = data
    
    try:
        for key in keys:
            value = value[key]
        return value
    except (KeyError, TypeError):
        return None

def is_event_from_today(data: Dict[str, Any]) -> bool:
    """
    Verifica se o evento é do dia de hoje com base no timestamp
    """
    from datetime import datetime, timezone, timedelta
    
    # Obter timestamp do evento
    timestamp_field = FILTER_CONFIG["date_field"]
    timestamp_str = data.get(timestamp_field)
    
    if not timestamp_str:
        # Se não tem timestamp, considerar como evento atual (agora)
        logger.info("Evento sem timestamp - considerando como atual")
        return True
    
    try:
        # Parse do timestamp do Segment (formato ISO)
        if isinstance(timestamp_str, str):
            # Formatos comuns do Segment
            try:
                event_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            except:
                # Tentar outro formato
                event_time = datetime.strptime(timestamp_str, '%Y-%m-%dT%H:%M:%S.%fZ')
                event_time = event_time.replace(tzinfo=timezone.utc)
        else:
            logger.warning(f"Timestamp inválido: {timestamp_str}")
            return True
        
        # Converter para UTC se necessário
        if event_time.tzinfo is None:
            event_time = event_time.replace(tzinfo=timezone.utc)
        
        # Obter hora atual
        now = datetime.now(timezone.utc)
        
        # Calcular diferença em horas
        max_age_hours = FILTER_CONFIG["max_age_hours"]
        time_diff = now - event_time
        hours_diff = time_diff.total_seconds() / 3600
        
        # Verificar se está dentro do período permitido
        is_recent = hours_diff <= max_age_hours
        
        if not is_recent:
            logger.info(f"Evento antigo ignorado: {hours_diff:.1f}h atrás (máx: {max_age_hours}h)")
        
        return is_recent
        
    except Exception as e:
        logger.warning(f"Erro ao processar timestamp {timestamp_str}: {str(e)}")
        # Em caso de erro, processar o evento
        return True

async def process_track_event(data: Dict[str, Any]) -> Dict[str, Any]:
    """Processar eventos de track (ações do usuário)"""
    event_name = data.get("event", "unknown")
    user_id = data.get("userId")
    properties = data.get("properties", {})
    
    logger.info(f"Processando evento track: {event_name} para usuário {user_id}")
    
    # Aqui você pode adicionar sua lógica específica
    # Por exemplo: salvar no banco de dados, enviar para outros serviços, etc.
    
    return {
        "processed": True,
        "event": event_name,
        "user_id": user_id,
        "properties_count": len(properties)
    }

async def process_identify_event(data: Dict[str, Any]) -> Dict[str, Any]:
    """Processar eventos de identify (identificação de usuário)"""
    user_id = data.get("userId")
    traits = data.get("traits", {})
    
    logger.info(f"Processando evento identify para usuário {user_id}")
    
    return {
        "processed": True,
        "user_id": user_id,
        "traits_count": len(traits)
    }

async def process_page_event(data: Dict[str, Any]) -> Dict[str, Any]:
    """Processar eventos de page (visualização de página)"""
    user_id = data.get("userId")
    page_name = data.get("name", "unknown")
    properties = data.get("properties", {})
    
    logger.info(f"Processando evento page: {page_name} para usuário {user_id}")
    
    return {
        "processed": True,
        "page": page_name,
        "user_id": user_id,
        "properties_count": len(properties)
    }

async def process_screen_event(data: Dict[str, Any]) -> Dict[str, Any]:
    """Processar eventos de screen (visualização de tela mobile)"""
    user_id = data.get("userId")
    screen_name = data.get("name", "unknown")
    properties = data.get("properties", {})
    
    logger.info(f"Processando evento screen: {screen_name} para usuário {user_id}")
    
    return {
        "processed": True,
        "screen": screen_name,
        "user_id": user_id,
        "properties_count": len(properties)
    }

async def process_unknown_event(data: Dict[str, Any]) -> Dict[str, Any]:
    """Processar eventos desconhecidos"""
    event_type = data.get("type", "unknown")
    
    logger.warning(f"Processando evento desconhecido: {event_type}")
    
    return {
        "processed": True,
        "event_type": event_type,
        "note": "Tipo de evento não reconhecido"
    }

@app.post("/webhook/test")
async def test_webhook(request: Request):
    """Endpoint de teste para validar o webhook"""
    try:
        body = await request.body()
        data = json.loads(body) if body else {}
        
        logger.info(f"Teste do webhook recebido: {data}")
        
        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "message": "Webhook de teste funcionando",
                "received_data": data,
                "timestamp": datetime.now().isoformat()
            }
        )
    except Exception as e:
        logger.error(f"Erro no teste do webhook: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/webhook/filters")
async def get_filters():
    """Visualizar configurações de filtro atuais"""
    return {
        "status": "success",
        "filters": FILTER_CONFIG,
        "timestamp": datetime.now().isoformat()
    }

@app.post("/webhook/filters")
async def update_filters(new_config: Dict[str, Any]):
    """Atualizar configurações de filtro"""
    try:
        # Atualizar configurações (em produção, salvar em banco de dados)
        for key, value in new_config.items():
            if key in FILTER_CONFIG:
                FILTER_CONFIG[key] = value
                logger.info(f"Filtro atualizado: {key} = {value}")
        
        return {
            "status": "success",
            "message": "Filtros atualizados com sucesso",
            "updated_filters": FILTER_CONFIG,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Erro ao atualizar filtros: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Storage simples para últimos eventos (em produção, usar banco de dados)
recent_events = []
MAX_RECENT_EVENTS = 50

def store_recent_event(event_data: Dict[str, Any]):
    """Armazenar evento recente na memória"""
    recent_events.append({
        "timestamp": datetime.now().isoformat(),
        "data": event_data
    })
    # Manter apenas os últimos N eventos
    if len(recent_events) > MAX_RECENT_EVENTS:
        recent_events.pop(0)

@app.get("/webhook/recent")
async def get_recent_events():
    """Visualizar últimos eventos recebidos"""
    return {
        "status": "success",
        "total_events": len(recent_events),
        "events": recent_events[-10:],  # Últimos 10 eventos
        "timestamp": datetime.now().isoformat()
    }

@app.get("/webhook/stats")
async def get_webhook_stats():
    """Estatísticas dos eventos recebidos"""
    if not recent_events:
        return {
            "status": "success",
            "message": "Nenhum evento recebido ainda",
            "total_events": 0,
            "timestamp": datetime.now().isoformat()
        }
    
    # Contar tipos de eventos
    event_types = {}
    event_names = {}
    users = set()
    
    for event in recent_events:
        data = event["data"]
        event_type = data.get("type", "unknown")
        event_types[event_type] = event_types.get(event_type, 0) + 1
        
        if event_type == "track":
            event_name = data.get("event", "unknown")
            event_names[event_name] = event_names.get(event_name, 0) + 1
        
        user_id = data.get("userId")
        if user_id:
            users.add(user_id)
    
    return {
        "status": "success",
        "total_events": len(recent_events),
        "unique_users": len(users),
        "event_types": event_types,
        "track_events": event_names,
        "first_event": recent_events[0]["timestamp"] if recent_events else None,
        "last_event": recent_events[-1]["timestamp"] if recent_events else None,
        "timestamp": datetime.now().isoformat()
    }

@app.get("/dashboard", response_class=HTMLResponse)
async def session_dashboard():
    """Interface web para análise de sessões"""
    html_content = """
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Dashboard de Sessões - Zé Delivery</title>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #f5f7fa; color: #333; }
            .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; text-align: center; }
            .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
            .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin-bottom: 30px; }
            .stat-card { background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
            .stat-number { font-size: 2rem; font-weight: bold; color: #667eea; }
            .stat-label { color: #666; margin-top: 5px; }
            .chart-container { background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); margin-bottom: 20px; }
            .sessions-table { background: white; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); overflow: hidden; }
            .table-header { background: #667eea; color: white; padding: 15px; font-weight: bold; }
            .session-row { padding: 15px; border-bottom: 1px solid #eee; display: grid; grid-template-columns: 2fr 1fr 1fr 1fr 2fr; gap: 10px; align-items: center; }
            .session-row:hover { background: #f8f9ff; }
            .session-id { font-family: monospace; font-size: 0.9rem; color: #666; }
            .user-type { padding: 3px 8px; border-radius: 12px; font-size: 0.8rem; font-weight: bold; }
            .identified { background: #e8f5e8; color: #2d5a2d; }
            .anonymous { background: #fff3cd; color: #856404; }
            .device-info { font-size: 0.9rem; color: #666; }
            .events-list { font-size: 0.8rem; color: #888; }
            .refresh-btn { background: #667eea; color: white; border: none; padding: 10px 20px; border-radius: 5px; cursor: pointer; margin: 10px 0; }
            .refresh-btn:hover { background: #5a6fd8; }
            .loading { text-align: center; padding: 20px; color: #666; }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🚀 Dashboard de Sessões - Zé Delivery</h1>
            <p>Análise em tempo real dos dados do Segment</p>
        </div>

        <div class="container">
            <button class="refresh-btn" onclick="loadData()">🔄 Atualizar Dados</button>
            
            <div class="stats-grid" id="statsGrid">
                <div class="loading">Carregando estatísticas...</div>
            </div>

            <div class="chart-container">
                <h3>📊 Eventos por Tipo</h3>
                <canvas id="eventsChart" width="400" height="200"></canvas>
            </div>

            <div class="chart-container">
                <h3>📱 Dispositivos</h3>
                <canvas id="devicesChart" width="400" height="200"></canvas>
            </div>

            <div class="sessions-table">
                <div class="table-header">
                    📱 Sessões Ativas
                </div>
                <div id="sessionsTable">
                    <div class="loading">Carregando sessões...</div>
                </div>
            </div>
        </div>

        <script>
            let eventsChart, devicesChart;

            async function loadData() {
                try {
                    // Carregar estatísticas
                    const statsResponse = await fetch('/webhook/stats');
                    const stats = await statsResponse.json();
                    
                    // Carregar dados de sessões
                    const sessionsResponse = await fetch('/api/sessions');
                    const sessions = await sessionsResponse.json();

                    updateStats(stats);
                    updateCharts(stats);
                    updateSessionsTable(sessions);
                } catch (error) {
                    console.error('Erro ao carregar dados:', error);
                }
            }

            function updateStats(stats) {
                const statsGrid = document.getElementById('statsGrid');
                statsGrid.innerHTML = `
                    <div class="stat-card">
                        <div class="stat-number">${stats.total_events}</div>
                        <div class="stat-label">Total de Eventos</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number">${stats.unique_users}</div>
                        <div class="stat-label">Usuários Únicos</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number">${Object.keys(stats.track_events || {}).length}</div>
                        <div class="stat-label">Tipos de Eventos</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number">${stats.total_events > 0 ? Math.round(stats.total_events / stats.unique_users * 100) / 100 : 0}</div>
                        <div class="stat-label">Eventos por Usuário</div>
                    </div>
                `;
            }

            function updateCharts(stats) {
                // Gráfico de eventos
                const eventsCtx = document.getElementById('eventsChart').getContext('2d');
                if (eventsChart) eventsChart.destroy();
                
                const eventLabels = Object.keys(stats.track_events || {}).slice(0, 10);
                const eventData = Object.values(stats.track_events || {}).slice(0, 10);
                
                eventsChart = new Chart(eventsCtx, {
                    type: 'bar',
                    data: {
                        labels: eventLabels,
                        datasets: [{
                            label: 'Quantidade de Eventos',
                            data: eventData,
                            backgroundColor: 'rgba(102, 126, 234, 0.8)',
                            borderColor: 'rgba(102, 126, 234, 1)',
                            borderWidth: 1
                        }]
                    },
                    options: {
                        responsive: true,
                        scales: {
                            y: { beginAtZero: true }
                        }
                    }
                });
            }

            function updateSessionsTable(sessions) {
                const table = document.getElementById('sessionsTable');
                
                if (!sessions.sessions || sessions.sessions.length === 0) {
                    table.innerHTML = '<div class="loading">Nenhuma sessão encontrada</div>';
                    return;
                }

                let html = `
                    <div class="session-row" style="font-weight: bold; background: #f8f9ff;">
                        <div>Session ID</div>
                        <div>Usuário</div>
                        <div>Device</div>
                        <div>Eventos</div>
                        <div>Última Atividade</div>
                    </div>
                `;

                sessions.sessions.forEach(session => {
                    const userType = session.user_id ? 'identified' : 'anonymous';
                    const userLabel = session.user_id ? 'Identificado' : 'Anônimo';
                    const userId = session.user_id || session.anonymous_id || 'N/A';
                    
                    html += `
                        <div class="session-row">
                            <div class="session-id">${session.session_id.substring(0, 20)}...</div>
                            <div>
                                <span class="user-type ${userType}">${userLabel}</span><br>
                                <small>${userId.substring(0, 15)}...</small>
                            </div>
                            <div class="device-info">
                                ${session.device_model || 'Unknown'}<br>
                                <small>iOS ${session.os_version || 'N/A'}</small>
                            </div>
                            <div>
                                <strong>${session.events.length}</strong><br>
                                <div class="events-list">
                                    ${session.events.slice(0, 2).map(e => e.event).join(', ')}
                                    ${session.events.length > 2 ? '...' : ''}
                                </div>
                            </div>
                            <div>
                                ${session.events.length > 0 ? new Date(session.events[session.events.length - 1].timestamp).toLocaleString('pt-BR') : 'N/A'}
                            </div>
                        </div>
                    `;
                });

                table.innerHTML = html;
            }

            // Carregar dados iniciais
            loadData();

            // Atualizar a cada 30 segundos
            setInterval(loadData, 30000);
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.get("/api/sessions")
async def get_sessions_analysis():
    """API para análise detalhada de sessões"""
    try:
        sessions = defaultdict(list)
        
        # Agrupar eventos por session_id
        for event in recent_events:
            event_data = event["data"]
            
            session_id = None
            if 'properties' in event_data and 'session_id' in event_data['properties']:
                session_id = event_data['properties']['session_id']
            elif 'context' in event_data and 'traits' in event_data['context'] and 'session_id' in event_data['context']['traits']:
                session_id = event_data['context']['traits']['session_id']
            
            if session_id:
                context = event_data.get('context', {})
                app_info = context.get('app', {})
                device_info = context.get('device', {})
                
                sessions[session_id].append({
                    'session_id': session_id,
                    'event': event_data.get('event', 'unknown'),
                    'timestamp': event_data.get('timestamp', ''),
                    'user_id': event_data.get('userId'),
                    'anonymous_id': event_data.get('anonymousId'),
                    'app_version': app_info.get('version'),
                    'device_model': device_info.get('model'),
                    'os_version': context.get('os', {}).get('version'),
                    'timezone': context.get('timezone'),
                    'network': context.get('network', {}),
                    'screen': event_data.get('properties', {}).get('screen_name')
                })
        
        # Processar sessões
        processed_sessions = []
        for session_id, events in sessions.items():
            # Ordenar eventos por timestamp
            events.sort(key=lambda x: x['timestamp'] or '')
            
            first_event = events[0]
            processed_sessions.append({
                'session_id': session_id,
                'user_id': first_event['user_id'],
                'anonymous_id': first_event['anonymous_id'],
                'device_model': first_event['device_model'],
                'os_version': first_event['os_version'],
                'timezone': first_event['timezone'],
                'network': first_event['network'],
                'events': [{'event': e['event'], 'timestamp': e['timestamp'], 'screen': e['screen']} for e in events],
                'total_events': len(events),
                'duration': calculate_session_duration(events),
                'first_event_time': events[0]['timestamp'],
                'last_event_time': events[-1]['timestamp']
            })
        
        # Ordenar por última atividade
        processed_sessions.sort(key=lambda x: x['last_event_time'] or '', reverse=True)
        
        return {
            "status": "success",
            "total_sessions": len(processed_sessions),
            "sessions": processed_sessions[:20],  # Últimas 20 sessões
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Erro ao analisar sessões: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

def calculate_session_duration(events):
    """Calcular duração da sessão em minutos"""
    if len(events) < 2:
        return 0
    
    try:
        first_time = datetime.fromisoformat(events[0]['timestamp'].replace('Z', '+00:00'))
        last_time = datetime.fromisoformat(events[-1]['timestamp'].replace('Z', '+00:00'))
        duration = (last_time - first_time).total_seconds() / 60
        return round(duration, 1)
    except:
        return 0

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)