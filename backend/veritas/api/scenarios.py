"""Scenario generation and paginated transaction reads."""

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from veritas.api.errors import ApiError
from veritas.api.settings import Settings
from veritas.simulator.scales import BenchmarkConfirmationRequired, ScaleError
from veritas.simulator.store import DemoDataRetained, ReseedRequired, seed_database
from veritas.storage.db import apply_migrations, connect
from veritas.storage.queries import list_scenarios, public_transactions

router = APIRouter(prefix="/api/v1")

_LIMIT = Query(50, ge=1, le=100)
_OFFSET = Query(0, ge=0, le=100_000)


class GenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seed: int = Field(default=42, ge=0, le=2_147_483_647)
    scale: str = "default"
    replace: bool = False
    confirm_benchmark: bool = False


class GenerateResponse(BaseModel):
    seed: int
    scale: str
    accounts: int
    transactions: int
    scenarios: list[str]
    replaced: bool
    content_sha256: str


class TransactionItem(BaseModel):
    transaction_id: str
    from_account_id: str
    to_account_id: str
    amount_minor: int
    event_time: str
    currency: str


class TransactionPage(BaseModel):
    items: list[TransactionItem]
    limit: int
    offset: int
    total: int


class ScenarioList(BaseModel):
    scenarios: list[dict[str, object]]


@router.post("/scenarios/generate", response_model=GenerateResponse)
def generate_scenario(body: GenerateRequest, request: Request) -> GenerateResponse:
    settings: Settings = request.app.state.settings
    try:
        result = seed_database(
            settings.db_path,
            seed=body.seed,
            scale=body.scale,
            replace=body.replace,
            confirm_benchmark=body.confirm_benchmark,
        )
    except BenchmarkConfirmationRequired as exc:
        raise ApiError("CONFIRM_BENCHMARK_REQUIRED", str(exc), 400) from exc
    except ScaleError as exc:
        raise ApiError("INVALID_SCALE", str(exc), 400) from exc
    except ReseedRequired as exc:
        raise ApiError("RESEED_REQUIRED", str(exc), 409) from exc
    except DemoDataRetained as exc:
        raise ApiError("DEMO_DATA_RETAINED", str(exc), 409) from exc
    return GenerateResponse(
        seed=int(result["seed"]),
        scale=str(result["scale"]),
        accounts=int(result["accounts"]),
        transactions=int(result["transactions"]),
        scenarios=list(result["scenarios"]),
        replaced=bool(result["replaced"]),
        content_sha256=str(result["content_sha256"]),
    )


@router.get("/scenarios", response_model=ScenarioList)
def get_scenarios(request: Request) -> ScenarioList:
    settings: Settings = request.app.state.settings
    with connect(settings.db_path) as connection:
        apply_migrations(connection)
        scenarios = list_scenarios(connection)
    return ScenarioList(scenarios=scenarios)


@router.get("/transactions", response_model=TransactionPage)
def get_transactions(
    request: Request,
    limit: int = _LIMIT,
    offset: int = _OFFSET,
) -> TransactionPage:
    settings: Settings = request.app.state.settings
    with connect(settings.db_path) as connection:
        apply_migrations(connection)
        items, total = public_transactions(connection, limit=limit, offset=offset)
    return TransactionPage(
        items=[TransactionItem.model_validate(item) for item in items],
        limit=limit,
        offset=offset,
        total=total,
    )
