from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import json
import os
from datetime import datetime
import logging
from typing import Dict, Any

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Webhook Segment",
    description="Webhook para receber eventos do Segment",
    version="1.0.0"
)

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
    """Endpoint de health check"""
    return {
        "message": "Webhook Segment está funcionando!",
        "timestamp": datetime.now().isoformat(),
        "status": "healthy"
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

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)