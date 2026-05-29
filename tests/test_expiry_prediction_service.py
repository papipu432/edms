"""Tests for the expiry prediction endpoint."""

from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.main import app
from app.models.document import Document, DocumentStatus
from app.models.group import Group
from app.models.lifecycle import DocumentLifecycle, LifecycleType
from app.models.user import User


@pytest_asyncio.fixture
async def prediction_client(db_session: AsyncSession) -> AsyncClient:
    """Create a test client with auth override for expiry prediction tests."""
    from collections.abc import AsyncGenerator

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        try:
            yield db_session
            await db_session.commit()
        except Exception:
            await db_session.rollback()
            raise

    async def override_current_user() -> User:
        return User(id="test-user-id", username="testuser", email="test@example.com", hashed_password="x")

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_current_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


class TestExpiryPrediction:
    """Test the expiry prediction endpoint."""

    @pytest.mark.asyncio
    async def test_predict_expiry_calculates_average(
        self, db_session: AsyncSession, prediction_client: AsyncClient
    ):
        """Test that prediction calculates average review_interval_days from siblings."""
        # Create a group
        group = Group(name="Prediction Test Group")
        db_session.add(group)
        await db_session.flush()

        base_time = datetime(2024, 1, 1, 12, 0, 0)

        # Create multiple documents with lifecycles in the same group
        docs = []
        for i in range(3):
            doc = Document(
                group_id=group.id,
                original_filename=f"doc{i}.pdf",
                storage_path=f"/tmp/doc{i}.pdf",
                file_type="application/pdf",
                file_size=1000,
                status=DocumentStatus.processed,
            )
            db_session.add(doc)
            docs.append(doc)
        await db_session.flush()

        # Create lifecycles with known review intervals
        # doc0: 30 days, doc1: 60 days, doc2: 90 days -> average = 60
        intervals = [30, 60, 90]
        for i, doc in enumerate(docs):
            lifecycle = DocumentLifecycle(
                document_id=doc.id,
                lifecycle_type=LifecycleType.recurring,
                review_interval_days=intervals[i],
                last_reviewed_at=base_time,
                created_at=base_time,
            )
            db_session.add(lifecycle)
        await db_session.flush()

        # Request prediction for the first document
        response = await prediction_client.get(
            f"/api/documents/{docs[0].id}/expiry-prediction"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["document_id"] == docs[0].id
        assert data["based_on_count"] == 3
        assert data["confidence"] == 0.3  # 3/10

        # Check predicted_review_date: base_time + avg(30, 60, 90) = base_time + 60 days
        predicted = datetime.fromisoformat(data["predicted_review_date"])
        expected = base_time + timedelta(days=60)
        assert predicted == expected

    @pytest.mark.asyncio
    async def test_predict_expiry_no_lifecycle(
        self, db_session: AsyncSession, prediction_client: AsyncClient
    ):
        """Test that document without lifecycle returns 404."""
        group = Group(name="No Lifecycle Group")
        db_session.add(group)
        await db_session.flush()

        doc = Document(
            group_id=group.id,
            original_filename="nolc.pdf",
            storage_path="/tmp/nolc.pdf",
            file_type="application/pdf",
            file_size=500,
            status=DocumentStatus.processed,
        )
        db_session.add(doc)
        await db_session.flush()

        response = await prediction_client.get(
            f"/api/documents/{doc.id}/expiry-prediction"
        )
        assert response.status_code == 404
        assert "No lifecycle found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_predict_expiry_document_not_found(
        self, prediction_client: AsyncClient
    ):
        """Test that non-existent document returns 404."""
        response = await prediction_client.get(
            "/api/documents/99999/expiry-prediction"
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_predict_expiry_no_review_intervals(
        self, db_session: AsyncSession, prediction_client: AsyncClient
    ):
        """Test that zero review intervals returns confidence 0 with fallback date."""
        group = Group(name="No Intervals Group")
        db_session.add(group)
        await db_session.flush()

        doc = Document(
            group_id=group.id,
            original_filename="nointerval.pdf",
            storage_path="/tmp/nointerval.pdf",
            file_type="application/pdf",
            file_size=500,
            status=DocumentStatus.processed,
        )
        db_session.add(doc)
        await db_session.flush()

        # Lifecycle without review_interval_days
        expires_at = datetime(2025, 6, 1, 0, 0, 0)
        lifecycle = DocumentLifecycle(
            document_id=doc.id,
            lifecycle_type=LifecycleType.expiring,
            review_interval_days=None,
            expires_at=expires_at,
            created_at=datetime(2024, 1, 1),
        )
        db_session.add(lifecycle)
        await db_session.flush()

        response = await prediction_client.get(
            f"/api/documents/{doc.id}/expiry-prediction"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["confidence"] == 0.0
        assert data["based_on_count"] == 0
        # Should fall back to expires_at
        predicted = datetime.fromisoformat(data["predicted_review_date"])
        assert predicted == expires_at

    @pytest.mark.asyncio
    async def test_predict_expiry_confidence_caps_at_one(
        self, db_session: AsyncSession, prediction_client: AsyncClient
    ):
        """Test that confidence caps at 1.0 with 10+ samples."""
        group = Group(name="High Confidence Group")
        db_session.add(group)
        await db_session.flush()

        base_time = datetime(2024, 1, 1, 12, 0, 0)

        # Create 12 documents with lifecycles
        target_doc = None
        for i in range(12):
            doc = Document(
                group_id=group.id,
                original_filename=f"doc{i}.pdf",
                storage_path=f"/tmp/doc{i}.pdf",
                file_type="application/pdf",
                file_size=1000,
                status=DocumentStatus.processed,
            )
            db_session.add(doc)
            await db_session.flush()

            lifecycle = DocumentLifecycle(
                document_id=doc.id,
                lifecycle_type=LifecycleType.recurring,
                review_interval_days=30,
                last_reviewed_at=base_time,
                created_at=base_time,
            )
            db_session.add(lifecycle)
            if i == 0:
                target_doc = doc
        await db_session.flush()

        response = await prediction_client.get(
            f"/api/documents/{target_doc.id}/expiry-prediction"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["confidence"] == 1.0
        assert data["based_on_count"] == 12
