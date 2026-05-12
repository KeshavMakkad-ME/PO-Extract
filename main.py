import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from api.admin_router import router as admin_router
from api.rm_pm.router import router as rm_pm_router
from api.po.router import router as po_router
from api.services.router import router as services_router
from core.llm_client import get_openai_client
from utils.rm_pm.gsheet import load_rm_pm_options
from utils.po.gsheet import load_dispatch_options, load_flipkart_sku_mapping, load_state_codes

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing — loading config, state codes, dispatch options, and OpenAI client...")
    app.state.model                 = get_openai_client()
    app.state.state_codes           = load_state_codes()
    app.state.dispatch_options      = load_dispatch_options()
    app.state.rm_pm_options         = load_rm_pm_options()
    app.state.flipkart_sku_mapping  = load_flipkart_sku_mapping()
    logger.info("Ready to serve requests")
    yield


app = FastAPI(title="PO to E-Invoice Converter", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501", "http://127.0.0.1:8501"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(po_router)
app.include_router(rm_pm_router)
app.include_router(services_router)
app.include_router(admin_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
