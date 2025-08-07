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

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)