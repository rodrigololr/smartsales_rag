"""Public JSON routes for products, feedback and checkout."""

import logging
import secrets
import uuid
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import AwareDatetime, BaseModel
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.commerce import (
    Catalog,
    CatalogNotReady,
    CatalogQuery,
    Checkout,
    CheckoutConflict,
    CheckoutCreate,
    FeedbackAlreadyRecorded,
    FeedbackCreate,
    FeedbackRecorded,
    MessageNotFound,
    Product,
    ProductNotFound,
    SessionEnded,
)
from app.metrics import InvalidMetricsWindow, Metrics, resolve_window
from app.repositories.commerce import PostgresCommerce
from app.routes.chat import error_response
from app.telemetry.http_errors import error_5xx_rate

logger = logging.getLogger(__name__)
CATALOG_VERSION_KEY = "catalog:version"


class ErrorDetail(BaseModel):
    code: str
    message: str
    trace_id: str
    details: object


class ErrorEnvelope(BaseModel):
    error: ErrorDetail


class DatabaseNotConfigured(Exception):
    """Legacy chat-only startup without DATABASE_URL."""


class AdminUnauthorized(Exception):
    """Missing or wrong X-Admin-Token, or ADMIN_TOKEN not configured."""


class CommerceRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handle = super().get_route_handler()

        async def protected(request: Request) -> Response:
            try:
                return await handle(request)
            except RequestValidationError as invalid:
                # No "input": the envelope must not echo what the client sent.
                errors = [
                    {key: value for key, value in error.items() if key != "input"}
                    for error in jsonable_encoder(invalid.errors())
                ]
                envelope = {
                    "code": "VALIDATION_ERROR",
                    "message": "Verifique os parâmetros enviados.",
                    "trace_id": str(uuid.uuid4()),
                    "details": {"errors": errors},
                }
                return JSONResponse({"error": envelope}, status_code=422)
            except AdminUnauthorized:
                return error_response(401, "UNAUTHORIZED", "Token administrativo inválido.")
            except InvalidMetricsWindow:
                return error_response(
                    422, "VALIDATION_ERROR", "O início da janela deve ser anterior ao fim."
                )
            except ProductNotFound:
                return error_response(404, "PRODUCT_NOT_FOUND", "Produto não encontrado.")
            except MessageNotFound:
                return error_response(
                    404, "MESSAGE_NOT_FOUND", "Mensagem não encontrada na sessão."
                )
            except FeedbackAlreadyRecorded:
                return error_response(
                    409, "FEEDBACK_ALREADY_RECORDED", "A mensagem já foi avaliada."
                )
            except SessionEnded:
                return error_response(410, "SESSION_ENDED", "A sessão foi encerrada.")
            except CatalogNotReady:
                return error_response(503, "SERVICE_UNAVAILABLE", "Catálogo ainda não carregado.")
            except DatabaseNotConfigured:
                return error_response(503, "DATABASE_UNAVAILABLE", "Banco de dados indisponível.")
            # Other psycopg errors reach the app-wide DatabaseError handler (503).

        return protected


router = APIRouter(
    prefix="/api/v1",
    route_class=CommerceRoute,
    responses={code: {"model": ErrorEnvelope} for code in (404, 410, 422, 500, 503)},
)


def get_repository(request: Request) -> PostgresCommerce:
    repository: PostgresCommerce | None = request.app.state.commerce
    if repository is None:
        raise DatabaseNotConfigured
    return repository


Repository = Annotated[PostgresCommerce, Depends(get_repository)]


def require_admin(
    request: Request, token: Annotated[str | None, Header(alias="X-Admin-Token")] = None
) -> None:
    expected = request.app.state.settings.admin_token
    # No ADMIN_TOKEN configured: closed, never open.
    if expected is None or token is None:
        raise AdminUnauthorized
    if not secrets.compare_digest(token.encode(), expected.get_secret_value().encode()):
        raise AdminUnauthorized


@router.get("/products", operation_id="listProducts")
async def list_products(query: Annotated[CatalogQuery, Query()], repository: Repository) -> Catalog:
    return await repository.list_products(query)


@router.get("/products/{sku}", operation_id="getProduct")
async def get_product(sku: str, repository: Repository) -> Product:
    return await repository.get_product(sku)


@router.post(
    "/feedback",
    status_code=201,
    operation_id="createFeedback",
    responses={409: {"model": ErrorEnvelope}},
)
async def record_feedback(body: FeedbackCreate, repository: Repository) -> FeedbackRecorded:
    return await repository.record_feedback(body)


@router.post(
    "/checkout/mock",
    response_model=Checkout,
    operation_id="checkoutMock",
    responses={409: {"model": CheckoutConflict}},
)
async def mock_checkout(
    body: CheckoutCreate, repository: Repository, request: Request
) -> Checkout | Response:
    result = await repository.checkout(body)
    cache: Redis | None = request.app.state.redis
    if cache is not None and (
        result.status == "PRICE_CHANGED"
        or (isinstance(result, Checkout) and result.remaining_stock == 0)
    ):
        try:
            await cache.incr(CATALOG_VERSION_KEY)
        except RedisError:
            # The checkout transaction already committed. Report the cache failure separately.
            logger.exception("checkout_catalog_version_failed", extra={"sku": body.sku})
    if isinstance(result, CheckoutConflict):
        return JSONResponse(result.model_dump(mode="json"), status_code=409)
    return result


@router.get(
    "/metrics/summary",
    operation_id="metricsSummary",
    dependencies=[Depends(require_admin)],  # runs before the query and the database
    responses={401: {"model": ErrorEnvelope}},
)
async def metrics_summary(
    repository: Repository,
    request: Request,
    window_from: Annotated[AwareDatetime | None, Query(alias="from")] = None,
    window_to: Annotated[AwareDatetime | None, Query(alias="to")] = None,
) -> Metrics:
    now = datetime.now(UTC)
    window = resolve_window(window_from, window_to, now)
    rate = await error_5xx_rate(request.app.state.redis, window.window_from, window.window_to, now)
    return await repository.metrics_summary(window, rate)
