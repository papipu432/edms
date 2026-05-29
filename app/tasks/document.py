"""Celery task for document processing pipeline."""

import asyncio

from celery.utils.log import get_task_logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.tasks import celery_app

logger = get_task_logger(__name__)


@celery_app.task(name="app.tasks.document.process_document_task")
def process_document_task(doc_id: int, db_url: str) -> None:
    """Process a document through the pipeline.

    Creates its own async engine and session since Celery workers are synchronous.
    """
    asyncio.run(_process_document(doc_id, db_url))


async def _process_document(doc_id: int, db_url: str) -> None:
    """Async implementation of document processing."""
    from app.services.pipeline import PipelineService
    from app.services.storage import StorageService

    engine = create_async_engine(db_url, echo=False)
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    try:
        async with session_factory() as session:
            storage_service = StorageService()
            svc = PipelineService(storage_service=storage_service)
            await svc.process_document(doc_id, session)
    finally:
        await engine.dispose()

    logger.info("Document %d processed successfully via Celery", doc_id)
